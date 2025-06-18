"""
Parse HTML using a YAML adapter: extract meta and content blocks in document order.
"""
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .adapter_loader import load_adapter, parse_meta_selector, get_meta_value


def _select_one(soup: BeautifulSoup, selector: str):
    """Return first match or None."""
    if not selector:
        return None
    try:
        return soup.select_one(selector)
    except Exception:
        return None


def _select_all(container, selector: str):
    """Return all matches (within container if given)."""
    if not selector:
        return []
    try:
        if container is None:
            return []
        return container.select(selector)
    except Exception:
        return []


def _text(elem) -> str:
    if elem is None:
        return ""
    return (elem.get_text() or "").strip()


def _text_node(elem) -> str:
    """Text from a single node (Tag or NavigableString) without recursing into ul/ol."""
    if elem is None:
        return ""
    if hasattr(elem, "get_text"):
        return (elem.get_text() or "").strip()
    return str(elem).strip()


def _list_items_tree(ul_or_ol, base_url: str | None = None) -> list[dict[str, Any] | str]:
    """
    Build nested list structure from ul/ol: each item is either a string (leaf) or
    {"text": str, "items": [...]}. Inline links in text preserved as markdown.
    """
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


def _content_with_links(elem, base_url: str | None = None) -> tuple[str, list[dict[str, str]]]:
    """
    Extract text from element but preserve <a> as markdown [text](url).
    Resolves relative hrefs when base_url is given. Returns (content, links) so
    sections can be marked with annotations.links for downstream.
    """
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


def _attr(elem, name: str) -> str | None:
    if elem is None:
        return None
    return elem.get(name)


def _extract_meta(soup: BeautifulSoup, adapter: dict, source_uri: str) -> dict[str, Any]:
    """Extract metadata from document using adapter meta selectors."""
    meta_config = adapter.get("meta") or {}
    result = {}
    base_url = source_uri if source_uri.startswith("http") else None

    for key in ("title", "url", "published_at", "updated_at"):
        spec = get_meta_value(meta_config, key)
        if spec is None:
            continue
        if key == "authors":
            continue
        if isinstance(spec, list):
            for s in spec:
                sel, attr = parse_meta_selector(s)
                el = _select_one(soup, sel) if sel else None
                if el:
                    result[key] = _attr(el, attr) if attr else _text(el)
                    break
            continue
        sel, attr = parse_meta_selector(spec)
        el = _select_one(soup, sel) if sel else None
        if el:
            result[key] = _attr(el, attr) if attr else _text(el)

    # Authors: single selector returning multiple nodes -> list of strings
    authors_spec = get_meta_value(meta_config, "authors")
    if authors_spec and isinstance(authors_spec, str):
        sel, attr = parse_meta_selector(authors_spec)
        if sel:
            nodes = soup.select(sel)
            result["authors"] = [
                (_attr(n, attr) if attr else _text(n)).strip()
                for n in nodes
                if (_attr(n, attr) if attr else _text(n)).strip()
            ]
    if "authors" not in result:
        result["authors"] = []

    if base_url and result.get("url") and not result["url"].startswith("http"):
        result["url"] = urljoin(base_url, result["url"])
    return result


def _heading_level(tag) -> int:
    """Map tag name to heading level 1-6."""
    if not tag:
        return 1
    name = getattr(tag, "name", None) or ""
    if isinstance(name, str) and len(name) == 2 and name[0] == "h" and name[1].isdigit():
        return min(6, max(1, int(name[1])))
    return 1


def _extract_blocks(
    container, blocks_config: list, content_root_selector: str, base_url: str = ""
) -> list[dict]:
    """
    Extract blocks in document order: walk container's descendants, for each element
    check if it matches any block selector (first match wins), then emit section.
    """
    if not container or not blocks_config:
        return []

    selector_to_block: list[tuple[str, str, dict]] = []
    for block_def in blocks_config:
        btype = block_def.get("type", "paragraph")
        sel = block_def.get("selector")
        if sel:
            selector_to_block.append((sel, btype, block_def))

    sections = []
    seen = set()
    try:
        descendants = list(container.descendants)
    except Exception:
        return []

    for el in descendants:
        if not getattr(el, "name", None):
            continue
        if id(el) in seen:
            continue
        btype, block_def = None, None
        for sel, bt, bd in selector_to_block:
            try:
                if el in (container.select(sel) or []):
                    btype, block_def = bt, bd
                    break
            except Exception:
                continue
        if not btype:
            continue
        seen.add(id(el))
        # Only mark descendants as seen for opaque containers (blockquote, list) so we
        # don't emit inner blocks again. Do NOT mark descendants for p/div so that
        # images or other blocks inside them are still emitted.
        if btype == "list" or (btype == "paragraph" and getattr(el, "name", None) == "blockquote"):
            for desc in el.descendants:
                if getattr(desc, "name", None):
                    seen.add(id(desc))
        attrs_config = block_def.get("attrs") or {}
        section = {"type": btype}
        if btype == "heading":
            section["level"] = _heading_level(el)
            section["content"] = _text(el)
            section["section_id"] = el.get("data-id") or f"heading-{len(sections)}"
        elif btype == "paragraph":
            content, links = _content_with_links(el, base_url or None)
            section["content"] = content
            if links:
                section["annotations"] = {"links": links}
        elif btype == "code":
            section["content"] = _text(el)
            lang = el.get("lang") or (el.get("class") and next((c.replace("language-", "") for c in el.get("class", []) if "language-" in str(c)), None))
            if lang:
                section["annotations"] = {"language": str(lang)}
        elif btype == "figure":
            src = el.get("src") or _attr(el, attrs_config.get("src", "src"))
            caption = el.get("alt") or _attr(el, attrs_config.get("caption", "alt")) or ""
            if src:
                section["assets"] = [{"original_src": src, "caption": caption or None}]
                section["content"] = ""
            else:
                continue
        elif btype == "list":
            section["section_id"] = el.get("data-id") or f"list-{len(sections)}"
            section["items"] = _list_items_tree(el, base_url or None)
            section["content"] = ""
        else:
            content, links = _content_with_links(el, base_url or None)
            section["content"] = content
            if links:
                section["annotations"] = {"links": links}
        sections.append(section)
    return sections


def parse_html(
    html_path: Path | str,
    adapter_path: Path | str,
    source_uri: str = "",
) -> dict[str, Any]:
    """
    Parse HTML file with the given adapter YAML path.
    Returns parser output: { "meta": {...}, "sections": [...], "parser_version": "..." }.
    """
    html_path = Path(html_path)
    adapter_path = Path(adapter_path)
    with open(html_path, "r", encoding="utf-8", errors="replace") as f:
        html = f.read()
    soup = BeautifulSoup(html, "html.parser")
    adapter = load_adapter(adapter_path)

    content = adapter.get("content") or {}
    root_sel = content.get("root") or "body"
    if isinstance(root_sel, str) and root_sel.startswith("css:"):
        root_sel = root_sel[4:].strip()
    container = _select_one(soup, root_sel)
    if not container:
        container = soup.find("body") or soup

    meta = _extract_meta(soup, adapter, source_uri)
    base_url = source_uri if isinstance(source_uri, str) and source_uri.startswith("http") else ""
    sections = _extract_blocks(container, content.get("blocks") or [], root_sel, base_url)

    return {
        "meta": meta,
        "sections": sections,
        "parser_version": "0.1.0",
    }
