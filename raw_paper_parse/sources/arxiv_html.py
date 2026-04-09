#!/usr/bin/env python3
"""
arXiv experimental HTML (ar5iv / LaTeXML): fetch, parse article.ltx_document -> Document schema.

Run via sources/router.py (see raw_paper_parse/README.md).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_RAW_PAPER_ROOT = Path(__file__).resolve().parents[1]
_RAW_INGEST_COMMON = _RAW_PAPER_ROOT.parent / "raw_ingest" / "common"
if str(_RAW_INGEST_COMMON) not in sys.path:
    sys.path.insert(0, str(_RAW_INGEST_COMMON))

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

from assets_doc import process_assets
from normalize_doc import normalize
from rawdoc_write import write_rawdoc_html
from repo_paths import REPO_ROOT
from schema_validate import validate_document
from sink_doc import write_document_outputs

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_ARXIV_NEW = re.compile(r"^\d{4}\.\d{4,5}(?:v\d+)?$", re.IGNORECASE)
_ARXIV_OLD = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z]{2})?/\d{7}(?:v\d+)?$", re.IGNORECASE)


def arxiv_id_from_url(url: str) -> str | None:
    """Extract arXiv id from abs, html, or pdf URL (new or old identifier scheme)."""
    u = (url or "").strip()
    if not u:
        return None
    parts = [p for p in (urlparse(u).path or "").split("/") if p]
    if not parts:
        return None
    if parts[0].lower() in ("abs", "html", "pdf"):
        parts = parts[1:]
    if not parts:
        return None
    tail = "/".join(parts)
    if tail.lower().endswith(".pdf"):
        tail = tail[:-4]
    if _ARXIV_NEW.match(tail) or _ARXIV_OLD.match(tail):
        return tail
    return None


def html_fetch_url(url: str) -> str:
    """Normalize arxiv abs/pdf URL to https://arxiv.org/html/<id>."""
    aid = arxiv_id_from_url(url)
    if not aid:
        return url
    low = url.lower()
    if "arxiv.org" not in low:
        return url
    return f"https://arxiv.org/html/{aid}"


def abs_canonical_url(url: str) -> str:
    aid = arxiv_id_from_url(url)
    if aid:
        return f"https://arxiv.org/abs/{aid}"
    return url


def _section_heading_level(sec: Tag) -> int:
    cls = sec.get("class") or []
    if "ltx_subsubsection" in cls:
        return 4
    if "ltx_subsection" in cls:
        return 3
    if "ltx_section" in cls:
        return 2
    return 2


def _heading_tag_for_section(sec: Tag) -> Tag | None:
    for ch in sec.children:
        if not isinstance(ch, Tag):
            continue
        if ch.name in ("h2", "h3", "h4") and "ltx_title" in (ch.get("class") or []):
            return ch
    return None


def _clean_tex(s: str) -> str:
    return " ".join(s.split()).strip()


def _extract_math_tex(m: Tag) -> str | None:
    """Prefer LaTeXML application/x-tex annotation over MathML text."""
    for enc in ("application/x-tex", "application/x-latex"):
        ann = m.find("annotation", attrs={"encoding": enc})
        if ann:
            t = ann.get_text()
            if t and t.strip():
                return _clean_tex(t)
    for ann in m.find_all("annotation"):
        e = (ann.get("encoding") or "").lower()
        if "tex" in e:
            t = ann.get_text()
            if t and t.strip():
                return _clean_tex(t)
    alt = (m.get("alttext") or "").strip()
    if alt:
        return _clean_tex(alt)
    return None


def _is_display_math(m: Tag) -> bool:
    if (m.get("display") or "").lower() == "block":
        return True
    cls = " ".join(m.get("class") or [])
    return "ltx_Math_display" in cls


def _extract_cite_refs(cite: Tag) -> list[dict[str, str]]:
    """LaTeXML \\citep: <a href=\"#bib.bib35\" class=\"ltx_ref\">35</a>."""
    refs: list[dict[str, str]] = []
    for a in cite.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if href.startswith("#"):
            href = href[1:]
        if not href:
            continue
        label = (a.get_text(strip=True) or "").strip()
        refs.append({"ref_id": href, "label": label or href})
    return refs


def _paragraph_segments(p: Tag) -> list[str | dict[str, Any]]:
    """Ordered text runs, math, citations, and nested tables (ar5iv / LaTeXML)."""
    parts: list[str | dict[str, Any]] = []
    buf: list[str] = []

    def flush_buf() -> None:
        if not buf:
            return
        s = "".join(buf)
        s = " ".join(s.split())
        if s:
            parts.append(s)
        buf.clear()

    def walk(node: Any) -> None:
        if isinstance(node, NavigableString):
            buf.append(str(node))
            return
        if not isinstance(node, Tag):
            return
        if node.name == "math":
            flush_buf()
            tex = _extract_math_tex(node)
            if tex:
                parts.append({"math": tex, "display": _is_display_math(node)})
            return
        if node.name == "cite":
            flush_buf()
            refs = _extract_cite_refs(node)
            if refs:
                parts.append({"cite": refs})
            return
        if node.name == "table":
            flush_buf()
            rows = _table_rows(node)
            if rows:
                parts.append({"table": {"rows": rows}})
            return
        for ch in node.children:
            walk(ch)

    walk(p)
    flush_buf()
    merged: list[str | dict[str, Any]] = []
    for x in parts:
        if isinstance(x, str):
            if merged and isinstance(merged[-1], str):
                merged[-1] = (merged[-1] + " " + x).strip()
            else:
                merged.append(x)
        else:
            merged.append(x)
    return merged


def _segment_is_structured(x: Any) -> bool:
    return isinstance(x, dict)


def _paragraph_dict_from_ltx_p(p: Tag, section_id: str) -> dict[str, Any] | None:
    segs = _paragraph_segments(p)
    if not segs:
        return None
    has_structured = any(_segment_is_structured(x) for x in segs)
    text_only = [x for x in segs if isinstance(x, str)]
    content = " ".join(text_only).strip()
    content = re.sub(r"\s+\.", ".", content)
    content = re.sub(r"\s+,", ",", content)
    if has_structured:
        items: list[Any] = []
        for x in segs:
            if isinstance(x, str):
                items.append(x)
            elif "math" in x:
                d: dict[str, Any] = {"math": x["math"]}
                if x.get("display"):
                    d["display"] = True
                items.append(d)
            elif "cite" in x:
                items.append({"cite": x["cite"]})
            elif "table" in x:
                items.append({"table": x["table"]})
        return {
            "section_id": section_id,
            "type": "paragraph",
            "content": content,
            "items": items,
        }
    return {
        "section_id": section_id,
        "type": "paragraph",
        "content": content,
    }


def _owning_table(tag: Tag) -> Tag | None:
    el: Any = tag.parent
    while el is not None:
        if isinstance(el, Tag) and el.name == "table":
            return el
        el = el.parent
    return None


def _table_rows(table: Tag) -> list[list[str]]:
    """Rows of this table only (ignore nested <table> rows)."""
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        if _owning_table(tr) is not table:
            continue
        cells = tr.find_all(["th", "td"], recursive=False)
        if not cells:
            continue
        rows.append([(c.get_text(" ", strip=True) or "").strip() for c in cells])
    return rows


def _list_items(tag: Tag) -> list[str]:
    out: list[str] = []
    for li in tag.find_all("li", recursive=False):
        t = li.get_text(" ", strip=True)
        if t:
            out.append(t)
    if not out:
        for li in tag.find_all("li"):
            t = li.get_text(" ", strip=True)
            if t:
                out.append(t)
    return out


def _extract_references(article: Tag) -> list[dict[str, Any]]:
    """LaTeXML bibliography: <li id=\"bib.bibN\" class=\"ltx_bibitem\">."""
    refs: list[dict[str, Any]] = []
    for li in article.find_all("li", class_=lambda c: c and "ltx_bibitem" in c):
        rid = (li.get("id") or "").strip()
        if not rid:
            continue
        label_el = li.find("span", class_=lambda c: c and "ltx_tag_bibitem" in c)
        label = (label_el.get_text(strip=True) if label_el else "").strip()
        blocks: list[str] = []
        for blk in li.find_all("span", class_=lambda c: c and "ltx_bibblock" in c):
            t = blk.get_text(" ", strip=True)
            if t:
                blocks.append(t)
        text = " ".join(blocks).strip()
        if not text:
            text = (li.get_text(" ", strip=True) or "").strip()
            if label and text.startswith(label):
                text = text[len(label) :].strip()
        entry: dict[str, Any] = {"ref_id": rid, "text": text}
        if label:
            entry["label"] = label
        if blocks:
            entry["blocks"] = blocks
        refs.append(entry)
    return refs


def parse_ar5iv_html(html: str, base_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    article = soup.find("article", class_=lambda c: c and "ltx_document" in c)
    if not article:
        raise ValueError("arXiv HTML: missing article.ltx_document")

    title_el = article.find("h1", class_=lambda c: c and "ltx_title_document" in c)
    title = (title_el.get_text(strip=True) if title_el else "") or "Untitled"

    authors: list[str] = []
    auth_block = article.find("div", class_=lambda c: c and "ltx_authors" in c)
    if auth_block:
        for span in auth_block.find_all("span", class_=lambda c: c and "ltx_personname" in c):
            name = span.get_text(strip=True)
            if name:
                authors.append(name)

    sections_out: list[dict[str, Any]] = []
    sid = 0

    def next_id(prefix: str) -> str:
        nonlocal sid
        sid += 1
        return f"{prefix}-{sid}"

    def emit_para_block(container: Tag) -> None:
        nonlocal sections_out
        for child in container.children:
            if isinstance(child, NavigableString):
                continue
            if not isinstance(child, Tag):
                continue
            nm = child.name
            if nm == "p" and "ltx_p" in (child.get("class") or []):
                pd = _paragraph_dict_from_ltx_p(child, next_id("p"))
                if pd:
                    sections_out.append(pd)
            elif nm == "img" and "ltx_graphics" in (child.get("class") or []):
                src = (child.get("src") or "").strip()
                alt = (child.get("alt") or "").strip() or None
                if src:
                    sections_out.append({
                        "section_id": next_id("fig"),
                        "type": "figure",
                        "content": "",
                        "assets": [{"caption": alt, "original_src": src}],
                    })
            elif nm == "table":
                rows = _table_rows(child)
                if rows:
                    sections_out.append({
                        "section_id": next_id("tbl"),
                        "type": "table",
                        "content": "",
                        "rows": rows,
                    })
            elif nm in ("ul", "ol"):
                items = _list_items(child)
                if items:
                    sections_out.append({
                        "section_id": next_id("lst"),
                        "type": "list",
                        "content": "",
                        "items": items,
                    })
            elif nm == "pre":
                code = child.get_text()
                if code.strip():
                    sections_out.append({
                        "section_id": next_id("cd"),
                        "type": "code",
                        "content": code.rstrip(),
                    })

    def walk_section(sec: Tag) -> None:
        nonlocal sections_out
        level = _section_heading_level(sec)
        ht = _heading_tag_for_section(sec)
        if ht:
            htext = ht.get_text(" ", strip=True)
            if htext:
                sections_out.append({
                    "section_id": next_id("h"),
                    "type": "heading",
                    "level": min(max(level, 2), 6),
                    "content": htext,
                })
        for ch in sec.children:
            if not isinstance(ch, Tag):
                continue
            if ch is ht:
                continue
            cname = ch.name
            ccls = ch.get("class") or []
            if cname == "section":
                walk_section(ch)
            elif cname == "div" and "ltx_para" in ccls:
                emit_para_block(ch)
            elif cname in ("figure",):
                img = ch.find("img", class_=lambda x: x and "ltx_graphics" in x)
                if img:
                    src = (img.get("src") or "").strip()
                    cap_el = ch.find(class_=lambda x: x and "ltx_caption" in x)
                    cap = cap_el.get_text(" ", strip=True) if cap_el else None
                    if src:
                        sections_out.append({
                            "section_id": next_id("fig"),
                            "type": "figure",
                            "content": "",
                            "assets": [{"caption": cap, "original_src": src}],
                        })

    for ch in article.children:
        if not isinstance(ch, Tag):
            continue
        if ch.name == "section" and "ltx_section" in (ch.get("class") or []):
            walk_section(ch)
        elif ch.name == "div" and "ltx_para" in (ch.get("class") or []):
            emit_para_block(ch)

    references = _extract_references(article)

    return {
        "meta": {
            "title": title,
            "authors": authors,
            "published_at": None,
            "language": "en",
            "tags": [],
        },
        "sections": sections_out,
        "references": references,
        "parser_version": "raw_paper_parse.arxiv_html 0.4.0",
    }


def run_one(
    fetch_url: str,
    canonical_url: str,
    rawdocs_dir: Path,
    assets_dir: Path,
    docs_dir: Path,
    timeout: int,
    do_validate: bool,
    *,
    work_id: str = "",
    variant: str = "preprint",
) -> None:
    fetch_effective = html_fetch_url(fetch_url)
    aid = arxiv_id_from_url(fetch_url) or arxiv_id_from_url(fetch_effective) or ""

    if work_id.strip() == "" and aid:
        work_id = f"arxiv:{aid}"

    canonical = (canonical_url or "").strip() or abs_canonical_url(fetch_effective)

    resp = requests.get(
        fetch_effective,
        headers=DEFAULT_HEADERS,
        timeout=timeout,
    )
    resp.raise_for_status()
    html_bytes = resp.content

    rawdoc = write_rawdoc_html(html_bytes, rawdocs_dir, canonical)
    rawdoc_id = rawdoc["rawdoc_id"]
    md = rawdoc.get("metadata") if isinstance(rawdoc.get("metadata"), dict) else {}
    md = dict(md)
    md.update({
        "work_id": work_id,
        "variant": variant,
        "arxiv_id": aid,
        "fetch_url": fetch_effective,
    })
    rawdoc["metadata"] = md
    meta_path = rawdocs_dir / f"{rawdoc_id}.meta.json"
    meta_path.write_text(json.dumps(rawdoc, ensure_ascii=False, indent=2), encoding="utf-8")

    parser_out = parse_ar5iv_html(html_bytes.decode("utf-8", errors="replace"), fetch_effective)
    doc = normalize(
        parser_out,
        rawdoc_id,
        rawdoc["storage_path"],
        canonical,
        source_type="html",
    )
    tags = list(doc["meta"].get("tags") or [])
    if work_id:
        tags.append(f"paper:work_id:{work_id}")
    tags.append(f"paper:variant:{variant}")
    doc["meta"]["tags"] = tags

    doc = process_assets(doc, assets_dir, base_url=fetch_effective)
    if do_validate:
        validate_document(doc, REPO_ROOT)

    doc_id = doc["doc_id"]
    md["doc_id"] = doc_id
    rawdoc["metadata"] = md
    meta_path.write_text(json.dumps(rawdoc, ensure_ascii=False, indent=2), encoding="utf-8")

    json_path, md_path = write_document_outputs(doc, docs_dir, rawdocs_dir, rawdoc_id, write_done=True)
    print(
        f"rawdoc_id={rawdoc_id} doc_id={doc_id} doc_json={json_path} doc_md={md_path}",
        flush=True,
    )


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Ingest arXiv HTML into data/docs")
    ap.add_argument("--fetch-url", default="", help="arXiv abs, html, or pdf URL")
    ap.add_argument("--canonical-url", default="", help="source_uri (default: arxiv abs)")
    ap.add_argument("--work-id", default="", help="Logical work id, e.g. arxiv:2401.00001v1")
    ap.add_argument("--variant", default="preprint", help="preprint|conference|journal")
    ap.add_argument("--rawdocs", default=None, help="RawDocs dir")
    ap.add_argument("--assets", default=None, help="Assets dir")
    ap.add_argument("--docs", default=None, help="Docs dir")
    ap.add_argument("--timeout", type=int, default=45)
    ap.add_argument("--no-validate", action="store_true")
    args = ap.parse_args()

    rawdocs_dir = Path(args.rawdocs or REPO_ROOT / "data" / "rawdocs")
    assets_dir = Path(args.assets or REPO_ROOT / "data" / "assets")
    docs_dir = Path(args.docs or REPO_ROOT / "data" / "docs")
    fetch = args.fetch_url.strip()
    if not fetch:
        print("Usage: --fetch-url https://arxiv.org/html/...", file=sys.stderr)
        sys.exit(2)
    canonical = args.canonical_url.strip() or abs_canonical_url(fetch)
    run_one(
        fetch,
        canonical,
        rawdocs_dir,
        assets_dir,
        docs_dir,
        args.timeout,
        not args.no_validate,
        work_id=args.work_id.strip(),
        variant=args.variant.strip() or "preprint",
    )


if __name__ == "__main__":
    main()
