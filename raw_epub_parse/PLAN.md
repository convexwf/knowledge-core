# raw_epub_parse — technical feasibility analysis

## Goals

- Ingest **EPUB** files and normalize them into the shared **Document** schema and **RawDoc** layout already used in [`raw_ingest`](../raw_ingest/README.md) and [`raw_paper_parse`](../raw_paper_parse/README.md).
- Reuse the existing **HTML-oriented processing chain** wherever possible instead of building a separate format-specific pipeline from scratch.
- Produce stable outputs under the same repository data layout:
  - `data/rawdocs/`
  - `data/docs/`
  - `data/assets/`

This is **technically feasible** and, compared with arbitrary web-page ingestion, EPUB is in several ways the easier input source because its main content is already packaged as structured XHTML.

---

## What an EPUB actually is

An EPUB file is typically a ZIP container with:

- `META-INF/container.xml`
- one OPF package file (`content.opf` or similar)
- multiple XHTML chapter files
- navigation files (`nav.xhtml` or legacy `.ncx`)
- CSS
- images/fonts/other assets

From an ingestion perspective, EPUB is best understood as:

```text
container
  -> package metadata
  -> ordered chapter documents
  -> linked assets
```

This matters because it means `raw_epub_parse` is not solving an OCR-style or PDF reconstruction problem. It is much closer to:

- multi-file HTML parsing
- asset resolution
- metadata normalization
- Markdown export

That makes it a strong architectural match for the repository’s existing document pipeline.

---

## Why this fits the current repository well

### 1. The repository already has the right output model

Both `raw_ingest` and `raw_paper_parse` ultimately normalize input into:

- RawDoc
- shared Document JSON
- Markdown
- processed assets

That output contract is already the hard part from a downstream integration perspective. EPUB can plug into the same contract cleanly.

### 2. EPUB chapters are already HTML/XHTML-like

Most EPUB text lives in XHTML files with familiar structures:

- headings
- paragraphs
- lists
- blockquotes
- images
- tables
- code blocks
- footnotes

So the parsing strategy can borrow directly from the HTML parsing lessons already established in:

- `raw_ingest`
- `raw_paper_parse`
- the broader HTML-to-Markdown summary documented in the Obsidian clipper notes

### 3. EPUB is usually cleaner than the web

Compared with open web pages, EPUB often has fewer issues with:

- ads
- popups
- dynamic JS rendering
- cookie walls
- social widgets
- hidden recommendation blocks

That means the “正文提取” problem is often less about selecting the right content region and more about:

- honoring reading order
- preserving section structure
- resolving assets and footnotes correctly

This reduces extraction complexity.

---

## Core feasibility judgment

`raw_epub_parse` is **highly feasible** as a new module in `knowledge-core`, and it can likely reuse a large portion of the existing normalization/export pipeline.

The main engineering work is not “whether EPUB can be parsed”, but:

1. how to map EPUB package structure into the repository’s input model
2. how to preserve chapter order and document hierarchy
3. how much formatting fidelity is needed in Markdown output

In other words, the risk is primarily in **design choices and edge-case coverage**, not in the basic viability of the format.

---

## Recommended architectural position

`raw_epub_parse` should be modeled closer to `raw_paper_parse` than to `raw_ingest`.

Why:

- `raw_ingest` is URL-first and site-router driven.
- EPUB is file-first and package-structure driven.
- `raw_paper_parse` already represents “new source type, same downstream schema”.

Recommended module shape:

```text
raw_epub_parse/
  README.md
  PLAN.md
  sources/
    router.py
    epub_file.py
  examples/
    ...
```

Suggested entry contract:

- input: local `.epub` file path
- optional metadata overrides:
  - `work_id`
  - `variant`
  - `canonical_uri`
  - `language`

This mirrors the “same normalized output, different upstream source” strategy already used by `raw_paper_parse`.

---

## Alignment with existing modules

| Existing module | What can be reused for EPUB |
| --- | --- |
| `raw_ingest/common/rawdoc_write.py` | write RawDoc payload + metadata |
| `raw_ingest/common/normalize_doc.py` | normalize structured content into document schema |
| `raw_ingest/common/assets_doc.py` | ingest/save referenced images/assets |
| `raw_ingest/common/sink_doc.py` | write final JSON + Markdown |
| `raw_ingest/common/schema_validate.py` | validate output |
| `raw_paper_parse` router pattern | source-based entrypoint organization |

The highest leverage path is:

- build a new EPUB-specific **source adapter**
- keep downstream normalization/export shared

---

## Proposed parsing pipeline

### Phase 1 pipeline

```text
.epub file
  -> unzip to temp workspace
  -> read META-INF/container.xml
  -> locate OPF package
  -> read package metadata
  -> resolve manifest + spine
  -> load chapter XHTML in reading order
  -> parse DOM blocks
  -> normalize into Document sections/items
  -> process assets
  -> write RawDoc + Document JSON + Markdown
```

This pipeline is straightforward and much more deterministic than many web parsers.

---

## Metadata extraction strategy

EPUB metadata usually comes from OPF package metadata, often including:

- title
- creator / author
- language
- identifier
- publisher
- date
- subject
- description

Recommended metadata priority:

1. explicit CLI/user override
2. OPF package metadata
3. chapter-level HTML metadata when present
4. filename / fallback defaults

Example mapping:

```text
title      <- dc:title
author     <- dc:creator
language   <- dc:language
identifier <- dc:identifier
published  <- dc:date
tags       <- dc:subject
summary    <- dc:description
```

Potential repository metadata additions:

- `meta.source.type: epub`
- `meta.source.path`
- `meta.source.identifier`
- `meta.book.chapter_count`
- `meta.book.spine_ids`

If the current schema is intentionally generic, some of these can also live in tags or RawDoc metadata first.

---

## Content extraction strategy

Unlike `raw_ingest`, Phase 1 for EPUB should usually **not** need aggressive “find the main article container” logic.

A more appropriate default is:

1. trust OPF spine order
2. parse each spine XHTML document
3. extract content from the document body
4. preserve section/chapter boundaries explicitly

This is a key difference from web clipping.

### Why full-body extraction is often acceptable

Because EPUB chapter files are often already content-only documents. They usually do not contain:

- site navigation
- unrelated recommendations
- comments
- cookie banners

So the default extraction mode can be much simpler:

- `body` as primary container
- optional removal of known boilerplate nodes
- chapter-aware block walking

### When extraction rules are still needed

Not all EPUBs are equally clean. You may still need cleanup rules for:

- duplicated chapter titles
- TOC pages included as body chapters
- publisher boilerplate
- copyright pages
- frontmatter/backmatter
- hidden anchors for footnotes and references

Recommended approach:

- simple defaults first
- selective cleanup rules second
- no heavy readability scoring unless necessary

---

## Markdown generation strategy

EPUB is especially well-suited to Markdown export because its source is already structured markup.

Recommended flow:

1. parse XHTML into normalized internal blocks
2. preserve semantic structures
3. emit Markdown from normalized blocks

This is usually better than doing a naive “raw XHTML -> Markdown” conversion on the whole package, because it gives better control over:

- chapter boundaries
- repeated headings
- footnotes
- images
- tables
- code blocks

### Important fidelity targets

- chapter title preservation
- heading hierarchy
- paragraph boundaries
- ordered/unordered lists
- blockquotes
- code blocks with language when possible
- image references and captions
- table preservation where practical
- internal footnote linking or flattening

### Recommended output shapes

There are two sensible modes:

1. **single-document mode**
   - one `.md` file for the full EPUB
2. **chapter-split mode**
   - one `.md` per chapter plus an index

Phase 1 should prefer **single-document mode**, because it aligns more closely with the existing “one input -> one document” pattern.

Later, chapter-split output can be added if needed.

---

## Asset handling feasibility

This is feasible and should reuse existing asset logic.

EPUB assets are typically local package resources, such as:

- cover image
- inline figures
- diagrams
- icons
- fonts

Key tasks:

1. resolve asset paths relative to each chapter file
2. copy or normalize them into `data/assets/`
3. rewrite document references

Compared with the web, EPUB assets are often easier because:

- they are already bundled locally
- no network fetch is needed
- paths are deterministic after unzip

Risks still exist for:

- SVG
- remote resources embedded in unusual EPUBs
- font-only decorative assets that should maybe be ignored

But overall this part is low risk.

---

## Footnotes, references, and navigation

EPUB often uses internal links for:

- table of contents
- footnotes
- endnotes
- bibliography

These are technically straightforward but require a policy decision.

Recommended Phase 1 behavior:

- preserve readable footnote text in output
- optionally flatten endnotes into inline/appendix markdown
- ignore purely navigational TOC pages unless explicitly requested

Possible strategies:

1. keep footnote anchors as Markdown links
2. convert to Markdown footnotes
3. collect notes into an appendix section

Option 2 is ideal if the normalized schema and exporter support it cleanly.

---

## Comparison with raw_ingest and raw_paper_parse

### Compared with raw_ingest

EPUB is easier in these dimensions:

- no network fetch
- no hostname routing
- less noisy HTML
- no dynamic rendering

EPUB is harder in these dimensions:

- package/container parsing
- multi-file reading order
- internal link and asset resolution

### Compared with raw_paper_parse

EPUB is similar in these dimensions:

- source-specific adapter feeding shared schema
- document-structure preservation matters
- figures/tables/notes need careful treatment

EPUB is easier in these dimensions:

- no arXiv-specific LaTeXML quirks
- no URL normalization from `abs/pdf/html`
- fewer citation-specific structural oddities

EPUB may be harder in these dimensions:

- richer frontmatter/backmatter variance
- publisher-specific packaging oddities
- chapter granularity decisions

---

## Main technical risks

### 1. EPUB flavor variance

Not all EPUBs are equally clean.

Possible differences:

- EPUB2 vs EPUB3
- `nav.xhtml` vs `.ncx`
- XHTML validity issues
- inconsistent metadata completeness
- odd chapter splitting

Mitigation:

- Phase 1 only support “common happy path”
- explicitly document unsupported edge cases
- build sample fixtures across several EPUB producers

### 2. Over-preserving boilerplate

If every XHTML body is trusted blindly, output may include:

- copyright pages
- dedications
- publication info
- navigation pages

Mitigation:

- filter spine items by media type and role
- optionally classify frontmatter/backmatter
- provide flags like `--include-frontmatter`

### 3. Markdown fidelity drift

Tables, footnotes, and layout-heavy chapters may degrade.

Mitigation:

- normalize before export
- add fixtures for complex books
- allow fallback to embedded HTML for unsupported structures

### 4. One EPUB, one doc may be too coarse

Some books are huge, and one Markdown file may become unwieldy.

Mitigation:

- Phase 1 keep one-doc simplicity
- Phase 2 add chapter-split mode

---

## Recommended implementation phases

## Phase 0: design + fixture collection

- collect 5 to 10 representative EPUB samples
- include:
  - simple fiction
  - technical book
  - book with images
  - book with footnotes
  - EPUB2 sample
  - EPUB3 sample
- define expected output shape

## Phase 1: local EPUB happy-path parser

- local file input only
- unzip + OPF + spine parsing
- parse chapter XHTML in order
- extract package metadata
- output one Document JSON + one Markdown file
- basic asset support for images
- schema validation

This phase is already enough to prove value.

## Phase 2: richer structure fidelity

- better footnote handling
- table normalization
- code block language hints
- chapter boundary metadata
- cover image support
- frontmatter/backmatter classification

## Phase 3: operational improvements

- batch ingestion
- chapter-split output mode
- dedup / canonical identifier policy
- optional AI summary/tag enrichment

---

## Suggested CLI and routing model

Recommended interface:

```bash
make epub-parse FILE=/path/to/book.epub
make epub-parse-batch FILE=raw_epub_parse/examples/example_epubs.tsv
```

Direct execution:

```bash
cd raw_epub_parse
python sources/router.py --file /path/to/book.epub
python sources/router.py --files-file examples/example_epubs.tsv
```

Batch TSV could be:

```text
# work_id	variant	epub_path	canonical_uri
isbn:9780000000001	book	/path/to/book.epub	https://example.com/book
```

Or a simpler file-only mode for Phase 1:

```text
/path/to/book.epub
```

This mirrors the flexible CLI style already used in `raw_paper_parse`.

---

## Data-model recommendation

Phase 1 can likely fit the existing schema without major changes.

Suggested tagging convention:

- `book:source:epub`
- `book:identifier:<id>`
- `book:language:<lang>`

Optional later structured metadata:

```text
meta.book.title
meta.book.authors
meta.book.language
meta.book.identifier
meta.book.publisher
meta.book.chapter_count
```

If schema changes are expensive, start by storing richer source information in RawDoc metadata first.

---

## Recommendation

The recommended decision is:

1. **Create `raw_epub_parse`**
2. **Implement Phase 1 as a local EPUB parser**
3. **Reuse the existing shared normalization/export pipeline**
4. **Avoid over-engineering正文识别 in the first version**

The central insight is:

- EPUB is already structured content
- the repository already knows how to normalize structured content
- therefore the missing piece is mainly a new source adapter, not a whole new system

So this feature is not only feasible; it is one of the more natural extensions of the current architecture.

---

## Related references

- [`../raw_ingest/README.md`](../raw_ingest/README.md)
- [`../raw_paper_parse/README.md`](../raw_paper_parse/README.md)
- [`../raw_paper_parse/PLAN.md`](../raw_paper_parse/PLAN.md)
- [`../../obsidian-clipper/web-content-extraction-and-markdown-guide.zh-CN.md`](../../obsidian-clipper/web-content-extraction-and-markdown-guide.zh-CN.md)
