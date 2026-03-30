#!/usr/bin/env python3
"""
Meta engineering blog (engineering.fb.com/...): WordPress single post, body in div.entry-content.

Run: cd raw_ingest && python sites/engineering_fb.py
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
    "https://engineering.fb.com/2025/10/17/ai-research/"
    "scaling-llm-inference-innovations-tensor-parallelism-context-parallelism-expert-parallelism/"
)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

_SKIP_ZONE_SUBSTR = (
    "sharedaddy",
    "sd-sharing",
    "sd-block",
    "robots-nocontent",
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


def _yoast_article_dates(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    for script in soup.find_all("script", type="application/ld+json"):
        raw = (script.string or script.get_text() or "").strip()
        if not raw or "@graph" not in raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        graph = data.get("@graph") if isinstance(data, dict) else None
        if not isinstance(graph, list):
            continue
        for node in graph:
            if not isinstance(node, dict):
                continue
            if node.get("@type") == "Article":
                pub = node.get("datePublished")
                mod = node.get("dateModified")
                return (
                    str(pub) if pub else None,
                    str(mod) if mod else None,
                )
    return None, None


def _in_skip_zone(elem, root) -> bool:
    p = elem.parent
    while p is not None and p is not root:
        blob = _classes_blob(p)
        for sub in _SKIP_ZONE_SUBSTR:
            if sub in blob:
                return True
        p = p.parent
    return False


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


def extract_engineering_fb_article(soup: BeautifulSoup, link_base: str) -> dict[str, Any]:
    meta: dict[str, Any] = {"authors": [], "tags": [], "language": "en"}

    article = soup.select_one("main#main article.hentry") or soup.select_one("main article.type-post")
    if not article:
        article = soup.select_one("article.post")

    if article:
        t_el = article.select_one(".entry-title")
        if t_el:
            meta["title"] = _text(t_el)
        for a in article.select(".entry-authors a.author"):
            n = _text(a)
            if n:
                meta["authors"].append(n)
        for a in article.select(".cat-links a[rel='category tag'], .cat-links a"):
            n = _text(a)
            if n:
                meta["tags"].append(n)

    if not meta.get("title"):
        og = _meta_property(soup, "og:title")
        meta["title"] = (og or _text(soup.find("title")) or "").strip()

    pub = _iso_from_published_string(_meta_property(soup, "article:published_time"))
    mod = _iso_from_published_string(_meta_property(soup, "article:modified_time"))
    if not pub:
        y_pub, y_mod = _yoast_article_dates(soup)
        pub = _iso_from_published_string(y_pub)
        if not mod:
            mod = _iso_from_published_string(y_mod)
    if pub:
        meta["published_at"] = pub
    if mod:
        meta["updated_at"] = mod
    elif pub:
        meta["updated_at"] = pub

    if not meta["authors"]:
        tw = soup.find("meta", attrs={"name": "twitter:data1"})
        if tw and tw.get("content"):
            meta["authors"] = [x.strip() for x in tw["content"].split(",") if x.strip()]

    container = None
    if article:
        container = article.select_one("div.entry-content")
    sections: list[dict[str, Any]] = []
    if not container:
        return {
            "meta": meta,
            "sections": sections,
            "parser_version": "raw_ingest.engineering_fb/0.1.0",
        }

    block_tags = (
        "h2", "h3", "h4", "h5", "h6",
        "p", "ul", "ol", "pre", "blockquote", "figure", "img",
    )

    for el in container.find_all(block_tags, recursive=True):
        if _in_skip_zone(el, container):
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

    for iframe in container.find_all("iframe", recursive=True):
        if _in_skip_zone(iframe, container):
            continue
        src = (iframe.get("src") or "").strip()
        if not src:
            continue
        if link_base and not src.startswith(("http://", "https://")):
            src = urljoin(link_base, src)
        sections.append({
            "type": "paragraph",
            "content": f"[Embedded video]({src})",
            "annotations": {"links": [{"href": src, "text": "Embedded video"}]},
        })

    return {
        "meta": meta,
        "sections": sections,
        "parser_version": "raw_ingest.engineering_fb/0.1.0",
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
    parser_output = extract_engineering_fb_article(soup, link_base=fetch_url)

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
    ap = argparse.ArgumentParser(description="Ingest engineering.fb.com posts into data/docs")
    ap.add_argument("--fetch-url", default="", help="Post URL to fetch")
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
