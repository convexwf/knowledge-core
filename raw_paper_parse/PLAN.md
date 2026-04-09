# raw_paper_parse — design plan

## Goals

- Fetch paper pages and normalize them into the shared **Document** schema ([`schemas/document.json`](../schemas/document.json)) and **RawDoc** layout ([`raw_ingest/common/rawdoc_write.py`](../raw_ingest/common/rawdoc_write.py)).
- **Variants**: `preprint`, `conference`, `journal`. If all three are ingested for the same work, that yields **three documents** (three `doc_id`s), linked by a shared **work id** in metadata.
- **Phase 1** (implemented here): **arXiv HTML** only (`https://arxiv.org/html/...`), experimental LaTeXML HTML (“ar5iv”).
- **Phase 2** (not implemented): conference pages (e.g. OpenReview HTML), journal publisher HTML or **PDF** (`meta.source.type: pdf` in the schema), discovery via Crossref / OpenAlex, optional tooling to suggest DOIs.

## Finding a DOI from an arXiv preprint

Many preprints **do not** list a journal DOI on arXiv until (or unless) authors or the journal register it. Try in order:

1. **arXiv abstract page** — `https://arxiv.org/abs/<id>`: look for **Journal reference**, **DOI**, or publisher links.
2. **arXiv Atom API** — `http://export.arxiv.org/api/query?id_list=<arxiv_id>`: check for `<arxiv:doi>` in the entry. Absence does not mean the paper was never published elsewhere.
3. **OpenAlex** — resolve the work by arXiv id or title; read `doi` / `ids.doi` (multiple works may exist; pick the right variant manually).
4. **Semantic Scholar Graph API** — `GET https://api.semanticscholar.org/graph/v1/paper/arXiv:<id>?fields=externalIds,...` and use `externalIds.DOI` when present (follow API key / rate-limit rules).
5. **Crossref** — bibliographic query by title + authors + year (noisy); prefer validating a DOI found via OpenAlex/S2.

Phase 1 does **not** auto-resolve DOIs: batch lines use an explicit `work_id` (often `arxiv:...`); conference/journal rows are filled manually when you have a DOI or official URL.

## Alignment with raw_ingest

| raw_ingest | raw_paper_parse |
|------------|-----------------|
| `sites/router.py` + `supported_sites.txt` | `sources/router.py` + `supported_sources.txt` |
| `sites/<module>.py` → `run_one(...)` | `sources/arxiv_html.py` → `run_one(...)` (+ optional `work_id`, `variant`) |
| Shared helpers | Add `raw_ingest/common` to `sys.path` and import `normalize_doc`, `sink_doc`, `rawdoc_write`, `assets_doc`, `schema_validate`, `repo_paths` |
| Output dirs | Default: same `data/rawdocs`, `data/docs`, `data/assets` as the repo Makefile |

## Work × variant model

- **work_id**: logical key, e.g. `arxiv:2401.12345v2` or `doi:10.xxxx/...` (provided in the batch file or CLI).
- **variant**: `preprint` | `conference` | `journal`.
- **Tags** on each document (convention):
  - `paper:work_id:<work_id>`
  - `paper:variant:<variant>`

Optional later: extend `schemas/document.json` with a typed `paper` object on `meta` instead of tag conventions.

## Batch input format

Tab-separated (one row = one document / one fetch):

```text
# work_id	variant	fetch_url	[canonical_url]
arxiv:2401.00001v1	preprint	https://arxiv.org/html/2401.00001v1	https://arxiv.org/abs/2401.00001v1
```

Lines starting with `#` are comments. URL-only lines (no tabs) are accepted for arXiv URLs: `work_id` defaults to `arxiv:<id>`, `variant` to `preprint`, `canonical` to the corresponding `abs` URL.

## arXiv HTML parsing (Phase 1)

- Normalize `abs` / `pdf` URLs to **`html`** where possible.
- Parse `article.ltx_document` (LaTeXML): document title, authors, nested `section` / `subsection` / `subsubsection`, `ltx_para` (paragraphs, figures, tables).
- Math: prefer plain text via BeautifulSoup `get_text()`; formulas may be lossy.
- Figures: `img.ltx_graphics` → `figure` sections + `process_assets` with fetch URL as base (respects `<base href>` on the page).

## Risks

- arXiv HTML DOM changes (LaTeXML / ar5iv updates).
- Conference/journal: paywalls, anti-bot, PDF-heavy workflows — separate adapters in Phase 2.

## Related files

- [`README.md`](README.md) — quick start and Makefile targets.
- [`README.zh-cn.md`](README.zh-cn.md) — Chinese version.
