package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
)

// instantPodcastHandler expects {"topic","document"} and returns audio/wav bytes.
func instantPodcastHandler(w http.ResponseWriter, r *http.Request) {
	var payload struct {
		Topic    string `json:"topic"`
		Document string `json:"document"`
	}
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil ||
		payload.Topic == "" || payload.Document == "" {
		http.Error(w, "Invalid JSON or missing 'topic'/'document'", http.StatusBadRequest)
		return
	}

	// Debug logging
	log.Printf("DEBUG: Received topic: %s", payload.Topic)
	log.Printf("DEBUG: Document length: %d characters", len(payload.Document))
	log.Printf("DEBUG: Document preview: %s", payload.Document[:100])

	// Run the full pipeline
	wavBytes, err := InstantPodcast(payload.Topic, payload.Document)
	if err != nil {
		log.Printf("ERROR: Podcast error: %v", err)
		http.Error(w, fmt.Sprintf("Podcast error: %v", err), http.StatusInternalServerError)
		return
	}

	log.Printf("DEBUG: Generated WAV of %d bytes", len(wavBytes))

	// Return the WAV so Svelte can do res.blob()
	w.Header().Set("Content-Type", "audio/wav")
	w.WriteHeader(http.StatusOK)
	w.Write(wavBytes)
}

// createPodcastHandler remains JSON
func createPodcastHandler(w http.ResponseWriter, r *http.Request) {
	var payload struct {
		Topic      string `json:"topic"`
		Collection string `json:"collection"`
	}
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil ||
		payload.Topic == "" || payload.Collection == "" {
		http.Error(w, "Invalid JSON or missing 'topic'/'collection'", http.StatusBadRequest)
		return
	}

	if err := CreatePodcast(payload.Topic, payload.Collection); err != nil {
		http.Error(w, fmt.Sprintf("Create error: %v", err), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	w.Write([]byte(`{"message":"Collection created, ready for uploads."}`))
}

// finishPodcastHandler returns a WAV blob instead of JSON
func finishPodcastHandler(w http.ResponseWriter, r *http.Request) {
	var payload struct {
		Topic      string `json:"topic"`
		Collection string `json:"collection"`
	}
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil ||
		payload.Topic == "" || payload.Collection == "" {
		http.Error(w, "Invalid JSON or missing 'topic'/'collection'", http.StatusBadRequest)
		return
	}

	wavBytes, err := FinishPodcast(payload.Topic, payload.Collection)
	if err != nil {
		http.Error(w, fmt.Sprintf("Finalize error: %v", err), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "audio/wav")
	w.WriteHeader(http.StatusOK)
	w.Write(wavBytes)
}

// uploadDocumentHandler stays JSON
func uploadDocumentHandler(w http.ResponseWriter, r *http.Request) {
	var payload struct {
		Collection string `json:"collection"`
		Document   string `json:"document"`
	}
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil ||
		payload.Collection == "" || payload.Document == "" {
		http.Error(w, "Invalid JSON or missing 'collection'/'document'", http.StatusBadRequest)
		return
	}

	UploadDocument(payload.Collection, payload.Document)

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	w.Write([]byte(`{"message":"Document uploaded."}`))
}
