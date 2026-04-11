"""Resolve repository root path."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def schemas_dir() -> Path:
    return REPO_ROOT / "schemas"
