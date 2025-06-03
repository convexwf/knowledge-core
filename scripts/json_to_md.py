# !/usr/bin/python3
# -*- coding: utf-8 -*-
# @Project : knowledge-core
# @FileName : scripts/json_to_md.py
# @Author : convexwf@gmail.com
# @CreateDate : 2025-06-03 11:33
# @UpdateTime : 2025-06-03 11:33

"""Convert extractor JSON IR (meta + sections) to a readable Markdown file.

Usage:
  python scripts/json_to_md.py data/source.json data/source.md

If output path omitted, writes to same basename with .md under data/.
"""
import json
import sys
import os


def esc_pipe(s):
    return s.replace("|", "\\|") if isinstance(s, str) else s


def table_to_md(header, rows):
    # ensure header exists
    if not header and rows:
        # build simple numeric headers
        header = [f"col{i+1}" for i in range(len(rows[0]))]
    h = "| " + " | ".join(esc_pipe(c) for c in header) + " |\n"
    sep = "| " + " | ".join("---" for _ in header) + " |\n"
    body = "".join("| " + " | ".join(esc_pipe(c) for c in row) + " |\n" for row in rows)
    return h + sep + body


def section_to_md(s):
    t = s.get("type")
    if t == "text":
        return s.get("text", "") + "\n\n"
    if t == "heading":
        tag = s.get("tag", "h2")
        # map h1..h6 to #
        level = 2
        if isinstance(tag, str) and tag.lower().startswith("h") and len(tag) > 1:
            try:
                level = int(tag[1])
            except Exception:
                level = 2
        return "#" * level + " " + s.get("text", "") + "\n\n"
    if t == "table":
        header = s.get("header", [])
        rows = s.get("rows", [])
        return table_to_md(header, rows) + "\n"
    if t == "code":
        code = s.get("code", "") or ""
        lang = s.get("language") or ""
        fence = f"```{lang}" if lang else "```"
        return fence + "\n" + code + "\n```\n\n"
    if t == "image":
        src = s.get("src") or s.get("url") or ""
        cap = s.get("caption") or ""
        return f"![{cap}]({src})\n\n"
    if t == "link":
        href = s.get("href", "")
        text = s.get("text") or href
        return f"[{text}]({href})\n\n"
    # fallback
    return (s.get("text") or "") + "\n\n"


def json_to_md(inp, outp):
    with open(inp, "r", encoding="utf-8") as f:
        data = json.load(f)

    meta = data.get("meta", {})
    sections = data.get("sections", [])

    lines = []
    # simple metadata block
    lines.append("---")
    for k in ("title", "author", "url", "published_at", "fetch_time", "description"):
        if meta.get(k) is not None:
            lines.append(f"{k}: {meta.get(k)}")
    lines.append("---\n")

    # title as H1 if present
    if meta.get("title"):
        lines.append(f"# {meta.get('title')}\n")

    for s in sections:
        lines.append(section_to_md(s))

    outdir = os.path.dirname(outp)
    if outdir and not os.path.exists(outdir):
        os.makedirs(outdir, exist_ok=True)

    with open(outp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main(argv=None):
    argv = argv or sys.argv[1:]
    if not argv:
        print("Usage: json_to_md.py input.json [output.md]")
        sys.exit(1)
    inp = argv[0]
    outp = argv[1] if len(argv) > 1 else os.path.splitext(inp)[0] + ".md"
    json_to_md(inp, outp)
    print("Wrote", outp)


if __name__ == "__main__":
    main()
