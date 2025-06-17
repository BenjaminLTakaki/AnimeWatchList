package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"net/http"
	"os"
	"regexp"
	"strconv"
	"strings"
	"time"
)

// maxContextLen caps how many characters of context we include.
const maxContextLen = 2000

// Script fetches vector context, truncates it, then calls Groq to build a podcast script.
func Script(topic, collectionID string) (string, error) {
	// 1) fetch context
	log.Printf("[Script] Fetching context for topic %q in collection %q", topic, collectionID)
	context, err := fetchContext(topic, collectionID)
	if err != nil {
		return "", fmt.Errorf("fetchContext: %w", err)
	}

	// 2) truncate context if too long
	if len(context) > maxContextLen {
		log.Printf("[Script] Context length %d > %d, truncating", len(context), maxContextLen)
		context = context[:maxContextLen] + " …"
	}

	// 3) build payload
	systemParts := []string{
		"You are a creative podcast script writer.",
		"Use the provided context to craft a dialogue between Host and Guest.",
		"Each line must start with 'Host:' or 'Guest:'.",
	}
	if context != "" {
		systemParts = append(systemParts, "Context: "+context)
	}
	userPrompt := fmt.Sprintf("Create a podcast script about '%s' using the context above.", topic)

	payload := map[string]interface{}{
		"model": "llama-3.1-8b-instant",
		"messages": []map[string]string{
			{"role": "system", "content": strings.Join(systemParts, " ")},
			{"role": "user", "content": userPrompt},
		},
		"temperature": 0.7,
	}

	// 4) marshal & log payload size
	payloadBytes, err := json.Marshal(payload)
	if err != nil {
		return "", fmt.Errorf("json.Marshal: %w", err)
	}
	log.Printf("[Script] Final payload size: %d bytes", len(payloadBytes))

	// 5) send to Groq with retry on 429
	req, _ := http.NewRequest("POST", "https://api.groq.com/openai/v1/chat/completions", bytes.NewBuffer(payloadBytes))
	req.Header.Set("Content-Type", "application/json")
	key := os.Getenv("GROQ_API_KEY")
	if key == "" {
		return "", fmt.Errorf("GROQ_API_KEY not set")
	}
	req.Header.Set("Authorization", "Bearer "+key)

	client := &http.Client{Timeout: 30 * time.Second}
	var res *http.Response
	for attempt := 1; attempt <= 2; attempt++ {
		log.Printf("[Script] Sending request to Groq (attempt %d)", attempt)
		res, err = client.Do(req)
		if err != nil {
			return "", fmt.Errorf("groq request: %w", err)
		}
		if res.StatusCode != http.StatusTooManyRequests {
			break
		}
		ra := res.Header.Get("Retry-After")
		wait := 5
		if sec, e := strconv.Atoi(ra); e == nil {
			wait = sec
		}
		res.Body.Close()
		log.Printf("[Script] Rate limited (429), retrying after %ds", wait)
		time.Sleep(time.Duration(wait) * time.Second)
	}
	defer res.Body.Close()

	body, _ := ioutil.ReadAll(res.Body)
	if res.StatusCode != http.StatusOK {
		return "", fmt.Errorf("Groq API returned %d: %s", res.StatusCode, string(body))
	}

	// 6) parse response
	var groqRes struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
	}
	if err := json.Unmarshal(body, &groqRes); err != nil {
		return "", fmt.Errorf("json.Unmarshal: %w", err)
	}
	if len(groqRes.Choices) == 0 {
		return "", fmt.Errorf("no choices in response: %s", string(body))
	}

	// 7) sanitize and return
	script := sanitizeScript(groqRes.Choices[0].Message.Content)
	return script, nil
}

// sanitizeScript strips markdown bold and HTML tags from Host:/Guest: lines.
func sanitizeScript(s string) string {
	// remove **Host:** / **Guest:**
	re := regexp.MustCompile(`(?i)\*\*(host|guest):\*\*`)
	s = re.ReplaceAllStringFunc(s, func(m string) string {
		return strings.Trim(m, "*")
	})
	// remove any HTML tags
	reHTML := regexp.MustCompile(`<[^>]+>`)
	return reHTML.ReplaceAllString(s, "")
}

// fetchContext calls the Chisel /lookup endpoint and returns the raw text.
func fetchContext(topic, collectionID string) (string, error) {
	chiselEndpoint := getChiselEndpoint()
	lookupURL := chiselEndpoint + "/lookup"

	reqBody := map[string]string{"query": topic, "collection": collectionID}
	b, _ := json.Marshal(reqBody)
	req, _ := http.NewRequest("POST", lookupURL, bytes.NewBuffer(b))
	req.Header.Set("Content-Type", "application/json")

	res, err := http.DefaultClient.Do(req)
	if err != nil {
		return "", fmt.Errorf("lookup request: %w", err)
	}
	defer res.Body.Close()

	data, _ := ioutil.ReadAll(res.Body)
	if res.StatusCode != http.StatusOK {
		return "", fmt.Errorf("lookup returned %d: %s", res.StatusCode, string(data))
	}
	return string(data), nil
}
