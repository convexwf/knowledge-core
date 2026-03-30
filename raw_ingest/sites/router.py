#!/usr/bin/env python3
"""
Route raw_ingest fetch URLs to site-specific run_one implementations.

Supported hosts are listed in supported_sites.txt (hostname -> module under sites/), e.g. blog.google, brendangregg.com, tech.meituan.com.

Batch: unsupported hosts print UNSUPPORTED to stderr and skip (exit 0 unless a run fails).
Single URL: unsupported host -> exit 1.

Run from repo: make raw-ingest URL='...'  or  make raw-ingest-batch FILE=...
  cd raw_ingest && python sites/router.py --url '...'
"""
from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

_RAW_INGEST_ROOT = Path(__file__).resolve().parents[1]
_COMMON = _RAW_INGEST_ROOT / "common"
if str(_COMMON) not in sys.path:
    sys.path.insert(0, str(_COMMON))

from repo_paths import REPO_ROOT

import medium_freedium

RunOne = Callable[
    [str, str, Path, Path, Path, int, bool],
    None,
]

_SITES_FILE = Path(__file__).with_name("supported_sites.txt")
_REGISTRY: dict[str, RunOne] | None = None


def _load_registry() -> dict[str, RunOne]:
    global _REGISTRY
    if _REGISTRY is not None:
        return _REGISTRY
    if not _SITES_FILE.is_file():
        raise FileNotFoundError(f"missing {_SITES_FILE}")
    reg: dict[str, RunOne] = {}
    for line in _SITES_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "\t" not in line:
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
    host = (urlparse(fetch_url).hostname or "").lower()
    return _load_registry().get(host)


def parse_urls_file_line(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if "|" in line:
        fetch, _, rest = line.partition("|")
        fetch, can = fetch.strip(), rest.strip()
        if fetch and can:
            return fetch, can
    fetch = line.strip()
    return fetch, medium_freedium.canonical_url_from_freedium_fetch(fetch)


def main() -> None:
    _load_registry()

    ap = argparse.ArgumentParser(
        description="Route article URLs to site-specific raw_ingest parsers",
    )
    ap.add_argument("--url", default="", help="Single article URL to fetch")
    ap.add_argument("--fetch-url", default="", help="Alias for --url")
    ap.add_argument("--canonical-url", default="", help="source_uri when using single URL")
    ap.add_argument("--urls-file", default="", help="Batch: one URL per line; optional fetch|canonical")
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

    jobs: list[tuple[str, str]] = []
    if args.urls_file:
        p = Path(args.urls_file)
        if not p.is_file():
            print("urls file not found:", p, file=sys.stderr)
            sys.exit(1)
        for line in p.read_text(encoding="utf-8").splitlines():
            pair = parse_urls_file_line(line)
            if pair:
                jobs.append(pair)
        if not jobs:
            print("No URLs in file:", p, file=sys.stderr)
            sys.exit(1)
    else:
        if not single:
            print(
                "Usage: python sites/router.py --url 'https://...' "
                "or --urls-file path/to/urls.txt",
                file=sys.stderr,
            )
            sys.exit(2)
        canonical = (
            args.canonical_url.strip()
            if args.canonical_url
            else medium_freedium.canonical_url_from_freedium_fetch(single)
        )
        jobs = [(single, canonical)]

    failed = 0
    batch = len(jobs) > 1 or bool(args.urls_file)

    for fetch_url, canonical_url in jobs:
        if batch:
            print("---", fetch_url, file=sys.stderr)
        runner = resolve_run_one(fetch_url)
        if runner is None:
            if batch:
                print("UNSUPPORTED:", fetch_url, file=sys.stderr)
            else:
                print("unsupported site:", fetch_url, file=sys.stderr)
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
            )
        except Exception as e:
            print("error:", e, file=sys.stderr)
            failed += 1

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
