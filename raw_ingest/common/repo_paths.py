"""Resolve repository root and schema paths (common/ lives under raw_ingest/)."""
from pathlib import Path

# common/ -> raw_ingest/ -> repo root
REPO_ROOT = Path(__file__).resolve().parents[2]


def schemas_dir() -> Path:
    return REPO_ROOT / "schemas"
