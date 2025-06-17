package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"
)

// GeneratePodcastSpeech takes the full podcast script, processes each line in order,
// calls OpenAI's TTS API for each line, saves the resulting MP3 segments to temporary files,
// then loads those segments with the 'beep' library, concatenates them in order,
// and outputs one final audio file (in WAV format) that contains the entire podcast.
func GeneratePodcastSpeech(script string) ([][]byte, error) {
	script = sanitizeScript(script)

	const ttsEndpoint = "https://api.openai.com/v1/audio/speech"

	callTTS := func(voice, text string) ([]byte, error) {
		payload := map[string]interface{}{
			"model": "gpt-4o-mini-tts",
			"input": text,
			"voice": voice,
		}
		jsonBody, err := json.Marshal(payload)
		if err != nil {
			return nil, err
		}

		req, err := http.NewRequest("POST", ttsEndpoint, bytes.NewBuffer(jsonBody))
		if err != nil {
			return nil, err
		}
		req.Header.Set("Content-Type", "application/json")

		openaiApiKey := os.Getenv("OPENAI_API_KEY")
		if openaiApiKey == "" {
			return nil, fmt.Errorf("OPENAI_API_KEY environment variable not set")
		}
		req.Header.Set("Authorization", "Bearer "+openaiApiKey)

		client := &http.Client{Timeout: 30 * time.Second}
		resp, err := client.Do(req)
		if err != nil {
			return nil, err
		}
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			body, _ := io.ReadAll(resp.Body)
			return nil, fmt.Errorf("TTS API error (%d): %s", resp.StatusCode, string(body))
		}

		return io.ReadAll(resp.Body)
	}

	lines := strings.Split(script, "\n")
	var segments [][]byte

	for i, line := range lines {
		trimmed := strings.TrimSpace(line)
		if trimmed == "" {
			continue
		}

		cleaned := strings.Trim(trimmed, "*")
		lower := strings.ToLower(cleaned)

		var voice, content string
		if strings.HasPrefix(lower, "host:") {
			voice = "alloy"
			content = strings.TrimSpace(strings.SplitN(cleaned, ":", 2)[1])
		} else if strings.HasPrefix(lower, "guest:") {
			voice = "echo"
			content = strings.TrimSpace(strings.SplitN(cleaned, ":", 2)[1])
		} else {
			continue
		}

		fmt.Printf("Generating TTS for line %d [%s]: %s\n", i, voice, content)
		audioData, err := callTTS(voice, content)
		if err != nil {
			fmt.Printf("Error generating TTS for line %d: %v\n", i, err)
			continue
		}

		segments = append(segments, audioData)
	}

	if len(segments) == 0 {
		return nil, fmt.Errorf("no audio segments were generated")
	}

	return segments, nil
}
