#!/usr/bin/env python3
"""
Poll data/rawdocs for unprocessed RawDocs and run ingest. For Docker ingest service.
Usage: python -m ingest.poller [--interval 30] [--rawdocs dir] [--assets dir] [--docs dir]
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def main():
    ap = argparse.ArgumentParser(description="Poll rawdocs and ingest unprocessed")
    ap.add_argument("--interval", type=int, default=30, help="Poll interval in seconds")
    ap.add_argument("--rawdocs", default=None, help="RawDocs directory")
    ap.add_argument("--assets", default=None, help="Assets directory")
    ap.add_argument("--docs", default=None, help="Output docs directory")
    ap.add_argument("--config", default=None, help="Routes config")
    args = ap.parse_args()

    rawdocs_dir = Path(args.rawdocs or REPO_ROOT / "data" / "rawdocs")
    assets_dir = Path(args.assets or REPO_ROOT / "data" / "assets")
    docs_dir = Path(args.docs or REPO_ROOT / "data" / "docs")
    config = args.config or str(REPO_ROOT / "configs" / "routes.yaml")

    rawdocs_dir.mkdir(parents=True, exist_ok=True)

    while True:
        metas = list(rawdocs_dir.glob("*.meta.json"))
        for meta_path in metas:
            # stem of "abc123.meta.json" is "abc123.meta" -> rawdoc_id = "abc123"
            rawdoc_id = meta_path.stem.removesuffix(".meta") if meta_path.stem.endswith(".meta") else meta_path.stem
            # Skip if already processed (.done marker)
            done_path = rawdocs_dir / f"{rawdoc_id}.done"
            if done_path.exists():
                continue
            cmd = [
                sys.executable, "-m", "ingest.run_ingest",
                "--rawdoc-id", rawdoc_id,
                "--rawdocs", str(rawdocs_dir),
                "--assets", str(assets_dir),
                "--docs", str(docs_dir),
                "--config", config,
            ]
            result = subprocess.run(cmd, cwd=REPO_ROOT)
            if result.returncode == 0:
                done_path.write_text("")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
