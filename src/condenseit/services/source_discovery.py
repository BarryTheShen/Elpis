"""Read-only publisher/source discovery for the authenticated admin UI.

This module deliberately has no store dependency. A caller supplies the
current source rows when it wants duplicate markers; discovery itself only
reads Google News and public publisher pages, verifies feed candidates, and
returns bounded evidence suitable for the browser.
"""

from __future__ import annotations

import html
import ipaddress
import json
import re
import socket
from collections import OrderedDict
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from itertools import islice
from typing import Any
from urllib.parse import quote_plus, urljoin, urlsplit, urlunsplit

import feedparser

from condenseit.fetch_headers import digest_fetch_headers
from condenseit.network import httpx_client

GOOGLE_NEWS_SEARCH_URL = "https://news.google.com/rss/search"

MAX_QUERY_CHARS = 500
MAX_LANGUAGE_CHARS = 8
MAX_COUNTRY_CHARS = 2
MAX_DISCOVERY_RESULTS = 200
MAX_DISCOVERY_LIMIT = 200
MAX_PAGE = 1_000
MAX_URL_CHARS = 2_048
MAX_BODY_CHARS = 512_000
MAX_DESCRIPTION_CHARS = 500
MAX_NAME_CHARS = 180
MAX_ERROR_CHARS = 200
MAX_EVIDENCE_ITEMS = 12
MAX_FEED_ATTEMPTS = 6
MAX_VERIFY_GROUPS = 8

_LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,8}$")
_COUNTRY_RE = re.compile(r"^[A-Za-z]{2}$")
_SPACE_RE = re.compile(r"\s+")
_TAG_RE = re.compile(r"<[^>]*>")

# These are intentionally conservative. The service should not probe an
# arbitrary URL space merely because a path happens to be common.
_COMMON_FEED_PATHS = (
    "/feed",
    "/feed/",
    "/rss",
    "/feed.xml",
    "/rss.xml",
    "/atom.xml",
    "/index.xml",
)
_ALT_FEED_TYPES = frozenset(
    {
        "application/atom+xml",
        "application/rss+xml",
        "application/rdf+xml",
        "application/xml",
        "text/xml",
    }
)


class SourceDiscoveryError(RuntimeError):
    """Raised when the upstream Google News search cannot be read."""


def _bounded_text(value: Any, limit: int) -> str:
    text = html.unescape(str(value or ""))
    text = _TAG_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip()[:limit]


def _bounded_error(value: Any) -> str:
    """Return a short, non-sensitive error label for health evidence."""
    text = _bounded_text(value, MAX_ERROR_CHARS)
    if not text:
        return "request failed"
    if "@" in text or "password" in text.casefold() or "token" in text.casefold():
        return "request failed"
    return text


def _safe_url_parts(raw: Any) -> tuple[str, str, str, str, str] | None:
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if not value or len(value) > MAX_URL_CHARS:
        return None
    if any(ord(ch) < 0x20 for ch in value):
        return None
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        # Accessing .port validates malformed port values.
        port = parsed.port
    except (TypeError, ValueError):
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    if not hostname or parsed.username is not None or parsed.password is not None:
        return None
    host = hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        return None
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # ``inet_aton`` also recognizes legacy numeric IPv4 spellings (for
        # example 2130706433), which must not bypass the literal-IP guard.
        try:
            address = ipaddress.ip_address(socket.inet_aton(host))
        except (OSError, ValueError):
            address = None
    if address is not None and (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
        or not address.is_global
    ):
        return None
    scheme = parsed.scheme.lower()
    host_for_netloc = f"[{host}]" if ":" in host else host
    if port is None or (scheme == "http" and port == 80) or (
        scheme == "https" and port == 443
    ):
        netloc = host_for_netloc
    else:
        netloc = f"{host_for_netloc}:{port}"
    path = parsed.path or "/"
    return scheme, netloc, path, parsed.query, ""


def canonical_url(raw: Any) -> str | None:
    """Normalize an HTTP(S) URL for duplicate comparisons.

    This is a syntactic normalizer. Network callers must use
    :func:`validate_public_url` before fetching so DNS-resolved private
    addresses are rejected at the egress boundary.
    """
    parts = _safe_url_parts(raw)
    if parts is None:
        return None
    scheme, netloc, path, query, _fragment = parts
    if path != "/":
        path = path.rstrip("/") or "/"
    result = urlunsplit((scheme, netloc, path, query, ""))
    return result[:MAX_URL_CHARS]

def _host_resolves_publicly(
    _scheme: str,
    host: str,
    port: int | None,
) -> bool:
    """Resolve the host before every fetch and reject failed DNS lookups."""
    try:
        addresses = socket.getaddrinfo(
            host,
            port or 443,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror:
        return False
    if not addresses:
        return False
    for _family, _kind, _proto, _canonname, sockaddr in addresses:
        try:
            address = ipaddress.ip_address(sockaddr[0])
        except (ValueError, IndexError):
            return False
        if not address.is_global:
            return False
    return True


def validate_public_url(raw: Any) -> str | None:
    """Return a canonical URL only when its current DNS targets are public."""
    canonical = canonical_url(raw)
    if canonical is None:
        return None
    parsed = urlsplit(canonical)
    if not _host_resolves_publicly(
        parsed.scheme,
        parsed.hostname or "",
        parsed.port,
    ):
        return None
    return canonical


def is_safe_url(raw: Any) -> bool:
    """Return whether ``raw`` is an acceptable public HTTP(S) URL."""
    return validate_public_url(raw) is not None


def validate_safe_url(raw: Any) -> str | None:
    """Return a public canonical URL or ``None`` when it is unsafe."""
    return validate_public_url(raw)


canonicalize_url = canonical_url


def build_google_news_url(
    query: str,
    *,
    language: str = "en",
    country: str = "US",
) -> str:
    query = _validate_query(query)
    language = _validate_language(language)
    country = _validate_country(country)
    return (
        f"{GOOGLE_NEWS_SEARCH_URL}?q={quote_plus(query)}"
        f"&hl={language}-{country}&gl={country}&ceid={country}:{language}"
    )


def _validate_query(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("query is required")
    query = _SPACE_RE.sub(" ", value.strip())
    if not query:
        raise ValueError("query is required")
    if len(query) > MAX_QUERY_CHARS:
        raise ValueError(f"query must be at most {MAX_QUERY_CHARS} characters")
    return query


def _validate_language(value: Any) -> str:
    language = str(value or "en").strip().lower()
    if not _LANGUAGE_RE.fullmatch(language):
        raise ValueError("language must be an ISO-style alphabetic code")
    return language


def _validate_country(value: Any) -> str:
    country = str(value or "US").strip().upper()
    if not _COUNTRY_RE.fullmatch(country):
        raise ValueError("country must be a two-letter code")
    return country


class _AlternateLinkParser(HTMLParser):
    """Extract only bounded HTML alternate feed links."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "link" or len(self.links) >= MAX_FEED_ATTEMPTS:
            return
        values = {key.casefold(): (value or "") for key, value in attrs}
        rel = {part.casefold() for part in values.get("rel", "").split()}
        mime = values.get("type", "").split(";", 1)[0].strip().casefold()
        href = values.get("href", "").strip()
        if "alternate" in rel and href and (mime in _ALT_FEED_TYPES or not mime):
            self.links.append((mime or "unknown", href[:MAX_URL_CHARS]))
class SourceDiscoveryService:
    """Discover publisher feeds from public Google News results.

    ``http_client`` and ``searcher`` are injectable to keep offline tests
    deterministic. ``searcher`` may be a callable or an object with a
    ``search`` method and should return an iterable of Google News entry-like
    mappings (or an envelope containing ``results``/``items``).
    """

    def __init__(
        self,
        *,
        http_client: Any | None = None,
        client: Any | None = None,
        searcher: Any | None = None,
        search: Any | None = None,
        search_client: Any | None = None,
        timeout: float = 4.0,
    ) -> None:
        # Friendly aliases keep offline fakes simple while the explicit names
        # document the two independent outbound dependencies.
        self._client = http_client or client or httpx_client(
            timeout=timeout,
            follow_redirects=False,
            headers=digest_fetch_headers(),
        )
        self._searcher = next(
            (
                candidate
                for candidate in (searcher, search, search_client)
                if candidate is not None
            ),
            None,
        )
        self._timeout = max(1.0, min(float(timeout), 30.0))
        self._headers = digest_fetch_headers()
    def search(
        self,
        query: str,
        *,
        language: str = "en",
        country: str = "US",
        page: int = 1,
        limit: int = 20,
        max_items: int | None = None,
        existing_sources: Iterable[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        """Return a bounded, paginated source preview without persistence."""
        query = _validate_query(query)
        language = _validate_language(language)
        country = _validate_country(country)
        page = self._validate_page(page)
        limit = self._validate_limit(limit if max_items is None else max_items)

        raw_rows = self._search_rows(
            query,
            language=language,
            country=country,
            max_items=MAX_DISCOVERY_RESULTS,
        )
        groups = self._group_rows(raw_rows, query=query)
        existing_keys = self._existing_keys(existing_sources)
        ranked_groups = sorted(
            groups.values(),
            key=lambda group: (
                -len(group.get("matched_terms") or ()),
                -len(group.get("article_urls") or ()),
                str(group.get("name", "")).casefold(),
            ),
        )
        # Verification is deliberately bounded, but the stride follows the
        # requested result limit.  Otherwise a small limit would skip the
        # unreturned candidates in the first verification batch on page two.
        stride = min(limit, MAX_VERIFY_GROUPS)
        group_start = (page - 1) * stride
        group_end = group_start + stride
        groups_to_verify = ranked_groups[group_start:group_end]

        def build(group: Mapping[str, Any]) -> dict[str, Any] | None:
            return self._build_candidate(
                group,
                query=query,
                language=language,
                country=country,
            )

        candidates: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, str]] = set()
        with ThreadPoolExecutor(
            max_workers=min(4, max(1, len(groups_to_verify)))
        ) as executor:
            built_candidates = executor.map(build, groups_to_verify)
        for candidate in built_candidates:
            if candidate is None:
                continue
            key = self._candidate_key(candidate)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            candidate["existing"] = self._candidate_existing(candidate, existing_keys)
            candidates.append(candidate)

        candidates.sort(
            key=lambda row: (
                -float(row.get("score", 0.0)),
                str(row.get("name", "")).casefold(),
                str(row.get("url", "")),
            )
        )
        visible = candidates[:limit]
        return {
            "query": query,
            "candidates": visible,
            "page": page,
            "limit": limit,
            "has_more": len(candidates) > len(visible)
            or group_end < len(ranked_groups),
        }

    # Common service spelling used by integrations and tests.
    discover = search

    @staticmethod
    def _validate_page(value: Any) -> int:
        if isinstance(value, bool):
            raise ValueError("page must be an integer")
        try:
            page = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("page must be an integer") from exc
        if not 1 <= page <= MAX_PAGE:
            raise ValueError(f"page must be between 1 and {MAX_PAGE}")
        return page

    @staticmethod
    def _validate_limit(value: Any) -> int:
        if isinstance(value, bool):
            raise ValueError("limit must be an integer")
        try:
            limit = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("limit must be an integer") from exc
        if not 1 <= limit <= MAX_DISCOVERY_LIMIT:
            raise ValueError(
                f"limit must be between 1 and {MAX_DISCOVERY_LIMIT}"
            )
        return limit

    @staticmethod
    def _bounded_items(value: Any, max_items: int) -> list[Any]:
        try:
            return list(islice(iter(value), max_items))
        except TypeError as exc:
            raise SourceDiscoveryError(
                "Google News search unavailable",
            ) from exc

    def _search_rows(
        self,
        query: str,
        *,
        language: str,
        country: str,
        max_items: int,
    ) -> list[Any]:
        try:
            if self._searcher is None:
                url = build_google_news_url(
                    query,
                    language=language,
                    country=country,
                )
                response = self._request(url)
                body = self._response_text(response)
                parsed = feedparser.parse(body)
                return self._bounded_items(
                    getattr(parsed, "entries", []),
                    max_items,
                )
            target = self._searcher
            method = getattr(target, "search", None)
            if callable(method):
                result = self._invoke_search(
                    method,
                    query,
                    language=language,
                    country=country,
                    max_items=max_items,
                )
            elif callable(target):
                result = self._invoke_search(
                    target,
                    query,
                    language=language,
                    country=country,
                    max_items=max_items,
                )
            else:
                raise TypeError("searcher must be callable or expose search()")
        except ValueError:
            raise
        except Exception as exc:
            raise SourceDiscoveryError("Google News search unavailable") from exc
        if isinstance(result, Mapping):
            for key in ("results", "items", "entries", "candidates"):
                if key not in result:
                    continue
                value = result.get(key)
                if value is None:
                    continue
                return self._bounded_items(value, max_items)
            return []
        if hasattr(result, "entries"):
            result = getattr(result, "entries")
        return self._bounded_items(result, max_items)

    @staticmethod
    def _invoke_search(
        method: Callable[..., Any],
        query: str,
        *,
        language: str,
        country: str,
        max_items: int,
    ) -> Any:
        # Existing GoogleNewsDiscovery and fakes generally accept keywords;
        # the positional fallback keeps simple test doubles convenient.
        try:
            return method(
                query,
                language=language,
                country=country,
                max_items=max_items,
            )
        except TypeError as first:
            try:
                return method(query, language, country, max_items)
            except TypeError:
                raise first

    def _group_rows(self, rows: Iterable[Any], *, query: str) -> OrderedDict:
        groups: OrderedDict[str, dict[str, Any]] = OrderedDict()
        query_terms = [
            term.casefold()
            for term in re.findall(r"[\w-]{2,}", query, flags=re.UNICODE)
        ]
        for raw in rows:
            if not isinstance(raw, Mapping):
                continue
            article_url = canonical_url(
                raw.get("url") or raw.get("link") or raw.get("article_url")
            )
            source_raw = raw.get("source") or raw.get("publisher")
            source_name = ""
            source_url_raw: Any = (
                raw.get("source_url")
                or raw.get("publisher_url")
                or raw.get("source_href")
            )
            if isinstance(source_raw, Mapping):
                source_name = _bounded_text(
                    source_raw.get("title") or source_raw.get("name"),
                    MAX_NAME_CHARS,
                )
                source_url_raw = source_url_raw or source_raw.get("href")
            else:
                source_name = _bounded_text(source_raw, MAX_NAME_CHARS)
            source_url = canonical_url(source_url_raw)
            if article_url is None and source_url is None:
                continue
            article_url = article_url or source_url
            assert article_url is not None
            article_parts = urlsplit(article_url)
            host = (article_parts.hostname or "").lower().removeprefix("www.")
            key = f"host:{host}" if host else ""
            if source_name:
                # Group section paths from one publisher together so the
                # paginated preview does not repeat the same feed candidate.
                key = key or f"name:{source_name.casefold()}"
            else:
                source_name = self._pretty_host(host)
            group = groups.setdefault(
                key,
                {
                    "name": source_name or self._pretty_host(host),
                    "page_url": source_url or article_url,
                    "article_urls": [],
                    "descriptions": [],
                    "titles": [],
                    "matched_terms": set(),
                    "source_url": source_url,
                },
            )
            if article_url not in group["article_urls"]:
                group["article_urls"].append(article_url)
            title = _bounded_text(raw.get("title"), MAX_NAME_CHARS)
            description = _bounded_text(
                raw.get("description") or raw.get("summary") or raw.get("snippet"),
                MAX_DESCRIPTION_CHARS,
            )
            if title and title not in group["titles"]:
                group["titles"].append(title)
            if description and description not in group["descriptions"]:
                group["descriptions"].append(description)
            searchable = f"{source_name} {title} {description}".casefold()
            group["matched_terms"].update(
                term for term in query_terms if term in searchable
            )
        return groups

    @staticmethod
    def _pretty_host(host: str) -> str:
        host = host.removeprefix("www.")
        if not host:
            return "Publisher"
        return host.split(":", 1)[0][:MAX_NAME_CHARS]

    def _build_candidate(
        self,
        group: Mapping[str, Any],
        *,
        query: str,
        language: str,
        country: str,
    ) -> dict[str, Any] | None:
        page_url = canonical_url(group.get("page_url"))
        if page_url is None:
            return None
        verification = self._verify_feed(page_url)
        articles = list(group.get("article_urls") or [])
        name = _bounded_text(group.get("name"), MAX_NAME_CHARS) or "Publisher"
        description = _bounded_text(
            (group.get("descriptions") or [""])[0],
            MAX_DESCRIPTION_CHARS,
        )
        matched_terms = sorted(
            {
                _bounded_text(term, 64)
                for term in (group.get("matched_terms") or set())
                if _bounded_text(term, 64)
            }
        )[:MAX_EVIDENCE_ITEMS]
        if verification["feed_url"]:
            source_type = "rss"
            feed_url = verification["feed_url"]
            candidate_url = page_url
            candidate_query: str | None = None
            health: dict[str, Any] = {
                "status": "verified",
                "entry_count": verification["entry_count"],
            }
            evidence: dict[str, Any] = {
                "feed_verified": True,
                "verification": verification["method"],
                "matched_terms": matched_terms,
                "article_count": min(len(articles), MAX_DISCOVERY_RESULTS),
            }
        else:
            source_type = "google_news"
            candidate_url = page_url
            candidate_query = query
            feed_url = build_google_news_url(
                query,
                language=language,
                country=country,
            )
            health = {"status": verification["status"]}
            if verification.get("error"):
                health["error"] = verification["error"]
            evidence = {
                "feed_verified": False,
                "verification": verification["method"],
                "matched_terms": matched_terms,
                "article_count": min(len(articles), MAX_DISCOVERY_RESULTS),
            }
        relevance = len(matched_terms) / max(1, len(set(query.casefold().split())))
        feed_bonus = 1.0 if verification["feed_url"] else 0.0
        volume = min(1.0, len(articles) / 5.0)
        score = round(min(1.0, 0.5 * feed_bonus + 0.3 * relevance + 0.2 * volume), 4)
        evidence["score_basis"] = {
            "feed": round(feed_bonus, 4),
            "relevance": round(min(1.0, relevance), 4),
            "volume": round(volume, 4),
        }
        return {
            "name": name,
            "source_type": source_type,
            "url": candidate_url,
            "feed_url": feed_url,
            "query": candidate_query,
            "category": "General",
            "description": description,
            "score": score,
            "evidence": evidence,
            "health": health,
            "existing": False,
        }

    def _verify_feed(self, page_url: str) -> dict[str, Any]:
        """Verify an RSS/Atom feed via direct URL, HTML alternates, or paths."""
        page_parts = urlsplit(page_url)
        page_response: Any | None = None
        page_body = ""
        page_failed = False
        try:
            page_response = self._request(page_url)
            page_body = self._response_text(page_response)
        except Exception:
            page_failed = True
        if page_response is not None:
            verified = self._parse_feed_response(page_url, page_response, page_body)
            if verified is not None:
                verified["method"] = "direct"
                return verified
        alternates: list[tuple[str, str]] = []
        parser = _AlternateLinkParser()
        try:
            parser.feed(page_body[:MAX_BODY_CHARS])
            alternates = parser.links
        except Exception:
            alternates = []
        attempts: list[tuple[str, str]] = []
        for _mime, href in alternates:
            resolved = canonical_url(urljoin(page_url, href))
            if resolved:
                attempts.append((resolved, "alternate"))
        origin = f"{page_parts.scheme}://{page_parts.netloc}"
        for path in _COMMON_FEED_PATHS:
            resolved = canonical_url(urljoin(origin + "/", path.lstrip("/")))
            if resolved:
                attempts.append((resolved, "common_path"))
        seen: set[str] = set()
        for feed_url, method in attempts[:MAX_FEED_ATTEMPTS]:
            if feed_url in seen:
                continue
            seen.add(feed_url)
            try:
                response = self._request(feed_url)
                body = self._response_text(response)
                verified = self._parse_feed_response(feed_url, response, body)
            except Exception:
                continue
            if verified is not None:
                verified["method"] = method
                return verified
        return {
            "feed_url": None,
            "method": "unavailable" if page_failed else "none",
            "status": "error" if page_failed else "unverified",
            "error": (
                "publisher check failed"
                if page_failed
                else "no verified feed found"
            ),
            "entry_count": 0,
        }

    @staticmethod
    def _parse_feed_response(
        requested_url: str,
        response: Any,
        body: str,
    ) -> dict[str, Any] | None:
        status = getattr(response, "status_code", None)
        if isinstance(status, int) and status >= 400:
            return None
        final_url = validate_public_url(
            str(getattr(response, "url", "") or requested_url)
        )
        if final_url is None:
            return None
        parsed = feedparser.parse(body[:MAX_BODY_CHARS])
        version = _bounded_text(getattr(parsed, "version", ""), 32).casefold()
        entries = getattr(parsed, "entries", []) or []
        if not version or not any(
            token in version for token in ("rss", "atom", "rdf")
        ):
            return None
        return {
            "feed_url": final_url,
            "entry_count": min(len(entries), MAX_DISCOVERY_RESULTS),
            "status": "verified",
        }

    def _request(self, url: str) -> Any:
        current = validate_public_url(url)
        if current is None:
            raise ValueError("unsafe URL")
        response: Any = None
        for _ in range(3):
            response = self._call_get(current)
            status = getattr(response, "status_code", None)
            if isinstance(status, int) and 300 <= status < 400:
                location = ""
                headers = getattr(response, "headers", {}) or {}
                try:
                    location = str(headers.get("location", ""))
                except Exception:
                    location = ""
                redirected = validate_public_url(urljoin(current, location))
                if not redirected or redirected == current:
                    return response
                current = redirected
                continue
            return response
        return response

    def _call_get(self, url: str) -> Any:
        get = getattr(self._client, "get", None)
        if not callable(get):
            raise TypeError("http client must expose get()")
        try:
            return get(
                url,
                headers=self._headers,
                timeout=self._timeout,
                follow_redirects=False,
            )
        except TypeError as first:
            try:
                return get(url, headers=self._headers, timeout=self._timeout)
            except TypeError:
                try:
                    return get(url, headers=self._headers)
                except TypeError:
                    try:
                        return get(url)
                    except TypeError:
                        raise first

    @staticmethod
    def _response_text(response: Any) -> str:
        status = getattr(response, "status_code", None)
        if isinstance(status, int) and status >= 400:
            raise SourceDiscoveryError("upstream request failed")
        raise_for_status = getattr(response, "raise_for_status", None)
        if callable(raise_for_status):
            raise_for_status()
        text = getattr(response, "text", "")
        if isinstance(text, bytes):
            text = text.decode("utf-8", errors="replace")
        return str(text or "")[:MAX_BODY_CHARS]

    @staticmethod
    def _candidate_key(candidate: Mapping[str, Any]) -> tuple[str, str]:
        source_type = str(candidate.get("source_type") or "")
        if source_type == "google_news":
            value = canonical_url(candidate.get("url"))
        else:
            value = canonical_url(candidate.get("feed_url")) or canonical_url(
                candidate.get("url"),
            )
        return ("publisher", value or "")

    @staticmethod
    def _existing_keys(
        existing_sources: Iterable[Mapping[str, Any]],
    ) -> set[tuple[str, str]]:
        keys: set[tuple[str, str]] = set()
        for row in existing_sources or ():
            if not isinstance(row, Mapping):
                continue
            source_type = _bounded_text(row.get("type") or row.get("source_type"), 32)
            for field in ("url", "feed_url"):
                value = canonical_url(row.get(field))
                if value:
                    keys.add((source_type, value))
                    keys.add(("*", value))
            extra = row.get("extra_json")
            if isinstance(extra, str):
                try:
                    extra = json.loads(extra)
                except Exception:
                    extra = {}
            if isinstance(extra, Mapping):
                value = canonical_url(extra.get("feed_url"))
                if value:
                    keys.add((source_type, value))
                    keys.add(("*", value))
                query = _bounded_text(extra.get("query"), MAX_QUERY_CHARS)
                if source_type == "google_news" and query:
                    try:
                        generated = build_google_news_url(
                            query,
                            language=str(extra.get("language") or "en"),
                            country=str(extra.get("country") or "US"),
                        )
                    except ValueError:
                        generated = None
                    if generated:
                        keys.add(("google_news", generated))
                        keys.add(("*", generated))
        return keys

    @staticmethod
    def _candidate_existing(
        candidate: Mapping[str, Any],
        existing_keys: set[tuple[str, str]],
    ) -> bool:
        source_type = str(candidate.get("source_type") or "")
        for value in (candidate.get("feed_url"), candidate.get("url")):
            canonical = canonical_url(value)
            if canonical and (
                (source_type, canonical) in existing_keys
                or ("*", canonical) in existing_keys
            ):
                return True
        return False


# Short aliases make the service straightforward to inject in applications and
# tests without exposing any persistence-oriented implementation.
SourceDiscovery = SourceDiscoveryService

__all__ = [
    "GOOGLE_NEWS_SEARCH_URL",
    "MAX_DISCOVERY_LIMIT",
    "MAX_DISCOVERY_RESULTS",
    "SourceDiscovery",
    "SourceDiscoveryError",
    "SourceDiscoveryService",
    "build_google_news_url",
    "canonical_url",
    "canonicalize_url",
    "is_safe_url",
    "validate_public_url",
]
