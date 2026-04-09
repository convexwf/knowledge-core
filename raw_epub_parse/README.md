# raw_epub_parse

Parse **EPUB** files, normalize them into the shared **Document** + **RawDoc** pipeline, and write **JSON + Markdown** under the same `data/` layout used by [`raw_ingest`](../raw_ingest/README.md) and [`raw_paper_parse`](../raw_paper_parse/README.md).

EPUB is technically a packaged collection of **XHTML/HTML-like chapters + OPF metadata + navigation + assets**, so it is a strong fit for reusing the existing HTML-oriented normalization and Markdown-generation pipeline.

Full feasibility analysis, pipeline design, and phased implementation plan: **[PLAN.md](PLAN.md)**.

## Proposed scope

Phase 1 should focus on **local `.epub` files**:

- unzip container
- read OPF package metadata
- resolve spine reading order
- parse chapter XHTML
- normalize into the shared document schema
- process embedded assets
- export Markdown

Future phases can extend to:

- batch EPUB ingestion
- chapter-aware output
- richer footnote/table/image preservation
- optional AI post-processing for summaries/tags

## Why this is feasible

- EPUB content is usually **well-formed XHTML**, easier to parse than arbitrary web HTML.
- Existing pipeline pieces in `raw_ingest/common/` should be reusable for:
  - RawDoc writing
  - document normalization
  - asset processing
  - schema validation
  - sink/export to JSON and Markdown
- Existing HTML extraction lessons from `raw_ingest` and `raw_paper_parse` apply directly to:
  - DOM walking
  - metadata fallback
  - relative URL resolution
  - code/table/figure handling

## Related

- [`PLAN.md`](PLAN.md) — technical feasibility and design
- [`../raw_ingest/README.md`](../raw_ingest/README.md)
- [`../raw_paper_parse/README.md`](../raw_paper_parse/README.md)
