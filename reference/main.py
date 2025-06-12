# !/usr/bin/python3
# -*- coding: utf-8 -*-
# @Project : knowledge-core
# @FileName : main.py
# @Author : convexwf@gmail.com
# @CreateDate : 2025-05-29 11:04
# @UpdateTime : 2025-05-29 11:04

import os
import json
import uuid
import requests
from urllib.parse import urljoin, urlparse
from pyquery import PyQuery as pq


def ensure_dir(path: str):
    """Create directory if it does not exist."""
    os.makedirs(path, exist_ok=True)


def download_image(img_url: str, save_dir: str, index: int) -> str:
    """
    Download image and save it locally.
    Returns relative asset path.
    """
    parsed = urlparse(img_url)
    ext = os.path.splitext(parsed.path)[1] or ".png"
    filename = f"img_{index:03d}{ext}"
    filepath = os.path.join(save_dir, filename)

    try:
        resp = requests.get(img_url, timeout=10)
        resp.raise_for_status()
        with open(filepath, "wb") as f:
            f.write(resp.content)
        return f"assets/{filename}"
    except Exception as e:
        print(f"[WARN] Failed to download image {img_url}: {e}")
        return None


def parse_html_to_json(html_path: str, output_dir: str):
    ensure_dir(output_dir)
    assets_dir = os.path.join(output_dir, "assets")
    ensure_dir(assets_dir)

    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    doc = pq(html)

    # ---------- Meta ----------
    title = doc("title").text() or "Untitled Document"

    result = {
        "doc_id": str(uuid.uuid4()),
        "meta": {
            "title": title,
            "source": {"type": "html", "path": os.path.basename(html_path)},
            "authors": [],
            "published_at": None,
            "ingested_at": None,
            "language": "zh",
            "tags": [],
            "reading_status": "unread",
        },
        "sections": [],
    }

    section_counter = 1
    image_counter = 1

    # ---------- Content Parsing ----------
    for elem in doc("body").children().items():

        tag = elem[0].tag.lower()

        # ---- Headings ----
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(tag[1])
            result["sections"].append(
                {
                    "section_id": f"h{section_counter}",
                    "type": "heading",
                    "level": level,
                    "format": "text",
                    "content": elem.text(),
                }
            )
            section_counter += 1

        # ---- Paragraphs ----
        elif tag == "p":
            text = elem.text().strip()
            if text:
                result["sections"].append(
                    {
                        "section_id": f"p{section_counter}",
                        "type": "paragraph",
                        "format": "text",
                        "content": text,
                    }
                )
                section_counter += 1

        # ---- Lists ----
        elif tag in {"ul", "ol"}:
            items = [li.text() for li in elem("li").items()]
            if items:
                result["sections"].append(
                    {
                        "section_id": f"list{section_counter}",
                        "type": "list",
                        "format": "text",
                        "items": items,
                    }
                )
                section_counter += 1

        # ---- Code Blocks ----
        elif tag == "pre":
            code = elem.text()
            if code:
                result["sections"].append(
                    {
                        "section_id": f"code{section_counter}",
                        "type": "code",
                        "format": "plain",
                        "content": code,
                        "annotations": {"language": "unknown"},
                    }
                )
                section_counter += 1

        # ---- Images ----
        elif tag == "img":
            src = elem.attr("src")
            if src:
                img_url = src
                asset_path = download_image(img_url, assets_dir, image_counter)
                image_counter += 1

                if asset_path:
                    result["sections"].append(
                        {
                            "section_id": f"fig{section_counter}",
                            "type": "figure",
                            "format": "image",
                            "assets": [asset_path],
                            "caption": elem.attr("alt") or None,
                        }
                    )
                    section_counter += 1

        # ---- Ignore other tags for v1 ----
        else:
            continue

    # ---------- Save JSON ----------
    output_json = os.path.join(output_dir, "doc.json")
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[OK] Parsed document saved to {output_json}")


if __name__ == "__main__":
    parse_html_to_json(html_path="data/source.html", output_dir="doc_folder")
