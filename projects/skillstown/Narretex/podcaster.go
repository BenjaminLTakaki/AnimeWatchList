package main

import (
	"bytes"
	"fmt"
	"io"

	"github.com/faiface/beep"
	"github.com/faiface/beep/mp3"
	"github.com/faiface/beep/wav"
	"github.com/google/uuid"
)

// memWriteSeeker provides a minimal in-memory WriteSeeker.
type memWriteSeeker struct {
	buf bytes.Buffer
}

func (m *memWriteSeeker) Write(p []byte) (int, error) {
	return m.buf.Write(p)
}
func (m *memWriteSeeker) Seek(offset int64, whence int) (int64, error) {
	// no real seeking; just pretend we're always at the end
	return int64(m.buf.Len()), nil
}

// InstantPodcast runs the full pipeline and returns a single WAV byte slice.
func InstantPodcast(topic, document string) ([]byte, error) {
	// 1) isolate a collection
	id := uuid.New().String()
	defer DeleteCollection(id)

	// 2) create + upload
	if err := CreateCollection(id, topic); err != nil {
		return nil, fmt.Errorf("create collection: %w", err)
	}
	UploadDocument(id, document)

	// 3) warm up RAG lookup (optional)
	_, _ = Lookup(topic, id)

	// 4) generate script
	script, err := Script(topic, id)
	if err != nil {
		return nil, fmt.Errorf("script generation: %w", err)
	}
	if script == "" {
		return nil, fmt.Errorf("empty script")
	}

	// 5) generate MP3 segments
	segments, err := GeneratePodcastSpeech(script)
	if err != nil {
		return nil, fmt.Errorf("tts error: %w", err)
	}
	if len(segments) == 0 {
		return nil, fmt.Errorf("no audio segments")
	}

	// 6) decode & collect streamers
	var streamers []beep.Streamer
	var format beep.Format
	for i, mp3data := range segments {
		rc := io.NopCloser(bytes.NewReader(mp3data))
		stream, f, err := mp3.Decode(rc)
		rc.Close()
		if err != nil {
			return nil, fmt.Errorf("decode segment %d: %w", i, err)
		}
		if i == 0 {
			format = f
		}
		streamers = append(streamers, stream)
	}

	// 7) concatenate into one stream
	combined := beep.Seq(streamers...)

	// 8) re-encode as WAV into our memWriteSeeker
	mem := &memWriteSeeker{}
	if err := wav.Encode(mem, combined, format); err != nil {
		return nil, fmt.Errorf("wav encode: %w", err)
	}

	return mem.buf.Bytes(), nil
}

// CreatePodcast initializes a named collection for later uploads.
func CreatePodcast(topic, collection string) error {
	return CreateCollection(collection, topic)
}

// FinishPodcast does the same but against an existing collection.
func FinishPodcast(topic, collection string) ([]byte, error) {
	// reuse RAG context
	_, _ = Lookup(topic, collection)

	script, err := Script(topic, collection)
	if err != nil {
		return nil, fmt.Errorf("script generation: %w", err)
	}
	if script == "" {
		return nil, fmt.Errorf("empty script")
	}

	segments, err := GeneratePodcastSpeech(script)
	if err != nil {
		return nil, fmt.Errorf("tts error: %w", err)
	}
	if len(segments) == 0 {
		return nil, fmt.Errorf("no audio segments")
	}

	var streamers []beep.Streamer
	var format beep.Format
	for i, mp3data := range segments {
		rc := io.NopCloser(bytes.NewReader(mp3data))
		stream, f, err := mp3.Decode(rc)
		rc.Close()
		if err != nil {
			return nil, fmt.Errorf("decode segment %d: %w", i, err)
		}
		if i == 0 {
			format = f
		}
		streamers = append(streamers, stream)
	}

	combined := beep.Seq(streamers...)
	mem := &memWriteSeeker{}
	if err := wav.Encode(mem, combined, format); err != nil {
		return nil, fmt.Errorf("wav encode: %w", err)
	}

	return mem.buf.Bytes(), nil
}
