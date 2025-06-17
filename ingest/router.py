"""
Resolve which HTML adapter to use for a given source_uri (URL or path).
"""
from pathlib import Path
from urllib.parse import urlparse

import yaml


def load_routes(routes_path: Path) -> list[dict]:
    """Load configs/routes.yaml and return routes list."""
    with open(routes_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return (data or {}).get("routes") or []


def select_adapter(source_uri: str, routes: list[dict], repo_root: Path) -> Path | None:
    """
    First match wins. domain and path_prefix are matched against source_uri (URL or path).
    Returns absolute path to adapter YAML file.
    """
    if not source_uri.strip():
        return None
    parsed = urlparse(source_uri)
    if parsed.scheme and parsed.netloc:
        domain = parsed.netloc.lower()
        path = parsed.path or "/"
    else:
        # Local file path: treat as no domain match unless we have a special rule
        domain = ""
        path = source_uri
    path = path or "/"

    for rule in routes:
        rule_domain = (rule.get("domain") or "*").lower()
        prefix = (rule.get("path_prefix") or "").strip()
        if rule_domain != "*" and rule_domain != domain:
            continue
        if prefix and not path.startswith(prefix):
            continue
        adapter_ref = rule.get("adapter")
        if not adapter_ref:
            continue
        adapter_path = repo_root / adapter_ref
        if adapter_path.exists():
            return adapter_path.resolve()
        if Path(adapter_ref).exists():
            return Path(adapter_ref).resolve()
    return None
