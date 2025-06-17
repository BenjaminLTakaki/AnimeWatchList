package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"
)

const openaiEmbeddingURL = "https://api.openai.com/v1/embeddings"
const openaiEmbeddingModel = "text-embedding-3-small"

var LookupSystemPrompt = `You are a semantic tag generator.
Given several numbered chunks of text, output a corresponding list of tag groups.
Each tag group should contain only the 1–2 most relevant and distinct tags summarizing the core topics of the chunk.
Use only lowercase where possible. Separate each tag with '|'. Return one line per chunk, tags only.`

// GetEmbeddingFromOpenAI fetches the embedding for a given string using OpenAI API.
func GetEmbeddingFromOpenAI(text string) ([]float32, error) {
	apiKey := os.Getenv("OPENAI_API_KEY")
	if apiKey == "" {
		return nil, fmt.Errorf("OPENAI_API_KEY not set")
	}

	payload := map[string]interface{}{
		"input": text,
		"model": openaiEmbeddingModel,
	}

	jsonData, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}

	req, err := http.NewRequest("POST", openaiEmbeddingURL, bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+apiKey)
	req.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		bodyBytes, _ := io.ReadAll(resp.Body)
		return nil, errors.New(string(bodyBytes))
	}

	var response struct {
		Data []struct {
			Embedding []float32 `json:"embedding"`
		} `json:"data"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&response); err != nil {
		return nil, err
	}

	if len(response.Data) == 0 {
		return nil, errors.New("no embedding returned")
	}

	return response.Data[0].Embedding, nil
}

// Lookup performs a similarity search in Qdrant with a given query string.
func Lookup(query string, collection string, filters map[string]interface{}) (string, error) {
	qdrantHost := getQdrantHost()
	qdrantSearchURL := fmt.Sprintf("%s/collections/%s/points/search", qdrantHost, collection)
	embedding, err := GetEmbeddingFromOpenAI(query)
	if err != nil {
		return "", fmt.Errorf("embedding error: %v", err)
	}

	payload := map[string]interface{}{
		"vector":       embedding,
		"limit":        20,
		"with_payload": true,
	}

	if filters != nil {
		payload["filter"] = filters
	}

	jsonPayload, _ := json.Marshal(payload)

	req, err := http.NewRequest("POST", qdrantSearchURL, bytes.NewBuffer(jsonPayload))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	fmt.Printf("Qdrant responsed")
	return string(body), nil
}

// GenerateLookupTags takes a slice of chunk texts and returns a slice of tag lists.
func GenerateLookupTags(chunkTexts []string) ([][]string, error) {
	if len(chunkTexts) == 0 {
		return [][]string{}, nil
	}

	const tokenLimit = 1800              // Max tokens per request to avoid 6k TPM issue
	const tokensPerMinuteLimit = 6000    // Free tier Groq limit
	var totalTokensUsed = 0              // For throttling
	var lastFlush time.Time = time.Now() // For rate limiting

	var allTags [][]string
	var inputBuilder strings.Builder
	var currentBatch []string
	estimateTokens := func(text string) int {
		return len(text) / 4 // Rough estimation
	}

	flushBatch := func() error {
		if len(currentBatch) == 0 {
			return nil
		}

		userMessage := inputBuilder.String()
		inputBuilder.Reset()

		totalTokensUsed += estimateTokens(userMessage)
		if totalTokensUsed > tokensPerMinuteLimit {
			sinceLast := time.Since(lastFlush)
			if sinceLast < time.Minute {
				time.Sleep(time.Minute - sinceLast)
			}
			totalTokensUsed = estimateTokens(userMessage)
			lastFlush = time.Now()
		}

		payload := map[string]interface{}{
			"model": groqModel,
			"messages": []map[string]string{
				{"role": "system", "content": tagSystemPrompt},
				{"role": "user", "content": userMessage},
			},
			"temperature": 0.3,
			"max_tokens":  2048,
		}

		jsonData, err := json.Marshal(payload)
		if err != nil {
			return err
		}

		req, err := http.NewRequest("POST", groqAPIURL, bytes.NewBuffer(jsonData))
		if err != nil {
			return err
		}
		req.Header.Set("Authorization", "Bearer "+os.Getenv("GROQ_API_KEY"))
		req.Header.Set("Content-Type", "application/json")

		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			return err
		}
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			bodyBytes, _ := io.ReadAll(resp.Body)
			return errors.New(string(bodyBytes))
		}

		var response struct {
			Choices []struct {
				Message struct {
					Content string `json:"content"`
				} `json:"message"`
			} `json:"choices"`
		}
		err = json.NewDecoder(resp.Body).Decode(&response)
		if err != nil {
			return err
		}

		rawOutput := strings.TrimSpace(response.Choices[0].Message.Content)
		batchTags := ParseLookupTags(rawOutput)
		allTags = append(allTags, batchTags...)
		currentBatch = nil
		return nil
	}

	var tokenCount int
	for i, text := range chunkTexts {
		estTokens := estimateTokens(text)
		if tokenCount+estTokens > tokenLimit {
			if err := flushBatch(); err != nil {
				return nil, err
			}
			tokenCount = 0
		}

		line := fmt.Sprintf("%d. %s\n", i+1, text)
		inputBuilder.WriteString(line)
		tokenCount += estTokens
		currentBatch = append(currentBatch, text)
	}

	if err := flushBatch(); err != nil {
		return nil, err
	}

	return allTags, nil
}

// ParseLookupTags processes the entire raw output string in one pass using runes.
func ParseLookupTags(input string) [][]string {
	lines := strings.Split(strings.TrimSpace(input), "\n")
	var result [][]string

	for _, line := range lines {
		line = strings.TrimSpace(prefixRegex.ReplaceAllString(line, ""))
		if line == "" {
			continue
		}
		parts := strings.Split(line, "|")
		var tags []string
		for i, part := range parts {
			if i >= 2 {
				break
			}
			tag := strings.TrimSpace(part)
			if tag != "" {
				tags = append(tags, tag)
			}
		}
		result = append(result, tags)
	}

	return result
}

func BuildFilter(subject string, from, to *string) map[string]interface{} {
	must := []map[string]interface{}{}

	if subject != "" {
		must = append(must, map[string]interface{}{
			"key": "subject",
			"match": map[string]string{
				"value": subject,
			},
		})
	}

	if from != nil || to != nil {
		rangeFilter := map[string]string{}
		if from != nil {
			rangeFilter["gte"] = *from
		}
		if to != nil {
			rangeFilter["lte"] = *to
		}
		must = append(must, map[string]interface{}{
			"key":   "timestamp",
			"range": rangeFilter,
		})
	}

	if len(must) == 0 {
		return nil
	}

	return map[string]interface{}{
		"must": must,
	}
}
