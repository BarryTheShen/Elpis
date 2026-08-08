"""Google News RSS search collector.

Fetches results from Google News's public RSS search endpoint, which supports
search operators such as ``site:``, ``when:``, ``intitle:``, and ``source:``.
No API key is needed.
"""

import logging
from datetime import UTC, datetime
from urllib.parse import quote_plus, urljoin

import feedparser

from condenseit.collectors.article_text import fetch_article_text
from condenseit.collectors.feed_dates import parse_feed_entry_date
from condenseit.collectors.health import collect_with_health
from condenseit.config import GoogleNewsSearchConfig
from condenseit.fetch_headers import digest_fetch_headers
from condenseit.network import httpx_client
from condenseit.services.source_discovery import canonical_url, validate_public_url
from condenseit.store.database import ContentStore

logger = logging.getLogger(__name__)
_MAX_FEED_BODY_CHARS = 512_000
_MAX_REDIRECTS = 3

_BASE_URL = "https://news.google.com/rss/search"


def build_gnews_url(config: GoogleNewsSearchConfig) -> str:
    """Return the Google News RSS search URL for ``config``."""
    lang = config.language.lower()
    country = config.country.upper()
    return (
        f"{_BASE_URL}?q={quote_plus(config.query)}"
        f"&hl={lang}-{country}&gl={country}&ceid={country}:{lang}"
    )


class GoogleNewsCollector:
    """Collect articles from Google News RSS search queries."""

    def __init__(self, sources: list[GoogleNewsSearchConfig]) -> None:
        self.sources = sources
        self._headers = digest_fetch_headers()
        self._client = httpx_client(
            timeout=30.0,
            follow_redirects=False,
            headers=self._headers,
        )

    def collect_all_with_health(
        self,
    ) -> tuple[list[dict[str, str]], list[tuple[str, str | None, int]]]:
        """Return ``(articles, [(rss_url, error_or_none, item_count), ...])``."""
        articles: list[dict[str, str]] = []
        health: list[tuple[str, str | None, int]] = []
        for cfg in self.sources:
            rss_url = build_gnews_url(cfg)
            items, entry = collect_with_health(
                rss_url,
                lambda cfg=cfg, rss_url=rss_url: self._collect_source(cfg, rss_url),
                log_label=f"Google News collect failed for query {cfg.query!r}",
            )
            articles.extend(items)
            health.append(entry)
        return articles, health

    @staticmethod
    def _redirect_url(current: str, response: object) -> str:
        headers = getattr(response, "headers", {}) or {}
        try:
            location = str(headers.get("location", ""))
        except Exception as exc:
            raise ValueError("unsafe redirect URL") from exc
        redirected = validate_public_url(urljoin(current, location))
        if redirected is None:
            raise ValueError("unsafe redirect URL")
        return redirected

    def _call_get(self, url: str) -> object:
        get = getattr(self._client, "get", None)
        if not callable(get):
            raise TypeError("http client must expose get()")
        try:
            return get(url, follow_redirects=False)
        except TypeError as first:
            try:
                return get(url)
            except TypeError:
                raise first

    def _safe_get(self, url: str) -> object:
        current = validate_public_url(url)
        if current is None:
            raise ValueError("unsafe URL")
        for _ in range(_MAX_REDIRECTS + 1):
            response = self._call_get(current)
            final_url = getattr(response, "url", None)
            if final_url and validate_public_url(str(final_url)) is None:
                raise ValueError("unsafe response URL")
            status = getattr(response, "status_code", None)
            if not isinstance(status, int) or not 300 <= status < 400:
                return response
            redirected = self._redirect_url(current, response)
            if redirected == current:
                return response
            current = redirected
        raise ValueError("too many redirects")

    @staticmethod
    def _response_text(response: object) -> str:
        text = getattr(response, "text", "")
        if isinstance(text, bytes):
            text = text.decode("utf-8", errors="replace")
        return str(text or "")[:_MAX_FEED_BODY_CHARS]

    def _collect_source(
        self,
        cfg: GoogleNewsSearchConfig,
        rss_url: str,
    ) -> list[dict[str, str]]:
        resp = self._safe_get(rss_url)
        resp.raise_for_status()
        feed = feedparser.parse(self._response_text(resp))
        candidates: list[tuple[feedparser.FeedParserDict, str]] = []
        seen_links: set[str] = set()
        for entry in getattr(feed, "entries", []) or ():
            if len(candidates) >= cfg.max_items:
                break
            raw_link = entry.get("link") if hasattr(entry, "get") else None
            link = canonical_url(raw_link)
            if link is None or link in seen_links:
                continue
            seen_links.add(link)
            candidates.append((entry, link))

        items: list[dict[str, str]] = []
        for entry, link in candidates:
            title = entry.get("title", "Untitled")
            content = self._extract_content(link, entry)
            if not content.strip():
                continue
            published = self._parse_published(entry)
            items.append(
                {
                    "url": link,
                    "title": title,
                    "content": content,
                    "source": "Google News",
                    "category": cfg.category,
                    "content_hash": ContentStore.content_hash(content),
                    "published_at": published,
                    "collected_at": datetime.now(UTC).isoformat(),
                },
            )
        return items

    def _extract_content(self, url: str, entry: feedparser.FeedParserDict) -> str:
        safe_url = canonical_url(url)
        extracted = fetch_article_text(self._client, safe_url) if safe_url else None
        if extracted:
            return extracted
        summary = entry.get("summary", "")
        return summary if isinstance(summary, str) else str(summary)

    @staticmethod
    def _parse_published(entry: feedparser.FeedParserDict) -> str:
        return parse_feed_entry_date(entry)
