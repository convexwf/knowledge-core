package fetch

import (
	"os"
	"path/filepath"
	"time"
)

// AcquireFile imports a local file into rawdocsDir, optionally with sourceURI for routing; returns the absolute meta path.
func AcquireFile(filePath, rawdocsDir, sourceURI string) (metaPath string, err error) {
	rawdocID := MustUUID()
	if err := EnsureDir(rawdocsDir); err != nil {
		return "", err
	}
	body, err := os.ReadFile(filePath)
	if err != nil {
		return "", err
	}
	ext := filepath.Ext(filePath)
	if ext == "" {
		ext = ".html"
	}
	storagePath := filepath.Join(rawdocsDir, rawdocID+ext)
	if err := os.WriteFile(storagePath, body, 0644); err != nil {
		return "", err
	}
	absPath, _ := filepath.Abs(storagePath)
	if sourceURI == "" {
		sourceURI, _ = filepath.Abs(filePath)
	}
	sourceType := "singlefile_html"
	if ext != ".html" && ext != ".htm" {
		sourceType = "url"
	}
	contentType := "text/html"
	if sourceType == "url" {
		contentType = "application/octet-stream"
	}
	rawdoc := &RawDoc{
		RawDocID:      rawdocID,
		SourceType:    sourceType,
		SourceURI:     sourceURI,
		FetchTime:     time.Now().UTC().Format(time.RFC3339),
		StoragePath:   absPath,
		ContentType:   contentType,
		ContentLength: len(body),
		Metadata:      map[string]any{},
	}
	return WriteMeta(rawdoc, rawdocsDir)
}
