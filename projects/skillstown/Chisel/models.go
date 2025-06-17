package main

import "time"

type Chunk struct {
	Text       string                 `json:"text"`
	Origin     string                 `json:"origin"`
	LineNumber int                    `json:"line_number"`
	Timestamp  time.Time              `json:"timestamp"`
	Tags       []string               `json:"tags"`
	Metadata   map[string]interface{} `json:"metadata"`
	Vector     []float32              `json:"vector"`
}

type ChunkRequest struct {
	Origin string `json:"origin"`
	Text   string `json:"text"`
}
