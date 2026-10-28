"""RSS news-feed service for current-affairs discovery.

Fetches a small, configurable set of reputable public RSS feeds with
per-request timeouts, normalizes entries into a consistent item format,
and keeps a short in-memory cache so repeated mobile refreshes do not
re-download feeds.

Only feed-provided metadata is used: no article pages are scraped and no
text, dates, or source details are fabricated. A feed item's `summary`
is exactly what the source feed published as its description.
"""

import html
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request

import feedparser

DEFAULT_FEEDS: List[Dict[str, str]] = [
    {
        "name": "The Hindu — National",
        "url": "https://www.thehindu.com/news/national/feeder/default.rss",
    },
    {
        "name": "The Hindu — International",
        "url": "https://www.thehindu.com/news/international/feeder/default.rss",
    },
    {
        "name": "Indian Express — India",
        "url": "https://indianexpress.com/section/india/feed/",
    },
    {
        "name": "BBC World",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
    },
]

_REQUEST_TIMEOUT_SECONDS = 15
_CACHE_TTL_SECONDS = 15 * 60          # avoid repeated identical downloads
_MAX_ITEMS_PER_FEED = 12
_USER_AGENT = "Mozilla/5.0 (compatible; NewQBackend/0.3; news reader)"
_REQUEST_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

_cache_lock = threading.Lock()
_feed_cache: Dict[str, tuple] = {}  # url -> (fetched_at_epoch, result_dict)


class FetchFailure(Exception):
    """A feed could not be downloaded (network, timeout, HTTP error)."""


def _configured_feeds() -> List[Dict[str, str]]:
    """Allow overriding the default feed set via NEWQ_FEED_URLS.

    Accepts "name=url" segments separated by semicolons or commas.
    """
    override = os.getenv("NEWQ_FEED_URLS", "").strip()
    if not override:
        return DEFAULT_FEEDS

    feeds = []
    for segment in re.split(r"[;,]", override):
        segment = segment.strip()
        if not segment:
            continue
        if "=" in segment:
            name, url = segment.split("=", 1)
            feeds.append({"name": name.strip() or url.strip(), "url": url.strip()})
        else:
            feeds.append({"name": segment.rstrip("/").split("/")[-1] or segment, "url": segment})
    return feeds


def _strip_html(value: Optional[str]) -> str:
    """Remove tags and unescape entities from a feed-provided summary."""
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _fetch_feed_bytes(url: str) -> bytes:
    req = urllib_request.Request(url, headers=_REQUEST_HEADERS)
    with urllib_request.urlopen(req, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
        return response.read()


def _parse_published(entry: Any) -> str:
    """Return an ISO-8601 UTC timestamp string, or "" when unknown."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return ""
    try:
        published = datetime.fromtimestamp(time.mktime(parsed), tz=timezone.utc)
        return published.isoformat()
    except (OverflowError, ValueError):
        return ""


def _normalize_entry(entry: Any, source_name: str) -> Optional[Dict[str, Any]]:
    title = _strip_html(entry.get("title", "")).strip()
    link = (entry.get("link") or "").strip()
    summary = _strip_html(entry.get("summary") or entry.get("description") or "")

    if not title:
        return None

    return {
        "title": title,
        "summary": summary,
        "source": source_name,
        "published": _parse_published(entry),
        "url": _is_safe_url(link) and link or "",
    }


def _is_safe_url(url: str) -> bool:
    return url.lower().startswith("http://") or url.lower().startswith("https://")


def _parse_feed(name: str, url: str, raw: bytes) -> List[Dict[str, Any]]:
    parsed = feedparser.parse(raw)
    items = []
    for entry in parsed.entries:
        item = _normalize_entry(entry, name)
        if item:
            items.append(item)
        if len(items) >= _MAX_ITEMS_PER_FEED:
            break
    return items


def get_news_feed(force_refresh: bool = False) -> Dict[str, Any]:
    """Fetch, cache, and normalize the configured RSS feeds.

    Returns:
        {
          "generated_at": ISO timestamp of this response,
          "feeds": [{name, url, ok, error?, item_count}, ...],
          "items": [{title, summary, source, published, url}, ...]
        }
    Items are sorted newest-first when dates are available.
    """
    feeds = _configured_feeds()
    now = time.time()

    results = []
    all_items = []

    for feed in feeds:
        name, url = feed["name"], feed["url"]
        cached = None

        if not force_refresh and _is_safe_url(url):
            with _cache_lock:
                cached = _feed_cache.get(url)

        if cached and now - cached[0] < _CACHE_TTL_SECONDS:
            feed_result = cached[1]
            results.append(feed_result)
            all_items.extend(feed_result.get("items", []))
            continue

        try:
            if not _is_safe_url(url):
                raise FetchFailure("Only http and https feed URLs are allowed.")

            raw = _fetch_feed_bytes(url)
            items = _parse_feed(name, url, raw)

            if not items:
                raise FetchFailure("The feed returned no readable news items.")

            feed_result = {
                "name": name,
                "url": url,
                "ok": True,
                "item_count": len(items),
            }

            with _cache_lock:
                _feed_cache[url] = (now, {"items": items, "feed": feed_result})

            results.append(feed_result)
            all_items.extend(items)

        except (FetchFailure, urllib_error.URLError, OSError) as exc:
            reason = getattr(exc, "reason", None) or exc
            feed_result = {
                "name": name,
                "url": url,
                "ok": False,
                "error": f"Feed unavailable: {reason}",
                "item_count": 0,
            }
            results.append(feed_result)

    all_items.sort(key=lambda item: item.get("published") or "", reverse=True)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "feeds": results,
        "items": all_items,
    }
