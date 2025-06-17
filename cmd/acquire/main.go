// Acquire: fetch URL or import local file, write RawDoc and content to rawdocs/.
// Per spec 5.1 "Acquisition in Go" – startup only; logic lives in fetch package.
package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/knowledge-core/fetch"
)

func main() {
	url := flag.String("url", "", "Fetch from URL")
	file := flag.String("file", "", "Import from local file path")
	sourceURI := flag.String("source-uri", "", "Source URI for routing (e.g. original URL when using -file)")
	rawdocs := flag.String("rawdocs", "data/rawdocs", "RawDocs directory")
	timeoutSec := flag.Int("timeout", 30, "HTTP timeout in seconds")
	flag.Parse()

	rawdocsDir := *rawdocs
	if !filepath.IsAbs(rawdocsDir) {
		cwd, _ := os.Getwd()
		rawdocsDir = filepath.Join(cwd, rawdocsDir)
	}

	var metaPath string
	var err error
	if *file != "" {
		metaPath, err = fetch.AcquireFile(*file, rawdocsDir, *sourceURI)
	} else if *url != "" {
		metaPath, err = fetch.AcquireURL(*url, rawdocsDir, time.Duration(*timeoutSec)*time.Second)
	} else {
		fmt.Fprintln(os.Stderr, "provide -url or -file")
		os.Exit(1)
	}
	if err != nil {
		fmt.Fprintf(os.Stderr, "acquire: %v\n", err)
		os.Exit(1)
	}
	fmt.Println(metaPath)
}
