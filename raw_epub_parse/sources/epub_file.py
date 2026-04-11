#!/usr/bin/env python3
"""
Core EPUB parser for Calibre directory input.

Pipeline:
  Calibre dir -> open_calibre_dir -> parse_calibre_metadata + parse_epub internals
              -> parse_chapters -> merge metadata -> normalize -> process assets -> sink
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sys
import uuid
import warnings
import zipfile
from collections import namedtuple
from pathlib import Path
from typing import Any, Callable
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup, NavigableString, Tag, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

from common.normalize import normalize
from common.paths import REPO_ROOT
from common.sink import write_document_outputs
from common.validate import validate_document

CalibreDir = namedtuple("CalibreDir", [
    "dir_path",
    "epub_path",
    "cover_path",
    "metadata_opf_path",
])

CalibreMeta = namedtuple("CalibreMeta", [
    "calibre_id",
    "isbn",
    "douban_id",
    "title",
    "creators",
    "publisher",
    "date",
    "language",
    "subjects",
    "description",
    "pages",
    "word_count",
    "title_sort",
])

ManifestItem = namedtuple("ManifestItem", ["id", "href", "media_type"])

EpubMeta = namedtuple("EpubMeta", [
    "title",
    "creators",
    "language",
    "publisher",
    "date",
    "identifier",
    "spine_items",
    "manifest_items",
    "cover_image_id",
    "opf_root",
    "chapter_labels",
])

OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"
NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"


def _el_text(parent: ET.Element, tag: str, default: str = "") -> str:
    for ns in (f"{{{DC_NS}}}", ""):
        el = parent.find(f"{ns}{tag}")
        if el is not None and el.text:
            return el.text.strip()
    return default


def _normalize_lang(lang: str) -> str:
    m = {
        "zho": "zh", "chi": "zh",
        "eng": "en",
        "jpn": "ja",
        "fre": "fr", "fra": "fr",
        "ger": "de", "deu": "de",
    }
    return m.get((lang or "").lower().strip(), lang or "")


def _strip_html(html_str: str) -> str:
    text = html_str.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _pick_nonempty(primary: list[str] | None, fallback: list[str]) -> list[str]:
    if primary and any(p.strip() for p in primary if p):
        return [p for p in primary if p and p.strip()]
    return fallback


def _pick_nonempty_string(primary: str | None, fallback: str | None) -> str | None:
    if primary and primary.strip():
        return primary.strip()
    if fallback and fallback.strip():
        return fallback.strip()
    return None


def _scan_calibre_dir(dir_path: Path) -> CalibreDir:
    files = list(dir_path.iterdir())
    epub_path = None
    cover_path = None
    metadata_path = None
    for f in files:
        if f.suffix.lower() == ".epub":
            epub_path = f
        elif f.name.lower() == "cover.jpg":
            cover_path = f
        elif f.name.lower() == "metadata.opf":
            metadata_path = f
    if not epub_path:
        raise FileNotFoundError(f"No .epub file found in {dir_path}")
    return CalibreDir(
        dir_path=dir_path,
        epub_path=epub_path,
        cover_path=cover_path,
        metadata_opf_path=metadata_path,
    )


def parse_calibre_metadata(opf_path: Path) -> CalibreMeta:
    tree = ET.parse(str(opf_path))
    root = tree.getroot()

    calibre_id = ""
    isbn = ""
    douban_id = ""
    for el in root.iterfind(f".//{{{DC_NS}}}identifier"):
        scheme = (el.get(f"{{{OPF_NS}}}scheme") or "").lower()
        text = (el.text or "").strip()
        if scheme == "calibre":
            calibre_id = text
        elif scheme == "isbn":
            isbn = text
        elif scheme in ("new_douban", "douban"):
            douban_id = text

    metadata = root.find(f"{{{OPF_NS}}}metadata")
    if metadata is None:
        metadata = root

    title = _el_text(metadata, "title")
    if not title:
        title = _el_text(root, "title")

    creators = []
    for el in metadata.findall(f"{{{DC_NS}}}creator"):
        role = el.get(f"{{{OPF_NS}}}role", "")
        if role in ("aut", ""):
            name = (el.text or "").strip()
            if name:
                creators.append(name)
    if not creators:
        for el in root.findall(f".//{{{DC_NS}}}creator"):
            name = (el.text or "").strip()
            if name:
                creators.append(name)

    publisher = _el_text(metadata, "publisher") or _el_text(root, "publisher")
    date = _el_text(metadata, "date") or _el_text(root, "date")
    language = _el_text(metadata, "language") or _el_text(root, "language")

    subjects = []
    for el in metadata.findall(f"{{{DC_NS}}}subject"):
        s = (el.text or "").strip()
        if s:
            subjects.append(s)

    description_raw = _el_text(metadata, "description") or _el_text(root, "description")
    description = _strip_html(description_raw) if description_raw else ""

    pages = None
    word_count = None
    for meta_el in metadata.findall(f"{{{OPF_NS}}}meta"):
        name = meta_el.get("name", "")
        content = (meta_el.text or "").strip()
        if name == "calibre:user_metadata:#pages":
            try:
                data = json.loads(content)
                pages = data.get("#value#")
            except json.JSONDecodeError:
                pass
        elif name == "calibre:user_metadata:#words":
            try:
                data = json.loads(content)
                word_count = data.get("#value#")
            except json.JSONDecodeError:
                pass

    title_sort = ""
    for meta_el in metadata.findall(f"{{{OPF_NS}}}meta"):
        if meta_el.get("name") == "calibre:title_sort":
            title_sort = (meta_el.get("content") or "").strip()
            break

    return CalibreMeta(
        calibre_id=calibre_id,
        isbn=isbn,
        douban_id=douban_id,
        title=title,
        creators=creators,
        publisher=publisher,
        date=date,
        language=language,
        subjects=subjects,
        description=description,
        pages=pages,
        word_count=word_count,
        title_sort=title_sort,
    )


def _parse_container_xml(zf: zipfile.ZipFile) -> str:
    try:
        raw = zf.read("META-INF/container.xml")
        root = ET.fromstring(raw)
    except KeyError:
        raise FileNotFoundError("META-INF/container.xml not found in EPUB")
    ns = "urn:oasis:names:tc:opendocument:xmlns:container"
    rootfiles = root.findall(f".//{{{ns}}}rootfile")
    for rf in rootfiles:
        mt = rf.get("media-type", "")
        fp = rf.get("full-path", "")
        if "oebps-package" in mt and fp:
            return fp
    for rf in rootfiles:
        fp = rf.get("full-path", "")
        if fp:
            return fp
    raise ValueError("No valid rootfile in container.xml")


def parse_epub_opf(zf: zipfile.ZipFile, opf_path: str) -> EpubMeta:
    raw = zf.read(opf_path)
    root = ET.fromstring(raw)

    opf_root = os.path.dirname(opf_path)
    if opf_root and not opf_root.endswith("/"):
        opf_root += "/"

    metadata = root.find(f"{{{OPF_NS}}}metadata")
    if metadata is None:
        metadata = root

    title = _el_text(metadata, "title")
    creators_raw = _el_text(metadata, "creator")
    creators = []
    for part in re.split(r"[；;]", creators_raw):
        part = part.strip()
        if part:
            creators.append(part)

    language = _el_text(metadata, "language")
    publisher = _el_text(metadata, "publisher")
    date = _el_text(metadata, "date")
    identifier = _el_text(metadata, "identifier")

    manifest: dict[str, ManifestItem] = {}
    for item in root.findall(f".//{{{OPF_NS}}}item"):
        item_id = item.get("id")
        href = item.get("href")
        media_type = item.get("media-type")
        if item_id and href:
            full_href = os.path.normpath(os.path.join(opf_root, href))
            manifest[item_id] = ManifestItem(item_id, full_href, media_type or "")

    spine: list[ManifestItem] = []
    for itemref in root.findall(f".//{{{OPF_NS}}}itemref"):
        idref = itemref.get("idref")
        if idref and idref in manifest:
            spine.append(manifest[idref])

    cover_id = None
    for meta_el in metadata.findall(f"{{{OPF_NS}}}meta"):
        if meta_el.get("name") == "cover":
            cover_id = meta_el.get("content")
            break

    epub_meta = EpubMeta(
        title=title,
        creators=creators,
        language=language,
        publisher=publisher,
        date=date,
        identifier=identifier,
        spine_items=spine,
        manifest_items=manifest,
        cover_image_id=cover_id,
        opf_root=opf_root,
        chapter_labels={},
    )

    epub_meta = _parse_ncx(zf, epub_meta)
    return epub_meta


def _parse_ncx(zf: zipfile.ZipFile, meta: EpubMeta) -> EpubMeta:
    ncx_item = None
    for item in meta.manifest_items.values():
        if item.media_type == "application/x-dtbncx+xml":
            ncx_item = item
            break
    if not ncx_item:
        return meta

    try:
        raw = zf.read(ncx_item.href).decode("utf-8", errors="replace")
    except Exception:
        return meta

    try:
        ncx_root = ET.fromstring(raw)
    except ET.ParseError:
        return meta

    chapter_labels: dict[str, str] = {}
    for navpoint in ncx_root.iter(f"{{{NCX_NS}}}navPoint"):
        label_el = navpoint.find(f"{{{NCX_NS}}}navLabel/{{{NCX_NS}}}text")
        content_el = navpoint.find(f"{{{NCX_NS}}}content")
        if label_el is not None and content_el is not None:
            title = (label_el.text or "").strip()
            src = (content_el.get("src") or "").split("#")[0]
            if title and src:
                chapter_dir = os.path.dirname(ncx_item.href)
                full_src = os.path.normpath(os.path.join(chapter_dir, src))
                chapter_labels[full_src] = title

    return meta._replace(chapter_labels=chapter_labels)


def should_skip_chapter(raw_html: str, item: ManifestItem, meta: EpubMeta) -> bool:
    soup = BeautifulSoup(raw_html, "lxml")
    body = soup.find("body")
    if not body:
        return False

    body_class = " ".join(body.get("class") or [])
    toc_classes = ("sgc-toc-title", "sgc-toc-level", "sgc-toc")
    if any(tc in body_class for tc in toc_classes):
        return True

    body_id = (body.get("id") or "").lower()
    if "toc" in body_id:
        return True

    total_text = body.get_text(" ", strip=True)
    link_text = " ".join(a.get_text(" ", strip=True) for a in body.find_all("a"))
    if total_text and len(link_text) / max(len(total_text), 1) > 0.5:
        return True

    cover_meta = soup.find("meta", attrs={"name": "calibre:cover"})
    if cover_meta and cover_meta.get("content") == "true":
        return True

    children = [c for c in body.children if isinstance(c, Tag)]
    text_content = body.get_text(" ", strip=True)
    if len(text_content) < 20 and any(c.name in ("svg", "image") for c in children):
        return True

    return False


def resolve_inline_src(src: str, item_href: str) -> str:
    chapter_dir = os.path.dirname(item_href) if item_href else ""
    return os.path.normpath(os.path.join(chapter_dir, src.strip()))


def _extract_list_items(tag: Tag) -> list[str]:
    items = []
    for li in tag.find_all("li", recursive=False):
        text = li.get_text(" ", strip=True)
        if text:
            items.append(text)
    return items


def _extract_table_rows(table: Tag) -> list[list[str]]:
    rows = []
    for tr in table.find_all("tr"):
        if tr.find_parent("table") is not table:
            continue
        cells = tr.find_all(["th", "td"])
        if cells:
            rows.append([c.get_text(" ", strip=True) for c in cells])
    return rows


def parse_chapter_body(
    body: Tag,
    next_id: Callable[[str], str],
    item_href: str,
    skip_first_h1: bool = False,
) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    _skipped_first_h1 = False

    def walk(node):
        nonlocal _skipped_first_h1
        if isinstance(node, NavigableString):
            return
        if not isinstance(node, Tag):
            return

        tag_name = node.name

        if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            if skip_first_h1 and not _skipped_first_h1 and tag_name == "h1":
                _skipped_first_h1 = True
                return
            text = node.get_text(" ", strip=True)
            if text:
                level = int(tag_name[1])
                sections.append({
                    "section_id": next_id("h"),
                    "type": "heading",
                    "level": level,
                    "content": text,
                })

        elif tag_name == "p":
            text = node.get_text(" ", strip=True)
            if text:
                sections.append({
                    "section_id": next_id("p"),
                    "type": "paragraph",
                    "content": text,
                })

        elif tag_name == "img":
            src = (node.get("src") or "").strip()
            alt = (node.get("alt") or "").strip() or None
            if src:
                resolved = resolve_inline_src(src, item_href)
                sections.append({
                    "section_id": next_id("fig"),
                    "type": "figure",
                    "content": "",
                    "assets": [{"caption": alt, "original_src": resolved}],
                })

        elif tag_name in ("ul", "ol"):
            items = _extract_list_items(node)
            if items:
                sections.append({
                    "section_id": next_id("lst"),
                    "type": "list",
                    "content": "",
                    "items": items,
                })

        elif tag_name == "table":
            rows = _extract_table_rows(node)
            if rows:
                sections.append({
                    "section_id": next_id("tbl"),
                    "type": "table",
                    "content": "",
                    "rows": rows,
                })

        elif tag_name in ("pre", "code"):
            text = node.get_text()
            if text.strip():
                sections.append({
                    "section_id": next_id("cd"),
                    "type": "code",
                    "content": text.rstrip(),
                })

        else:
            for child in node.children:
                walk(child)

    for child in body.children:
        walk(child)

    return sections


def parse_chapters(
    zf: zipfile.ZipFile,
    meta: EpubMeta,
    filter_skippable: bool = True,
) -> dict[str, Any]:
    all_sections: list[dict[str, Any]] = []
    sid = 0

    def next_id(prefix: str) -> str:
        nonlocal sid
        sid += 1
        return f"{prefix}-{sid}"

    for item in meta.spine_items:
        mt = item.media_type.lower()
        if "html" not in mt and "xhtml" not in mt:
            continue

        try:
            raw = zf.read(item.href).decode("utf-8", errors="replace")
        except Exception:
            print(f"WARNING: Cannot read chapter {item.href}", file=sys.stderr)
            continue

        if filter_skippable and should_skip_chapter(raw, item, meta):
            continue

        soup = BeautifulSoup(raw, "lxml")
        body = soup.find("body")
        if not body:
            continue

        chapter_title = meta.chapter_labels.get(item.href)
        if chapter_title and chapter_title != "目录":
            all_sections.append({
                "section_id": next_id("h"),
                "type": "heading",
                "level": 2,
                "content": chapter_title,
            })

        chapter_sections = parse_chapter_body(
            body, next_id, item.href,
            skip_first_h1=(chapter_title is not None),
        )
        all_sections.extend(chapter_sections)

    return {
        "meta": {},
        "sections": all_sections,
        "parser_version": "raw_epub_parse.epub_file 0.1.0",
    }


def merge_metadata(calibre: CalibreMeta | None, epub: EpubMeta, calibre_dir: CalibreDir) -> dict:
    c = calibre
    return {
        "title": (c.title if c else None) or epub.title or calibre_dir.dir_path.name or "Untitled",
        "authors": _pick_nonempty(c.creators if c else None, epub.creators),
        "language": _normalize_lang((c.language if c else None) or epub.language),
        "published_at": _pick_nonempty_string(
            (c.date if c else None), epub.date,
        ),
        "tags": c.subjects if c else [],
    }


def _process_assets(
    doc: dict[str, Any],
    zf: zipfile.ZipFile,
    calibre_dir: CalibreDir,
    assets_dir: Path,
) -> dict[str, Any]:
    doc = dict(doc)
    sections: list[dict[str, Any]] = list(doc.get("sections") or [])
    assets_dir.mkdir(parents=True, exist_ok=True)

    for sec in sections:
        if sec.get("type") != "figure" or not sec.get("assets"):
            continue
        new_assets = []
        for a in sec["assets"]:
            orig = (a.get("_original_src") or a.get("original_src") or "").strip()
            if not orig:
                new_assets.append({"asset_id": "", "path": "", "caption": a.get("caption")})
                continue
            data = None
            ext = os.path.splitext(orig)[1].lower() or ".png"
            try:
                data = zf.read(orig)
            except (KeyError, OSError):
                pass
            if data is None:
                new_assets.append({"asset_id": "", "path": "", "caption": a.get("caption")})
                continue
            h = hashlib.sha256(data[:65536]).hexdigest()[:16]
            asset_id = f"{h}{ext}"
            (assets_dir / asset_id).write_bytes(data)
            new_assets.append({
                "asset_id": asset_id,
                "path": f"assets/{asset_id}",
                "caption": a.get("caption"),
            })
        sec["assets"] = new_assets

    if calibre_dir.cover_path and calibre_dir.cover_path.is_file():
        cover_data = calibre_dir.cover_path.read_bytes()
        ext = os.path.splitext(str(calibre_dir.cover_path))[1].lower() or ".jpg"
        h = hashlib.sha256(cover_data[:65536]).hexdigest()[:16]
        asset_id = f"{h}{ext}"
        (assets_dir / asset_id).write_bytes(cover_data)

        cover_section = {
            "section_id": "cover",
            "type": "figure",
            "content": "",
            "items": [],
            "rows": [],
            "assets": [{
                "asset_id": asset_id,
                "path": f"assets/{asset_id}",
                "caption": "Cover",
            }],
            "annotations": {},
        }

        has_cover = any(
            s.get("type") == "figure" and s.get("section_id") == "cover"
            for s in sections
        )
        if has_cover:
            for i, s in enumerate(sections):
                if s.get("section_id") == "cover":
                    sections[i] = cover_section
                    break
        else:
            sections.insert(0, cover_section)

    doc["sections"] = sections
    return doc


def open_calibre_dir(dir_path: str | Path) -> tuple[CalibreDir, CalibreMeta | None, EpubMeta, zipfile.ZipFile]:
    dir_path = Path(dir_path)
    if not dir_path.is_dir():
        raise FileNotFoundError(f"Not a directory: {dir_path}")

    cd = _scan_calibre_dir(dir_path)

    calibre_meta = None
    if cd.metadata_opf_path and cd.metadata_opf_path.is_file():
        try:
            calibre_meta = parse_calibre_metadata(cd.metadata_opf_path)
        except Exception as e:
            print(f"WARNING: Failed to parse Calibre metadata: {e}", file=sys.stderr)

    epub_bytes = cd.epub_path.read_bytes()
    zf = zipfile.ZipFile(io.BytesIO(epub_bytes))

    opf_path = _parse_container_xml(zf)
    epub_meta = parse_epub_opf(zf, opf_path)

    return cd, calibre_meta, epub_meta, zf


def run_one(
    dir_path: str,
    canonical_url: str,
    rawdocs_dir: Path,
    assets_dir: Path,
    docs_dir: Path,
    timeout: int,
    do_validate: bool,
    *,
    work_id: str = "",
    variant: str = "book",
    write_rawdoc: bool = False,
) -> None:
    calibre_dir, calibre_meta, epub_meta, zf = open_calibre_dir(dir_path)
    source_uri = canonical_url or f"file://{calibre_dir.dir_path.resolve()}"

    merged_meta = merge_metadata(calibre_meta, epub_meta, calibre_dir)

    parser_output = parse_chapters(zf, epub_meta)

    parser_output["meta"]["title"] = (
        parser_output["meta"].get("title")
        or merged_meta["title"]
        or "Untitled"
    )
    parser_output["meta"]["authors"] = (
        parser_output["meta"].get("authors")
        or merged_meta["authors"]
    )
    parser_output["meta"]["language"] = (
        parser_output["meta"].get("language")
        or merged_meta["language"]
    )
    parser_output["meta"]["published_at"] = (
        parser_output["meta"].get("published_at")
        or merged_meta["published_at"]
        or None
    )
    parser_output["meta"]["parser_version"] = "raw_epub_parse.epub_file 0.1.0"

    tags: list[str] = list(parser_output["meta"].get("tags") or [])
    tags.extend(merged_meta.get("tags") or [])
    tags.append(f"book:variant:{variant}")
    if work_id:
        tags.append(f"book:work_id:{work_id}")
    if calibre_meta:
        if calibre_meta.isbn:
            tags.append(f"book:isbn:{calibre_meta.isbn}")
        if calibre_meta.douban_id:
            tags.append(f"book:douban:{calibre_meta.douban_id}")
    parser_output["meta"]["tags"] = tags

    rawdoc_id = str(uuid.uuid4())

    doc = normalize(
        parser_output,
        rawdoc_id=rawdoc_id,
        storage_path=str(calibre_dir.epub_path.resolve()),
        source_uri=source_uri,
        source_type="epub",
    )

    doc = _process_assets(doc, zf, calibre_dir, assets_dir)

    if do_validate:
        validate_document(doc, REPO_ROOT)

    doc_id = doc["doc_id"]

    json_path, md_path = write_document_outputs(
        doc, docs_dir, rawdocs_dir, rawdoc_id, write_done=False,
    )

    print(
        f"doc_id={doc_id} doc_json={json_path} doc_md={md_path}",
        flush=True,
    )


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Parse Calibre EPUB directory into Document schema")
    ap.add_argument("--dir", default="", help="Calibre book directory path")
    ap.add_argument("--file", default="", help="Single .epub file (legacy compat)")
    ap.add_argument("--canonical-url", default="", help="source_uri override")
    ap.add_argument("--work-id", default="", help="Logical work id")
    ap.add_argument("--variant", default="book", help="book|article|...")
    ap.add_argument("--rawdocs", default=None, help="RawDocs dir")
    ap.add_argument("--assets", default=None, help="Assets dir")
    ap.add_argument("--docs", default=None, help="Docs dir")
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--no-validate", action="store_true")
    args = ap.parse_args()

    rawdocs_dir = Path(args.rawdocs or REPO_ROOT / "data" / "rawdocs")
    assets_dir = Path(args.assets or REPO_ROOT / "data" / "assets")
    docs_dir = Path(args.docs or REPO_ROOT / "data" / "docs")
    do_validate = not args.no_validate

    single = (args.dir or args.file or "").strip()
    if not single:
        print(
            "Usage: python sources/epub_file.py --dir '/path/to/Calibre Dir (id)'\n"
            "   or: python sources/epub_file.py --file /path/to/book.epub",
            file=sys.stderr,
        )
        sys.exit(2)

    canonical = args.canonical_url.strip() or f"file://{Path(single).resolve()}"
    work_id = args.work_id.strip()

    run_one(
        single,
        canonical,
        rawdocs_dir,
        assets_dir,
        docs_dir,
        args.timeout,
        do_validate,
        work_id=work_id,
        variant=args.variant.strip() or "book",
    )


if __name__ == "__main__":
    main()
