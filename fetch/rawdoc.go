// Package fetch provides acquisition logic: URL/file fetch and RawDoc write.
// Used by cmd/acquire and other commands.
package fetch

import (
	"crypto/rand"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

// RawDoc is the contract between acquire and parse (see spec).
type RawDoc struct {
	RawDocID      string         `json:"rawdoc_id"`
	SourceType    string         `json:"source_type"`
	SourceURI     string         `json:"source_uri"`
	FetchTime     string         `json:"fetch_time"`
	StoragePath   string         `json:"storage_path"`
	ContentType   string         `json:"content_type"`
	ContentLength int            `json:"content_length"`
	Metadata      map[string]any `json:"metadata"`
}

// MustUUID returns a new UUID v4-style string; panics on RNG error.
func MustUUID() string {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		panic(err)
	}
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return fmt.Sprintf("%08x-%04x-%04x-%04x-%12x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}

// EnsureDir creates the directory and parents if needed.
func EnsureDir(p string) error {
	return os.MkdirAll(p, 0755)
}

// WriteMeta writes rawdoc to rawdocsDir/<rawdoc_id>.meta.json and returns the absolute meta path.
func WriteMeta(rawdoc *RawDoc, rawdocsDir string) (metaPath string, err error) {
	metaPath = filepath.Join(rawdocsDir, rawdoc.RawDocID+".meta.json")
	metaJSON, err := json.MarshalIndent(rawdoc, "", "  ")
	if err != nil {
		return "", err
	}
	if err := os.WriteFile(metaPath, metaJSON, 0644); err != nil {
		return "", err
	}
	return filepath.Abs(metaPath)
}
