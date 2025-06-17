#!/usr/bin/env python3
"""
End-to-end ingest: acquire (Go) -> parse -> normalize -> assets -> sink.
Per spec: acquisition is in Go; this script invokes the Go acquire binary when URL/file given.
Usage:
  python -m ingest.run_ingest --url https://...
  python -m ingest.run_ingest --file path/to/local.html --url https://...
  python -m ingest.run_ingest --rawdoc-id <id>   # ingest only, from existing RawDoc
Requires: Go binary bin/acquire (make build).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

# Repo root (parent of ingest/)
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ingest.assets import process_assets
from ingest.normalize import normalize
from ingest.html.parser import parse_html
from ingest.router import load_routes, select_adapter


def run_acquire(args, rawdocs_dir: Path) -> dict:
    """Run Go acquire binary; return RawDoc dict from emitted meta file path."""
    acquire_bin = REPO_ROOT / "bin" / "acquire"
    if not acquire_bin.exists():
        print("Acquire must be implemented in Go (spec 5.1). Build with: make build", file=sys.stderr)
        sys.exit(1)
    cmd = [
        str(acquire_bin),
        "-rawdocs", str(rawdocs_dir),
    ]
    if args.file:
        html_path = Path(args.file)
        if not html_path.is_absolute():
            html_path = REPO_ROOT / html_path
        cmd.extend(["-file", str(html_path)])
        if args.url:
            cmd.extend(["-source-uri", args.url])
    else:
        cmd.extend(["-url", args.url])
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr or result.stdout, file=sys.stderr)
        sys.exit(1)
    meta_path = result.stdout.strip().splitlines()[0].strip()
    with open(meta_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_rawdoc_meta(rawdocs_dir: Path, rawdoc_id: str) -> dict | None:
    """Load RawDoc meta by rawdoc_id from rawdocs_dir."""
    meta_path = rawdocs_dir / f"{rawdoc_id}.meta.json"
    if not meta_path.exists():
        return None
    with open(meta_path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser(description="Ingest URL or local HTML into normalized docs")
    ap.add_argument("--url", default="", help="Source URL (for routing and asset base URL)")
    ap.add_argument("--file", default="", help="Local HTML file (if set, use instead of fetching URL)")
    ap.add_argument("--rawdoc-id", default="", help="Ingest only: process this existing RawDoc")
    ap.add_argument("--rawdocs", default=None, help="RawDocs directory (default: data/rawdocs)")
    ap.add_argument("--assets", default=None, help="Assets directory (default: data/assets)")
    ap.add_argument("--docs", default=None, help="Output docs directory (default: data/docs)")
    ap.add_argument("--config", default=None, help="Routes config (default: configs/routes.yaml)")
    args = ap.parse_args()

    rawdocs_dir = Path(args.rawdocs or REPO_ROOT / "data" / "rawdocs")
    assets_dir = Path(args.assets or REPO_ROOT / "data" / "assets")
    docs_dir = Path(args.docs or REPO_ROOT / "data" / "docs")
    config_path = Path(args.config or REPO_ROOT / "configs" / "routes.yaml")

    if args.rawdoc_id:
        # Skip if already processed (poller / ingest-all)
        if (rawdocs_dir / f"{args.rawdoc_id}.done").exists():
            print("Already processed:", args.rawdoc_id)
            sys.exit(0)
        # Ingest only: load existing RawDoc meta
        rawdoc = load_rawdoc_meta(rawdocs_dir, args.rawdoc_id)
        if not rawdoc:
            print(f"RawDoc not found: {args.rawdoc_id}", file=sys.stderr)
            sys.exit(1)
    elif args.file or args.url:
        # Full pipeline: acquire then ingest
        rawdoc = run_acquire(args, rawdocs_dir)
    else:
        print("Provide --url, --file, or --rawdoc-id", file=sys.stderr)
        sys.exit(1)

    rawdoc_id = rawdoc["rawdoc_id"]
    storage_path = rawdoc["storage_path"]
    source_uri = rawdoc["source_uri"]
    source_type = rawdoc["source_type"]

    # Router: select adapter for HTML
    if source_type not in ("url", "singlefile_html"):
        print(f"Unsupported source_type: {source_type}", file=sys.stderr)
        sys.exit(1)
    routes = load_routes(config_path)
    adapter_path = select_adapter(source_uri, routes, REPO_ROOT)
    if not adapter_path:
        adapter_path = REPO_ROOT / "ingest" / "html" / "adapters" / "generic.yaml"
        if not adapter_path.exists():
            print("No adapter selected and generic not found", file=sys.stderr)
            sys.exit(1)

    # Parse
    parser_output = parse_html(storage_path, adapter_path, source_uri=source_uri)

    # Normalize
    doc = normalize(
        parser_output,
        rawdoc_id=rawdoc_id,
        storage_path=storage_path,
        source_uri=source_uri,
        source_type="html",
    )

    # Assets
    docs_dir.mkdir(parents=True, exist_ok=True)
    doc = process_assets(doc, assets_dir, base_url=args.url or source_uri if source_uri.startswith("http") else None)

    # Sink
    doc_id = doc["doc_id"]
    json_path = docs_dir / f"{doc_id}.json"
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    # Optional: write Markdown (images use ../assets/ so they resolve when viewing docs/*.md)
    md_path = docs_dir / f"{doc_id}.md"
    lines = [f"# {doc['meta']['title']}\n", f"Source: {doc['meta']['source'].get('url') or doc['meta']['source']['path']}\n"]
    for s in doc["sections"]:
        if s["type"] == "heading":
            lines.append(f"\n{'#' * s.get('level', 1)} {s.get('content', '')}\n")
        elif s["type"] == "paragraph" and s.get("content"):
            lines.append(s["content"] + "\n")
        elif s["type"] == "code" and s.get("content"):
            lines.append("```\n" + s["content"] + "\n```\n")
        elif s["type"] == "figure" and s.get("assets"):
            for a in s["assets"]:
                path = a.get("path")
                if path:
                    rel = path if path.startswith("assets/") else f"assets/{path}"
                    if not rel.startswith("../"):
                        rel = "../" + rel
                    cap = (a.get("caption") or "").replace("]", "\\]")
                    lines.append(f"![{cap}]({rel})\n")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    # Mark RawDoc as processed (for poller / ingest-all)
    if args.rawdoc_id:
        (rawdocs_dir / f"{rawdoc_id}.done").write_text("")

    print("rawdoc_id:", rawdoc_id)
    print("doc_id:", doc_id)
    print("title:", doc["meta"]["title"])
    print("sections:", len(doc["sections"]))
    print("wrote:", json_path, md_path)


if __name__ == "__main__":
    main()
