# raw_paper_parse

Fetch **paper** HTML (Phase 1: **arXiv** experimental HTML), normalize into the same **Document** + **RawDoc** pipeline as [`raw_ingest`](../raw_ingest/README.md).

Full design, DOI lookup notes, and work/variant semantics: **[PLAN.md](PLAN.md)** (Chinese: [PLAN.zh-cn.md](PLAN.zh-cn.md)).

## Quick start

From the **repository root**:

```bash
make paper-parse-deps
make paper-parse URL='https://arxiv.org/html/2401.00001v1'
```

Batch (tab-separated; see [examples/example_papers.tsv](examples/example_papers.tsv)):

```bash
make paper-parse-batch FILE=raw_paper_parse/examples/example_papers.tsv
```

Or from this directory:

```bash
cd raw_paper_parse && pip install -r requirements.txt
python sources/router.py --url 'https://arxiv.org/html/2401.00001v1'
python sources/router.py --urls-file examples/example_papers.tsv
```

Optional single-URL metadata:

```bash
python sources/router.py --url 'https://arxiv.org/abs/2401.00001v1' \
  --work-id 'arxiv:2401.00001v1' --variant preprint
```

`--variant` is one of: `preprint`, `conference`, `journal` (conference/journal sources are not implemented yet; tags are still written for your pipeline).

Each successful run prints one line to **stdout**, for example:

`rawdoc_id=<uuid> doc_id=<uuid> doc_json=.../data/docs/<doc_id>.json doc_md=.../data/docs/<doc_id>.md`

The RawDoc `metadata` in `data/rawdocs/<rawdoc_id>.meta.json` also includes **`doc_id`** after ingest.

## Phase 2 (not implemented)

Planned extensions (see [PLAN.md](PLAN.md)):

- **Conference**: HTML from OpenReview or conference open-access pages (site-specific parsers, rate limits, robots.txt).
- **Journal**: publisher HTML or **PDF** ingest (`meta.source.type: pdf` in the document schema); likely a separate fetch path from HTML.
- **Discovery**: Crossref / OpenAlex (and optionally Semantic Scholar) to list DOI vs arXiv id for the same work; any automation should stay **confirm-by-human** for ambiguous matches.

## Related

- Data directories: by default `data/rawdocs`, `data/docs`, `data/assets` (same as `make raw-ingest`).
- Chinese README: [README.zh-cn.md](README.zh-cn.md).
