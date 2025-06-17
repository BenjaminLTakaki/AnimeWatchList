package main

import (
	"log"
	"strings"
	"time"
)

func SentenceChunk(text, origin string) []Chunk {
	var chunks []Chunk
	var sentence strings.Builder
	var sentences []string
	runes := []rune(text)

	// Basic sentence split
	for _, r := range runes {
		sentence.WriteRune(r)
		if r == '.' || r == '!' || r == '?' {
			trimmed := strings.TrimSpace(sentence.String())
			if trimmed != "" {
				sentences = append(sentences, trimmed)
			}
			sentence.Reset()
		}
	}

	// Build chunks with overlap
	for i, current := range sentences {
		chunkParts := []string{}

		// Add 3 trailing words from previous sentence
		if i > 0 {
			prevWords := strings.Fields(sentences[i-1])
			start := len(prevWords) - 3
			if start < 0 {
				start = 0
			}
			chunkParts = append(chunkParts, strings.Join(prevWords[start:], " "))
		}

		// Add current sentence
		chunkParts = append(chunkParts, current)

		// Add 3 leading words from next sentence
		if i+1 < len(sentences) {
			nextWords := strings.Fields(sentences[i+1])
			end := 3
			if len(nextWords) < end {
				end = len(nextWords)
			}
			chunkParts = append(chunkParts, strings.Join(nextWords[:end], " "))
		}

		log.Print("starting embedding")
		text := strings.Join(chunkParts, " ")
		embedding, err := GetEmbedding(text)
		if err != nil {
			log.Printf("embedding error: %v", err)
			embedding = []float32{}
		}

		chunks = append(chunks, Chunk{
			Text:       text,
			Origin:     origin,
			LineNumber: i + 1,
			Timestamp:  time.Now(),
			Tags:       []string{},
			Metadata:   map[string]interface{}{},
			Vector:     embedding,
		})
	}

	return chunks
}
