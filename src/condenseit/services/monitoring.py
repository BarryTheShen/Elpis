"""Google News discovery and persisted monitoring services.

Monitoring intentionally does not share digest/article rows.  Search results are
normalized at this boundary and only deterministic evidence is retained; no
model or provider reasoning is ever accepted into a monitor payload.
"""

from __future__ import annotations

import html
import json
import logging
import re
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote_plus, urlsplit, urlunsplit

import feedparser

from condenseit.collectors.feed_dates import parse_feed_entry_date
from condenseit.fetch_headers import digest_fetch_headers
from condenseit.network import httpx_client, load_network_proxy, safe_network_error
from condenseit.store.database import ContentStore

logger = logging.getLogger(__name__)

GOOGLE_NEWS_SEARCH_URL = "https://news.google.com/rss/search"
MONITOR_SCOPES = frozenset({"general_discovery", "configured_feeds", "both"})
MONITOR_STATES = frozenset({"new", "seen", "dismissed"})
MIN_CADENCE_MINUTES = 1
MAX_CADENCE_MINUTES = 43_200  # 30 days; ready for a future scheduler.
MAX_MONITOR_ITEMS = 200
MAX_KEYWORDS = 20
MAX_KEYWORD_CHARS = 64
MAX_QUESTION_CHARS = 500
MAX_SEARCH_QUERY_CHARS = 500
MAX_CATEGORY_CHARS = 80
MAX_LANGUAGE_CHARS = 8
MAX_COUNTRY_CHARS = 2
MAX_URL_CHARS = 2_048
MAX_TITLE_CHARS = 500
MAX_SNIPPET_CHARS = 4_000

# Provider/model output is deliberately not part of this allowlist.
_EVIDENCE_KEYS = frozenset({"matched_terms", "provider", "freshness"})
_TAG_RE = re.compile(r"<[^>]*>")
_SPACE_RE = re.compile(r"\s+")
_LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,8}$")
_COUNTRY_RE = re.compile(r"^[A-Za-z]{2}$")


def _text(value: Any, limit: int) -> str:
    """Return bounded plain text with feed markup removed."""
    value = html.unescape(str(value or ""))
    value = _TAG_RE.sub(" ", value)
    return _SPACE_RE.sub(" ", value).strip()[:limit]


def _normalise_terms(value: Any, field: str = "keywords") -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values: Iterable[Any] = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        raise ValueError(f"{field} must be a list or comma-separated string")
    terms: list[str] = []
    seen: set[str] = set()
    for raw in values:
        term = _text(raw, MAX_KEYWORD_CHARS + 1)
        if not term:
            continue
        if len(term) > MAX_KEYWORD_CHARS:
            raise ValueError(
                f"{field} entries must be at most {MAX_KEYWORD_CHARS} characters"
            )
        key = term.casefold()
        if key in seen:
            continue
        terms.append(term)
        seen.add(key)
    if len(terms) > MAX_KEYWORDS:
        raise ValueError(f"{field} may contain at most {MAX_KEYWORDS} entries")
    return terms


def derive_search_query(
    question: str,
    include_keywords: Iterable[str] | None = None,
    exclude_keywords: Iterable[str] | None = None,
) -> str:
    """Derive a bounded Google News query without changing saved question text."""
    base = _SPACE_RE.sub(" ", question.strip())
    parts = [base]
    existing = base.casefold()
    for term in include_keywords or ():
        term = _text(term, MAX_KEYWORD_CHARS)
        if term and term.casefold() not in existing:
            parts.append(f'"{term}"')
            existing = f"{existing} {term.casefold()}"
    for term in exclude_keywords or ():
        term = _text(term, MAX_KEYWORD_CHARS)
        if term:
            parts.append(f'-"{term}"')
    return _SPACE_RE.sub(" ", " ".join(parts))[:MAX_SEARCH_QUERY_CHARS]


def validate_monitor_payload(
    payload: dict[str, Any],
    *,
    partial: bool = False,
) -> dict[str, Any]:
    """Validate and normalize monitor input for API and service callers."""
    if not isinstance(payload, dict):
        raise ValueError("monitor payload must be an object")
    out: dict[str, Any] = {}
    if not partial or "question" in payload:
        question = payload.get("question")
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question is required")
        if len(question) > MAX_QUESTION_CHARS:
            raise ValueError(
                f"question must be at most {MAX_QUESTION_CHARS} characters"
            )
        # Keep the exact submitted string, including intentional surrounding
        # whitespace.  Only the derived query is normalized.
        out["question"] = question

    if not partial or "scope" in payload:
        scope = str(payload.get("scope") or "general_discovery").strip().lower()
        if scope not in MONITOR_SCOPES:
            raise ValueError(
                "scope must be general_discovery, configured_feeds, or both"
            )
        out["scope"] = scope

    if not partial or "cadence_minutes" in payload:
        raw_cadence = payload.get("cadence_minutes", 1440)
        if isinstance(raw_cadence, bool):
            raise ValueError("cadence_minutes must be an integer")
        try:
            cadence = int(raw_cadence)
        except (TypeError, ValueError) as exc:
            raise ValueError("cadence_minutes must be an integer") from exc
        if not MIN_CADENCE_MINUTES <= cadence <= MAX_CADENCE_MINUTES:
            raise ValueError(
                f"cadence_minutes must be between {MIN_CADENCE_MINUTES} and "
                f"{MAX_CADENCE_MINUTES}"
            )
        out["cadence_minutes"] = cadence

    if not partial or "include_keywords" in payload or "include_terms" in payload:
        out["include_keywords"] = _normalise_terms(
            payload.get("include_keywords", payload.get("include_terms", [])),
            "include_keywords",
        )
    if not partial or "exclude_keywords" in payload or "exclude_terms" in payload:
        out["exclude_keywords"] = _normalise_terms(
            payload.get("exclude_keywords", payload.get("exclude_terms", [])),
            "exclude_keywords",
        )

    if not partial or "category" in payload:
        category = str(payload.get("category") or "General").strip()
        if len(category) > MAX_CATEGORY_CHARS:
            raise ValueError(
                f"category must be at most {MAX_CATEGORY_CHARS} characters"
            )
        out["category"] = category or "General"

    if not partial or "language" in payload:
        language = str(payload.get("language") or "en").strip().lower()
        if not _LANGUAGE_RE.fullmatch(language):
            raise ValueError("language must be an ISO-style alphabetic code")
        out["language"] = language[:MAX_LANGUAGE_CHARS]

    if not partial or "country" in payload:
        country = str(payload.get("country") or "US").strip().upper()
        if not _COUNTRY_RE.fullmatch(country):
            raise ValueError("country must be a two-letter code")
        out["country"] = country

    if not partial or "max_items" in payload:
        raw_max = payload.get("max_items", 20)
        if isinstance(raw_max, bool):
            raise ValueError("max_items must be an integer")
        try:
            max_items = int(raw_max)
        except (TypeError, ValueError) as exc:
            raise ValueError("max_items must be an integer") from exc
        if not 1 <= max_items <= MAX_MONITOR_ITEMS:
            raise ValueError(f"max_items must be between 1 and {MAX_MONITOR_ITEMS}")
        out["max_items"] = max_items

    if "enabled" in payload:
        if not isinstance(payload["enabled"], bool):
            raise ValueError("enabled must be a boolean")
        out["enabled"] = payload["enabled"]

    if not partial or "search_query" in payload:
        explicit = payload.get("search_query")
        if explicit is not None and not isinstance(explicit, str):
            raise ValueError("search_query must be a string")
        if explicit and len(explicit) > MAX_SEARCH_QUERY_CHARS:
            raise ValueError(
                f"search_query must be at most {MAX_SEARCH_QUERY_CHARS} characters"
            )
        question = out.get("question", str(payload.get("question") or ""))
        includes = out.get(
            "include_keywords",
            _normalise_terms(payload.get("include_keywords", []), "include_keywords"),
        )
        excludes = out.get(
            "exclude_keywords",
            _normalise_terms(payload.get("exclude_keywords", []), "exclude_keywords"),
        )
        out["search_query"] = (
            _SPACE_RE.sub(" ", explicit.strip())
            if explicit and explicit.strip()
            else derive_search_query(question, includes, excludes)
        )
        if not out["search_query"]:
            raise ValueError("search_query cannot be empty")

    return out


def build_google_news_search_url(
    query: str,
    *,
    language: str = "en",
    country: str = "US",
) -> str:
    """Build a Google News RSS URL using bounded, validated locale values."""
    language = str(language or "en").strip().lower()
    country = str(country or "US").strip().upper()
    if not _LANGUAGE_RE.fullmatch(language):
        raise ValueError("language must be a two-to-eight letter code")
    if not _COUNTRY_RE.fullmatch(country):
        raise ValueError("country must be a two-letter code")
    query = _text(query, MAX_SEARCH_QUERY_CHARS)
    if not query:
        raise ValueError("query is required")
    return (
        f"{GOOGLE_NEWS_SEARCH_URL}?q={quote_plus(query)}"
        f"&hl={language}-{country}&gl={country}&ceid={country}:{language}"
    )


def _canonical_url(value: Any) -> str:
    raw = str(value or "").strip()
    if len(raw) > MAX_URL_CHARS:
        return ""
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return ""
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path or "/",
            parsed.query,
            "",
        )
    )[:MAX_URL_CHARS]


def _freshness(published_at: str) -> float:
    if not published_at:
        return 0.0
    try:
        value = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        age_hours = max(
            0.0,
            (datetime.now(UTC) - value.astimezone(UTC)).total_seconds() / 3600,
        )
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return round(max(0.0, min(1.0, 1.0 - age_hours / (24 * 30))), 4)


def _matched_terms(text: str, terms: Iterable[str]) -> list[str]:
    folded = text.casefold()
    return [term for term in terms if term.casefold() in folded]


def _normalise_entry(
    entry: Any,
    *,
    category: str,
    include_keywords: Iterable[str] = (),
    exclude_keywords: Iterable[str] = (),
    provider: str = "google_news",
) -> dict[str, Any] | None:
    url = _canonical_url(entry.get("link") or entry.get("url"))
    if not url:
        return None
    title = _text(entry.get("title") or "Untitled", MAX_TITLE_CHARS)
    snippet = _text(
        entry.get("summary") or entry.get("description") or entry.get("snippet"),
        MAX_SNIPPET_CHARS,
    )
    body = f"{title} {snippet}".strip()
    excludes = list(exclude_keywords)
    if any(term.casefold() in body.casefold() for term in excludes):
        return None
    includes = list(include_keywords)
    matched = _matched_terms(body, includes)
    published_at = parse_feed_entry_date(entry, fallback_now=False)
    freshness = _freshness(published_at)
    match_ratio = len(matched) / max(1, len(includes)) if includes else 0.0
    score = round(max(0.0, min(1.0, (match_ratio * 0.7) + (freshness * 0.3))), 4)
    evidence = {
        "matched_terms": matched[:MAX_KEYWORDS],
        "provider": _text(provider, 80) or "google_news",
        "freshness": freshness,
    }
    return {
        "url": url,
        "title": title,
        "snippet": snippet,
        "excerpt": snippet,
        "source": _text(
            (entry.get("source") or {}).get("title")
            if isinstance(entry.get("source"), dict)
            else entry.get("source"),
            120,
        )
        or "Google News",
        "category": _text(category, MAX_CATEGORY_CHARS) or "General",
        "published_at": published_at,
        "relevance_score": score,
        "evidence": evidence,
    }


def _sanitize_result(result: dict[str, Any], *, category: str) -> dict[str, Any] | None:
    """Drop untrusted fields, especially provider/model reasoning fields."""
    if not isinstance(result, dict):
        return None
    url = _canonical_url(result.get("url"))
    if not url:
        return None
    title = _text(result.get("title"), MAX_TITLE_CHARS)
    snippet = _text(result.get("snippet") or result.get("excerpt"), MAX_SNIPPET_CHARS)
    evidence_raw = result.get("evidence")
    if isinstance(evidence_raw, str):
        try:
            evidence_raw = json.loads(evidence_raw)
        except json.JSONDecodeError:
            evidence_raw = {}
    evidence_raw = evidence_raw if isinstance(evidence_raw, dict) else {}
    matched = _normalise_terms(evidence_raw.get("matched_terms", []), "matched_terms")
    provider = _text(evidence_raw.get("provider"), 80) or "google_news"
    try:
        freshness = round(
            max(0.0, min(1.0, float(evidence_raw.get("freshness", 0)))),
            4,
        )
    except (TypeError, ValueError):
        freshness = 0.0
    try:
        relevance_score = round(
            max(0.0, min(1.0, float(result.get("relevance_score", 0)))),
            4,
        )
    except (TypeError, ValueError):
        relevance_score = 0.0
    published_at = _text(result.get("published_at"), 64)
    return {
        "url": url,
        "title": title,
        "snippet": snippet,
        "source": _text(result.get("source"), 120) or "Google News",
        "category": _text(result.get("category") or category, MAX_CATEGORY_CHARS)
        or "General",
        "published_at": published_at,
        "relevance_score": relevance_score,
        "evidence": {
            "matched_terms": matched,
            "provider": provider,
            "freshness": freshness,
        },
    }


class GoogleNewsDiscovery:
    """Read-only Google News RSS search with normalized public results."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client or httpx_client(
            timeout=30.0,
            follow_redirects=False,
            headers=digest_fetch_headers(),
        )

    def search(
        self,
        query: str,
        *,
        language: str = "en",
        country: str = "US",
        max_items: int = 20,
        include_keywords: Iterable[str] = (),
        exclude_keywords: Iterable[str] = (),
        category: str = "General",
    ) -> list[dict[str, Any]]:
        if not 1 <= int(max_items) <= MAX_MONITOR_ITEMS:
            raise ValueError(f"max_items must be between 1 and {MAX_MONITOR_ITEMS}")
        url = build_google_news_search_url(query, language=language, country=country)
        response = self._client.get(url)
        response.raise_for_status()
        parsed = feedparser.parse(response.text)
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for entry in getattr(parsed, "entries", [])[: int(max_items) * 2]:
            normalized = _normalise_entry(
                entry,
                category=category,
                include_keywords=include_keywords,
                exclude_keywords=exclude_keywords,
            )
            if not normalized or normalized["url"] in seen:
                continue
            seen.add(normalized["url"])
            results.append(normalized)
            if len(results) >= int(max_items):
                break
        return results

    def close(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            close()


class MonitoringService:
    """Persisted monitor CRUD and synchronous check-now orchestration."""

    def __init__(
        self,
        store: ContentStore,
        discovery: GoogleNewsDiscovery | Any | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
        source_registry: Any | None = None,
        configured_client: Any | None = None,
    ) -> None:
        self.store = store
        self.discovery = discovery or GoogleNewsDiscovery()
        self.clock = clock or (lambda: datetime.now(UTC))
        self.source_registry = source_registry
        self.configured_client = configured_client

    def create_monitor(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = validate_monitor_payload(payload)
        monitor_id = self.store.create_monitor_query(normalized)
        return self.store.get_monitor_query(monitor_id) or {}

    def get_monitor(self, monitor_id: int) -> dict[str, Any] | None:
        return self.store.get_monitor_query(monitor_id)

    def list_monitors(self, *, enabled_only: bool = False) -> list[dict[str, Any]]:
        return self.store.list_monitor_queries(enabled_only=enabled_only)

    def update_monitor(
        self,
        monitor_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        current = self.store.get_monitor_query(monitor_id)
        if current is None:
            return None
        merged = dict(current)
        merged.update(payload)
        if "question" in payload and "search_query" not in payload:
            merged.pop("search_query", None)
        normalized = validate_monitor_payload(merged)
        normalized["enabled"] = bool(
            payload.get("enabled", current.get("enabled", True))
        )
        return self.store.update_monitor_query(monitor_id, normalized)

    def delete_monitor(self, monitor_id: int) -> bool:
        return self.store.delete_monitor_query(monitor_id)

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _search(self, monitor: dict[str, Any]) -> list[dict[str, Any]]:
        scope = str(monitor.get("scope") or "general_discovery")
        # Configured-feed monitoring is represented by the same normalized
        # contract.  A future scheduler can plug in a feed-specific collector;
        # Google News remains the deterministic MVP provider for all scopes.
        if scope in MONITOR_SCOPES:
            return self.discovery.search(
                str(monitor.get("search_query") or monitor.get("question") or ""),
                language=str(monitor.get("language") or "en"),
                country=str(monitor.get("country") or "US"),
                max_items=int(monitor.get("max_items") or 20),
                include_keywords=monitor.get("include_keywords") or [],
                exclude_keywords=monitor.get("exclude_keywords") or [],
                category=str(monitor.get("category") or "General"),
            )
        return []

    @staticmethod
    def _matches_monitor_terms(
        result: dict[str, Any],
        monitor: dict[str, Any],
    ) -> bool:
        haystack = f"{result.get('title', '')} {result.get('snippet', '')}".casefold()
        includes = [
            str(term).strip().casefold()
            for term in monitor.get("include_keywords") or []
            if str(term).strip()
        ]
        excludes = [
            str(term).strip().casefold()
            for term in monitor.get("exclude_keywords") or []
            if str(term).strip()
        ]
        if any(term in haystack for term in excludes):
            return False
        return not includes or any(term in haystack for term in includes)

    def check_now(self, monitor_id: int) -> dict[str, Any]:
        monitor = self.store.get_monitor_query(monitor_id)
        if monitor is None:
            raise KeyError(f"monitor {monitor_id} not found")
        now = self._now()
        now_iso = now.isoformat()
        cadence = int(monitor.get("cadence_minutes") or 1440)
        next_iso = (now + timedelta(minutes=cadence)).isoformat()
        self.store.update_monitor_query(
            monitor_id,
            {
                "status": "running",
                "last_checked_at": now_iso,
                "last_error": "",
                "next_check_at": next_iso,
            },
        )
        try:
            raw_results = self._search(
                self.store.get_monitor_query(monitor_id) or monitor
            )
            seen_urls: set[str] = set()
            for raw in raw_results:
                if not isinstance(raw, dict):
                    continue
                sanitized = _sanitize_result(
                    raw,
                    category=str(monitor.get("category") or "General"),
                )
                if (
                    not sanitized
                    or sanitized["url"] in seen_urls
                    or not self._matches_monitor_terms(sanitized, monitor)
                ):
                    continue
                seen_urls.add(sanitized["url"])
                self.store.upsert_monitor_result(monitor_id, sanitized)
            new_count = self.store.monitor_new_count(monitor_id)
            updated = self.store.update_monitor_query(
                monitor_id,
                {
                    "status": "ok",
                    "last_checked_at": now_iso,
                    "last_success_at": now_iso,
                    "next_check_at": next_iso,
                    "last_error": "",
                    "new_count": new_count,
                },
            )
            return {
                "monitor": updated or self.store.get_monitor_query(monitor_id),
                "results": self.store.list_monitor_results(
                    monitor_id,
                    limit=int(monitor.get("max_items") or 20),
                ),
                "new_count": new_count,
                "error": None,
            }
        except Exception as exc:  # preserve evidence on every network failure
            error = safe_network_error(exc, load_network_proxy(self.store))
            error = _text(error, 500)
            new_count = self.store.monitor_new_count(monitor_id)
            updated = self.store.update_monitor_query(
                monitor_id,
                {
                    "status": "error",
                    "last_checked_at": now_iso,
                    "next_check_at": next_iso,
                    "last_error": error,
                    "new_count": new_count,
                },
            )
            logger.warning("Monitor %s check failed: %s", monitor_id, error)
            return {
                "monitor": updated or self.store.get_monitor_query(monitor_id),
                "results": self.store.list_monitor_results(monitor_id, limit=200),
                "new_count": new_count,
                "error": error,
            }

    def list_results(
        self,
        monitor_id: int,
        *,
        page: int = 1,
        limit: int = 50,
        state: str | None = None,
    ) -> dict[str, Any]:
        monitor = self.store.get_monitor_query(monitor_id)
        if monitor is None:
            raise KeyError(f"monitor {monitor_id} not found")
        page = max(1, int(page))
        limit = max(1, min(MAX_MONITOR_ITEMS, int(limit)))
        offset = (page - 1) * limit
        results = self.store.list_monitor_results(
            monitor_id,
            limit=limit,
            offset=offset,
            state=state,
        )
        total = self.store.count_monitor_results(monitor_id, state=state)
        return {
            "monitor_id": int(monitor_id),
            "results": results,
            "items": results,
            "page": page,
            "limit": limit,
            "total": total,
            "has_more": offset + len(results) < total,
            "new_count": self.store.monitor_new_count(monitor_id),
        }

    def set_result_state(
        self,
        monitor_id: int,
        result_id: int,
        state: str,
    ) -> dict[str, Any] | None:
        result = self.store.update_monitor_result_state(
            result_id,
            state,
            monitor_id=monitor_id,
        )
        if result is not None:
            self.store.update_monitor_query(
                monitor_id,
                {"new_count": self.store.monitor_new_count(monitor_id)},
            )
        return result


# Small aliases make the service easy to discover for callers without creating
# duplicate implementations.
DiscoveryService = GoogleNewsDiscovery
MonitorService = MonitoringService
GoogleNewsDiscoveryService = GoogleNewsDiscovery
MonitoringQueryService = MonitoringService
build_discovery_url = build_google_news_search_url
def search_google_news(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    """Convenience read-only Google News search function."""
    service = GoogleNewsDiscovery()
    try:
        return service.search(*args, **kwargs)
    finally:
        service.close()

__all__ = [
    "DiscoveryService",
    "GoogleNewsDiscovery",
    "GoogleNewsDiscoveryService",
    "MAX_MONITOR_ITEMS",
    "MONITOR_SCOPES",
    "MONITOR_STATES",
    "MonitorService",
    "MonitoringQueryService",
    "MonitoringService",
    "build_discovery_url",
    "build_google_news_search_url",
    "derive_search_query",
    "search_google_news",
    "validate_monitor_payload",
]
