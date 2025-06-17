package fetch

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// AcquireURL fetches url, writes content and meta under rawdocsDir, returns the absolute meta path.
func AcquireURL(url string, rawdocsDir string, timeout time.Duration) (metaPath string, err error) {
	rawdocID := MustUUID()
	if err := EnsureDir(rawdocsDir); err != nil {
		return "", err
	}
	client := &http.Client{Timeout: timeout}
	resp, err := client.Get(url)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("HTTP %d", resp.StatusCode)
	}
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}
	ct := resp.Header.Get("Content-Type")
	if i := strings.Index(ct, ";"); i >= 0 {
		ct = strings.TrimSpace(ct[:i])
	}
	ext := ".html"
	if ct != "" && !strings.Contains(strings.ToLower(ct), "html") {
		ext = ".bin"
	}
	storagePath := filepath.Join(rawdocsDir, rawdocID+ext)
	if err := os.WriteFile(storagePath, body, 0644); err != nil {
		return "", err
	}
	absPath, _ := filepath.Abs(storagePath)
	rawdoc := &RawDoc{
		RawDocID:      rawdocID,
		SourceType:    "url",
		SourceURI:     url,
		FetchTime:     time.Now().UTC().Format(time.RFC3339),
		StoragePath:   absPath,
		ContentType:   ct,
		ContentLength: len(body),
		Metadata:      map[string]any{},
	}
	return WriteMeta(rawdoc, rawdocsDir)
}
