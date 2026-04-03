# raw_ingest

Python pipeline that **fetches HTML**, writes **RawDocs** under `data/rawdocs/`, normalizes into the shared **document schema**, processes **assets**, and writes **JSON + Markdown** under `data/docs/` (and `data/assets/`).

The repo root **Makefile** exposes `raw-ingest`, `raw-ingest-batch`, and `raw-ingest-list`; the article entrypoint is `sites/router.py`, which dispatches by **fetch URL hostname** (and a special case for the Internet Archive). Post **lists** (RSS/hub pages) are handled separately under `list/`.

---

## Quick start

From the **repository root**:

```bash
make raw-ingest-deps
make raw-ingest URL='https://example.com/article'
```

Batch (one URL per line; lines starting with `#` are comments):

```bash
make raw-ingest-batch FILE=raw_ingest/examples/example_urls.txt
```

Or from `raw_ingest/`:

```bash
cd raw_ingest && python sites/router.py --url 'https://...'
cd raw_ingest && python sites/router.py --urls-file /path/to/urls.txt
```

Optional **`CANONICAL=`** (with `make raw-ingest`) or **`fetch|canonical`** in a URL file: HTML is fetched from the first URL, but `source_uri` / metadata use the canonical URL (used for Freedium, Wayback + real blog URL, etc.).

### Post lists (RSS / hub snapshots)

From the **repository root**, after `make raw-ingest-deps`:

```bash
make raw-ingest-list
# or: make raw-ingest-list FILE=path/to/site_list.url
```

This reads **`examples/site_list.url`**: one row per site, tab-separated **`site_id<TAB>list_url`** (`#` starts a comment). `site_id` matches a `sites/<module>.py` name (e.g. `engineering_fb`). Most sites use an RSS/Atom URL; **`blog_x_com`** uses an HTML engineering hub URL (often a **Wayback** URL if the live site returns a Cloudflare challenge). **`blog.google`** list traffic should use **`https://blog.google/rss/`** (the `/feed/` path is a JS shell, not a feed).

Each run writes **`data/post_lists/<site_id>_<UTC>.json`** with `posts` (`title`, `url`, `published`, `summary`), `parser` (`rss` or `html`), and optional `error` if the fetch/list step failed.

---

## Architecture

| Piece | Role |
|--------|------|
| `sites/router.py` | Parses fetch URL → loads `run_one` from registry |
| `sites/supported_sites.txt` | Tab-separated: `hostname` → `module` (no `.py`), one row per host alias |
| `sites/<module>.py` | Implements `run_one(fetch_url, canonical_url, rawdocs_dir, assets_dir, docs_dir, timeout, do_validate)` |
| `list/fetch_post_lists.py` | CLI: read `site_list.url`, fetch lists, write `data/post_lists/*.json` |
| `list/feed_parse.py` | RSS/Atom via `feedparser` → normalized `posts` |
| `list/blog_x_list.py` | Engineering hub HTML → article links (reuses Cloudflare detection from `blog_x_com`) |
| `common/` | Shared helpers: `rawdoc_write`, `normalize_doc`, `assets_doc`, `sink_doc`, `schema_validate`, `repo_paths` |

When you run `python sites/router.py`, Python puts the **script directory** (`raw_ingest/sites/`) on `sys.path`, so registry modules are imported as top-level names (e.g. `blog_google`).

### Internet Archive (`web.archive.org`)

If the fetch URL is `https://web.archive.org/web/<timestamp>/https://original-host/...`, the router **extracts the inner original URL** and resolves the parser from **that** host. So a batch line can use Wayback as fetch while keeping the real article URL as canonical:

```text
https://web.archive.org/web/20240304231722/https://blog.x.com/...|https://blog.x.com/...
```

---

## Supported sites (registry)

Hosts are listed in `sites/supported_sites.txt`. As of the last doc update, modules include (non-exhaustive; see the file for truth):

| Module | Typical hosts |
|--------|----------------|
| `medium_freedium` | `freedium-mirror.cfd` |
| `engineering_fb` | `engineering.fb.com` |
| `meituan_tech` | `tech.meituan.com` |
| `vickiboykis` | `vickiboykis.com`, `www.vickiboykis.com` |
| `allthings_distributed` | `www.allthingsdistributed.com`, … |
| `brendan_gregg_blog` | `www.brendangregg.com`, … |
| `blog_google` | `blog.google` |
| `smashing_magazine` | `www.smashingmagazine.com`, `smashingmagazine.com` |
| `blog_x_com` | `blog.x.com`, `blog.twitter.com` |

Unsupported hosts in a batch file log **`UNSUPPORTED`** on stderr and are skipped (exit 0 unless a supported URL fails).

---

## Handoff: work done in prior chats (context for new sessions)

This section summarizes **decisions and additions** from earlier conversations so a new chat does not need the full thread.

1. **Smashing Magazine** (`smashing_magazine.py`): Article body lives in `article div.c-garfield-the-cat`. Parser walks structural nodes, skips ads/sidebars/feature panels (class-based), handles summary block and standard blocks (`p`, headings, lists, `pre`, `blockquote`, `figure`, `img`, `center`). Dates in meta like `article:published_time` may include `+0000 UTC` — normalized to ISO/Z.

2. **X / Twitter engineering blog** (`blog_x_com.py`): Live `blog.x.com` often returns **Cloudflare challenge** or **403** to plain `requests`. Parser targets the historical DOM (`div.column.column-6`, `bl13-rich-text-editor`, `bl14-image`, author card data attributes, `data-src` on images). **Recommended:** fetch from **Wayback** with **`fetch|canonical`** so `source_uri` stays the official URL; router resolves `web.archive.org` to `blog_x_com` via the embedded inner URL.

3. **example_urls.txt**: Maintained as **roughly one sample URL per supported parser**. Direct `blog.x.com` links may fail in batch; comment in the file points to Wayback + canonical if needed.

4. **Meta engineering** (`engineering_fb.py`): WordPress — `main article.hentry` + `div.entry-content`. Skips Jetpack/share blocks; turns YouTube `iframe`s into link paragraphs. Authors from `.entry-authors`; dates from meta or Yoast `@graph` Article node.

5. **Vicki Boykis** (`vickiboykis.py`): Hugo Bear Blog — body in `<main><content>` (custom element). Default author name **Vicki Boykis**; tags from `/tags/` links under `main`.

6. **Adding a new site (repeatable checklist)**  
   - Add `sites/<name>.py` with `run_one(...)` matching existing modules (see `brendan_gregg_blog.py` or `blog_google.py` for the block-walking pattern).  
   - Append **tab-separated** rows to `sites/supported_sites.txt` for every hostname users will paste (including `www.` if applicable).  
   - No router code change unless you need special URL schemes (Wayback is already handled).  
   - Optionally add one line to `examples/example_urls.txt`.  
   - Run `make raw-ingest URL='...'` and fix schema validation if `validate_document` fails.

---

## Related Makefile targets

- `raw-ingest` / `raw-ingest-batch` — unified article router (above).  
- `raw-ingest-list` — post list snapshots from `examples/site_list.url` (or `FILE=...`).  
- `raw-ingest-freedium` / `raw-ingest-meituan-tech` — call site scripts directly (legacy convenience).

---

## Chinese version

See [README.zh-cn.md](README.zh-cn.md) for the same content in Chinese.
