package main

import (
	"fmt"
	"log"
	"net/http"
	"os"

	"github.com/joho/godotenv"
)

func init() {
	// Load .env file if it exists
	if err := godotenv.Load(); err != nil {
		log.Println("No .env file found, using system environment variables")
	}
}

var httpPort = os.Getenv("PORT")

func enableCORS(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		// Allow all origins
		w.Header().Set("Access-Control-Allow-Origin", "*")
		// Allow specific headers and methods
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
		w.Header().Set("Access-Control-Allow-Methods", "POST, OPTIONS")

		// Handle preflight
		if r.Method == "OPTIONS" {
			w.WriteHeader(http.StatusOK)
			return
		}

		next.ServeHTTP(w, r)
	}
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	http.HandleFunc("/chunk", enableCORS(chunkHandler))
	http.HandleFunc("/lookup", enableCORS(lookupHandler))
	http.HandleFunc("/create-collection", enableCORS(createCollectionHandler))
	http.HandleFunc("/delete-collection", enableCORS(deleteCollectionHandler))
	http.HandleFunc("/delete-point", enableCORS(deletePointHandler))
	
	fmt.Printf("🧠 Chisel API running on http://localhost:%s\n", port)
	log.Fatal(http.ListenAndServe(":"+port, nil))
}
