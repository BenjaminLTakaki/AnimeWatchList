package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
)

func chunkHandler(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Text       string `json:"text"`
		Origin     string `json:"origin"`
		Collection string `json:"collection,omitempty"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	// Debug logging
	log.Printf("DEBUG: Received text length: %d characters", len(req.Text))
	log.Printf("DEBUG: Origin: %s", req.Origin)
	log.Printf("DEBUG: Collection: %s", req.Collection)
	log.Printf("DEBUG: Text preview: %s", req.Text[:100])

	// Use provided collection or fallback to default.
	collection := req.Collection
	if collection == "" {
		collection = "Database"
	}

	log.Printf("Phase 1 - Chunking for collection: %s", collection)
	chunks := SentenceChunk(req.Text, req.Origin)

	log.Printf("DEBUG: Created %d chunks", len(chunks))
	for i, chunk := range chunks {
		log.Printf("DEBUG: Chunk %d length: %d characters", i, len(chunk.Text))
		if len(chunk.Text) > 50 {
			log.Printf("DEBUG: Chunk %d preview: %s", i, chunk.Text[:50])
		} else {
			log.Printf("DEBUG: Chunk %d full text: %s", i, chunk.Text)
		}
	}

	// Rest of your existing code...
	log.Print("Phase 2 - Tagging chunks")
	taggedChunks, err := EnrichChunksWithTags(chunks)
	if err != nil {
		log.Printf("Error tagging chunks: %v", err)
		http.Error(w, "Failed to tag chunks", http.StatusInternalServerError)
		return
	}

	log.Print("Phase 3 - Uploading chunks to Qdrant")
	for _, chunk := range taggedChunks {
		log.Print("Uploading chunk...")
		if err := SendChunkToQdrant(chunk, collection); err != nil {
			log.Printf("Error sending chunk to Qdrant: %v", err)
		}
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(taggedChunks)
}

func lookupHandler(w http.ResponseWriter, r *http.Request) {
	var payload struct {
		Query      string `json:"query"`
		Collection string `json:"collection,omitempty"`
		Subject    string `json:"subject,omitempty"`
		From       string `json:"from,omitempty"` // ISO8601 timestamp
		To         string `json:"to,omitempty"`
	}

	// Decode input
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil || payload.Query == "" {
		http.Error(w, "Invalid JSON or missing 'query' field", http.StatusBadRequest)
		return
	}

	collection := payload.Collection
	if collection == "" {
		collection = "Database"
	}

	log.Printf("Performing vector lookup for: %s in collection: %s", payload.Query, collection)

	// Build optional filters
	var fromPtr, toPtr *string
	if payload.From != "" {
		fromPtr = &payload.From
	}
	if payload.To != "" {
		toPtr = &payload.To
	}
	filter := BuildFilter(payload.Subject, fromPtr, toPtr)

	// Call vector search
	lookupResult, err := Lookup(payload.Query, collection, filter)
	if err != nil {
		http.Error(w, fmt.Sprintf("Lookup failed: %v", err), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	if _, err := w.Write([]byte(lookupResult)); err != nil {
		log.Printf("Error writing response: %v", err)
	}
}

func createCollectionHandler(w http.ResponseWriter, r *http.Request) {
	var payload struct {
		Name string `json:"name"`
	}

	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil || payload.Name == "" {
		http.Error(w, "Invalid JSON or missing 'name' field", http.StatusBadRequest)
		return
	}

	qdrantHost := getQdrantHost()
	url := fmt.Sprintf("%s/collections/%s", qdrantHost, payload.Name)

	body := map[string]interface{}{
		"vectors": map[string]interface{}{
			"size":     1536,
			"distance": "Cosine",
		},
	}

	jsonBody, _ := json.Marshal(body)

	req, _ := http.NewRequest("PUT", url, bytes.NewBuffer(jsonBody))
	req.Header.Set("Content-Type", "application/json")

	res, err := http.DefaultClient.Do(req)
	if err != nil {
		http.Error(w, fmt.Sprintf("Request error: %v", err), http.StatusInternalServerError)
		return
	}
	defer res.Body.Close()

	respBody, _ := io.ReadAll(res.Body)
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(res.StatusCode)
	w.Write(respBody)
}

func deleteCollectionHandler(w http.ResponseWriter, r *http.Request) {
	var payload struct {
		Name string `json:"name"`
	}

	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil || payload.Name == "" {
		http.Error(w, "Invalid JSON or missing 'name' field", http.StatusBadRequest)
		return
	}

	qdrantHost := getQdrantHost()
	url := fmt.Sprintf("%s/collections/%s", qdrantHost, payload.Name)

	req, _ := http.NewRequest("DELETE", url, nil)
	res, err := http.DefaultClient.Do(req)
	if err != nil {
		http.Error(w, fmt.Sprintf("Request error: %v", err), http.StatusInternalServerError)
		return
	}
	defer res.Body.Close()

	respBody, _ := io.ReadAll(res.Body)
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(res.StatusCode)
	w.Write(respBody)
}

func deletePointHandler(w http.ResponseWriter, r *http.Request) {
	var payload struct {
		Collection string `json:"collection"`
		PointID    string `json:"point_id"`
	}

	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil || payload.Collection == "" || payload.PointID == "" {
		http.Error(w, "Invalid JSON or missing fields 'collection' and 'point_id'", http.StatusBadRequest)
		return
	}

	if err := DeletePointFromQdrant(payload.PointID, payload.Collection); err != nil {
		http.Error(w, fmt.Sprintf("Failed to delete point: %v", err), http.StatusInternalServerError)
		return
	}

	w.WriteHeader(http.StatusOK)
	w.Write([]byte(`{"status":"deleted"}`))
}
