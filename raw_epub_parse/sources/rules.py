"""Tag-driven parse rule loader."""

from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None

RULES_DIR = Path(__file__).resolve().parents[1] / "rules"


def _default_rules() -> dict[str, Any]:
    return {
        "name": "default",
        "heading_class_map": {},
        "heading_bold_span": {"enabled": False, "level": 2, "max_length": 120},
        "skip_rules": {"link_density_threshold": 0.5},
        "ignore_paragraph_classes": [],
    }


def load_rules(user_tags: str) -> dict[str, Any]:
    if not user_tags or yaml is None:
        return _default_rules()
    tags = [t.strip() for t in user_tags.split(",") if t.strip()]
    for tag in tags:
        rule_file = RULES_DIR / f"{tag}.yaml"
        if rule_file.is_file():
            try:
                with open(rule_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
    return _default_rules()
