"""
Optional validation against repo schemas/document.json (referenced by path only).
"""
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def validate_document(doc: dict[str, Any], repo_root: Path) -> None:
    schema_path = repo_root / "schemas" / "document.json"
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    Draft202012Validator(schema).validate(doc)
