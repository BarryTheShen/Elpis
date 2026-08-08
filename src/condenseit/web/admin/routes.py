"""Admin panel routes - Jinja2 HTML pages and JSON API endpoints."""

import asyncio
import json
import math
import os
import re
import secrets
from typing import Any
from urllib.parse import quote, quote_plus, urlsplit

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
)
from starlette.concurrency import run_in_threadpool

from condenseit.api_urls import youtube_channel_feed_url
from condenseit.config import (
    DEFAULT_SOURCE_MAX_ITEMS,
    LOCAL_INSTALL_FALLBACK_CREDENTIAL,
    MAX_SOURCE_ITEMS,
    load_config,
)
from condenseit.network import (
    NetworkProxySettings,
    load_network_proxy,
    parse_bypass_hosts,
    safe_network_error,
    save_network_proxy,
    test_network_connection,
    validate_proxy_url,
)
from condenseit.providers.catalog import (
    PROVIDER_SPECS,
    get_provider_base_url,
    get_provider_model,
    get_provider_spec,
)
from condenseit.providers.openrouter_models import pick_cheapest_text_model
from condenseit.services.monitoring import (
    MAX_MONITOR_ITEMS,
    GoogleNewsDiscovery,
    MonitoringService,
    validate_monitor_payload,
)
from condenseit.services.ollama_client import (
    ollama_delete,
    ollama_list_tags,
    ollama_pull,
)
from condenseit.services.source_discovery import (
    SourceDiscoveryError,
    SourceDiscoveryService,
    canonical_url,
)
from condenseit.settings_overlay import apply_db_settings
from condenseit.store.database import ContentStore
from condenseit.store.opml import MAX_OPML_BYTES, build_opml, parse_opml_outlines
from condenseit.store.secure_keys import SecureKeyStore
from condenseit.store.sources import SourceRegistry
from condenseit.web.passwords import hash_password, verify_password
from condenseit.web.templating import page_context, templates

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

_GNEWS_BASE = "https://news.google.com/rss/search"
_HN_BASE = "https://hacker-news.firebaseio.com/v0"

_LEMMY_INSTANCE = "https://lemmy.world"
_REDDIT_HOST_RE = re.compile(
    r"(?:https?://)?(?:www\.|old\.)?reddit\.com/r/([^/?#\s]+)", re.IGNORECASE
)
_PUBLIC_DISCOVERY_MAX_CONCURRENT = 8


def _reddit_subreddit_to_lemmy_url(subreddit: str) -> str:
    """Return a Lemmy.world RSS feed URL equivalent to r/{subreddit}."""
    sub = subreddit.strip().lstrip("r/").lstrip("/").rstrip("/")
    return f"{_LEMMY_INSTANCE}/feeds/c/{sub}.xml?sort=Active&type_=All"


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request", "").lower() == "true"


def _parse_keyword_list(value: Any) -> list[str]:
    """Parse a keyword list from a comma-separated string or a JSON array.

    Returns a deduplicated list of non-empty stripped strings, preserving order.
    """
    if isinstance(value, list):
        items = [str(v).strip() for v in value]
    elif isinstance(value, str) and value.strip():
        raw = value.strip()
        if raw.startswith("["):
            try:
                items = [str(v).strip() for v in json.loads(raw)]
            except Exception:
                items = [p.strip() for p in raw.split(",")]
        else:
            items = [p.strip() for p in raw.split(",")]
    else:
        items = []
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out
def _candidate_text(value: Any, limit: int) -> str:
    text = re.sub(r"<[^>]*>", " ", str(value or ""))
    return " ".join(text.split())[:limit]


def _candidate_numeric(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return int(number) if number.is_integer() else number


def _sanitize_candidate(row: Any, fallback_rank: int) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    raw_url = _candidate_text(row.get("url"), 2_048)
    try:
        parsed = urlsplit(raw_url)
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    url = parsed._replace(fragment="").geturl()
    rank_raw = _candidate_numeric(row.get("rank"))
    rank = int(rank_raw) if rank_raw is not None else fallback_rank
    score = _candidate_numeric(row.get("preference_score"))
    if score is None:
        score = 0.0
    raw_breakdown = row.get("score_breakdown")
    breakdown: dict[str, int | float] = {}
    if isinstance(raw_breakdown, dict):
        for key, value in raw_breakdown.items():
            number = _candidate_numeric(value)
            if number is not None:
                breakdown[_candidate_text(key, 80)] = number
    raw_evidence = row.get("evidence")
    raw_evidence = raw_evidence if isinstance(raw_evidence, dict) else {}
    evidence: dict[str, Any] = {}
    for key in ("matched_terms", "title_matches", "context_matches"):
        values = raw_evidence.get(key, [])
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            values = []
        evidence[key] = [
            _candidate_text(value, 128)
            for value in values[:20]
            if _candidate_text(value, 128)
        ]
    reason = _candidate_text(raw_evidence.get("relevance_reason"), 240)
    if re.search(
        r"(?:chain.?of.?thought|scratchpad|llm|model reasoning)",
        reason,
        re.I,
    ):
        reason = ""
    evidence["relevance_reason"] = reason
    evidence["selected"] = bool(
        raw_evidence.get("selected", row.get("selected", False))
    )
    return {
        "rank": rank,
        "url": url[:2_048],
        "title": _candidate_text(row.get("title"), 500),
        "source": _candidate_text(row.get("source"), 120),
        "category": _candidate_text(row.get("category"), 80) or "General",
        "kind": _candidate_text(row.get("kind"), 40) or "article",
        "published_at": _candidate_text(row.get("published_at"), 64),
        "excerpt": _candidate_text(row.get("excerpt"), 2_048),
        "preference_score": score,
        "score_breakdown": breakdown,
        "evidence": evidence,
    }



def _build_source_extra(
    source_type: str,
    url: str,
    channel_id: str,
    name: str,
    *,
    query: str = "",
    language: str = "en",
    country: str = "US",
    max_items: int = DEFAULT_SOURCE_MAX_ITEMS,
    hn_feed: str = "top",
    hn_max_items: int = 20,
    hn_min_score: int = 50,
    subreddit: str = "",
    reddit_sort: str = "hot",
    reddit_time_filter: str = "day",
    reddit_max_items: int = 20,
    reddit_min_score: int = 10,
    github_repo: str = "",
    hide_keywords: list[str] | None = None,
    highlight_keywords: list[str] | None = None,
    require_keywords: list[str] | None = None,
) -> tuple[dict[str, Any], str, str, str | None]:
    """Return ``(extra_json_dict, feed_url, effective_type, conversion_note)``

    ``effective_type`` may differ from ``source_type`` when a Reddit source is
    automatically converted to a Lemmy RSS feed. ``conversion_note`` is a
    human-readable explanation of the conversion, or ``None`` if no conversion
    occurred.
    """
    extra: dict[str, Any] = {}
    feed_url = url
    effective_type = source_type
    conversion_note: str | None = None
    source_max_items = max(1, min(MAX_SOURCE_ITEMS, int(max_items)))

    if source_type == "youtube" and channel_id:
        extra = {"channel_id": channel_id, "handle": name}
        feed_url = youtube_channel_feed_url(channel_id)

    elif source_type == "google_news":
        lang = (language or "en").lower()
        ctry = (country or "US").upper()
        extra = {
            "query": query,
            "language": lang,
            "country": ctry,
            "max_items": source_max_items,
        }
        feed_url = (
            f"{_GNEWS_BASE}?q={quote_plus(query)}"
            f"&hl={lang}-{ctry}&gl={ctry}&ceid={ctry}:{lang}"
        )

    elif source_type == "hackernews":
        valid_feeds = {"top", "best", "new", "ask", "show"}
        feed = hn_feed if hn_feed in valid_feeds else "top"
        extra = {
            "feed": feed,
            "max_items": hn_max_items,
            "min_score": hn_min_score,
        }
        feed_url = f"{_HN_BASE}/{feed}stories.json"

    elif source_type == "reddit":
        sub = (subreddit or "").strip().lstrip("r/").lstrip("/")
        # Also try to extract subreddit from a pasted Reddit URL.
        if not sub and url:
            m = _REDDIT_HOST_RE.search(url)
            if m:
                sub = m.group(1)
        feed_url = _reddit_subreddit_to_lemmy_url(sub)
        # Keep effective_type="reddit" so the UI badge stays "Reddit".
        extra = {
            "converted_from": f"reddit:r/{sub}",
            "max_items": source_max_items,
        }
        conversion_note = (
            f"r/{sub} automatically routed via Lemmy.world RSS "
            f"(Reddit's API is blocked on most server IPs). "
            f"Feed: {feed_url}"
        )

    elif source_type == "rss" and url and _REDDIT_HOST_RE.search(url):
        # User pasted a reddit.com URL into the RSS URL field - convert it too.
        m = _REDDIT_HOST_RE.search(url)
        sub = m.group(1) if m else ""
        if sub:
            feed_url = _reddit_subreddit_to_lemmy_url(sub)
            extra = {
                "converted_from": f"reddit:r/{sub}",
                "max_items": source_max_items,
            }
            conversion_note = (
                f"Reddit URL detected and converted to a Lemmy.world RSS feed. "
                f"Feed: {feed_url}"
            )

    elif source_type == "github_releases":
        repo = (github_repo or "").strip().strip("/")
        extra = {"repo": repo, "max_items": source_max_items}
        feed_url = f"https://github.com/{repo}/releases.atom"

    elif source_type == "podcast":
        extra = {
            "feed_url": url,
            "name": name,
            "max_items": source_max_items,
        }
        feed_url = url
    if source_type == "rss" and "max_items" not in extra:
        extra["max_items"] = source_max_items

    # Persist filter rules regardless of source type.
    if hide_keywords:
        extra["hide_keywords"] = hide_keywords
    if highlight_keywords:
        extra["highlight_keywords"] = highlight_keywords
    if require_keywords:
        extra["require_keywords"] = require_keywords

    return extra, feed_url, effective_type, conversion_note

async def _read_source_payload(request: Request) -> dict[str, Any]:
    """Read source form or JSON payloads into one normalized shape."""
    ct = request.headers.get("content-type", "")
    if "multipart/form-data" in ct or "application/x-www-form-urlencoded" in ct:
        form = await request.form()

        def _fstr(key: str, default: str = "") -> str:
            value = form.get(key, default)
            return default if value is None else str(value).strip()

        def _fint(key: str, default: int = 0) -> Any:
            value = form.get(key, default)
            if key == "max_items":
                # Preserve malformed values so the API can return 422 instead
                # of silently replacing them with a valid default.
                return value
            try:
                return int(value)
            except (TypeError, ValueError):
                return value

        return {
            "source_type": _fstr("source_type", "rss"),
            "name": _fstr("name"),
            "url": _fstr("url"),
            "category": _fstr("category", "General") or "General",
            "priority": _fint("priority", 2),
            "channel_id": _fstr("channel_id"),
            "query": _fstr("query"),
            "language": _fstr("language", "en") or "en",
            "country": _fstr("country", "US") or "US",
            "max_items": _fint("max_items", DEFAULT_SOURCE_MAX_ITEMS),
            "hn_feed": _fstr("hn_feed", "top") or "top",
            "hn_max_items": _fint("hn_max_items", 20),
            "hn_min_score": _fint("hn_min_score", 50),
            "subreddit": _fstr("subreddit"),
            "reddit_sort": _fstr("reddit_sort", "hot") or "hot",
            "reddit_time_filter": _fstr("reddit_time_filter", "day") or "day",
            "reddit_max_items": _fint("reddit_max_items", 20),
            "reddit_min_score": _fint("reddit_min_score", 10),
            "github_repo": _fstr("github_repo"),
            "hide_keywords": _parse_keyword_list(_fstr("hide_keywords")),
            "highlight_keywords": _parse_keyword_list(_fstr("highlight_keywords")),
            "require_keywords": _parse_keyword_list(_fstr("require_keywords")),
        }

    body = await request.json()
    if not isinstance(body, dict):
        raise ValueError("source payload must be an object")

    def _jstr(key: str, default: str = "") -> str:
        value = body.get(key, default)
        return default if value is None else str(value).strip()

    return {
        "source_type": _jstr("source_type", "rss"),
        "name": _jstr("name"),
        "url": _jstr("url"),
        "category": _jstr("category", "General") or "General",
        "priority": body.get("priority", 2),
        "channel_id": _jstr("channel_id"),
        "query": _jstr("query"),
        "language": _jstr("language", "en") or "en",
        "country": _jstr("country", "US") or "US",
        "max_items": body.get("max_items", DEFAULT_SOURCE_MAX_ITEMS),
        "hn_feed": _jstr("hn_feed", "top") or "top",
        "hn_max_items": body.get("hn_max_items", 20),
        "hn_min_score": body.get("hn_min_score", 50),
        "subreddit": _jstr("subreddit"),
        "reddit_sort": _jstr("reddit_sort", "hot") or "hot",
        "reddit_time_filter": _jstr("reddit_time_filter", "day") or "day",
        "reddit_max_items": body.get("reddit_max_items", 20),
        "reddit_min_score": body.get("reddit_min_score", 10),
        "github_repo": _jstr("github_repo"),
        "hide_keywords": _parse_keyword_list(body.get("hide_keywords", [])),
        "highlight_keywords": _parse_keyword_list(body.get("highlight_keywords", [])),
        "require_keywords": _parse_keyword_list(body.get("require_keywords", [])),
    }


def _source_payload_error(payload: dict[str, Any]) -> str | None:
    """Return an API-facing validation message for invalid source payloads."""
    if not payload.get("name"):
        return "name field is required"
    raw_priority = payload.get("priority")
    if isinstance(raw_priority, bool):
        return "priority must be between 1 and 5"
    try:
        priority = int(raw_priority)
    except (TypeError, ValueError):
        return "priority must be between 1 and 5"
    if not 1 <= priority <= 5:
        return "priority must be between 1 and 5"

    raw_max_items = payload.get("max_items")
    if raw_max_items is None or isinstance(raw_max_items, bool):
        return "max_items must be an integer"
    if isinstance(raw_max_items, float) and not raw_max_items.is_integer():
        return "max_items must be an integer"
    try:
        max_items = int(raw_max_items)
    except (TypeError, ValueError):
        return "max_items must be an integer"
    if not 1 <= max_items <= MAX_SOURCE_ITEMS:
        return f"max_items must be between 1 and {MAX_SOURCE_ITEMS}"

    source_type = str(payload.get("source_type") or "").strip().lower()
    raw_url = payload.get("url")
    if raw_url is not None and raw_url != "":
        if canonical_url(raw_url) is None:
            return "url must be a public http(s) URL"
    elif source_type in {"rss", "podcast"}:
        return "url must be a public http(s) URL"
    return None


def create_admin_router(
    config_path: str | None,
    store: ContentStore | None = None,
    source_discovery: SourceDiscoveryService | Any | None = None,
) -> APIRouter:
    router = APIRouter()
    config = load_config(config_path)
    store = store or ContentStore()
    sources = SourceRegistry(store)
    sources.seed_from_config(config)
    keys = SecureKeyStore(store)
    discovery = GoogleNewsDiscovery()
    public_discovery_slots = asyncio.Semaphore(_PUBLIC_DISCOVERY_MAX_CONCURRENT)
    monitoring = MonitoringService(store, discovery=discovery)
    source_discovery = source_discovery or SourceDiscoveryService()

    def _digests() -> list[dict]:
        return store.list_digests(limit=12)

    def _merged():
        return apply_db_settings(load_config(config_path), store)

    @router.get("/api/config/network", response_model=None)
    async def api_get_network() -> JSONResponse:
        return JSONResponse(load_network_proxy(store).as_api_payload())

    @router.put("/api/config/network", response_model=None)
    async def api_save_network(body: dict[str, Any]) -> JSONResponse:
        enabled = body.get("enabled")
        if not isinstance(enabled, bool):
            return JSONResponse({"error": "enabled must be a boolean"}, status_code=422)
        bypass = body.get("bypass_hosts", "")
        if not isinstance(bypass, (str, list)):
            return JSONResponse(
                {"error": "bypass_hosts must be a string or list"},
                status_code=422,
            )
        proxy_url = body.get("proxy_url")
        if proxy_url is None:
            proxy_url = ""
        if not isinstance(proxy_url, str):
            return JSONResponse(
                {"error": "proxy_url must be a string"},
                status_code=422,
            )
        try:
            settings = save_network_proxy(
                store,
                enabled=enabled,
                proxy_url=proxy_url,
                bypass_hosts=bypass,
            )
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"ok": True, **settings.as_api_payload()})

    @router.post("/api/config/network/test", response_model=None)
    def api_test_network(body: dict[str, Any] | None = None) -> JSONResponse:
        settings = load_network_proxy(store)
        if body is not None:
            enabled = body.get("enabled")
            bypass = body.get("bypass_hosts", "")
            proxy_url = body.get("proxy_url") or ""
            if not isinstance(enabled, bool):
                return JSONResponse(
                    {"error": "enabled must be a boolean"},
                    status_code=422,
                )
            if not isinstance(bypass, (str, list)):
                return JSONResponse(
                    {"error": "bypass_hosts must be a string or list"},
                    status_code=422,
                )
            if not isinstance(proxy_url, str):
                return JSONResponse(
                    {"error": "proxy_url must be a string"},
                    status_code=422,
                )
            try:
                candidate = (
                    validate_proxy_url(proxy_url or settings.proxy_url)
                    if enabled
                    else ""
                )
            except ValueError as exc:
                return JSONResponse({"error": str(exc)}, status_code=422)
            settings = NetworkProxySettings(
                proxy_url=candidate,
                bypass_hosts=parse_bypass_hosts(bypass),
                source="database" if candidate else "disabled",
                youtube_proxy_override=settings.youtube_proxy_override,
            )
        try:
            result = test_network_connection(settings)
        except Exception as exc:
            return JSONResponse(
                {
                    "ok": False,
                    "proxy_used": bool(
                        settings.proxy_for_url("https://www.google.com")
                    ),
                    "error": safe_network_error(exc, settings),
                },
                status_code=502,
            )
        return JSONResponse({"ok": True, **result})

    def _sources_table_response(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "partials/sources_table_inner.html",
            page_context(
                request,
                "Sources",
                "sources",
                digests=_digests(),
                sources=sources.list_all(),
            ),
        )

    @router.get("/api/sources", response_model=None)
    async def api_list_sources() -> JSONResponse:
        return JSONResponse([dict(s) for s in sources.list_all()])
    @router.get("/api/sources/discover", response_model=None)
    async def api_discover_sources(
        q: str | None = Query(None, min_length=1, max_length=500),
        query: str | None = Query(None, min_length=1, max_length=500),
        language: str = Query("en", max_length=8),
        country: str = Query("US", min_length=2, max_length=2),
        page: int = Query(1, ge=1, le=1_000),
        limit: int | None = Query(None, ge=1, le=100),
        max_items: int | None = Query(None, ge=1, le=200),
    ) -> JSONResponse:
        """Preview publisher feeds without creating or changing any rows."""
        search_term = (q or query or "").strip()
        if not search_term:
            return JSONResponse(
                {"error": "q or query is required"},
                status_code=422,
            )
        requested_limit = max_items if max_items is not None else (limit or 20)
        try:
            discover = getattr(source_discovery, "search", None)
            if not callable(discover):
                discover = getattr(source_discovery, "discover", None)
            if not callable(discover):
                raise SourceDiscoveryError("discovery service unavailable")
            result = await run_in_threadpool(
                discover,
                search_term,
                language=language,
                country=country,
                page=page,
                limit=requested_limit,
                existing_sources=sources.list_all(),
            )
        except ValueError as exc:
            # Validation messages are bounded and contain no upstream data.
            message = str(exc).strip()[:200] or "Invalid discovery request."
            return JSONResponse({"error": message}, status_code=422)
        except SourceDiscoveryError:
            return JSONResponse(
                {"error": "Source discovery is temporarily unavailable."},
                status_code=502,
            )
        except Exception:
            return JSONResponse(
                {"error": "Source discovery is temporarily unavailable."},
                status_code=502,
            )
        if not isinstance(result, dict):
            return JSONResponse(
                {"error": "Source discovery returned an invalid response."},
                status_code=502,
            )
        return JSONResponse(result)


    @router.post("/api/sources", response_model=None)
    async def api_add_source(request: Request) -> JSONResponse:
        try:
            payload = await _read_source_payload(request)
        except (TypeError, ValueError):
            return JSONResponse(
                {"error": "invalid source payload"},
                status_code=422,
            )
        error = _source_payload_error(payload)
        if error is not None:
            return JSONResponse({"error": error}, status_code=422)
        source_type = str(payload["source_type"])
        name = str(payload["name"])
        url = str(payload["url"])
        category = str(payload["category"])
        priority = int(payload["priority"])
        channel_id = str(payload["channel_id"])
        source_max_items = int(payload["max_items"])
        query = str(payload["query"])
        language = str(payload["language"])
        country = str(payload["country"])
        hn_feed = str(payload["hn_feed"])
        hn_max_items = int(payload["hn_max_items"])
        hn_min_score = int(payload["hn_min_score"])
        subreddit = str(payload["subreddit"])
        reddit_sort = str(payload["reddit_sort"])
        reddit_time_filter = str(payload["reddit_time_filter"])
        reddit_max_items = int(payload["reddit_max_items"])
        reddit_min_score = int(payload["reddit_min_score"])
        github_repo = str(payload["github_repo"])

        extra, feed_url, effective_type, conversion_note = _build_source_extra(
            source_type,
            url,
            channel_id,
            name,
            query=query,
            language=language,
            country=country,
            max_items=source_max_items,
            hn_feed=hn_feed,
            hn_max_items=hn_max_items,
            hn_min_score=hn_min_score,
            subreddit=subreddit,
            reddit_sort=reddit_sort,
            reddit_time_filter=reddit_time_filter,
            reddit_max_items=reddit_max_items,
            reddit_min_score=reddit_min_score,
            github_repo=github_repo,
            hide_keywords=payload["hide_keywords"],
            highlight_keywords=payload["highlight_keywords"],
            require_keywords=payload["require_keywords"],
        )
        sources.add(effective_type, name, category, priority, feed_url, extra=extra)
        resp: dict[str, Any] = {"ok": True}
        if conversion_note:
            resp["note"] = conversion_note
        return JSONResponse(resp)

    @router.put("/api/sources/{source_id}", response_model=None)
    async def api_update_source(source_id: int, request: Request) -> JSONResponse:
        try:
            payload = await _read_source_payload(request)
        except (TypeError, ValueError):
            return JSONResponse(
                {"error": "invalid source payload"},
                status_code=422,
            )
        error = _source_payload_error(payload)
        if error is not None:
            return JSONResponse({"error": error}, status_code=422)

        extra, feed_url, effective_type, conversion_note = _build_source_extra(
            str(payload["source_type"]),
            str(payload["url"]),
            str(payload["channel_id"]),
            str(payload["name"]),
            query=str(payload["query"]),
            language=str(payload["language"]),
            max_items=int(payload["max_items"]),
            country=str(payload["country"]),
            hn_feed=str(payload["hn_feed"]),
            hn_max_items=int(payload["hn_max_items"]),
            hn_min_score=int(payload["hn_min_score"]),
            subreddit=str(payload["subreddit"]),
            reddit_sort=str(payload["reddit_sort"]),
            reddit_time_filter=str(payload["reddit_time_filter"]),
            reddit_max_items=int(payload["reddit_max_items"]),
            reddit_min_score=int(payload["reddit_min_score"]),
            github_repo=str(payload["github_repo"]),
            hide_keywords=payload["hide_keywords"],
            highlight_keywords=payload["highlight_keywords"],
            require_keywords=payload["require_keywords"],
        )
        sources.update(
            source_id,
            effective_type,
            str(payload["name"]),
            str(payload["category"]),
            int(payload["priority"]),
            feed_url,
            extra=extra,
        )
        resp: dict[str, Any] = {"ok": True}
        if conversion_note:
            resp["note"] = conversion_note
        return JSONResponse(resp)

    @router.delete("/api/sources/{source_id}", response_model=None)
    async def api_delete_source(source_id: int) -> JSONResponse:
        sources.delete(source_id)
        return JSONResponse({"ok": True})

    @router.patch("/api/sources/{source_id}/toggle", response_model=None)
    async def api_toggle_source(source_id: int, body: dict[str, Any]) -> JSONResponse:
        """Enable or disable a source. Body: ``{"enabled": true|false}``."""
        if "enabled" not in body:
            return JSONResponse({"error": "enabled field is required"}, status_code=422)
        sources.toggle(source_id, bool(body["enabled"]))
        return JSONResponse({"ok": True})

    @router.post("/api/sources/import-opml", response_model=None)
    async def api_import_opml(file: UploadFile = File(...)) -> JSONResponse:
        raw = await file.read(MAX_OPML_BYTES + 1)
        if len(raw) > MAX_OPML_BYTES:
            return JSONResponse({"error": "OPML file is too large."}, status_code=413)
        text = raw.decode("utf-8", errors="replace")
        try:
            outline_rows = parse_opml_outlines(text)
        except Exception:
            return JSONResponse({"error": "Invalid OPML file."}, status_code=400)
        existing = {r["url"] for r in sources.list_all()}
        added = 0
        for row in outline_rows:
            xml_url = canonical_url(row.get("xmlUrl"))
            if xml_url is None or xml_url in existing:
                continue
            title = row.get("title") or xml_url
            sources.add("rss", title[:240], "Imported", 2, xml_url)
            existing.add(xml_url)
            added += 1
        return JSONResponse({"added": added})

    @router.get("/api/sources/export.opml", response_class=PlainTextResponse)
    async def api_export_opml() -> PlainTextResponse:
        body = build_opml(sources.list_all())
        return PlainTextResponse(
            body,
            media_type="application/xml; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="elpis-sources.opml"',
            },
        )

    def _provider_payload(merged) -> dict[str, Any]:
        stored_rows = {
            str(row["service"]): row for row in keys.list_keys()
        }
        rows: list[dict[str, Any]] = []
        for spec in PROVIDER_SPECS:
            secret = keys.get_key(spec.key_service) or ""
            if spec.id == "openrouter":
                secret = secret or merged.llm.openrouter_api_key
            elif spec.id in {"openai", "custom"}:
                secret = secret or merged.llm.openai_api_key
            stored = stored_rows.get(spec.key_service)
            rows.append(
                {
                    "id": spec.id,
                    "label": spec.label,
                    "description": spec.description,
                    "litellm_provider": spec.litellm_provider,
                    "base_url": get_provider_base_url(merged, spec.id),
                    "default_base_url": spec.default_base_url,
                    "supports_base_url": spec.supports_base_url,
                    "requires_api_key": spec.requires_api_key,
                    "api_key_configured": bool(secret),
                    "key_preview": (
                        str(stored["key_preview"])
                        if stored is not None
                        else ("Configured via environment" if secret else "")
                    ),
                }
            )
        ollama_host = get_provider_base_url(merged, "ollama")
        try:
            ollama_models = ollama_list_tags(ollama_host)
            ollama_reachable = True
        except Exception:
            ollama_models = []
            ollama_reachable = False
        cheapest = (
            pick_cheapest_text_model()
            if merged.llm.openrouter_pick_cheapest
            else None
        )
        return {
            "active_provider": merged.llm.provider,
            "providers": rows,
            "openrouter_pick_cheapest": merged.llm.openrouter_pick_cheapest,
            "cheapest_model_id": cheapest,
            "ollama_host": ollama_host,
            "ollama_models": ollama_models,
            "ollama_reachable": ollama_reachable,
        }

    @router.get("/api/config/providers", response_model=None)
    async def api_get_providers() -> JSONResponse:
        payload = await run_in_threadpool(_provider_payload, _merged())
        return JSONResponse(payload)

    @router.put("/api/config/providers", response_model=None)
    async def api_save_providers(body: dict[str, Any]) -> JSONResponse:
        active = str(body.get("active_provider", "")).strip().lower()
        valid_ids = {spec.id for spec in PROVIDER_SPECS} | {"fallback"}
        if active not in valid_ids:
            return JSONResponse({"error": "Unknown provider"}, status_code=422)

        endpoints = body.get("endpoints", {})
        if not isinstance(endpoints, dict):
            return JSONResponse(
                {"error": "endpoints must be an object"},
                status_code=422,
            )
        cleaned: dict[str, dict[str, str]] = {}
        for provider_id, raw in endpoints.items():
            spec = get_provider_spec(str(provider_id))
            if spec is None or not isinstance(raw, dict):
                continue
            base_url = str(raw.get("base_url", "")).strip().rstrip("/")
            if base_url and not base_url.startswith(("http://", "https://")):
                return JSONResponse(
                    {"error": f"{spec.label} base URL must use http:// or https://"},
                    status_code=422,
                )
            if base_url:
                cleaned[spec.id] = {"base_url": base_url}

        if active == "custom" and not cleaned.get("custom", {}).get("base_url"):
            return JSONResponse(
                {"error": "Custom OpenAI-compatible base URL is required"},
                status_code=422,
            )

        store.set_setting("llm_provider", active)
        store.set_setting("llm_providers", json.dumps(cleaned))
        if "openrouter_pick_cheapest" in body:
            store.set_setting(
                "openrouter_pick_cheapest",
                "1" if bool(body["openrouter_pick_cheapest"]) else "0",
            )
        return JSONResponse({"ok": True})

    @router.get("/api/config/llm", response_model=None)
    async def api_get_llm() -> JSONResponse:
        merged = _merged()
        return JSONResponse(
            {
                "provider": merged.llm.provider,
                "model": get_provider_model(merged, store),
                "reasoning_effort": merged.llm.reasoning_effort,
                "thinking_enabled": merged.llm.thinking_enabled,
                "thinking_budget_tokens": merged.llm.thinking_budget_tokens,
            }
        )

    @router.put("/api/config/llm", response_model=None)
    async def api_save_llm(body: dict[str, Any]) -> JSONResponse:
        if "model" in body:
            model = str(body["model"]).strip()
            if not model:
                return JSONResponse({"error": "model is required"}, status_code=422)
            store.set_setting("model", model)
        if "reasoning_effort" in body:
            effort = str(body["reasoning_effort"]).strip().lower()
            if effort not in {"none", "minimal", "low", "medium", "high", "xhigh"}:
                return JSONResponse(
                    {"error": "Invalid reasoning_effort"},
                    status_code=422,
                )
            store.set_setting("reasoning_effort", effort)
        if "thinking_enabled" in body:
            if not isinstance(body["thinking_enabled"], bool):
                return JSONResponse(
                    {"error": "thinking_enabled must be a boolean"},
                    status_code=422,
                )
            store.set_setting(
                "thinking_enabled",
                "1" if body["thinking_enabled"] else "0",
            )
        if "thinking_budget_tokens" in body:
            try:
                budget = int(body["thinking_budget_tokens"])
            except (TypeError, ValueError):
                return JSONResponse(
                    {"error": "thinking_budget_tokens must be 0-100000"},
                    status_code=422,
                )
            if not 0 <= budget <= 100000:
                return JSONResponse(
                    {"error": "thinking_budget_tokens must be 0-100000"},
                    status_code=422,
                )
            store.set_setting("thinking_budget_tokens", str(budget))
        return JSONResponse({"ok": True})

    @router.post("/api/config/llm/ollama/pull", response_model=None)
    async def api_ollama_pull(body: dict[str, Any]) -> JSONResponse:
        merged = _merged()
        model = str(body.get("model", "")).strip()
        if not model:
            return JSONResponse({"error": "model required"}, status_code=422)
        try:
            await run_in_threadpool(
                ollama_pull,
                get_provider_base_url(merged, "ollama"),
                model,
            )
            return JSONResponse({"message": f"Pulled {model}."})
        except Exception as exc:
            return JSONResponse({"message": f"Pull failed: {exc}"}, status_code=500)

    @router.post("/api/config/llm/ollama/delete", response_model=None)
    async def api_ollama_delete(body: dict[str, Any]) -> JSONResponse:
        merged = _merged()
        model = str(body.get("model", "")).strip()
        if not model:
            return JSONResponse({"error": "model required"}, status_code=422)
        try:
            await run_in_threadpool(
                ollama_delete,
                get_provider_base_url(merged, "ollama"),
                model,
            )
            return JSONResponse({"message": f"Deleted {model}."})
        except Exception as exc:
            return JSONResponse({"message": f"Delete failed: {exc}"}, status_code=500)

    @router.get("/api/config/keys", response_model=None)
    async def api_list_keys() -> JSONResponse:
        return JSONResponse(
            [
                {"service": k["service"], "key_preview": k["key_preview"]}
                for k in keys.list_keys()
            ]
        )

    @router.post("/api/config/keys", response_model=None)
    async def api_save_key(body: dict[str, Any]) -> JSONResponse:
        service = str(body.get("service", "")).strip().lower()
        key_value = str(body.get("key_value", "")).strip()
        valid_services = {spec.key_service for spec in PROVIDER_SPECS} | {"resend"}
        if service not in valid_services:
            return JSONResponse({"error": "Unsupported provider key"}, status_code=422)
        if not key_value:
            return JSONResponse(
                {"error": "service and key_value required"},
                status_code=422,
            )
        keys.store_key(service, key_value)
        return JSONResponse({"ok": True})

    @router.delete("/api/config/keys/{service}", response_model=None)
    async def api_delete_key(service: str) -> JSONResponse:
        service = service.strip().lower()
        valid_services = {spec.key_service for spec in PROVIDER_SPECS} | {"resend"}
        if service not in valid_services:
            return JSONResponse({"error": "Unsupported provider key"}, status_code=422)
        keys.delete_key(service)
        return JSONResponse({"ok": True})

    @router.get("/api/config/digest", response_model=None)
    async def api_get_digest_config() -> JSONResponse:
        merged = _merged()
        langs_raw = store.get_setting("preferred_languages", "")
        try:
            langs = json.loads(langs_raw) if langs_raw else merged.preferred_languages
        except Exception:
            langs = merged.preferred_languages
        kw_raw = store.get_setting("exclude_keywords", "")
        try:
            excl_kw = json.loads(kw_raw) if kw_raw else merged.exclude_keywords
        except Exception:
            excl_kw = merged.exclude_keywords
        digest_lang = store.get_setting("digest_language", "") or merged.digest_language
        return JSONResponse(
            {
                "max_articles_per_digest": merged.max_articles_per_digest,
                "digest_history_limit": merged.digest_history_limit,
                "balance_digest_categories": merged.balance_digest_categories,
                "max_articles_per_category": merged.max_articles_per_category,
                "max_article_age_hours": merged.max_article_age_hours,
                "preferred_languages": langs,
                "exclude_keywords": excl_kw,
                "disliked_keywords": merged.relevance.disliked_keywords,
                "max_key_takeaways": merged.max_key_takeaways,
                "max_summary_paragraphs": merged.max_summary_paragraphs,
                "digest_language": digest_lang,
                "youtube_transcription_enabled": merged.youtube_transcription.enabled,
                "youtube_transcription_model": merged.youtube_transcription.model,
                "youtube_transcription_max_duration": (
                    merged.youtube_transcription.max_duration_seconds
                ),
            }
        )

    @router.put("/api/config/digest", response_model=None)
    async def api_save_digest_config(body: dict[str, Any]) -> JSONResponse:
        if "max_articles_per_digest" in body:
            try:
                val = int(body["max_articles_per_digest"])
                if 1 <= val <= 200:
                    store.set_setting("max_articles_per_digest", str(val))
                else:
                    return JSONResponse(
                        {"error": "max_articles_per_digest must be 1-200"},
                        status_code=422,
                    )
            except (ValueError, TypeError):
                return JSONResponse(
                    {"error": "max_articles_per_digest must be 1-200"},
                    status_code=422,
                )
        if "digest_history_limit" in body:
            try:
                val = int(body["digest_history_limit"])
                if 1 <= val <= 1000:
                    store.set_setting("digest_history_limit", str(val))
                    store.prune_digests(val)
                else:
                    return JSONResponse(
                        {"error": "digest_history_limit must be 1-1000"},
                        status_code=422,
                    )
            except (ValueError, TypeError):
                return JSONResponse(
                    {"error": "digest_history_limit must be 1-1000"},
                    status_code=422,
                )
        if "balance_digest_categories" in body:
            store.set_setting(
                "balance_digest_categories",
                "1" if body["balance_digest_categories"] else "0",
            )
        if "max_articles_per_category" in body:
            try:
                val = int(body["max_articles_per_category"])
                if 1 <= val <= 50:
                    store.set_setting("max_articles_per_category", str(val))
                else:
                    return JSONResponse(
                        {"error": "max_articles_per_category must be 1-50"},
                        status_code=422,
                    )
            except (ValueError, TypeError):
                return JSONResponse(
                    {"error": "max_articles_per_category must be 1-50"},
                    status_code=422,
                )
        if "max_article_age_hours" in body:
            try:
                val = int(body["max_article_age_hours"])
                if val >= 0:
                    store.set_setting("max_article_age_hours", str(val))
                else:
                    return JSONResponse(
                        {"error": "max_article_age_hours must be 0 or greater"},
                        status_code=422,
                    )
            except (ValueError, TypeError):
                return JSONResponse(
                    {"error": "max_article_age_hours must be 0 or greater"},
                    status_code=422,
                )
        if "preferred_languages" in body:
            langs = body["preferred_languages"]
            if not isinstance(langs, list):
                return JSONResponse(
                    {"error": "preferred_languages must be a list"},
                    status_code=422,
                )
            cleaned = [
                str(language).strip().lower()
                for language in langs
                if str(language).strip()
            ]
            store.set_setting("preferred_languages", json.dumps(cleaned))
        if "exclude_keywords" in body:
            kw_list = body["exclude_keywords"]
            if not isinstance(kw_list, list):
                return JSONResponse(
                    {"error": "exclude_keywords must be a list"},
                    status_code=422,
                )
            cleaned_kw = [
                str(phrase).strip() for phrase in kw_list if str(phrase).strip()
            ]
            store.set_setting("exclude_keywords", json.dumps(cleaned_kw))
        if "disliked_keywords" in body:
            dk_list = body["disliked_keywords"]
            if not isinstance(dk_list, list):
                return JSONResponse(
                    {"error": "disliked_keywords must be a list"},
                    status_code=422,
                )
            # Persisted under the onboarding key the ranking engine already
            # consumes (settings_overlay merges it into relevance.disliked_keywords).
            cleaned_dk = [
                str(phrase).strip() for phrase in dk_list if str(phrase).strip()
            ]
            store.set_setting("bootstrap_dislikes", json.dumps(cleaned_dk))
        if "max_key_takeaways" in body:
            try:
                val = int(body["max_key_takeaways"])
                if 1 <= val <= 10:
                    store.set_setting("max_key_takeaways", str(val))
            except (ValueError, TypeError):
                return JSONResponse(
                    {"error": "max_key_takeaways must be 1-10"},
                    status_code=422,
                )
        if "max_summary_paragraphs" in body:
            try:
                val = int(body["max_summary_paragraphs"])
                if 1 <= val <= 10:
                    store.set_setting("max_summary_paragraphs", str(val))
            except (ValueError, TypeError):
                return JSONResponse(
                    {"error": "max_summary_paragraphs must be 1-10"},
                    status_code=422,
                )
        if "digest_language" in body:
            lang_val = str(body["digest_language"]).strip().lower()
            if lang_val:
                store.set_setting("digest_language", lang_val)
            else:
                store.set_setting("digest_language", "en")
        if "youtube_transcription_enabled" in body:
            store.set_setting(
                "youtube_transcription_enabled",
                "1" if body["youtube_transcription_enabled"] else "0",
            )
        if "youtube_transcription_model" in body:
            model_val = str(body["youtube_transcription_model"]).strip()
            if model_val:
                store.set_setting("youtube_transcription_model", model_val)
        if "youtube_transcription_max_duration" in body:
            try:
                val = int(body["youtube_transcription_max_duration"])
                if 60 <= val <= 7200:
                    store.set_setting("youtube_transcription_max_duration", str(val))
            except (ValueError, TypeError):
                return JSONResponse(
                    {"error": "youtube_transcription_max_duration must be 60-7200"},
                    status_code=422,
                )
        return JSONResponse({"ok": True})

    @router.get("/api/config/budget-limits", response_model=None)
    async def api_get_budget_limits() -> JSONResponse:
        merged = _merged()
        return JSONResponse(
            {
                "daily_budget_usd": merged.llm.openrouter_daily_budget_usd,
                "monthly_budget_usd": merged.llm.openrouter_monthly_budget_usd,
            }
        )

    @router.put("/api/config/budget-limits", response_model=None)
    async def api_save_budget_limits(body: dict[str, Any]) -> JSONResponse:
        if "daily_budget_usd" in body:
            try:
                val = float(body["daily_budget_usd"])
                if val < 0:
                    raise ValueError
                store.set_setting("openrouter_daily_budget_usd", str(val))
            except (ValueError, TypeError):
                return JSONResponse(
                    {"error": "daily_budget_usd must be a non-negative number"},
                    status_code=422,
                )
        if "monthly_budget_usd" in body:
            try:
                val = float(body["monthly_budget_usd"])
                if val < 0:
                    raise ValueError
                store.set_setting("openrouter_monthly_budget_usd", str(val))
            except (ValueError, TypeError):
                return JSONResponse(
                    {"error": "monthly_budget_usd must be a non-negative number"},
                    status_code=422,
                )
        return JSONResponse({"ok": True})

    @router.get("/api/config/password-info", response_model=None)
    async def api_password_info() -> JSONResponse:
        """Return the current password source so the UI can show a warning."""
        db_pw = store.get_setting("auth_password", "")
        if db_pw:
            source = "db"
        else:
            env_pw = (
                os.environ.get("CONDENSEIT_AUTH_PASSWORD", "").strip()
                or os.environ.get("DIGEST_PWA_AUTH_PASSWORD", "").strip()
            )
            source = "env" if env_pw else "default"
        return JSONResponse({"source": source, "using_default": source == "default"})

    @router.put("/api/config/password", response_model=None)
    async def api_change_password(
        request: Request,
        body: dict[str, Any],
    ) -> JSONResponse:
        """Change the admin password and store only a password hash."""
        current = str(body.get("current_password", "")).strip()
        new_pw = str(body.get("new_password", "")).strip()

        if not current or not new_pw:
            return JSONResponse(
                {"error": "current_password and new_password are required"},
                status_code=422,
            )
        if len(new_pw) < 8 or len(new_pw) > 256:
            return JSONResponse(
                {"error": "New password must be between 8 and 256 characters."},
                status_code=422,
            )

        db_pw = store.get_setting("auth_password", "")
        env_pw = (
            os.environ.get("CONDENSEIT_AUTH_PASSWORD", "").strip()
            or os.environ.get("DIGEST_PWA_AUTH_PASSWORD", "").strip()
        )
        effective = db_pw or env_pw or LOCAL_INSTALL_FALLBACK_CREDENTIAL

        if not verify_password(current, effective):
            return JSONResponse(
                {"error": "Current password is incorrect."},
                status_code=401,
            )

        store.set_setting("auth_password", hash_password(new_pw))
        generation = secrets.token_hex(16)
        store.set_setting("auth_generation", generation)
        request.session["authenticated"] = True
        request.session["auth_generation"] = generation
        return JSONResponse({"ok": True})

    def _feed_url(request: Request, token: str) -> str:
        base = str(request.base_url).rstrip("/")
        return f"{base}/api/feed/atom?token={token}"

    @router.get("/api/config/feed-token", response_model=None)
    async def api_get_feed_token(request: Request) -> JSONResponse:
        token = store.get_setting("feed_token", "")
        if token:
            return JSONResponse(
                {"exists": True, "token": token, "feed_url": _feed_url(request, token)}
            )
        return JSONResponse({"exists": False, "token": None, "feed_url": None})

    @router.post("/api/config/feed-token", response_model=None)
    async def api_generate_feed_token(request: Request) -> JSONResponse:
        token = secrets.token_urlsafe(32)
        store.set_setting("feed_token", token)
        return JSONResponse(
            {"exists": True, "token": token, "feed_url": _feed_url(request, token)}
        )

    @router.delete("/api/config/feed-token", response_model=None)
    async def api_revoke_feed_token() -> JSONResponse:
        store.set_setting("feed_token", "")
        return JSONResponse({"ok": True})

    @router.get("/api/logs", response_model=None)
    async def api_list_logs() -> JSONResponse:
        rows = store.list_run_logs(limit=30)
        return JSONResponse([dict(r) for r in rows])

    @router.get("/api/logs/latest", response_model=None)
    async def api_latest_log() -> JSONResponse:
        row = store.latest_run_log()
        if not row:
            return JSONResponse(None)
        return JSONResponse(dict(row))

    @router.get("/api/logs/{log_id}", response_model=None)
    async def api_get_log(log_id: int) -> JSONResponse:
        row = store.get_run_log(log_id)
        if not row:
            return JSONResponse(None, status_code=404)
        return JSONResponse(dict(row))

    @router.get("/admin/", response_model=None)
    async def admin_home() -> RedirectResponse:
        return RedirectResponse("/admin/sources", status_code=303)

    @router.get("/admin/sources", response_class=HTMLResponse)
    async def sources_list(request: Request) -> HTMLResponse:
        if _is_htmx(request):
            return _sources_table_response(request)
        return templates.TemplateResponse(
            request,
            "sources.html",
            page_context(
                request,
                "Sources",
                "sources",
                digests=_digests(),
                sources=sources.list_all(),
            ),
        )

    @router.get("/admin/sources/table", response_class=HTMLResponse)
    async def sources_table(request: Request) -> HTMLResponse:
        return _sources_table_response(request)

    @router.post("/admin/sources", response_model=None)
    async def sources_add(
        request: Request,
        source_type: str = Form(...),
        name: str = Form(...),
        url: str = Form(""),
        category: str = Form("General"),
        priority: int = Form(2),
        channel_id: str = Form(""),
        query: str = Form(""),
        language: str = Form("en"),
        country: str = Form("US"),
        max_items: int = Form(DEFAULT_SOURCE_MAX_ITEMS),
        hn_feed: str = Form("top"),
        hn_max_items: int = Form(20),
        hn_min_score: int = Form(50),
        subreddit: str = Form(""),
        reddit_sort: str = Form("hot"),
        reddit_time_filter: str = Form("day"),
        reddit_max_items: int = Form(20),
        reddit_min_score: int = Form(10),
        github_repo: str = Form(""),
    ) -> HTMLResponse | RedirectResponse:
        payload_error = _source_payload_error(
            {
                "name": name.strip(),
                "priority": priority,
                "max_items": max_items,
                "source_type": source_type,
                "url": url.strip(),
            }
        )
        if payload_error is not None:
            return JSONResponse({"error": payload_error}, status_code=422)
        extra, feed_url, effective_type, _note = _build_source_extra(
            source_type,
            url,
            channel_id,
            name,
            query=query,
            language=language,
            country=country,
            max_items=max_items,
            hn_feed=hn_feed,
            hn_max_items=hn_max_items,
            hn_min_score=hn_min_score,
            subreddit=subreddit,
            reddit_sort=reddit_sort,
            reddit_time_filter=reddit_time_filter,
            reddit_max_items=reddit_max_items,
            reddit_min_score=reddit_min_score,
            github_repo=github_repo,
        )
        sources.add(effective_type, name, category, priority, feed_url, extra=extra)
        if _is_htmx(request):
            return _sources_table_response(request)
        return RedirectResponse("/admin/sources", status_code=303)

    @router.post("/admin/sources/{source_id}/delete", response_model=None)
    async def sources_delete(
        request: Request,
        source_id: int,
    ) -> HTMLResponse | RedirectResponse:
        sources.delete(source_id)
        if _is_htmx(request):
            return _sources_table_response(request)
        return RedirectResponse("/admin/sources", status_code=303)

    @router.post("/admin/sources/import-opml", response_model=None)
    async def sources_import_opml(
        request: Request,
        file: UploadFile = File(...),
    ) -> HTMLResponse | RedirectResponse:
        raw = await file.read(MAX_OPML_BYTES + 1)
        if len(raw) > MAX_OPML_BYTES:
            if _is_htmx(request):
                return HTMLResponse(
                    '<p class="flash flash-warn">OPML file is too large.</p>',
                    status_code=413,
                )
            return RedirectResponse("/admin/sources?imported=0&err=1", status_code=303)
        text = raw.decode("utf-8", errors="replace")
        try:
            outline_rows = parse_opml_outlines(text)
        except Exception:
            if _is_htmx(request):
                return HTMLResponse(
                    '<p class="flash flash-warn">Invalid OPML file.</p>',
                    status_code=400,
                )
            return RedirectResponse("/admin/sources?imported=0&err=1", status_code=303)
        existing = {r["url"] for r in sources.list_all()}
        added = 0
        for row in outline_rows:
            xml_url = canonical_url(row.get("xmlUrl"))
            if xml_url is None or xml_url in existing:
                continue
            title = row.get("title") or xml_url
            sources.add("rss", title[:240], "Imported", 2, xml_url)
            existing.add(xml_url)
            added += 1
        if _is_htmx(request):
            return _sources_table_response(request)
        return RedirectResponse(
            f"/admin/sources?imported={added}",
            status_code=303,
        )

    @router.get("/admin/sources/export.opml", response_class=PlainTextResponse)
    async def sources_export_opml() -> PlainTextResponse:
        body = build_opml(sources.list_all())
        return PlainTextResponse(
            body,
            media_type="application/xml; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="elpis-sources.opml"',
            },
        )

    @router.get("/admin/llm", response_class=HTMLResponse)
    async def llm_config(request: Request) -> HTMLResponse:
        merged = _merged()
        return templates.TemplateResponse(
            request,
            "llm_config.html",
            page_context(
                request,
                "LLM",
                "llm",
                digests=_digests(),
                model=get_provider_model(merged, store),
                provider=merged.llm.provider,
                reasoning_effort=merged.llm.reasoning_effort,
                thinking_enabled=merged.llm.thinking_enabled,
                thinking_budget_tokens=merged.llm.thinking_budget_tokens,
                msg=request.query_params.get("msg", ""),
            ),
        )

    @router.post("/admin/llm")
    async def llm_save(
        model: str = Form(...),
        reasoning_effort: str = Form("none"),
        thinking_enabled: str = Form(""),
        thinking_budget_tokens: str = Form("0"),
    ) -> RedirectResponse:
        effort = reasoning_effort.strip().lower()
        if effort not in {"none", "minimal", "low", "medium", "high", "xhigh"}:
            effort = "none"
        try:
            budget = max(0, min(100000, int(thinking_budget_tokens)))
        except ValueError:
            budget = 0
        store.set_setting("model", model.strip())
        store.set_setting("reasoning_effort", effort)
        store.set_setting("thinking_enabled", "1" if thinking_enabled == "on" else "0")
        store.set_setting("thinking_budget_tokens", str(budget))
        return RedirectResponse("/admin/llm", status_code=303)

    @router.post("/admin/llm/ollama/pull", response_model=None)
    async def llm_ollama_pull(
        request: Request,
        pull_model: str = Form(...),
    ) -> HTMLResponse | RedirectResponse:
        merged = _merged()
        try:
            ollama_pull(get_provider_base_url(merged, "ollama"), pull_model)
            msg = f"Pulled {pull_model}."
        except Exception as exc:
            msg = f"Pull failed: {exc}"
        if _is_htmx(request):
            return HTMLResponse(f'<p class="flash">{msg}</p>')
        return RedirectResponse(f"/admin/llm?msg={quote(msg[:500])}", status_code=303)

    @router.post("/admin/llm/ollama/delete", response_model=None)
    async def llm_ollama_delete(
        request: Request,
        delete_model: str = Form(...),
    ) -> HTMLResponse | RedirectResponse:
        merged = _merged()
        try:
            ollama_delete(get_provider_base_url(merged, "ollama"), delete_model)
            msg = f"Deleted {delete_model}."
        except Exception as exc:
            msg = f"Delete failed: {exc}"
        if _is_htmx(request):
            return HTMLResponse(f'<p class="flash flash-warn">{msg}</p>')
        return RedirectResponse(f"/admin/llm?msg={quote(msg[:500])}", status_code=303)

    @router.get("/admin/providers", response_class=HTMLResponse)
    async def providers_page(request: Request) -> HTMLResponse:
        payload = await run_in_threadpool(_provider_payload, _merged())
        return templates.TemplateResponse(
            request,
            "providers.html",
            page_context(
                request,
                "Providers",
                "providers",
                digests=_digests(),
                providers=payload["providers"],
                active_provider=payload["active_provider"],
                openrouter_pick_cheapest=payload["openrouter_pick_cheapest"],
                ollama_host=payload["ollama_host"],
                ollama_models=payload["ollama_models"],
                msg=request.query_params.get("msg", ""),
            ),
        )

    @router.post("/admin/providers")
    async def providers_save(request: Request) -> RedirectResponse:
        form = await request.form()
        active = str(form.get("active_provider", "")).strip().lower()
        valid_ids = {spec.id for spec in PROVIDER_SPECS} | {"fallback"}
        if active not in valid_ids:
            return RedirectResponse(
                "/admin/providers?msg=Unknown%20provider",
                status_code=303,
            )
        endpoints: dict[str, dict[str, str]] = {}
        for spec in PROVIDER_SPECS:
            base_url = str(form.get(f"base_url_{spec.id}", "")).strip().rstrip("/")
            if base_url:
                endpoints[spec.id] = {"base_url": base_url}
        if active == "custom" and not endpoints.get("custom", {}).get("base_url"):
            return RedirectResponse(
                "/admin/providers?msg=Custom%20base%20URL%20is%20required",
                status_code=303,
            )
        store.set_setting("llm_provider", active)
        store.set_setting("llm_providers", json.dumps(endpoints))
        store.set_setting(
            "openrouter_pick_cheapest",
            "1" if form.get("openrouter_pick_cheapest") == "on" else "0",
        )
        return RedirectResponse("/admin/providers", status_code=303)

    @router.get("/admin/keys")
    async def keys_page() -> RedirectResponse:
        return RedirectResponse("/admin/providers", status_code=303)

    @router.post("/admin/keys")
    async def keys_save(
        service: str = Form(...),
        key_value: str = Form(...),
    ) -> RedirectResponse:
        valid_services = {spec.key_service for spec in PROVIDER_SPECS}
        if service.strip().lower() in valid_services and key_value.strip():
            keys.store_key(service.strip().lower(), key_value.strip())
        return RedirectResponse("/admin/providers", status_code=303)

    @router.post("/admin/keys/{service}/delete")
    async def keys_delete(service: str) -> RedirectResponse:
        keys.delete_key(service.strip().lower())
        return RedirectResponse("/admin/providers", status_code=303)

    @router.get("/api/discovery", response_model=None)
    @router.get("/api/discover", response_model=None)
    async def api_discover(
        q: str | None = Query(None, max_length=500),
        query: str | None = Query(None, max_length=500),
        language: str = Query("en", max_length=8),
        country: str = Query("US", max_length=2),
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=MAX_MONITOR_ITEMS),
        max_items: int | None = Query(None, ge=1, le=MAX_MONITOR_ITEMS),
    ) -> JSONResponse:
        search_query = (q if q is not None else query or "").strip()
        if not search_query:
            return JSONResponse({"error": "q or query is required"}, status_code=422)
        page_limit = int(max_items or limit)
        offset = (page - 1) * page_limit
        fetch_limit = min(MAX_MONITOR_ITEMS, offset + page_limit + 1)
        try:
            async with public_discovery_slots:
                results = await run_in_threadpool(
                    discovery.search,
                    search_query,
                    language=language,
                    country=country,
                    max_items=fetch_limit,
                )
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        except Exception:
            # Public discovery must not expose upstream response bodies or
            # credentials.  The generic error remains useful to clients.
            return JSONResponse(
                {"error": "discovery search failed"},
                status_code=502,
            )
        page_results = results[offset : offset + page_limit]
        has_more = len(results) > offset + page_limit
        return JSONResponse(
            {
                "query": search_query,
                "results": page_results,
                "items": page_results,
                "page": page,
                "limit": page_limit,
                "has_more": has_more,
                "total": None,
            }
        )

    def _validated_monitor_payload(
        body: dict[str, Any],
        *,
        partial: bool,
    ) -> tuple[dict[str, Any] | None, JSONResponse | None]:
        try:
            return validate_monitor_payload(body, partial=partial), None
        except ValueError as exc:
            return None, JSONResponse({"error": str(exc)}, status_code=422)

    @router.get("/api/admin/monitoring", response_model=None)
    @router.get("/api/monitoring", response_model=None)
    async def api_list_monitoring(
        enabled: bool | None = Query(None),
    ) -> JSONResponse:
        rows = monitoring.list_monitors(enabled_only=enabled is True)
        if enabled is False:
            rows = [row for row in rows if not row.get("enabled")]
        return JSONResponse(rows)

    @router.post("/api/admin/monitoring", response_model=None)
    @router.post("/api/monitoring", response_model=None)
    async def api_create_monitoring(body: dict[str, Any]) -> JSONResponse:
        payload, error = _validated_monitor_payload(body, partial=False)
        if error is not None:
            return error
        try:
            row = monitoring.create_monitor(payload or {})
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(row, status_code=201)

    @router.get("/api/admin/monitoring/{monitor_id}", response_model=None)
    @router.get("/api/monitoring/{monitor_id}", response_model=None)
    async def api_get_monitoring(monitor_id: int) -> JSONResponse:
        row = monitoring.get_monitor(monitor_id)
        if row is None:
            return JSONResponse({"error": "monitor not found"}, status_code=404)
        return JSONResponse(row)

    @router.put("/api/admin/monitoring/{monitor_id}", response_model=None)
    @router.patch("/api/admin/monitoring/{monitor_id}", response_model=None)
    @router.put("/api/monitoring/{monitor_id}", response_model=None)
    @router.patch("/api/monitoring/{monitor_id}", response_model=None)
    async def api_update_monitoring(
        monitor_id: int,
        body: dict[str, Any],
    ) -> JSONResponse:
        payload, error = _validated_monitor_payload(body, partial=True)
        if error is not None:
            return error
        try:
            row = monitoring.update_monitor(monitor_id, payload or {})
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        if row is None:
            return JSONResponse({"error": "monitor not found"}, status_code=404)
        return JSONResponse(row)

    @router.delete("/api/admin/monitoring/{monitor_id}", response_model=None)
    @router.delete("/api/monitoring/{monitor_id}", response_model=None)
    async def api_delete_monitoring(monitor_id: int) -> JSONResponse:
        if not monitoring.delete_monitor(monitor_id):
            return JSONResponse({"error": "monitor not found"}, status_code=404)
        return JSONResponse({"ok": True})

    @router.post(
        "/api/admin/monitoring/{monitor_id}/check",
        response_model=None,
    )
    @router.post("/api/monitoring/{monitor_id}/check", response_model=None)
    async def api_check_monitoring(monitor_id: int) -> JSONResponse:
        try:
            payload = await run_in_threadpool(monitoring.check_now, monitor_id)
        except KeyError:
            return JSONResponse({"error": "monitor not found"}, status_code=404)
        status_code = 502 if payload.get("error") else 200
        return JSONResponse(payload, status_code=status_code)

    @router.get(
        "/api/admin/monitoring/{monitor_id}/results",
        response_model=None,
    )
    @router.get("/api/monitoring/{monitor_id}/results", response_model=None)
    async def api_monitoring_results(
        monitor_id: int,
        page: int = Query(1, ge=1),
        limit: int = Query(50, ge=1, le=MAX_MONITOR_ITEMS),
        state: str | None = Query(None),
    ) -> JSONResponse:
        if state is not None and state not in {"new", "seen", "dismissed"}:
            return JSONResponse({"error": "invalid result state"}, status_code=422)
        try:
            payload = monitoring.list_results(
                monitor_id,
                page=page,
                limit=limit,
                state=state,
            )
        except KeyError:
            return JSONResponse({"error": "monitor not found"}, status_code=404)
        return JSONResponse(payload)

    async def _set_monitor_result_state(
        monitor_id: int,
        result_id: int,
        state: str,
    ) -> JSONResponse:
        try:
            row = monitoring.set_result_state(monitor_id, result_id, state)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        if row is None:
            return JSONResponse({"error": "result not found"}, status_code=404)
        return JSONResponse(row)

    @router.post(
        "/api/admin/monitoring/{monitor_id}/results/{result_id}/seen",
        response_model=None,
    )
    @router.post(
        "/api/monitoring/{monitor_id}/results/{result_id}/seen",
        response_model=None,
    )
    async def api_mark_monitor_result_seen(
        monitor_id: int,
        result_id: int,
    ) -> JSONResponse:
        return await _set_monitor_result_state(monitor_id, result_id, "seen")

    @router.post(
        "/api/admin/monitoring/{monitor_id}/results/{result_id}/dismiss",
        response_model=None,
    )
    @router.post(
        "/api/monitoring/{monitor_id}/results/{result_id}/dismiss",
        response_model=None,
    )
    async def api_dismiss_monitor_result(
        monitor_id: int,
        result_id: int,
    ) -> JSONResponse:
        return await _set_monitor_result_state(monitor_id, result_id, "dismissed")

    @router.patch(
        "/api/admin/monitoring/{monitor_id}/results/{result_id}",
        response_model=None,
    )
    @router.patch(
        "/api/monitoring/{monitor_id}/results/{result_id}",
        response_model=None,
    )
    async def api_update_monitor_result(
        monitor_id: int,
        result_id: int,
        body: dict[str, Any],
    ) -> JSONResponse:
        state = str(body.get("state") or "").strip().lower()
        return await _set_monitor_result_state(monitor_id, result_id, state)

    @router.get("/api/admin/candidates", response_model=None)
    @router.get("/api/candidates", response_model=None)
    async def api_candidates(
        digest_id: int | None = Query(None, ge=1),
        page: int = Query(1, ge=1),
        limit: int = Query(50, ge=1, le=200),
        before_id: int | None = Query(None, ge=1),
        before_rank: int | None = Query(None, ge=1),
    ) -> JSONResponse:
        """Return sanitized ranked candidates from a selected digest.

        Candidates are metadata/snippet rows already persisted by the ranking
        pipeline. This endpoint never fetches unpublished article content.
        """
        if digest_id is None:
            digest = store.latest_digest()
        else:
            rows = list(
                store.db.query("SELECT * FROM digests WHERE id = ?", [digest_id])
            )
            digest = dict(rows[0]) if rows else None
        if not digest:
            return JSONResponse(
                {
                    "digest_id": digest_id,
                    "candidates": [],
                    "items": [],
                    "page": page,
                    "limit": limit,
                    "total": 0,
                    "has_more": False,
                    "next_page": None,
                    "before_id": before_id,
                    "next_before_id": None,
                }
            )
        try:
            stats = json.loads(str(digest.get("stats_json") or "{}"))
        except (TypeError, json.JSONDecodeError):
            stats = {}
        raw_candidates = stats.get("candidate_items")
        if not isinstance(raw_candidates, list):
            raw_candidates = stats.get("candidates")
        if not isinstance(raw_candidates, list):
            raw_candidates = []
        candidates: list[dict[str, Any]] = []
        for index, raw in enumerate(raw_candidates, start=1):
            candidate = _sanitize_candidate(raw, index)
            if candidate is not None:
                candidates.append(candidate)
        candidates.sort(key=lambda item: (int(item.get("rank", 0)), item["url"]))

        cursor = before_rank if before_rank is not None else before_id
        if cursor is not None:
            candidates = [
                candidate
                for candidate in candidates
                if int(candidate.get("rank", 0)) > int(cursor)
            ]
            page_number = 1
            page_items = candidates[:limit]
        else:
            page_number = page
            offset = (page - 1) * limit
            page_items = candidates[offset : offset + limit]

        has_more = (
            len(candidates) > len(page_items)
            if cursor is not None
            else page * limit < len(candidates)
        )
        next_cursor = int(page_items[-1]["rank"]) if has_more else None
        return JSONResponse(
            {
                "digest_id": int(digest.get("id") or digest_id or 0),
                "candidates": page_items,
                "items": page_items,
                "page": page_number,
                "limit": limit,
                "before_id": cursor,
                "next_before_id": next_cursor,
                "has_more": has_more,
                "next_page": page_number + 1 if has_more else None,
                "total": len(candidates),
            }
        )

    return router
