#!/usr/bin/env python3
"""
X / Twitter engineering blog (blog.x.com/engineering/...).

Live HTML is often behind a Cloudflare browser challenge; plain ``requests`` then returns
a challenge page instead of the article. Use a saved HTML file, a fetch path that passes the
challenge, or an Internet Archive URL as ``fetch`` with the real article URL as ``canonical``:

  make raw-ingest URL='https://web.archive.org/web/20240304231722/https://blog.x.com/...' \\
    CANONICAL='https://blog.x.com/...'

Run: cd raw_ingest && python sites/blog_x_com.py
"""
from __future__ import annotations

import argparse
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
    "https://blog.x.com/engineering/en_us/topics/infrastructure/2023/"
    "how-we-scaled-reads-on-the-twitter-users-database"
)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

_CF_MARKERS = (
    b"Just a moment",
    b"__cf_chl_opt",
    b"cf-browser-verification",
    b"challenge-platform",
)

# Ancestor class substrings — skip masthead, embeds, related, footer blocks inside the main column.
_BLOGX_SKIP_SUBSTR = (
    "bl02-blog-post-text-masthead",
    "bl13-tweet-template",
    "bl07-author-card",
    "bl10-post-tags-share",
    "bl09-related",
    "bl09-related-posts",
    "bl18__horizontal-rule",
)


def _text(elem) -> str:
    if elem is None:
        return ""
    return (elem.get_text() or "").strip()


def _classes_blob(tag) -> str:
    c = tag.get("class")
    if not c:
        return ""
    if isinstance(c, str):
        return c
    return " ".join(c)


def _is_cloudflare_challenge(html_bytes: bytes) -> bool:
    if b"<title>" in html_bytes[:8000] and b"Just a moment" in html_bytes[:12000]:
        return True
    return any(m in html_bytes for m in _CF_MARKERS)


def _ensure_not_cloudflare_challenge(html_bytes: bytes) -> None:
    if _is_cloudflare_challenge(html_bytes):
        raise RuntimeError(
            "blog.x.com returned a Cloudflare challenge page, not article HTML. "
            "Fetch with a browser or use an Internet Archive URL as fetch with the real URL "
            "as canonical (see module docstring)."
        )


def _blogx_in_skip_zone(elem, root) -> bool:
    p = elem.parent
    while p is not None and p is not root:
        blob = _classes_blob(p)
        for sub in _BLOGX_SKIP_SUBSTR:
            if sub in blob:
                return True
        p = p.parent
    return False


def _img_effective_src(img, link_base: str) -> str:
    src = (img.get("src") or img.get("data-src") or "").strip()
    if not src:
        return ""
    if link_base and not src.startswith(("http://", "https://", "data:")):
        src = urljoin(link_base, src)
    return src


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
            src = _img_effective_src(child, base_url or "")
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


def _parse_masthead_date(s: str) -> str | None:
    s = s.strip()
    for fmt in ("%A, %d %B %Y", "%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            return dt.isoformat().replace("+00:00", "Z")
        except ValueError:
            continue
    return None


def extract_blog_x_engineering_post(soup: BeautifulSoup, link_base: str) -> dict[str, Any]:
    meta: dict[str, Any] = {"authors": [], "tags": [], "language": "en"}

    h1 = soup.select_one("h1.b02-blog-post-no-masthead__title") or soup.select_one(
        "h1.b02-blog-post-masthead__title"
    )
    if h1 and _text(h1):
        meta["title"] = _text(h1)
    if not meta.get("title"):
        og = soup.find("meta", attrs={"property": "og:title"})
        meta["title"] = ((og.get("content") if og else "") or _text(soup.find("title"))).strip()

    date_el = soup.select_one(".b02-blog-post-no-masthead__date") or soup.select_one(
        ".b02-blog-post-masthead__date"
    )
    if date_el:
        parsed = _parse_masthead_date(_text(date_el))
        if parsed:
            meta["published_at"] = parsed
            meta["updated_at"] = parsed

    card = soup.select_one(".bl07-author-card[data-primary-author-fullname]")
    if card:
        a1 = (card.get("data-primary-author-fullname") or "").strip()
        a2 = (card.get("data-secondary-author-fullname") or "").strip()
        meta["authors"] = [x for x in (a1, a2) if x]

    topic = soup.select_one(".b02-blog-post-no-masthead__topic") or soup.select_one(
        ".b02-blog-post-masthead__topic"
    )
    if topic and _text(topic):
        meta["tags"] = [_text(topic)]

    main_col = soup.select_one("div.left-rail-container div.column.column-6") or soup.select_one(
        "#component-wrapper div.column.column-6"
    )
    sections: list[dict[str, Any]] = []
    if not main_col:
        return {
            "meta": meta,
            "sections": sections,
            "parser_version": "raw_ingest.blog_x_com/0.1.0",
        }

    block_tags = (
        "h2", "h3", "h4", "h5", "h6",
        "p", "ul", "ol", "pre", "blockquote", "figure", "img",
    )

    for el in main_col.find_all(block_tags, recursive=True):
        if _blogx_in_skip_zone(el, main_col):
            continue

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
            if not img:
                continue
            src = _img_effective_src(img, link_base)
            if not src:
                continue
            cap_el = el.select_one(".image__caption") or el.find("figcaption")
            cap = _text(cap_el) if cap_el else ((img.get("alt") or "").strip() or None)
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
            src = _img_effective_src(el, link_base)
            if not src:
                continue
            cap = None
            parent = el.parent
            while parent is not None and parent is not main_col:
                ce = parent.select_one(".image__caption")
                if ce:
                    cap = _text(ce) or None
                    break
                parent = parent.parent
            sections.append({
                "type": "figure",
                "content": "",
                "assets": [{"original_src": src, "caption": cap}],
            })

    return {
        "meta": meta,
        "sections": sections,
        "parser_version": "raw_ingest.blog_x_com/0.1.0",
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
    _ensure_not_cloudflare_challenge(html_bytes)

    rawdoc = write_rawdoc_html(html_bytes, rawdocs_dir, canonical_url)
    rawdoc_id = rawdoc["rawdoc_id"]
    storage_path = rawdoc["storage_path"]

    soup = BeautifulSoup(html_bytes, "lxml")
    parser_output = extract_blog_x_engineering_post(soup, link_base=fetch_url)

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
    ap = argparse.ArgumentParser(description="Ingest blog.x.com engineering posts into data/docs")
    ap.add_argument("--fetch-url", default="", help="URL to fetch (may be Wayback)")
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
