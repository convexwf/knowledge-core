"""
Write RawDoc HTML + meta.json under rawdocs/. Matches fetch/file.go AcquireFile semantics.
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_rawdoc_html(
    html_bytes: bytes,
    rawdocs_dir: Path,
    source_uri: str,
) -> dict[str, Any]:
    """
    Write data/rawdocs/{uuid}.html and {uuid}.meta.json (singlefile_html, source_uri as given).
    Returns the RawDoc dict (same keys as schemas/rawdoc.json).
    """
    rawdocs_dir.mkdir(parents=True, exist_ok=True)
    rawdoc_id = str(uuid.uuid4())
    storage_path = rawdocs_dir / f"{rawdoc_id}.html"
    storage_path.write_bytes(html_bytes)
    abs_path = str(storage_path.resolve())
    fetch_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    rawdoc: dict[str, Any] = {
        "rawdoc_id": rawdoc_id,
        "source_type": "singlefile_html",
        "source_uri": source_uri,
        "fetch_time": fetch_time,
        "storage_path": abs_path,
        "content_type": "text/html",
        "content_length": len(html_bytes),
        "metadata": {},
    }
    meta_path = rawdocs_dir / f"{rawdoc_id}.meta.json"
    meta_path.write_text(json.dumps(rawdoc, ensure_ascii=False, indent=2), encoding="utf-8")
    return rawdoc
