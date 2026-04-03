"""Fetch RSS/Atom URL and normalize entries to post dicts."""
from __future__ import annotations

from calendar import timegm
from datetime import datetime, timezone
from typing import Any

import feedparser
import requests


def _struct_time_to_iso(st: Any) -> str | None:
    if st is None:
        return None
    try:
        dt = datetime.fromtimestamp(timegm(st), tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, TypeError, ValueError):
        return None


def fetch_feed_posts(
    list_url: str,
    timeout: int,
    headers: dict[str, str],
) -> tuple[list[dict[str, str | None]], str | None]:
    """
    GET list_url, parse as RSS/Atom. Returns (posts, error_message).
    error_message is set only when the response is unusable (HTTP error, empty feed, parse failure).
    """
    try:
        r = requests.get(list_url, headers=headers, timeout=timeout)
        r.raise_for_status()
    except requests.RequestException as e:
        return [], str(e)

    parsed = feedparser.parse(r.content)
    if not parsed.entries:
        bozo = getattr(parsed, "bozo_exception", None)
        if parsed.bozo and bozo:
            return [], f"feed parse: {bozo}"
        return [], "no entries in feed"

    posts: list[dict[str, str | None]] = []
    for e in parsed.entries:
        link = (e.get("link") or "").strip()
        if not link and e.get("links"):
            for L in e["links"]:
                if L.get("rel") == "alternate" and L.get("href"):
                    link = (L.get("href") or "").strip()
                    break
            if not link and e["links"]:
                link = (e["links"][0].get("href") or "").strip()

        title = (e.get("title") or "").strip()
        summary = (e.get("summary") or e.get("description") or "").strip() or None
        published = _struct_time_to_iso(
            e.get("published_parsed") or e.get("updated_parsed"),
        )

        posts.append(
            {
                "title": title or None,
                "url": link or None,
                "published": published,
                "summary": summary,
            },
        )

    return posts, None
