"""
Map parser output to Document schema; insert asset placeholders for figures.
"""
import uuid
from datetime import datetime, timezone
from typing import Any


def normalize(
    parser_output: dict[str, Any],
    rawdoc_id: str,
    storage_path: str,
    source_uri: str,
    source_type: str = "html",
) -> dict[str, Any]:
    """
    Convert parser output to Document schema. Figures keep original_src as placeholder;
    assets stage will resolve and set asset_id/path.
    """
    meta = parser_output.get("meta") or {}
    sections_in = parser_output.get("sections") or []
    parser_version = parser_output.get("parser_version") or "0.1.0"

    doc_id = str(uuid.uuid4())
    ingested_at = datetime.now(timezone.utc).isoformat()

    sections = []
    for i, s in enumerate(sections_in):
        sec = {
            "section_id": s.get("section_id") or f"sec-{i}",
            "type": s.get("type", "paragraph"),
            "content": s.get("content") or "",
            "items": s.get("items") or [],
            "rows": s.get("rows") or [],
            "assets": [],
            "annotations": s.get("annotations") or {},
        }
        if s.get("type") == "heading":
            sec["level"] = s.get("level", 1)
        if s.get("type") == "figure" and s.get("assets"):
            for a in s["assets"]:
                sec["assets"].append({
                    "asset_id": "",  # filled by assets stage
                    "path": "",  # filled by assets stage
                    "caption": a.get("caption"),
                    "_original_src": a.get("original_src"),
                })
            # Remove internal key before final doc if desired; assets stage will replace
        sections.append(sec)

    return {
        "doc_id": doc_id,
        "meta": {
            "title": (meta.get("title") or "").strip() or "Untitled",
            "source": {
                "type": source_type,
                "path": storage_path,
                "url": source_uri if source_uri.startswith("http") else None,
                "rawdoc_id": rawdoc_id,
            },
            "authors": meta.get("authors") or [],
            "published_at": meta.get("published_at") or None,
            "updated_at": meta.get("updated_at") or None,
            "ingested_at": ingested_at,
            "language": meta.get("language") or "",
            "tags": meta.get("tags") or [],
            "parser_version": parser_version,
        },
        "sections": sections,
    }
