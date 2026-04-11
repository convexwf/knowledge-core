#!/usr/bin/env python3
"""
Route Calibre directory paths (or .epub files) to raw_epub_parse source parsers.

Single directory:
    python sources/router.py --dir "tmp/苏菲的世界 (371)"

Single .epub file:
    python sources/router.py --file "/path/to/book.epub"

Batch:
    python sources/router.py --urls-file path/to/batch.tsv

Run from repo root:
    make epub-parse DIR="tmp/苏菲的世界 (371)"
    make epub-parse FILE="/path/to/book.epub"
"""
from __future__ import annotations

import argparse
import importlib
import sys
import time
from collections.abc import Callable
from pathlib import Path

_SOURCES_DIR = Path(__file__).resolve().parents[0]
_EPUB_PARSE_ROOT = _SOURCES_DIR.parent
if str(_EPUB_PARSE_ROOT) not in sys.path:
    sys.path.insert(0, str(_EPUB_PARSE_ROOT))

import epub_file

from common.paths import REPO_ROOT

RunOne = Callable[..., None]

_SOURCES_FILE = Path(__file__).with_name("supported_sources.txt")
_REGISTRY: dict[str, RunOne] | None = None
_BATCH_DELAY_SEC = 0.0


def _load_registry() -> dict[str, RunOne]:
    global _REGISTRY
    if _REGISTRY is not None:
        return _REGISTRY

    _REGISTRY = {
        "*.epub": epub_file.run_one,
        "dir": epub_file.run_one,
    }

    if _SOURCES_FILE.is_file():
        for line in _SOURCES_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "\t" not in line:
                continue
            pattern, mod = line.split("\t", 1)
            pattern = pattern.strip().lower()
            mod = mod.strip().removesuffix(".py")
            if not pattern or not mod:
                continue
            m = importlib.import_module(mod)
            _REGISTRY[pattern] = m.run_one

    return _REGISTRY


def resolve_run_one(input_path: str) -> RunOne | None:
    reg = _load_registry()
    p = Path(input_path)
    if p.is_dir():
        return reg.get("dir")
    if input_path.lower().endswith(".epub"):
        return reg.get("*.epub")
    return None


def main() -> None:
    _load_registry()

    ap = argparse.ArgumentParser(
        description="Parse Calibre EPUB directories into Document schema",
    )
    ap.add_argument("--dir", default="", help="Calibre book directory path")
    ap.add_argument("--file", default="", help="Single .epub file (legacy compat)")
    ap.add_argument("--canonical-url", default="", help="source_uri override")
    ap.add_argument("--work-id", default="", help="Logical work id")
    ap.add_argument("--variant", default="book", help="book|article|...")
    ap.add_argument("--urls-file", default="", help="Batch: one path per line (tab-separated)")
    ap.add_argument("--rawdocs", default=None, help="RawDocs dir")
    ap.add_argument("--assets", default=None, help="Assets dir")
    ap.add_argument("--docs", default=None, help="Docs dir")
    ap.add_argument("--timeout", type=int, default=60, help="Reserved")
    ap.add_argument("--no-validate", action="store_true", help="Skip schema validation")
    args = ap.parse_args()

    rawdocs_dir = Path(args.rawdocs or REPO_ROOT / "data" / "rawdocs")
    assets_dir = Path(args.assets or REPO_ROOT / "data" / "assets")
    docs_dir = Path(args.docs or REPO_ROOT / "data" / "docs")
    do_validate = not args.no_validate

    single: str = (args.dir or args.file or "").strip()

    if args.urls_file and single:
        print("Use either --urls-file or --dir/--file, not both", file=sys.stderr)
        sys.exit(2)

    jobs: list[tuple[str, str, str, str]] = []

    if args.urls_file:
        p = Path(args.urls_file)
        if not p.is_file():
            print(f"URLs file not found: {p}", file=sys.stderr)
            sys.exit(1)
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [x for x in line.split("\t")]
            parts = [x.strip() for x in parts]
            if len(parts) >= 3:
                wid, var, epath = parts[0], parts[1], parts[2]
                canonical = parts[3] if len(parts) > 3 else f"file://{Path(epath).resolve()}"
            else:
                epath = parts[0]
                wid = ""
                var = "book"
                canonical = f"file://{Path(epath).resolve()}"
            jobs.append((wid, var, epath, canonical))
        if not jobs:
            print(f"No valid jobs in file: {p}", file=sys.stderr)
            sys.exit(1)
    else:
        if not single:
            print(
                "Usage: python sources/router.py --dir '/path/to/Calibre Dir (id)'\n"
                "   or: python sources/router.py --file /path/to/book.epub\n"
                "   or: python sources/router.py --urls-file path/to/batch.tsv",
                file=sys.stderr,
            )
            sys.exit(2)
        canonical = args.canonical_url.strip() or f"file://{Path(single).resolve()}"
        work_id = args.work_id.strip()
        variant = args.variant.strip() or "book"
        jobs = [(work_id, variant, single, canonical)]

    failed = 0
    batch = len(jobs) > 1

    for i, (work_id, variant, input_path, canonical) in enumerate(jobs):
        if batch:
            print(f"--- {input_path}", file=sys.stderr)
        if i > 0:
            time.sleep(_BATCH_DELAY_SEC)

        p = Path(input_path)
        if not (p.is_dir() or p.is_file()):
            print(f"MISSING: {input_path}", file=sys.stderr)
            failed += 1
            continue

        runner = resolve_run_one(input_path)
        if runner is None:
            print(f"UNSUPPORTED: {input_path}", file=sys.stderr)
            failed += 1
            continue

        if not work_id:
            work_id = p.name if p.is_dir() else p.stem

        try:
            runner(
                input_path,
                canonical,
                rawdocs_dir,
                assets_dir,
                docs_dir,
                args.timeout,
                do_validate,
                work_id=work_id,
                variant=variant,
            )
        except Exception as e:
            import traceback
            traceback.print_exc(file=sys.stderr)
            print(f"error: {e}", file=sys.stderr)
            failed += 1

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
