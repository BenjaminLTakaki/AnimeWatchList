package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"regexp"
	"strings"
	"time"
)

const groqAPIURL = "https://api.groq.com/openai/v1/chat/completions"
const groqModel = "llama-3.1-8b-instant"

var tagSystemPrompt = `You are a semantic tag generator.
Given several numbered chunks of text, output a corresponding list of tag groups.
Each tag group summarizes the key topics, concepts, or categories from its associated chunk.
Use only lowercase where possible. Each tag group should be a single line of up to 20 tags separated by '|'.
Output only the tag lines, one per chunk, in the same order.`

var prefixRegex = regexp.MustCompile(`^\d+\.\s*`)

// BatchGenerateTags takes a slice of chunk texts and returns a slice of tag lists.
func BatchGenerateTags(chunkTexts []string) ([][]string, error) {
	if len(chunkTexts) == 0 {
		return [][]string{}, nil
	}

	const tokenLimit = 1800              // Max tokens per request to avoid 6k TPM issue
	const tokensPerMinuteLimit = 5500    // Free tier Groq limit (-500 tokens for good measure)
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
				lastFlush = time.Now()
			}
			totalTokensUsed = estimateTokens(userMessage) // reset to current batch
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
		batchTags := ParseBatchTags(rawOutput)
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

// ParseBatchTags processes the entire raw output string in one pass using runes.
func ParseBatchTags(input string) [][]string {
	lines := strings.Split(strings.TrimSpace(input), "\n")
	var result [][]string

	for _, line := range lines {
		line = strings.TrimSpace(prefixRegex.ReplaceAllString(line, ""))
		if line == "" {
			continue
		}
		parts := strings.Split(line, "|")
		var tags []string
		for _, part := range parts {
			tag := strings.TrimSpace(part)
			if tag != "" {
				tags = append(tags, tag)
			}
		}
		result = append(result, tags)
	}

	return result
}
