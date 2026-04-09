#!/usr/bin/env python3
"""
Route paper fetch URLs to source-specific parsers (Phase 1: arXiv HTML).

Batch file: tab-separated work_id, variant, fetch_url, [canonical_url].
Lines without tabs: a single arXiv URL -> work_id=arxiv:<id>, variant=preprint.

Run from repo: make paper-parse URL='...'  or  make paper-parse-batch FILE=...
  cd raw_paper_parse && python sources/router.py --url 'https://...'
"""
from __future__ import annotations

import argparse
import importlib
import sys
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

_RAW_PAPER_ROOT = Path(__file__).resolve().parents[1]
_RAW_INGEST_COMMON = _RAW_PAPER_ROOT.parent / "raw_ingest" / "common"
if str(_RAW_INGEST_COMMON) not in sys.path:
    sys.path.insert(0, str(_RAW_INGEST_COMMON))

from repo_paths import REPO_ROOT

import arxiv_html

RunOne = Callable[..., None]

_SOURCES_FILE = Path(__file__).with_name("supported_sources.txt")
_REGISTRY: dict[str, RunOne] | None = None

_BATCH_DELAY_SEC = 0.35


def _load_registry() -> dict[str, RunOne]:
    global _REGISTRY
    if _REGISTRY is not None:
        return _REGISTRY
    if not _SOURCES_FILE.is_file():
        raise FileNotFoundError(f"missing {_SOURCES_FILE}")
    reg: dict[str, RunOne] = {}
    for line in _SOURCES_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "\t" not in line:
            continue
        host, mod = line.split("\t", 1)
        host = host.strip().lower()
        mod = mod.strip().removesuffix(".py")
        if not host or not mod:
            continue
        m = importlib.import_module(mod)
        reg[host] = m.run_one
    _REGISTRY = reg
    return _REGISTRY


def resolve_run_one(fetch_url: str) -> RunOne | None:
    reg = _load_registry()
    host = (urlparse(fetch_url).hostname or "").lower()
    return reg.get(host)


def parse_paper_line(line: str) -> tuple[str, str, str, str] | None:
    """
    Return (work_id, variant, fetch_url, canonical_url) or None to skip.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if "\t" in line:
        raw_parts = [p.strip() for p in line.split("\t")]
        while raw_parts and raw_parts[-1] == "":
            raw_parts.pop()
        if len(raw_parts) < 3:
            return None
        work_id, variant, fetch_url = raw_parts[0], raw_parts[1], raw_parts[2]
        canonical = raw_parts[3] if len(raw_parts) > 3 and raw_parts[3] else fetch_url
        if not fetch_url:
            return None
        return work_id, variant, fetch_url, canonical
    # URL-only line
    u = line.strip()
    if u.startswith("http") and "arxiv.org" in u.lower():
        aid = arxiv_html.arxiv_id_from_url(u)
        wid = f"arxiv:{aid}" if aid else ""
        return wid, "preprint", u, arxiv_html.abs_canonical_url(u)
    return None


def main() -> None:
    _load_registry()

    ap = argparse.ArgumentParser(
        description="Route paper URLs to raw_paper_parse sources (arXiv HTML)",
    )
    ap.add_argument("--url", default="", help="Single paper URL to fetch")
    ap.add_argument("--fetch-url", default="", help="Alias for --url")
    ap.add_argument("--canonical-url", default="", help="source_uri when using single URL")
    ap.add_argument("--work-id", default="", help="Logical work id for single URL mode")
    ap.add_argument(
        "--variant",
        default="preprint",
        help="preprint|conference|journal (single URL mode)",
    )
    ap.add_argument("--urls-file", default="", help="Batch: tab lines or arXiv URL per line")
    ap.add_argument("--rawdocs", default=None, help="RawDocs dir (default: <repo>/data/rawdocs)")
    ap.add_argument("--assets", default=None, help="Assets dir (default: <repo>/data/assets)")
    ap.add_argument("--docs", default=None, help="Docs dir (default: <repo>/data/docs)")
    ap.add_argument("--timeout", type=int, default=45, help="HTTP timeout seconds")
    ap.add_argument("--no-validate", action="store_true", help="Skip jsonschema validation")
    args = ap.parse_args()

    rawdocs_dir = Path(args.rawdocs or REPO_ROOT / "data" / "rawdocs")
    assets_dir = Path(args.assets or REPO_ROOT / "data" / "assets")
    docs_dir = Path(args.docs or REPO_ROOT / "data" / "docs")
    do_validate = not args.no_validate

    single = (args.url or args.fetch_url or "").strip()
    if args.urls_file and single:
        print("Use either --urls-file or --url/--fetch-url, not both", file=sys.stderr)
        sys.exit(2)

    jobs: list[tuple[str, str, str, str]] = []
    if args.urls_file:
        p = Path(args.urls_file)
        if not p.is_file():
            print("urls file not found:", p, file=sys.stderr)
            sys.exit(1)
        for line in p.read_text(encoding="utf-8").splitlines():
            parsed = parse_paper_line(line)
            if parsed:
                jobs.append(parsed)
        if not jobs:
            print("No jobs in file:", p, file=sys.stderr)
            sys.exit(1)
    else:
        if not single:
            print(
                "Usage: python sources/router.py --url 'https://arxiv.org/html/...' "
                "or --urls-file path/to/batch.tsv",
                file=sys.stderr,
            )
            sys.exit(2)
        canonical = (
            args.canonical_url.strip()
            if args.canonical_url
            else arxiv_html.abs_canonical_url(single)
        )
        work_id = args.work_id.strip()
        variant = (args.variant.strip() or "preprint")
        jobs = [(work_id, variant, single, canonical)]

    failed = 0
    batch = len(jobs) > 1 or bool(args.urls_file)

    for i, (work_id, variant, fetch_url, canonical_url) in enumerate(jobs):
        if batch:
            print("---", fetch_url, file=sys.stderr)
        if i > 0 and batch:
            time.sleep(_BATCH_DELAY_SEC)
        runner = resolve_run_one(fetch_url)
        if runner is None:
            if batch:
                print("UNSUPPORTED:", fetch_url, file=sys.stderr)
            else:
                print("unsupported host:", fetch_url, file=sys.stderr)
                sys.exit(1)
            continue
        try:
            runner(
                fetch_url,
                canonical_url,
                rawdocs_dir,
                assets_dir,
                docs_dir,
                args.timeout,
                do_validate,
                work_id=work_id,
                variant=variant,
            )
        except Exception as e:
            print("error:", e, file=sys.stderr)
            failed += 1

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
