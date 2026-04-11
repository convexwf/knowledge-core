"""
Write Document JSON and Markdown.
"""
import json
from pathlib import Path
from typing import Any


def _list_item_math_to_md(item: dict[str, Any]) -> str:
    tex = (item.get("math") or "").strip()
    if item.get("display"):
        return f"$$\n{tex}\n$$"
    return f"${tex}$"


def _md_escape_table_cell(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()


def _rows_to_md_table(rows: list[Any]) -> str:
    if not rows:
        return ""
    lines_out: list[str] = []
    for i, row in enumerate(rows):
        if not isinstance(row, list):
            continue
        cells = [_md_escape_table_cell(str(c)) for c in row]
        if not cells:
            continue
        lines_out.append("| " + " | ".join(cells) + " |")
        if i == 0:
            lines_out.append("| " + " | ".join(["---"] * len(cells)) + " |")
    if not lines_out:
        return ""
    return "\n" + "\n".join(lines_out) + "\n"


def _paragraph_items_to_markdown(items: list[Any]) -> str:
    chunks: list[str] = []
    for it in items:
        if isinstance(it, str):
            chunks.append(it)
        elif isinstance(it, dict) and it.get("math") is not None:
            chunks.append(_list_item_math_to_md(it))
        elif isinstance(it, dict) and it.get("cite") is not None:
            continue
        elif isinstance(it, dict) and it.get("table") is not None:
            trows = (it.get("table") or {}).get("rows")
            if trows:
                chunks.append(_rows_to_md_table(trows))
        elif isinstance(it, dict) and it.get("text") is not None:
            chunks.append(it.get("text") or "")

    def _needs_space_between(prev: str, nxt: str) -> bool:
        if not prev or not nxt:
            return False
        pl = prev[-1]
        nf = nxt.lstrip()[:1]
        if not nf:
            return False
        if pl.isalnum() and nf.isalnum():
            return True
        if pl in ".!?:" and nf.isalnum():
            return True
        if pl.isalnum() and nxt.lstrip().startswith("$"):
            return True
        if prev.rstrip().endswith("$") and nf.isalnum():
            return True
        return False

    out: list[str] = []
    for c in chunks:
        if not c:
            continue
        if out and _needs_space_between(out[-1], c):
            out.append(" ")
        out.append(c)
    return "".join(out).strip()


def document_to_markdown(doc: dict[str, Any]) -> str:
    lines = [
        f"# {doc['meta']['title']}\n",
        f"Source: {doc['meta']['source'].get('url') or doc['meta']['source']['path']}\n",
    ]

    def append_list_items(items: list, indent: str = "") -> None:
        for item in items:
            if isinstance(item, dict) and item.get("cite") is not None:
                continue
            elif isinstance(item, dict) and item.get("table") is not None:
                trows = (item.get("table") or {}).get("rows")
                if trows:
                    lines.append(_rows_to_md_table(trows))
            elif isinstance(item, dict) and item.get("math") is not None:
                body = _list_item_math_to_md(item).replace("\n", " ").strip()
                lines.append(indent + "- " + body + "\n")
            elif isinstance(item, dict):
                text = (item.get("text") or "").replace("\n", " ").strip()
                lines.append(indent + "- " + text + "\n")
                if item.get("items"):
                    append_list_items(item["items"], indent + "  ")
            else:
                lines.append(indent + "- " + (str(item) or "").replace("\n", " ") + "\n")

    for s in doc["sections"]:
        if s["type"] == "heading":
            lines.append(f"\n{'#' * s.get('level', 1)} {s.get('content', '')}\n")
        elif s["type"] == "paragraph":
            items = s.get("items") or []
            if items:
                body = _paragraph_items_to_markdown(items)
                if body:
                    lines.append(body + "\n")
            elif s.get("content"):
                lines.append(s["content"] + "\n")
        elif s["type"] == "list" and s.get("items"):
            append_list_items(s["items"])
        elif s["type"] == "table" and s.get("rows"):
            lines.append(_rows_to_md_table(s["rows"]) + "\n")
        elif s["type"] == "code" and s.get("content"):
            lines.append("```\n" + s["content"] + "\n```\n")
        elif s["type"] == "figure" and s.get("assets"):
            for a in s["assets"]:
                path = a.get("path")
                if path:
                    rel = path if path.startswith("assets/") else f"assets/{path}"
                    if not rel.startswith("../"):
                        rel = "../" + rel
                    cap = (a.get("caption") or "").replace("]", "\\]")
                    lines.append(f"![{cap}]({rel})\n")
    return "\n".join(lines)


def write_document_outputs(
    doc: dict[str, Any],
    docs_dir: Path,
    rawdocs_dir: Path,
    rawdoc_id: str,
    write_done: bool = False,
) -> tuple[Path, Path]:
    docs_dir.mkdir(parents=True, exist_ok=True)
    doc_id = doc["doc_id"]
    json_path = docs_dir / f"{doc_id}.json"
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path = docs_dir / f"{doc_id}.md"
    md_path.write_text(document_to_markdown(doc), encoding="utf-8")
    return json_path, md_path
