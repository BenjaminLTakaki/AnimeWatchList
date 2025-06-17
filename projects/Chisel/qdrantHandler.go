package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/google/uuid"
)

func getQdrantHost() string {
	host := os.Getenv("QDRANT_HOST")
	if host == "" {
		host = "https://qdrant-vector-db-t8ao.onrender.com"
	}

	// For Render services, ensure we're using the correct URL format
	if strings.Contains(host, "onrender.com") && !strings.Contains(host, ":") {
		// Render services use HTTPS by default
		if !strings.HasPrefix(host, "https://") {
			host = "https://" + strings.TrimPrefix(host, "http://")
		}
	}

	return host
}

func SendChunkToQdrant(chunk Chunk, collection string) error {
	if len(chunk.Vector) == 0 {
		return fmt.Errorf("chunk vector is empty")
	}

	if collection == "" {
		collection = "Memory"
	}

	qdrantHost := getQdrantHost()
	url := fmt.Sprintf("%s/collections/%s/points", qdrantHost, collection)

	point := map[string]interface{}{
		"id":     uuid.New().String(),
		"vector": chunk.Vector,
		"payload": map[string]interface{}{
			"text":      chunk.Text,
			"origin":    chunk.Origin,
			"timestamp": chunk.Timestamp.Format(time.RFC3339),
			"tags":      chunk.Tags,
			"metadata":  chunk.Metadata,
		},
	}

	payload := map[string]interface{}{
		"points": []interface{}{point},
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("failed to marshal payload: %w", err)
	}

	req, err := http.NewRequest("PUT", url, bytes.NewBuffer(body))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{
		Timeout: 30 * time.Second, // Add timeout for Render services
	}
	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 300 {
		return fmt.Errorf("qdrant insert failed: %s", resp.Status)
	}

	return nil
}

func DeletePointFromQdrant(pointID string, collection string) error {
	qdrantHost := getQdrantHost()
	url := fmt.Sprintf("%s/collections/%s/points/delete", qdrantHost, collection)

	bodyData := map[string]interface{}{
		"points": []string{pointID},
	}

	body, err := json.Marshal(bodyData)
	if err != nil {
		return fmt.Errorf("failed to marshal delete payload: %w", err)
	}

	req, err := http.NewRequest("POST", url, bytes.NewBuffer(body))
	if err != nil {
		return fmt.Errorf("failed to create delete request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{
		Timeout: 30 * time.Second, // Add timeout for Render services
	}
	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("failed to send delete request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 300 {
		return fmt.Errorf("qdrant delete failed: %s", resp.Status)
	}

	return nil
}
