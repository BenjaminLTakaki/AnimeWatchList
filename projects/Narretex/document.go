package main

import (
	"fmt"
)

// UploadDocument calls the UploadData function (from apiHandler.go)
// to send a document to the Chisel API for processing.
func UploadDocument(collection string, document string) {
	err := UploadData(collection, document)
	if err != nil {
		fmt.Printf("[UploadDocument] Error: %v\n", err)
	} else {
		fmt.Printf("[UploadDocument] Successfully uploaded document to collection: %s\n", collection)
	}
}
