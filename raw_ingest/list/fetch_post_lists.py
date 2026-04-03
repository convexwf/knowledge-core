#!/usr/bin/env python3
"""
Fetch latest post lists per site from raw_ingest/examples/site_list.url (or custom file).

Each line: site_id<TAB>list_url  (# comments allowed). blog_x_com uses HTML hub parsing;
other site_ids use RSS/Atom via feedparser.

Output: <repo>/data/post_lists/<site_id>_<UTC>.json

Run from repo: make raw-ingest-list
  cd raw_ingest && python list/fetch_post_lists.py --urls-file examples/site_list.url
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_LIST_DIR = Path(__file__).resolve().parent
_RAW_INGEST_ROOT = _LIST_DIR.parent
_COMMON = _RAW_INGEST_ROOT / "common"
if str(_COMMON) not in sys.path:
    sys.path.insert(0, str(_COMMON))
if str(_LIST_DIR) not in sys.path:
    sys.path.insert(0, str(_LIST_DIR))

from repo_paths import REPO_ROOT

import blog_x_list
import feed_parse

import blog_x_com


def _parse_site_list_line(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if "\t" not in line:
        return None
    site_id, url = line.split("\t", 1)
    site_id = site_id.strip()
    url = url.strip()
    if not site_id or not url:
        return None
    return site_id, url


def _html_headers() -> dict[str, str]:
    return dict(blog_x_com.DEFAULT_HEADERS)


def _rss_headers() -> dict[str, str]:
    """Prefer XML feeds; blog.google and others may return HTML if Accept is text/html only."""
    h = dict(blog_x_com.DEFAULT_HEADERS)
    h["Accept"] = (
        "application/rss+xml,application/atom+xml,application/xml;q=0.9,"
        "text/xml;q=0.9,*/*;q=0.8"
    )
    return h


def _fetch_posts_for_site(
    site_id: str,
    list_url: str,
    timeout: int,
) -> tuple[list[dict[str, str | None]], str | None, str]:
    """Returns (posts, error, parser_kind)."""
    if site_id == "blog_x_com":
        posts, err = blog_x_list.fetch_hub_posts(list_url, timeout, _html_headers())
        return posts, err, "html"
    posts, err = feed_parse.fetch_feed_posts(list_url, timeout, _rss_headers())
    return posts, err, "rss"


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch post list JSON per site from site_list.url")
    ap.add_argument(
        "--urls-file",
        default="",
        help="Tab-separated: site_id<TAB>list_url (default: examples/site_list.url under raw_ingest)",
    )
    ap.add_argument(
        "--output-dir",
        default="",
        help="Output directory (default: <repo>/data/post_lists)",
    )
    ap.add_argument("--timeout", type=int, default=45, help="HTTP timeout seconds")
    args = ap.parse_args()

    urls_file = Path(args.urls_file or _RAW_INGEST_ROOT / "examples" / "site_list.url")
    if not urls_file.is_file():
        print("urls file not found:", urls_file, file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.output_dir or REPO_ROOT / "data" / "post_lists")
    out_dir.mkdir(parents=True, exist_ok=True)

    jobs: list[tuple[str, str]] = []
    for line in urls_file.read_text(encoding="utf-8").splitlines():
        pair = _parse_site_list_line(line)
        if pair:
            jobs.append(pair)

    if not jobs:
        print("No site rows in file:", urls_file, file=sys.stderr)
        sys.exit(1)

    failed = 0
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")

    for site_id, list_url in jobs:
        print("---", site_id, list_url, file=sys.stderr)
        posts, err, parser_kind = _fetch_posts_for_site(site_id, list_url, args.timeout)
        fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        payload: dict[str, object] = {
            "site_id": site_id,
            "list_source_url": list_url,
            "fetched_at": fetched_at,
            "parser": parser_kind,
            "posts": posts,
        }
        if err:
            payload["error"] = err
            failed += 1

        out_path = out_dir / f"{site_id}_{stamp}.json"
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print("wrote", out_path, file=sys.stderr)

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
