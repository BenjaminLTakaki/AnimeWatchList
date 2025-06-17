package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
)

func getChiselEndpoint() string {
	endpoint := os.Getenv("CHISEL_ENDPOINT")
	if endpoint == "" {
		endpoint = "http://localhost:8080"
	}
	return endpoint
}

// UploadData sends document data to the Chisel API.
func UploadData(collection string, data string) error {
	chiselEndpoint := getChiselEndpoint()
	chiselURL := chiselEndpoint + "/chunk"

	payload := map[string]string{
		"text":       data,
		"origin":     "NarreteX",
		"collection": collection,
	}
	jsonBody, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("failed to marshal payload: %v", err)
	}

	req, err := http.NewRequest("POST", chiselURL, bytes.NewBuffer(jsonBody))
	if err != nil {
		return fmt.Errorf("failed to create request: %v", err)
	}
	req.Header.Set("Content-Type", "application/json")

	res, err := http.DefaultClient.Do(req)
	if err != nil {
		return fmt.Errorf("failed to send request to Chisel: %v", err)
	}
	defer res.Body.Close()

	if res.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(res.Body)
		return fmt.Errorf("Chisel API error (%d): %s", res.StatusCode, string(body))
	}

	return nil
}

// Lookup sends a query along with the collection identifier to the Chisel API
func Lookup(query string, collection string) (string, error) {
	chiselEndpoint := getChiselEndpoint()
	lookupURL := chiselEndpoint + "/lookup"

	payload := map[string]string{
		"query":      query,
		"collection": collection,
	}
	jsonBody, err := json.Marshal(payload)
	if err != nil {
		return "", fmt.Errorf("failed to marshal payload: %v", err)
	}

	req, err := http.NewRequest("POST", lookupURL, bytes.NewBuffer(jsonBody))
	if err != nil {
		return "", fmt.Errorf("failed to create lookup request: %v", err)
	}
	req.Header.Set("Content-Type", "application/json")

	res, err := http.DefaultClient.Do(req)
	if err != nil {
		return "", fmt.Errorf("lookup request failed: %v", err)
	}
	defer res.Body.Close()

	body, err := io.ReadAll(res.Body)
	if err != nil {
		return "", fmt.Errorf("failed to read lookup response: %v", err)
	}

	return string(body), nil
}

// CreateCollection calls the Chisel /create-collection endpoint
func CreateCollection(name string, topic string) error {
	chiselEndpoint := getChiselEndpoint()
	createURL := chiselEndpoint + "/create-collection"

	payload := map[string]string{
		"name": name,
	}
	jsonBody, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("failed to marshal JSON: %w", err)
	}

	res, err := http.Post(createURL, "application/json", bytes.NewBuffer(jsonBody))
	if err != nil {
		return fmt.Errorf("failed to send request: %w", err)
	}
	defer res.Body.Close()

	bodyBytes, _ := io.ReadAll(res.Body)
	if res.StatusCode >= 400 {
		return fmt.Errorf("error from server: %s", string(bodyBytes))
	}

	fmt.Printf("CreateCollection OK: %s\n", string(bodyBytes))
	return nil
}

// DeleteCollection calls the Chisel /delete-collection endpoint
func DeleteCollection(name string) error {
	chiselEndpoint := getChiselEndpoint()
	deleteURL := chiselEndpoint + "/delete-collection"

	payload := map[string]string{
		"name": name,
	}
	jsonBody, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("failed to marshal JSON: %w", err)
	}

	res, err := http.Post(deleteURL, "application/json", bytes.NewBuffer(jsonBody))
	if err != nil {
		return fmt.Errorf("failed to send request: %w", err)
	}
	defer res.Body.Close()

	bodyBytes, _ := io.ReadAll(res.Body)
	if res.StatusCode >= 400 {
		return fmt.Errorf("error from server: %s", string(bodyBytes))
	}
	fmt.Printf("DeleteCollection OK: %s\n", string(bodyBytes))
	return nil
}
