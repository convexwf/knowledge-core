# !/usr/bin/python3
# -*- coding: utf-8 -*-
# @Project : knowledge-core
# @FileName : scripts/extract_source.py
# @Author : convexwf@gmail.com
# @CreateDate : 2025-05-29 11:04
# @UpdateTime : 2025-05-29 11:04

import re
import json
import sys
import os
import base64
import hashlib
from datetime import datetime

try:
    from pyquery import PyQuery as pq
except Exception:
    print("pyquery is required. Install with: pip install pyquery lxml")
    raise

try:
    import yaml
except Exception:
    yaml = None
try:
    from PIL import Image
    from io import BytesIO

    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False


DEFAULT_ADAPTER = "adapators/mp_weixin.yaml"


def extract_saved_date(html_text):
    m = re.search(r"saved date:\s*(.+)", html_text)
    if m:
        s = m.group(1).strip()
        try:
            dt = datetime.strptime(s, "%a %b %d %Y %H:%M:%S GMT%z (%Z)")
            return dt.isoformat()
        except Exception:
            return s
    return None


def load_adapter(path):
    if yaml is None:
        raise RuntimeError("PyYAML required. Install with: pip install pyyaml")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def apply_selector(d, html, spec, saved=None):
    # spec can be string like 'css:selector@attr', or list
    if spec is None:
        return None
    if isinstance(spec, list):
        for s in spec:
            v = apply_selector(d, html, s, saved)
            if v:
                return v
        return None

    if isinstance(spec, str):
        if spec == "saved_time" and saved:
            return saved
        if spec.startswith("css:"):
            body = spec[len("css:") :]
            attr = None
            if "@" in body:
                sel, attr = body.split("@", 1)
            else:
                sel = body
            node = d(sel)
            if not node:
                return None
            if attr is None or attr == "text":
                return node.text().strip() or None
            else:
                return node.attr(attr) or None

    return None


def extract_with_adapter(adapter, html, input_path=None):
    d = pq(html)
    saved = extract_saved_date(html)

    meta_cfg = adapter.get("meta", {}) if adapter else {}
    content_cfg = adapter.get("content", {}) if adapter else {}

    meta = {}
    # Extract meta fields using adapter selectors
    for k, spec in meta_cfg.items():
        meta[k] = apply_selector(d, html, spec, saved)

    # defaults / fallbacks
    if not meta.get("title"):
        meta["title"] = (
            d("title").text()
            or apply_selector(d, html, "css:meta[property='og:title']@content")
            or ""
        )
    if not meta.get("url"):
        meta["url"] = (
            apply_selector(
                d,
                html,
                [
                    "css:link[rel='canonical']@href",
                    "css:meta[property='og:url']@content",
                ],
            )
            or None
        )
    if not meta.get("fetch_time"):
        meta["fetch_time"] = saved or datetime.utcnow().isoformat() + "Z"

    # content blocks
    blocks = content_cfg.get("blocks", [])

    # determine root selector from adapter if provided
    root_sel = content_cfg.get("root") if content_cfg else None
    if isinstance(root_sel, str) and root_sel.startswith("css:"):
        root_sel = root_sel[len("css:") :].strip()

    # pick root: adapter root -> #js_content -> body -> document
    root = None
    if root_sel:
        try:
            root = d(root_sel)
        except Exception:
            root = None

    if not root or len(root) == 0:
        root = d("#js_content")
    if not root or len(root) == 0:
        root = d("body")
    if not root or len(root) == 0:
        root = d

    # apply ignore rules (remove unwanted subtrees)
    ignores = content_cfg.get("ignore", []) if content_cfg else []
    if ignores:
        for ig in ignores:
            if isinstance(ig, str) and ig.startswith("css:"):
                ig_sel = ig[len("css:") :].strip()
            else:
                ig_sel = ig
            try:
                # remove matching nodes under root
                root.find(ig_sel).remove()
            except Exception:
                continue

    # remove common noise containers and style/script nodes under root
    try:
        root.find("style, script, noscript, iframe, svg").remove()
    except Exception:
        pass

    def looks_like_css(text):
        if not text:
            return False
        t = text.strip()
        if len(t) < 80:
            return False
        # heuristics: many braces or weui/wx classnames or data-uri-like css
        if ("{" in t and "}" in t) or "wx-root" in t or "weui-" in t:
            return True
        return False

    # prepare images dir
    images_dir = os.path.join("data", "images")
    try:
        os.makedirs(images_dir, exist_ok=True)
    except Exception:
        pass

    def save_data_image(datauri):
        # data:[<mediatype>][;base64],<data>
        m = re.match(r"data:(image/[^;]+);base64,(.+)", datauri, re.I)
        if not m:
            return None
        mime = m.group(1).lower()
        b64 = m.group(2)
        try:
            data = base64.b64decode(b64)
        except Exception:
            return None
        # hash to get filename
        h = hashlib.sha1(data).hexdigest()
        png_name = f"{h}.png"
        png_path = os.path.join(images_dir, png_name)
        try:
            if PIL_AVAILABLE:
                img = Image.open(BytesIO(data))
                # convert to RGBA/RGB as needed
                if img.mode in ("RGBA", "LA"):
                    bg = Image.new("RGBA", img.size, (255, 255, 255, 0))
                    bg.paste(img, (0, 0), img)
                    out = bg.convert("RGBA")
                else:
                    out = img.convert("RGB")
                out.save(png_path, format="PNG")
            else:
                # fallback: just write raw bytes to .png (may be original format)
                with open(png_path, "wb") as f:
                    f.write(data)
        except Exception:
            try:
                with open(png_path, "wb") as f:
                    f.write(data)
            except Exception:
                return None
        # return relative path
        return os.path.join("data", "images", png_name).replace("\\", "/")

    def _strip_root_prefix(sel, root_selector):
        if not sel:
            return sel
        s = sel
        if isinstance(s, str) and s.startswith("css:"):
            s = s[len("css:") :].strip()
        if root_selector:
            rs = root_selector.strip()
            if rs and s.startswith(rs):
                return s[len(rs) :].lstrip()
            # also handle cases like "#id > p" or "#id p"
            if rs and s.startswith(rs + " "):
                return s[len(rs) :].lstrip()
            if rs and s.startswith(rs + ">"):
                return s[len(rs) :].lstrip()
        return s

    sections = []
    # walk in document order under root
    for node in root.find("*").items():
        # skip nodes that contain large CSS/text noise
        try:
            ntext = node.text()
            if looks_like_css(ntext):
                continue
        except Exception:
            pass
        for blk in blocks:
            sel = blk.get("selector")
            if not sel:
                continue
            try:
                sel_rel = _strip_root_prefix(sel, root_sel)
                # if selector becomes empty, skip
                if not sel_rel:
                    continue
                if node.is_(sel_rel):
                    btype = blk.get("type")
                    attrs = blk.get("attrs") or {}
                    if btype == "heading":
                        sections.append(
                            {
                                "type": "heading",
                                "tag": node[0].tag,
                                "text": node.text().strip(),
                            }
                        )
                    elif btype == "paragraph":
                        text = node.text().strip()
                        if text and not looks_like_css(text):
                            sections.append({"type": "paragraph", "text": text})
                    elif btype in ("figure", "image"):
                        item = {"type": "image"}
                        # gather attrs; if src is data: URI, save to file
                        for outk, in_attr in attrs.items():
                            if in_attr == "text":
                                item[outk] = node.text().strip()
                            else:
                                val = node.attr(in_attr) or ""
                                if isinstance(val, str) and val.startswith("data:"):
                                    saved = save_data_image(val)
                                    if saved:
                                        item[outk] = saved
                                    else:
                                        item[outk] = val
                                else:
                                    item[outk] = val
                        sections.append(item)
                    elif btype == "link":
                        href = (
                            node.attr(attrs.get("href", "href"))
                            if attrs
                            else node.attr("href")
                        )
                        text = node.text().strip()
                        sections.append(
                            {"type": "link", "href": href or "", "text": text}
                        )
                    else:
                        sections.append({"type": btype, "text": node.text().strip()})
                    break
            except Exception:
                continue

    headings = [s for s in sections if s.get("type") == "heading"]
    paragraphs = [s for s in sections if s.get("type") == "paragraph"]
    images = [s for s in sections if s.get("type") == "image"]
    links = [s for s in sections if s.get("type") == "link"]

    # enrich some meta defaults
    if "author" not in meta or not meta.get("author"):
        meta["author"] = (
            d("meta[property='og:article:author']").attr("content")
            or d("meta[name='author']").attr("content")
            or None
        )
    if "description" not in meta or not meta.get("description"):
        meta["description"] = (
            d("meta[name='description']").attr("content")
            or d("meta[property='og:description']").attr("content")
            or None
        )
    if "image" not in meta or not meta.get("image"):
        meta["image"] = d("meta[property='og:image']").attr("content") or None

    return {
        "meta": meta,
        "sections": sections,
        "headings": headings,
        "paragraphs": paragraphs,
        "images": images,
        "links": links,
    }


def main(argv=None):
    argv = argv or sys.argv[1:]
    adapter_path = argv[0] if len(argv) >= 1 else DEFAULT_ADAPTER
    input_path = argv[1] if len(argv) >= 2 else "data/source.html"
    output_path = argv[2] if len(argv) >= 3 else "data/source.json"

    if yaml is None:
        print("PyYAML not found. Install with: pip install pyyaml")
        # don't raise; allow limited operation

    with open(input_path, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()

    adapter = None
    try:
        adapter = load_adapter(adapter_path)
    except Exception as e:
        # adapter optional; continue with defaults
        adapter = None

    result = extract_with_adapter(adapter, html, input_path)

    with open(output_path, "w", encoding="utf-8") as out:
        json.dump(result, out, ensure_ascii=False, indent=2)

    print("Wrote", output_path)


if __name__ == "__main__":
    main()
