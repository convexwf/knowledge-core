# Knowledge-core: acquire (Go) + ingest (Python). Use make fetch | ingest | run.
.PHONY: build build-py fetch ingest run docker-build docker-up clean \
	raw-ingest-deps raw-ingest raw-ingest-batch \
	raw-ingest-freedium-deps raw-ingest-freedium raw-ingest-freedium-batch \
	raw-ingest-meituan-tech-deps raw-ingest-meituan-tech raw-ingest-meituan-tech-batch

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

# raw_ingest: Freedium -> Medium (standalone Python under raw_ingest/)
RAW_INGEST_DIR := $(REPO_ROOT)/raw_ingest

# Unified router: Freedium, Meituan tech, All Things Distributed (see raw_ingest/sites/router.py)
raw-ingest-deps:
	@cd "$(RAW_INGEST_DIR)" && pip install -q -r requirements.txt

# Single URL: make raw-ingest URL='https://...'  (optional CANONICAL=... for Freedium)
raw-ingest: raw-ingest-deps
	@test -n "$(URL)" || (echo "Usage: make raw-ingest URL='https://...'"; exit 1)
	@cd "$(RAW_INGEST_DIR)" && python sites/router.py --url "$(URL)" $(if $(CANONICAL),--canonical-url "$(CANONICAL)")

# Mixed URL list: unsupported hosts are skipped (stderr UNSUPPORTED); see raw_ingest/examples/example_urls.txt
raw-ingest-batch: raw-ingest-deps
	@test -n "$(FILE)" || (echo "Usage: make raw-ingest-batch FILE=path/to/urls.txt"; exit 1)
	@cd "$(RAW_INGEST_DIR)" && python sites/router.py --urls-file "$(abspath $(FILE))"

raw-ingest-freedium-deps:
	@cd "$(RAW_INGEST_DIR)" && pip install -q -r requirements.txt

# Single URL: make raw-ingest-freedium URL='https://freedium-mirror.cfd/https://medium.com/...'
# Optional CANONICAL=https://medium.com/... if not derivable from URL
raw-ingest-freedium: raw-ingest-freedium-deps
	@test -n "$(URL)" || (echo "Usage: make raw-ingest-freedium URL='https://freedium-mirror.cfd/https://medium.com/...'"; exit 1)
	@cd "$(RAW_INGEST_DIR)" && python sites/medium_freedium.py --fetch-url "$(URL)" $(if $(CANONICAL),--canonical-url "$(CANONICAL)")

# Batch: FILE is a text file, one Freedium (or fetch|canonical) URL per line; # starts comments
raw-ingest-freedium-batch: raw-ingest-freedium-deps
	@test -n "$(FILE)" || (echo "Usage: make raw-ingest-freedium-batch FILE=path/to/urls.txt"; exit 1)
	@cd "$(RAW_INGEST_DIR)" && python sites/medium_freedium.py --urls-file "$(abspath $(FILE))"

# Meituan tech blog (tech.meituan.com)
raw-ingest-meituan-tech-deps:
	@cd "$(RAW_INGEST_DIR)" && pip install -q -r requirements.txt

# Single URL: make raw-ingest-meituan-tech URL='https://tech.meituan.com/2026/03/20/....html'
raw-ingest-meituan-tech: raw-ingest-meituan-tech-deps
	@test -n "$(URL)" || (echo "Usage: make raw-ingest-meituan-tech URL='https://tech.meituan.com/...'"; exit 1)
	@cd "$(RAW_INGEST_DIR)" && python sites/meituan_tech.py --fetch-url "$(URL)" $(if $(CANONICAL),--canonical-url "$(CANONICAL)")

# Batch: one article URL per line; optional fetch|canonical; # starts comments
raw-ingest-meituan-tech-batch: raw-ingest-meituan-tech-deps
	@test -n "$(FILE)" || (echo "Usage: make raw-ingest-meituan-tech-batch FILE=path/to/urls.txt"; exit 1)
	@cd "$(RAW_INGEST_DIR)" && python sites/meituan_tech.py --urls-file "$(abspath $(FILE))"
