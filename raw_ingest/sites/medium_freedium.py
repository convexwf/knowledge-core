#!/usr/bin/env python3
"""
Freedium mirror of a Medium article: fetch, imperative HTML extract, normalize, assets, sink.
Site-specific entry under raw_ingest/sites/ — does not import repo ingest/.

rawdoc_id vs doc_id:
  rawdoc_id identifies the stored RawDoc (HTML + .meta.json under data/rawdocs/).
  doc_id identifies the normalized Document (JSON/MD under data/docs/). One fetch produces
  one RawDoc and one Document; IDs differ because they are separate entities in the pipeline.

Run from raw_ingest (conda py312):
  cd raw_ingest && pip install -r requirements.txt && python sites/medium_freedium.py
  python sites/medium_freedium.py --urls-file /path/to/urls.txt
"""
from __future__ import annotations

import argparse
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

FETCH_URL = (
    "https://freedium-mirror.cfd/https://medium.com/language-lab/"
    "how-many-words-do-you-need-to-learn-a-language-8a6f5e5b1646"
)
CANONICAL_URL = (
    "https://medium.com/language-lab/how-many-words-do-you-need-to-learn-a-language-8a6f5e5b1646"
)


def canonical_url_from_freedium_fetch(fetch_url: str) -> str:
    """
    Map https://freedium-mirror.cfd/https://medium.com/... -> https://medium.com/...
    If not a freedium wrapper URL, return stripped input unchanged.
    """
    u = fetch_url.strip()
    m = re.match(r"^https://freedium-mirror\.cfd/(https?://.+)$", u, re.I)
    if m:
        return m.group(1)
    return u


def _parse_freedium_published_updated(main) -> tuple[str | None, str | None]:
    """
    Freedium author card line like: December 8, 2025 (Updated: December 8, 2025)
    """
    card = main.select_one("div.m-2.mt-5.bg-gray-100")
    if not card:
        return None, None
    for span in card.select("span.text-gray-500"):
        t = _text(span)
        if not t or "min read" in t or t.startswith("Free:"):
            continue
        if re.search(r"\d{4}", t) and ("Updated:" in t or re.match(r"^[A-Za-z]", t)):
            m = re.match(r"^(.+?)\s+\(Updated:\s*(.+)\)\s*$", t)
            if m:
                pub_s, upd_s = m.group(1).strip(), m.group(2).strip()
                return _date_str_to_iso(pub_s), _date_str_to_iso(upd_s)
            return _date_str_to_iso(t), None
    return None, None


def _date_str_to_iso(s: str) -> str | None:
    s = s.strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            return dt.isoformat().replace("+00:00", "Z")
        except ValueError:
            continue
    return None


def _extract_author_from_card(main) -> list[str]:
    """Primary author: Freedium card link with font-semibold (not Follow)."""
    card = main.select_one("div.m-2.mt-5.bg-gray-100")
    if not card:
        return []
    for a in card.select("div.flex-grow > a[href*='/@']"):
        name = _text(a)
        if not name or name == "Follow":
            continue
        cls = " ".join(a.get("class") or [])
        if "font-semibold" in cls:
            return [name]
    a = card.select_one("a[href*='/@']")
    if a:
        name = _text(a)
        if name and name != "Follow":
            return [name]
    return []


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


def _skip_banner_paragraph(p) -> bool:
    t = _text(p)
    if not t:
        return True
    if "Go to the original" in t:
        return True
    cls = " ".join(p.get("class") or [])
    if "text-green-500" in cls and "font-bold" in cls and "pb-3" in cls:
        return True
    return False


def _skip_img(img) -> bool:
    cls = " ".join(img.get("class") or [])
    if "rounded-full" in cls:
        return True
    if "w-4" in cls and "h-4" in cls:
        return True
    if "h-11" in cls and "w-11" in cls:
        return True
    return False


def _is_reporting_footer(el) -> bool:
    if el.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
        t = _text(el)
        if t.startswith("Reporting a Problem"):
            return True
    return False


def _georgia_article_root(soup: BeautifulSoup):
    """Freedium wraps title + author card + div.main-content inside a Georgia-styled div."""
    for div in soup.select("div.container div"):
        style = div.get("style") or ""
        if "Georgia" in style:
            return div
    return soup.select_one("div.container") or soup.find("body")


def _inside_author_card(el) -> bool:
    p = el.find_parent("div")
    while p is not None:
        cls = p.get("class") or []
        cls_s = " ".join(cls) if isinstance(cls, list) else str(cls)
        if "bg-gray-100" in cls_s and "border-gray-300" in cls_s:
            return True
        p = p.find_parent("div")
    return False


def _caption_for_freedium_img(img) -> str | None:
    """Freedium often uses <div><img></div><figcaption> instead of <figure>."""
    par = img.parent
    if par is not None and par.name == "div":
        sib = par.find_next_sibling()
        if sib is not None and sib.name == "figcaption":
            t = _text(sib)
            if t:
                return t
    alt = (img.get("alt") or "").strip()
    return alt or None


def extract_freedium_article(soup: BeautifulSoup, link_base: str) -> dict[str, Any]:
    """Imperative Freedium/Medium article extract -> parser_output for normalize."""
    main = _georgia_article_root(soup)
    meta: dict[str, Any] = {"authors": [], "tags": []}

    title_el = main.find("h1")
    if title_el:
        meta["title"] = _text(title_el)
    if not meta.get("title"):
        og = soup.find("meta", property="og:title")
        meta["title"] = (og.get("content") or "").strip() if og else ""

    meta["authors"] = _extract_author_from_card(main)
    pub, upd = _parse_freedium_published_updated(main)
    if pub:
        meta["published_at"] = pub
    if upd:
        meta["updated_at"] = upd

    sections: list[dict[str, Any]] = []
    block_tags = (
        "h1", "h2", "h3", "h4", "h5", "h6",
        "p", "ul", "ol", "pre", "blockquote", "figure", "img",
    )

    skipping_recommendations = False

    for el in main.find_all(block_tags, recursive=True):
        if _is_reporting_footer(el):
            break

        if el.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            ht = _text(el)
            if ht.startswith("You may also like"):
                skipping_recommendations = True
                continue
            if skipping_recommendations and ht.startswith("References"):
                skipping_recommendations = False
            elif skipping_recommendations:
                continue

        if skipping_recommendations:
            continue

        if el.name == "p":
            if el.find_parent("ul") or el.find_parent("ol"):
                continue
            if _inside_author_card(el):
                continue
            if _skip_banner_paragraph(el):
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

        if el.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            content = _text(el)
            if not content:
                continue
            sections.append({
                "type": "heading",
                "level": _heading_level(el),
                "content": content,
                "section_id": el.get("id") or f"heading-{len(sections)}",
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
            if _skip_img(el):
                continue
            src = (el.get("src") or "").strip()
            if not src:
                continue
            cap = _caption_for_freedium_img(el)
            sections.append({
                "type": "figure",
                "content": "",
                "assets": [{"original_src": src, "caption": cap}],
            })

    return {
        "meta": meta,
        "sections": sections,
        "parser_version": "raw_ingest.medium_freedium/0.1.0",
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
    parser_output = extract_freedium_article(soup, link_base=fetch_url)

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
    fetch = line
    return fetch, canonical_url_from_freedium_fetch(fetch)


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest Freedium Medium mirror into data/docs")
    ap.add_argument("--fetch-url", default="", help="Freedium mirror URL to fetch")
    ap.add_argument("--canonical-url", default="", help="Medium source_uri (default: derive from fetch URL)")
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
        fetch = args.fetch_url or FETCH_URL
        canonical = args.canonical_url or canonical_url_from_freedium_fetch(fetch)
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
