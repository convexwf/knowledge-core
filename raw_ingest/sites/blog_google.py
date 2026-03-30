#!/usr/bin/env python3
"""
Google Keyword blog (blog.google/...): article body in div.rich-text (speech / long-form).

Run: cd raw_ingest && python sites/blog_google.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

_RAW_INGEST_ROOT = Path(__file__).resolve().parents[1]
_COMMON = _RAW_INGEST_ROOT / "common"
if str(_COMMON) not in sys.path:
    sys.path.insert(0, str(_COMMON))

import requests
from bs4 import BeautifulSoup

from assets_doc import process_assets
from normalize_doc import normalize
from rawdoc_write import write_rawdoc_html
from repo_paths import REPO_ROOT
from schema_validate import validate_document
from sink_doc import write_document_outputs

DEFAULT_URL = (
    "https://blog.google/company-news/inside-google/message-ceo/"
    "sundar-pichai-ai-impact-summit-2026/"
)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}


def _text(elem) -> str:
    if elem is None:
        return ""
    return (elem.get_text() or "").strip()


def _meta_name(soup: BeautifulSoup, name: str) -> str | None:
    m = soup.find("meta", attrs={"name": name})
    if m and m.get("content"):
        return (m.get("content") or "").strip()
    return None


def _meta_property(soup: BeautifulSoup, prop: str) -> str | None:
    m = soup.find("meta", attrs={"property": prop})
    if m and m.get("content"):
        return (m.get("content") or "").strip()
    return None


def _iso_from_published_string(s: str | None) -> str | None:
    if not s:
        return None
    s = s.strip().replace("Z", "+00:00")
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        dt = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _ld_json_dates_and_author(soup: BeautifulSoup) -> tuple[str | None, str | None, str | None]:
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        if data.get("@type") not in ("NewsArticle", "Article", "BlogPosting"):
            continue
        pub = data.get("datePublished")
        mod = data.get("dateModified")
        author = data.get("author")
        auth_name = None
        if isinstance(author, dict):
            auth_name = author.get("name")
        elif isinstance(author, list) and author:
            a0 = author[0]
            if isinstance(a0, dict):
                auth_name = a0.get("name")
        return (
            str(pub) if pub else None,
            str(mod) if mod else None,
            str(auth_name) if auth_name else None,
        )
    return None, None, None


def _content_with_links(elem, base_url: str | None = None) -> tuple[str, list[dict[str, str]]]:
    if elem is None:
        return "", []
    if not hasattr(elem, "children"):
        return (str(elem).strip(), [])
    links: list[dict[str, str]] = []
    parts: list[str] = []
    for child in elem.children:
        if not getattr(child, "name", None):
            parts.append(str(child).strip())
            continue
        if child.name == "a":
            href = (child.get("href") or "").strip()
            if base_url and href and not href.startswith(("http://", "https://", "#")):
                href = urljoin(base_url, href)
            anchor = (child.get_text() or "").strip()
            if href:
                parts.append(f"[{anchor}]({href})")
                links.append({"href": href, "text": anchor})
            else:
                parts.append(anchor)
            continue
        if child.name == "img":
            src = (child.get("src") or "").strip()
            if base_url and src and not src.startswith(("http://", "https://")):
                src = urljoin(base_url, src)
            alt = (child.get("alt") or "").strip()
            if src:
                parts.append(f"![{alt}]({src})")
            continue
        c, l = _content_with_links(child, base_url)
        if c:
            parts.append(c)
        links.extend(l)
    return (" ".join(parts).strip(), links)


def _list_items_tree(ul_or_ol, base_url: str | None = None) -> list[dict[str, Any] | str]:
    items: list[dict[str, Any] | str] = []
    for li in ul_or_ol.find_all("li", recursive=False):
        text_parts: list[str] = []
        sub_items: list[dict[str, Any] | str] = []
        for child in li.children:
            if getattr(child, "name", None) in ("ul", "ol"):
                sub_items.extend(_list_items_tree(child, base_url))
            else:
                part, _ = _content_with_links(child, base_url)
                if part:
                    text_parts.append(part)
        text = " ".join(text_parts).strip()
        if sub_items:
            items.append({"text": text, "items": sub_items})
        else:
            items.append(text if text else "")
    return items


def _heading_level(tag) -> int:
    name = getattr(tag, "name", None) or ""
    if isinstance(name, str) and len(name) == 2 and name[0] == "h" and name[1].isdigit():
        return min(6, max(1, int(name[1])))
    return 1


def extract_blog_google_article(soup: BeautifulSoup, link_base: str) -> dict[str, Any]:
    meta: dict[str, Any] = {"authors": [], "tags": [], "language": "en"}

    title = (_meta_property(soup, "og:title") or _text(soup.find("title")) or "").strip()
    meta["title"] = title

    ld_pub, ld_mod, ld_author = _ld_json_dates_and_author(soup)
    pub = _iso_from_published_string(_meta_name(soup, "published_time"))
    if not pub:
        pub = _iso_from_published_string(_meta_property(soup, "article:published_time"))
    if not pub and ld_pub:
        pub = _iso_from_published_string(ld_pub)
    if pub:
        meta["published_at"] = pub
    mod = _iso_from_published_string(ld_mod) if ld_mod else None
    if mod:
        meta["updated_at"] = mod

    author = _meta_name(soup, "authors") or _meta_name(soup, "article-author") or ld_author
    if author:
        meta["authors"] = [a.strip() for a in re.split(r"\s*,\s*", author) if a.strip()]

    tags_raw = _meta_name(soup, "tags")
    if tags_raw:
        meta["tags"] = [t.strip() for t in tags_raw.split(",") if t.strip()]

    container = soup.select_one("div.rich-text")
    sections: list[dict[str, Any]] = []
    if not container:
        return {
            "meta": meta,
            "sections": sections,
            "parser_version": "raw_ingest.blog_google/0.1.0",
        }

    block_tags = (
        "h2", "h3", "h4", "h5", "h6",
        "p", "ul", "ol", "pre", "blockquote", "figure", "img",
    )

    for el in container.find_all(block_tags, recursive=True):
        if el.name in ("h2", "h3", "h4", "h5", "h6"):
            ht = _text(el)
            if not ht:
                continue
            sections.append({
                "type": "heading",
                "level": _heading_level(el),
                "content": ht,
                "section_id": el.get("id") or f"heading-{len(sections)}",
            })
            continue

        if el.name == "p":
            if el.find_parent("ul") or el.find_parent("ol"):
                continue
            content, links = _content_with_links(el, link_base)
            if not content:
                continue
            sec: dict[str, Any] = {"type": "paragraph", "content": content}
            if links:
                sec["annotations"] = {"links": links}
            sections.append(sec)
            continue

        if el.name in ("ul", "ol"):
            if el.find_parent("ul") or el.find_parent("ol"):
                continue
            items = _list_items_tree(el, link_base)
            if not items:
                continue
            sections.append({
                "type": "list",
                "section_id": el.get("id") or f"list-{len(sections)}",
                "items": items,
                "content": "",
            })
            continue

        if el.name == "pre":
            code = el.find("code")
            body = _text(code) if code else _text(el)
            if not body:
                continue
            sections.append({"type": "code", "content": body})
            continue

        if el.name == "blockquote":
            content, links = _content_with_links(el, link_base)
            if not content:
                continue
            sec = {"type": "paragraph", "content": content}
            if links:
                sec["annotations"] = {"links": links}
            sections.append(sec)
            continue

        if el.name == "figure":
            img = el.find("img")
            if not img or not (img.get("src") or "").strip():
                continue
            src = img.get("src").strip()
            if link_base and not src.startswith(("http://", "https://")):
                src = urljoin(link_base, src)
            cap = (img.get("alt") or "") or _text(el.find("figcaption"))
            sections.append({
                "type": "figure",
                "content": "",
                "assets": [{"original_src": src, "caption": cap or None}],
            })
            continue

        if el.name == "img":
            if el.find_parent("figure"):
                continue
            if el.find_parent("p"):
                continue
            src = (el.get("src") or "").strip()
            if not src:
                continue
            if link_base and not src.startswith(("http://", "https://")):
                src = urljoin(link_base, src)
            cap = (el.get("alt") or "").strip() or None
            sections.append({
                "type": "figure",
                "content": "",
                "assets": [{"original_src": src, "caption": cap}],
            })

    return {
        "meta": meta,
        "sections": sections,
        "parser_version": "raw_ingest.blog_google/0.1.0",
    }


def run_one(
    fetch_url: str,
    canonical_url: str,
    rawdocs_dir: Path,
    assets_dir: Path,
    docs_dir: Path,
    timeout: int,
    do_validate: bool,
) -> None:
    r = requests.get(fetch_url, headers=DEFAULT_HEADERS, timeout=timeout)
    r.raise_for_status()
    html_bytes = r.content

    rawdoc = write_rawdoc_html(html_bytes, rawdocs_dir, canonical_url)
    rawdoc_id = rawdoc["rawdoc_id"]
    storage_path = rawdoc["storage_path"]

    soup = BeautifulSoup(html_bytes, "lxml")
    parser_output = extract_blog_google_article(soup, link_base=fetch_url)

    doc = normalize(
        parser_output,
        rawdoc_id=rawdoc_id,
        storage_path=storage_path,
        source_uri=canonical_url,
        source_type="html",
    )
    doc = process_assets(doc, assets_dir, base_url=fetch_url)

    if do_validate:
        validate_document(doc, REPO_ROOT)

    json_path, md_path = write_document_outputs(
        doc, docs_dir, rawdocs_dir, rawdoc_id, write_done=True
    )

    print("rawdoc_id:", rawdoc_id)
    print("doc_id:", doc["doc_id"])
    print("title:", doc["meta"]["title"])
    print("sections:", len(doc["sections"]))
    print("wrote:", json_path, md_path)


def _parse_urls_file_line(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if "|" in line:
        fetch, _, rest = line.partition("|")
        fetch, can = fetch.strip(), rest.strip()
        if fetch and can:
            return fetch, can
    fetch = line.strip()
    return fetch, fetch


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest blog.google articles into data/docs")
    ap.add_argument("--fetch-url", default="", help="Article URL to fetch")
    ap.add_argument("--canonical-url", default="", help="source_uri (default: same as fetch URL)")
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

    jobs: list[tuple[str, str]] = []
    if args.urls_file:
        p = Path(args.urls_file)
        if not p.is_file():
            print("urls file not found:", p, file=sys.stderr)
            sys.exit(1)
        for line in p.read_text(encoding="utf-8").splitlines():
            pair = _parse_urls_file_line(line)
            if pair:
                jobs.append(pair)
        if not jobs:
            print("No URLs in file:", p, file=sys.stderr)
            sys.exit(1)
    else:
        fetch = args.fetch_url or DEFAULT_URL
        canonical = args.canonical_url or fetch
        jobs = [(fetch, canonical)]

    failed = 0
    for fetch_url, canonical_url in jobs:
        if len(jobs) > 1:
            print("---", fetch_url, file=sys.stderr)
        try:
            run_one(
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
