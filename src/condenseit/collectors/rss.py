"""RSS and Atom feed collection."""

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.error import URLError
from urllib.parse import urljoin
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
    urlopen,
)

import feedparser
import httpx
import trafilatura

from condenseit.collectors.feed_dates import parse_feed_entry_date
from condenseit.collectors.health import collect_with_health
from condenseit.config import FeedConfig
from condenseit.fetch_headers import digest_fetch_headers
from condenseit.network import (
    httpx_client,
    load_network_proxy,
    requests_session,
    safe_network_error,
)
from condenseit.services.source_discovery import canonical_url, validate_public_url
from condenseit.store.database import ContentStore

logger = logging.getLogger(__name__)
_ARTICLE_EXTRACTION_WORKERS = 8
_MAX_FEED_BODY_CHARS = 512_000
_MAX_FEED_BODY_BYTES = _MAX_FEED_BODY_CHARS
_MAX_REDIRECTS = 3
_DEFAULT_URLOPEN = urlopen


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        req,
        fp,
        code,
        msg,
        headers,
        newurl,
    ):
        resolved = validate_public_url(urljoin(req.full_url, newurl))
        if resolved is None:
            raise ValueError("unsafe redirect URL")
        return super().redirect_request(
            req,
            fp,
            code,
            msg,
            headers,
            resolved,
        )


_SAFE_URLOPEN = build_opener(_SafeRedirectHandler)

# Matches og:image or twitter:image meta tags in any attribute order.
# Group 1 captures the content value.
_OG_IMAGE_RE = re.compile(
    r'<meta\b[^>]*\bproperty=["\']og:image["\'][^>]*\bcontent=["\']([^"\']+)["\']'
    r'|<meta\b[^>]*\bcontent=["\']([^"\']+)["\'][^>]*\bproperty=["\']og:image["\']'
    r'|<meta\b[^>]*\bname=["\']twitter:image["\'][^>]*\bcontent=["\']([^"\']+)["\']'
    r'|<meta\b[^>]*\bcontent=["\']([^"\']+)["\'][^>]*\bname=["\']twitter:image["\']',
    re.IGNORECASE,
)


def _extract_og_image(html_text: str) -> str | None:
    """Return the first og:image or twitter:image URL found in ``html_text``."""
    match = _OG_IMAGE_RE.search(html_text)
    if not match:
        return None
    for group in match.groups():
        if group:
            return group.strip()
    return None


@dataclass
class CollectedArticle:
    url: str
    title: str
    content: str
    source: str
    category: str
    published_at: str
    content_hash: str
    image_url: str | None = field(default=None)

    def to_dict(self) -> dict[str, str | None]:
        return {
            "url": self.url,
            "title": self.title,
            "content": self.content,
            "source": self.source,
            "category": self.category,
            "content_hash": self.content_hash,
            "published_at": self.published_at,
            "collected_at": datetime.now(UTC).isoformat(),
            "image_url": self.image_url,
        }


class RSSCollector:
    def __init__(self, feeds: list[FeedConfig]) -> None:
        self.feeds = feeds
        self.fetch_headers = digest_fetch_headers()
        self.client = httpx_client(
            timeout=30.0,
            follow_redirects=False,
            headers=self.fetch_headers,
        )

    def collect_feed_results(
        self,
    ) -> list[tuple[FeedConfig, list[CollectedArticle], str | None]]:
        """Per-feed collection; ``error`` is None on success."""
        out: list[tuple[FeedConfig, list[CollectedArticle], str | None]] = []
        for feed in self.feeds:
            items, (_url, error, _count) = collect_with_health(
                feed.url,
                lambda feed=feed: self._collect_feed(feed),
                log_label=f"Failed to collect feed {feed.url}",
            )
            out.append((feed, items, error))
        return out

    def collect_all(self) -> list[CollectedArticle]:
        articles: list[CollectedArticle] = []
        for _feed, items, _err in self.collect_feed_results():
            articles.extend(items)
        return articles

    def _collect_feed(self, feed: FeedConfig) -> list[CollectedArticle]:
        parsed = feedparser.parse(self._fetch_feed_text(feed.url))
        source_title = parsed.feed.get("title", feed.url)
        candidates: list[tuple[feedparser.FeedParserDict, str]] = []
        seen_links: set[str] = set()
        for entry in getattr(parsed, "entries", []) or ():
            if len(candidates) >= feed.max_items:
                break
            raw_link = entry.get("link") if hasattr(entry, "get") else None
            link = canonical_url(raw_link)
            if link is None or link in seen_links:
                continue
            seen_links.add(link)
            candidates.append((entry, link))
        if not candidates:
            return []

        # ``executor.map`` yields in input order even when page requests finish
        # out of order, keeping the feed's deterministic ordering intact.
        with ThreadPoolExecutor(
            max_workers=min(_ARTICLE_EXTRACTION_WORKERS, len(candidates)),
        ) as executor:
            extracted = executor.map(
                lambda candidate: self._extract_content(
                    candidate[1],
                    candidate[0],
                ),
                candidates,
            )
            items: list[CollectedArticle] = []
            for (entry, link), (content, image_url) in zip(candidates, extracted):
                if not content.strip():
                    continue
                title = entry.get("title", "Untitled")
                published = self._parse_published(entry)
                items.append(
                    CollectedArticle(
                        url=link,
                        title=title,
                        content=content,
                        source=source_title,
                        category=feed.category,
                        published_at=published,
                        content_hash=ContentStore.content_hash(content),
                        image_url=image_url,
                    ),
                )
        return items

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
        get = getattr(self.client, "get", None)
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

    def _fetch_feed_text(self, url: str) -> str:
        safe_url = validate_public_url(url)
        if safe_url is None:
            raise ValueError("unsafe URL")
        response = self._safe_get(safe_url)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 403:
                raise
            return self._fetch_feed_text_with_urllib(safe_url, exc)
        return self._response_text(response)

    def _fetch_feed_text_with_urllib(
        self,
        url: str,
        original_exc: httpx.HTTPStatusError,
    ) -> str:
        safe_url = validate_public_url(url)
        if safe_url is None:
            raise ValueError("unsafe URL")
        settings = load_network_proxy()
        if settings.proxy_url.lower().startswith(("socks5://", "socks5h://")):
            try:
                current = safe_url
                with requests_session(settings) as session:
                    for _ in range(_MAX_REDIRECTS + 1):
                        response = session.get(
                            current,
                            headers=self.fetch_headers,
                            timeout=30.0,
                            allow_redirects=False,
                        )
                        status = getattr(response, "status_code", None)
                        if isinstance(status, int) and 300 <= status < 400:
                            current = self._redirect_url(current, response)
                            continue
                        response.raise_for_status()
                        return str(response.text or "")[:_MAX_FEED_BODY_CHARS]
                raise ValueError("too many redirects")
            except ValueError:
                raise
            except Exception as exc:
                raise original_exc from exc
        logger.info(
            "RSS feed %s returned 403 via httpx; retrying with urllib",
            safe_url,
        )
        request = Request(safe_url, headers=self.fetch_headers)
        try:
            opener = (
                _SAFE_URLOPEN if urlopen is _DEFAULT_URLOPEN else None
            )
            opened = (
                opener.open(request, timeout=30.0)
                if opener is not None
                else urlopen(request, timeout=30.0)
            )
            with opened as response:
                final_url = getattr(response, "geturl", lambda: safe_url)()
                if final_url and validate_public_url(str(final_url)) is None:
                    raise ValueError("unsafe response URL")
                try:
                    body = response.read(_MAX_FEED_BODY_BYTES)
                except TypeError:
                    body = response.read()
                headers = getattr(response, "headers", None)
                get_charset = getattr(headers, "get_content_charset", None)
                encoding = get_charset() if callable(get_charset) else None
        except ValueError:
            raise
        except (OSError, URLError) as exc:
            raise original_exc from exc
        if isinstance(body, bytes):
            return body.decode(encoding or "utf-8", errors="replace")[
                :_MAX_FEED_BODY_CHARS
            ]
        return str(body or "")[:_MAX_FEED_BODY_CHARS]

    def _extract_content(
        self,
        url: str,
        entry: feedparser.FeedParserDict,
    ) -> tuple[str, str | None]:
        """Fetch the article page and return ``(text_content, image_url)``.

        ``image_url`` is the first ``og:image`` or ``twitter:image`` found on
        the page, or ``None`` when unavailable.
        """
        image_url: str | None = None
        try:
            page = self._safe_get(url)
            page.raise_for_status()
            page_text = self._response_text(page)
            image_url = _extract_og_image(page_text)
            extracted = trafilatura.extract(
                page_text,
                include_comments=False,
            )
            if extracted:
                return extracted, image_url
        except Exception as exc:
            logger.debug(
                "article fetch failed for %s: %s",
                canonical_url(url) or "<unsafe-url>",
                safe_network_error(exc, load_network_proxy()),
            )
        summary = entry.get("summary", "")
        content = summary if isinstance(summary, str) else str(summary)
        return content, image_url

    @staticmethod
    def _parse_published(entry: feedparser.FeedParserDict) -> str:
        return parse_feed_entry_date(entry)


def collect_rss_feeds(feeds: list[FeedConfig]) -> list[dict[str, str]]:
    return [a.to_dict() for a in RSSCollector(feeds).collect_all()]
