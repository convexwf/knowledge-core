"""
Load HTML adapter YAML and resolve selector format: css:selector@attr
"""
import re
from pathlib import Path
from typing import Any

import yaml


def _resolve_adapter_path(adapter_ref: str, repo_root: Path) -> Path:
    """Resolve adapter path (relative to repo root) to absolute path."""
    p = repo_root / adapter_ref
    if not p.exists():
        p = Path(adapter_ref)
    return p.resolve()


def load_adapter(adapter_path: Path) -> dict[str, Any]:
    """Load and return adapter YAML as dict."""
    with open(adapter_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def parse_meta_selector(spec: str) -> tuple[str | None, str | None]:
    """
    Parse meta selector spec: 'css:selector' or 'css:selector@attr'.
    Returns (selector, attr). attr is None for text content.
    """
    if not spec or not isinstance(spec, str):
        return None, None
    spec = spec.strip()
    if not spec.startswith("css:"):
        return None, None
    rest = spec[4:].strip()
    if "@" in rest:
        sel, attr = rest.rsplit("@", 1)
        return sel.strip() or None, attr.strip() or None
    return rest or None, None


def get_meta_value(adapter_meta: dict, key: str) -> str | list[str] | None:
    """Return meta selector spec for key; authors may be a single selector for multiple nodes."""
    if not adapter_meta:
        return None
    v = adapter_meta.get(key)
    if v is None:
        return None
    if isinstance(v, list):
        return v
    return str(v).strip()
