"""
Resolve figure refs: download or decode images, save to assets/, rewrite Document with paths.

Image format: we preserve the source format (spec 6.5: assets/<asset_id>.<ext>).
If the page uses data:image/webp;base64,... or Content-Type image/webp, we save as .webp.
No conversion to PNG/JPG is done unless we add an optional policy later.
"""
import base64
import hashlib
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _ext_from_content_type(ct: str) -> str:
    if "png" in ct:
        return ".png"
    if "jpeg" in ct or "jpg" in ct:
        return ".jpg"
    if "gif" in ct:
        return ".gif"
    if "webp" in ct:
        return ".webp"
    return ".png"


def _asset_id_from_bytes(data: bytes, ext: str) -> str:
    h = hashlib.sha256(data[:65536]).hexdigest()[:16]
    return f"{h}{ext}"


def resolve_src(src: str, base_url: str | None) -> tuple[bytes | None, str]:
    """
    Resolve image src to bytes. Handles http(s) URLs and data: URLs.
    Returns (bytes, ext) or (None, "") on failure.
    """
    src = (src or "").strip()
    if not src:
        return None, ""

    if src.startswith("data:"):
        # data:image/png;base64,...
        m = re.match(r"data:image/(\w+);base64,(.+)", src)
        if m:
            try:
                data = base64.b64decode(m.group(2))
                ext = "." + (m.group(1).lower() or "png")
                if ext == ".jpeg":
                    ext = ".jpg"
                return data, ext
            except Exception:
                return None, ""
        return None, ""

    if src.startswith("http://") or src.startswith("https://"):
        try:
            r = requests.get(src, timeout=15)
            r.raise_for_status()
            ct = r.headers.get("Content-Type", "")
            ext = _ext_from_content_type(ct) or ".png"
            return r.content, ext
        except Exception:
            return None, ""
    if base_url:
        url = urljoin(base_url, src)
        try:
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            ct = r.headers.get("Content-Type", "")
            ext = _ext_from_content_type(ct) or ".png"
            return r.content, ext
        except Exception:
            return None, ""
    return None, ""


def process_assets(
    doc: dict[str, Any],
    assets_dir: Path,
    base_url: str | None = None,
) -> dict[str, Any]:
    """
    For each section with assets (figure), resolve original_src, save to assets_dir,
    rewrite section.assets with asset_id and path. Removes _original_src.
    """
    doc = dict(doc)
    sections = list(doc.get("sections") or [])
    ensure_dir(assets_dir)
    base_url = base_url or (doc.get("meta") or {}).get("source", {}).get("url")

    for sec in sections:
        if sec.get("type") != "figure" or not sec.get("assets"):
            continue
        new_assets = []
        for a in sec["assets"]:
            orig = a.get("_original_src")
            if not orig:
                new_assets.append({
                    "asset_id": a.get("asset_id") or "",
                    "path": a.get("path") or "",
                    "caption": a.get("caption"),
                })
                continue
            data, ext = resolve_src(orig, base_url)
            if not data:
                new_assets.append({
                    "asset_id": "",
                    "path": "",
                    "caption": a.get("caption"),
                })
                continue
            asset_id = _asset_id_from_bytes(data, ext)
            out_path = assets_dir / asset_id
            out_path.write_bytes(data)
            rel_path = f"assets/{asset_id}"
            new_assets.append({
                "asset_id": asset_id,
                "path": rel_path,
                "caption": a.get("caption"),
            })
        sec["assets"] = new_assets
    doc["sections"] = sections
    return doc
