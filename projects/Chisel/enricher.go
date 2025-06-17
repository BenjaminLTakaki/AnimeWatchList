package main

func EnrichChunksWithTags(chunks []Chunk) ([]Chunk, error) {
	var texts []string
	for _, chunk := range chunks {
		texts = append(texts, chunk.Text)
	}

	allTags, err := BatchGenerateTags(texts)
	if err != nil {
		return nil, err
	}

	for i := range chunks {
		if i < len(allTags) {
			chunks[i].Tags = append(chunks[i].Tags, allTags[i]...)
			chunks[i].Metadata["auto_tags"] = allTags[i]
		}
	}

	return chunks, nil
}
