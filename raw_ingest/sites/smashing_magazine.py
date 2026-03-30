#!/usr/bin/env python3
"""
Smashing Magazine articles (www.smashingmagazine.com/...): body in article div.c-garfield-the-cat.

Run: cd raw_ingest && python sites/smashing_magazine.py
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

DEFAULT_URL = (
    "https://www.smashingmagazine.com/2026/03/"
    "site-search-paradox-why-big-box-always-wins/"
)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

# Skip subtrees (class substring match on an ancestor between the node and .c-garfield-the-cat).
_SKIP_ZONE_SUBSTR = (
    "c-garfield-header",
    "meta-box",
    "c-garfield-aside--meta",
    "c-garfield-native-panel",
    "feature-panel-container",
    "feature-panel",
    "partners__lead-place",
    "partners__native",
    "signature",
    "category__related",
    "c-garfield__nl",
    "l-author-bio",
    "toc-components",
    "article__comments",
    "c-friskies-box",
    "sponsor-panel",
    "nl-box",
    "drop-caps",
    "c-garfield-bio",
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


def _iso_smashing_published(s: str | None) -> str | None:
    if not s:
        return None
    s = s.strip()
    # e.g. "2026-03-26 10:00:00 +0000 UTC" or " 2026-03-26 10:00:00 +0000 UTC"
    s = re.sub(r"\s+UTC\s*$", "", s, flags=re.I).strip()
    dt: datetime | None = None
    for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            break
        except ValueError:
            continue
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


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


def _skip_div_root(ch) -> bool:
    blob = _classes_blob(ch)
    return any(sub in blob for sub in _SKIP_ZONE_SUBSTR)


def _emit_block(
    el,
    cat,
    link_base: str,
    sections: list[dict[str, Any]],
) -> None:
    if _in_skip_zone(el, cat):
        return

    if el.name in ("h2", "h3", "h4", "h5", "h6"):
        ht = _text(el)
        if not ht:
            return
        sections.append({
            "type": "heading",
            "level": _heading_level(el),
            "content": ht,
            "section_id": el.get("id") or f"heading-{len(sections)}",
        })
        return

    if el.name == "p":
        if el.find_parent("ul") or el.find_parent("ol"):
            return
        content, links = _content_with_links(el, link_base)
        if not content:
            return
        sec: dict[str, Any] = {"type": "paragraph", "content": content}
        if links:
            sec["annotations"] = {"links": links}
        sections.append(sec)
        return

    if el.name == "center":
        if el.find_parent("p"):
            return
        imgs = el.find_all("img", recursive=False)
        if len(imgs) == 1 and not _text(el).replace(_text(imgs[0]), "").strip():
            src = (imgs[0].get("src") or "").strip()
            if src:
                if link_base and not src.startswith(("http://", "https://")):
                    src = urljoin(link_base, src)
                cap = (imgs[0].get("alt") or "").strip() or None
                sections.append({
                    "type": "figure",
                    "content": "",
                    "assets": [{"original_src": src, "caption": cap}],
                })
            return
        content, links = _content_with_links(el, link_base)
        if not content:
            return
        sec = {"type": "paragraph", "content": content}
        if links:
            sec["annotations"] = {"links": links}
        sections.append(sec)
        return

    if el.name in ("ul", "ol"):
        if el.find_parent("ul") or el.find_parent("ol"):
            return
        items = _list_items_tree(el, link_base)
        if not items:
            return
        sections.append({
            "type": "list",
            "section_id": el.get("id") or f"list-{len(sections)}",
            "items": items,
            "content": "",
        })
        return

    if el.name == "pre":
        code = el.find("code")
        body = _text(code) if code else _text(el)
        if not body:
            return
        sections.append({"type": "code", "content": body})
        return

    if el.name == "blockquote":
        content, links = _content_with_links(el, link_base)
        if not content:
            return
        sec = {"type": "paragraph", "content": content}
        if links:
            sec["annotations"] = {"links": links}
        sections.append(sec)
        return

    if el.name == "figure":
        img = el.find("img")
        src = ""
        if img:
            src = (img.get("src") or "").strip()
        if not src:
            return
        if link_base and not src.startswith(("http://", "https://")):
            src = urljoin(link_base, src)
        cap = (img.get("alt") or "") or _text(el.find("figcaption"))
        sections.append({
            "type": "figure",
            "content": "",
            "assets": [{"original_src": src, "caption": cap or None}],
        })
        return

    if el.name == "img":
        if el.find_parent("figure"):
            return
        if el.find_parent("p"):
            return
        if el.find_parent("center"):
            return
        src = (el.get("src") or "").strip()
        if not src:
            return
        if link_base and not src.startswith(("http://", "https://")):
            src = urljoin(link_base, src)
        cap = (el.get("alt") or "").strip() or None
        sections.append({
            "type": "figure",
            "content": "",
            "assets": [{"original_src": src, "caption": cap}],
        })


_BLOCK = frozenset({
    "p", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "pre", "blockquote", "figure", "img", "center",
})


def _walk_smashing_cat(cat, link_base: str, sections: list[dict[str, Any]]) -> None:
    for ch in cat.children:
        if not getattr(ch, "name", None):
            continue
        blob = _classes_blob(ch)
        if "c-garfield-summary" in blob:
            sec_el = ch.select_one("section.article__summary")
            st = _text(sec_el) if sec_el else _text(ch)
            if st:
                sections.append({"type": "paragraph", "content": st})
            continue
        if ch.name in ("div", "section", "article"):
            if _skip_div_root(ch):
                continue
            _walk_smashing_cat(ch, link_base, sections)
            continue
        if ch.name in _BLOCK:
            _emit_block(ch, cat, link_base, sections)


def extract_smashing_article(soup: BeautifulSoup, link_base: str) -> dict[str, Any]:
    meta: dict[str, Any] = {"authors": [], "tags": [], "language": "en"}

    h1 = soup.select_one(".c-garfield-header h1") or soup.select_one("article.article h1")
    og = (_meta_property(soup, "og:title") or "").strip()
    if h1 and _text(h1):
        meta["title"] = _text(h1)
    elif og:
        meta["title"] = re.sub(r"\s*—\s*Smashing Magazine\s*$", "", og, flags=re.I).strip()
    else:
        meta["title"] = _text(soup.find("title"))

    pub = _iso_smashing_published(_meta_property(soup, "article:published_time"))
    if pub:
        meta["published_at"] = pub
        meta["updated_at"] = pub

    mod_raw = _meta_property(soup, "article:modified_time")
    mod = _iso_smashing_published(mod_raw)
    if mod:
        meta["updated_at"] = mod

    auth_el = soup.select_one(".c-garfield-header .author-post__author-title")
    if auth_el and _text(auth_el):
        meta["authors"] = [_text(auth_el)]
    auth_link = soup.select_one('.c-garfield-header a[href*="/author/"]')
    if not meta["authors"] and auth_link and _text(auth_link):
        meta["authors"] = [_text(auth_link)]

    for tag_m in soup.find_all("meta", attrs={"property": "article:tag"}):
        c = (tag_m.get("content") or "").strip()
        if c:
            meta["tags"].append(c)

    cat = soup.select_one("article.article div.c-garfield-the-cat") or soup.select_one(
        "div.c-garfield-the-cat"
    )
    sections: list[dict[str, Any]] = []
    if not cat:
        return {
            "meta": meta,
            "sections": sections,
            "parser_version": "raw_ingest.smashing_magazine/0.1.0",
        }

    _walk_smashing_cat(cat, link_base, sections)

    return {
        "meta": meta,
        "sections": sections,
        "parser_version": "raw_ingest.smashing_magazine/0.1.0",
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
    parser_output = extract_smashing_article(soup, link_base=fetch_url)

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
    ap = argparse.ArgumentParser(description="Ingest Smashing Magazine articles into data/docs")
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
