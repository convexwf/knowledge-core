"""Extract article links from blog.x.com engineering hub HTML (live or Wayback)."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

_RAW_INGEST_ROOT = Path(__file__).resolve().parents[1]
_SITES = _RAW_INGEST_ROOT / "sites"
if str(_SITES) not in sys.path:
    sys.path.insert(0, str(_SITES))

import requests
from bs4 import BeautifulSoup

import blog_x_com

_DEFAULT_HEADERS = blog_x_com.DEFAULT_HEADERS
_YEAR_IN_PATH = re.compile(r"/\d{4}/")


def _inner_url_from_wayback_path(path: str) -> str | None:
    if not path.startswith("/web/"):
        return None
    parts = path.split("/", 3)
    if len(parts) < 4:
        return None
    inner = parts[3]
    if inner.startswith("http://") or inner.startswith("https://"):
        return inner
    return None


def _normalize_href(href: str, base: str) -> str:
    href = (href or "").strip()
    if not href or href.startswith("#"):
        return ""
    abs_url = urljoin(base, href)
    u = urlparse(abs_url)
    if u.netloc.lower() == "web.archive.org":
        inner = _inner_url_from_wayback_path(u.path or "")
        if inner:
            return inner
    return abs_url


def _is_blog_x_article_url(url: str) -> bool:
    u = urlparse(url)
    host = (u.hostname or "").lower()
    if host != "blog.x.com":
        return False
    p = u.path or ""
    if "/engineering/" not in p:
        return False
    tail = p.rstrip("/")
    if tail.endswith("/engineering/en_us") or tail.endswith("/engineering/en_uk"):
        return False
    # Typical posts include a year segment; avoids topic index pages.
    return bool(_YEAR_IN_PATH.search(p))


def fetch_hub_posts(
    list_url: str,
    timeout: int,
    headers: dict[str, str] | None = None,
) -> tuple[list[dict[str, str | None]], str | None]:
    """
    GET hub/listing page, extract article links. Returns (posts, error_message).
    """
    hdrs = headers or _DEFAULT_HEADERS
    try:
        r = requests.get(list_url, headers=hdrs, timeout=timeout)
        r.raise_for_status()
    except requests.RequestException as e:
        return [], str(e)

    raw = r.content
    if blog_x_com._is_cloudflare_challenge(raw):
        return [], (
            "Cloudflare challenge page (not hub HTML). "
            "Use a web.archive.org URL pointing at the engineering hub."
        )

    soup = BeautifulSoup(raw, "lxml")
    seen: set[str] = set()
    posts: list[dict[str, str | None]] = []

    for a in soup.find_all("a", href=True):
        norm = _normalize_href(a["href"], list_url)
        if not norm or not _is_blog_x_article_url(norm):
            continue
        if norm in seen:
            continue
        seen.add(norm)
        title = (a.get_text() or "").strip() or None
        posts.append(
            {
                "title": title,
                "url": norm,
                "published": None,
                "summary": None,
            },
        )

    if not posts:
        return [], "no article links matched (DOM may have changed or page is not the hub)"

    return posts, None
