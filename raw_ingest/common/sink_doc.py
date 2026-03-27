"""
Write Document JSON, Markdown, and RawDoc .done marker. Vendored from ingest/run_ingest sink.
"""
import json
from pathlib import Path
from typing import Any


def document_to_markdown(doc: dict[str, Any]) -> str:
    lines = [
        f"# {doc['meta']['title']}\n",
        f"Source: {doc['meta']['source'].get('url') or doc['meta']['source']['path']}\n",
    ]

    def append_list_items(items: list, indent: str = "") -> None:
        for item in items:
            if isinstance(item, dict):
                text = (item.get("text") or "").replace("\n", " ").strip()
                lines.append(indent + "- " + text + "\n")
                if item.get("items"):
                    append_list_items(item["items"], indent + "  ")
            else:
                lines.append(indent + "- " + (str(item) or "").replace("\n", " ") + "\n")

    for s in doc["sections"]:
        if s["type"] == "heading":
            lines.append(f"\n{'#' * s.get('level', 1)} {s.get('content', '')}\n")
        elif s["type"] == "paragraph" and s.get("content"):
            lines.append(s["content"] + "\n")
        elif s["type"] == "list" and s.get("items"):
            append_list_items(s["items"])
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
    write_done: bool = True,
) -> tuple[Path, Path]:
    docs_dir.mkdir(parents=True, exist_ok=True)
    doc_id = doc["doc_id"]
    json_path = docs_dir / f"{doc_id}.json"
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path = docs_dir / f"{doc_id}.md"
    md_path.write_text(document_to_markdown(doc), encoding="utf-8")
    if write_done:
        (rawdocs_dir / f"{rawdoc_id}.done").write_text("", encoding="utf-8")
    return json_path, md_path
