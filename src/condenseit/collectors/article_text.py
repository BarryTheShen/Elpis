"""Shared article body extraction for collectors."""

import logging
from urllib.parse import urljoin

import httpx
import trafilatura

from condenseit.network import load_network_proxy, safe_network_error
from condenseit.services.source_discovery import canonical_url, validate_public_url

logger = logging.getLogger(__name__)
_MAX_REDIRECTS = 3
_MAX_ARTICLE_BODY_CHARS = 512_000


def _call_get(client: httpx.Client, url: str) -> object:
    get = getattr(client, "get", None)
    if not callable(get):
        raise TypeError("http client must expose get()")
    try:
        return get(url, follow_redirects=False)
    except TypeError as first:
        try:
            return get(url)
        except TypeError:
            raise first


def _safe_get(client: httpx.Client, url: str) -> object:
    current = validate_public_url(url)
    if current is None:
        raise ValueError("unsafe URL")
    for _ in range(_MAX_REDIRECTS + 1):
        page = _call_get(client, current)
        final_url = getattr(page, "url", None)
        if final_url and validate_public_url(str(final_url)) is None:
            raise ValueError("unsafe response URL")
        status = getattr(page, "status_code", None)
        if not isinstance(status, int) or not 300 <= status < 400:
            return page
        headers = getattr(page, "headers", {}) or {}
        location = str(headers.get("location", ""))
        redirected = validate_public_url(urljoin(current, location))
        if redirected is None:
            raise ValueError("unsafe redirect URL")
        if redirected == current:
            return page
        current = redirected
    raise ValueError("too many redirects")


def fetch_article_text(client: httpx.Client, url: str) -> str | None:
    """Return extracted article text, or None when fetch/extraction fails."""
    try:
        page = _safe_get(client, url)
        page.raise_for_status()
        body = getattr(page, "text", "")
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="replace")
        extracted = trafilatura.extract(
            str(body or "")[:_MAX_ARTICLE_BODY_CHARS],
            include_comments=False,
        )
        if extracted:
            return extracted
    except Exception as exc:
        logger.debug(
            "Article fetch failed for %s",
            canonical_url(url) or "<unsafe-url>",
            extra={"error": safe_network_error(exc, load_network_proxy())},
        )
    return None
