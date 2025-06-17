# Knowledge-core: acquire (Go) + ingest (Python). Use make fetch | ingest | run.
.PHONY: build build-py fetch ingest run docker-build docker-up clean

REPO_ROOT := $(CURDIR)
DATA_RAWDOCS := $(REPO_ROOT)/data/rawdocs
DATA_ASSETS := $(REPO_ROOT)/data/assets
DATA_DOCS := $(REPO_ROOT)/data/docs

build:
	go build -o bin/acquire ./cmd/acquire

build-py:
	pip install -r requirements.txt

# Acquire only: fetch URL or file into data/rawdocs/
fetch:
	@if [ -z "$(URL)" ] && [ -z "$(FILE)" ]; then \
		echo "Usage: make fetch URL=https://... or make fetch FILE=path/to/file.html"; exit 1; fi
	$(MAKE) build
	@if [ -n "$(FILE)" ]; then \
		./bin/acquire -file "$(FILE)" -rawdocs "$(DATA_RAWDOCS)" $(if $(URL),-source-uri "$(URL)"); \
	else \
		./bin/acquire -url "$(URL)" -rawdocs "$(DATA_RAWDOCS)"; fi

# Ingest only: parse data/rawdocs/ -> data/docs/ and data/assets/
ingest:
	@mkdir -p "$(DATA_RAWDOCS)" "$(DATA_ASSETS)" "$(DATA_DOCS)"
	@if [ -n "$(RAWDOC_ID)" ]; then \
		python -m ingest.run_ingest --rawdoc-id "$(RAWDOC_ID)" --rawdocs "$(DATA_RAWDOCS)" --assets "$(DATA_ASSETS)" --docs "$(DATA_DOCS)"; \
	else \
		$(MAKE) ingest-all; fi

# Process all unprocessed RawDocs (skip if .done exists)
ingest-all:
	@mkdir -p "$(DATA_RAWDOCS)" "$(DATA_ASSETS)" "$(DATA_DOCS)"
	@for meta in $(DATA_RAWDOCS)/*.meta.json; do \
		[ -f "$$meta" ] || continue; \
		id=$$(basename "$$meta" .meta.json); \
		python -m ingest.run_ingest --rawdoc-id "$$id" --rawdocs "$(DATA_RAWDOCS)" --assets "$(DATA_ASSETS)" --docs "$(DATA_DOCS)" || true; \
	done

# Full pipeline for one URL or file: fetch then ingest
run:
	@if [ -z "$(URL)" ] && [ -z "$(FILE)" ]; then \
		echo "Usage: make run URL=https://... or make run FILE=path/to/file.html"; exit 1; fi
	$(MAKE) build
	@if [ -n "$(FILE)" ]; then \
		./bin/acquire -file "$(FILE)" -rawdocs "$(DATA_RAWDOCS)" $(if $(URL),-source-uri "$(URL)"); \
	else \
		./bin/acquire -url "$(URL)" -rawdocs "$(DATA_RAWDOCS)"; fi
	@meta=$$(ls -t $(DATA_RAWDOCS)/*.meta.json 2>/dev/null | head -1); \
	if [ -n "$$meta" ]; then \
		id=$$(basename "$$meta" .meta.json); \
		python -m ingest.run_ingest --rawdoc-id "$$id" --rawdocs "$(DATA_RAWDOCS)" --assets "$(DATA_ASSETS)" --docs "$(DATA_DOCS)"; \
	fi

docker-build:
	docker compose build

docker-up:
	docker compose up -d

clean:
	rm -rf bin/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "Optionally remove data: rm -rf data/"
