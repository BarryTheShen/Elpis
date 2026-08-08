"""Website change detection."""

import logging
from difflib import unified_diff
from urllib.parse import urljoin

import trafilatura

from condenseit.config import WatchUrlConfig
from condenseit.fetch_headers import digest_fetch_headers
from condenseit.network import httpx_client, load_network_proxy, sanitize_network_text
from condenseit.services.source_discovery import validate_public_url
from condenseit.store.database import ContentStore

logger = logging.getLogger(__name__)
_MAX_REDIRECTS = 3
_MAX_PAGE_BODY_CHARS = 512_000


def _fetch_text(url: str) -> str:
    current = validate_public_url(url)
    if current is None:
        raise ValueError("unsafe URL")
    with httpx_client(
        follow_redirects=False,
        headers=digest_fetch_headers(),
    ) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            response = client.get(
                current,
                timeout=30.0,
                follow_redirects=False,
                headers=digest_fetch_headers(),
            )
            final_url = getattr(response, "url", None)
            if final_url and validate_public_url(str(final_url)) is None:
                raise ValueError("unsafe response URL")
            status = getattr(response, "status_code", None)
            if not isinstance(status, int) or not 300 <= status < 400:
                break
            headers = getattr(response, "headers", {}) or {}
            location = str(headers.get("location", ""))
            redirected = validate_public_url(urljoin(current, location))
            if redirected is None:
                raise ValueError("unsafe redirect URL")
            if redirected == current:
                break
            current = redirected
        else:
            raise ValueError("too many redirects")
    response.raise_for_status()
    downloaded = str(response.text or "")[:_MAX_PAGE_BODY_CHARS]
    text = trafilatura.extract(downloaded, include_comments=False)
    return text or downloaded[:8000]


def _meaningful_change(
    old: str,
    new: str,
    threshold: float,
) -> bool:
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    diff = list(unified_diff(old_lines, new_lines))
    if not old_lines:
        return bool(new_lines)
    change_ratio = len(diff) / max(len(old_lines), 1)
    return change_ratio > threshold


def check_website_changes(
    watch_urls: list[WatchUrlConfig],
    store: ContentStore,
) -> list[dict[str, str]]:
    changes, _health = check_website_changes_with_health(watch_urls, store)
    return changes


def check_website_changes_with_health(
    watch_urls: list[WatchUrlConfig],
    store: ContentStore,
) -> tuple[list[dict[str, str]], list[tuple[str, str | None, int]]]:
    """Return ``(change_events, [(url, error_or_none, snapshot_bytes), ...])``."""
    changes: list[dict[str, str]] = []
    health: list[tuple[str, str | None, int]] = []
    for item in watch_urls:
        try:
            current = _fetch_text(item.url)
            previous = store.get_snapshot(item.url)
            if previous is None:
                store.save_snapshot(item.url, current)
                changes.append(
                    {
                        "url": item.url,
                        "category": item.category,
                        "status": "new",
                        "snippet": current[:500],
                    },
                )
                health.append((item.url, None, len(current)))
                continue
            if _meaningful_change(
                previous["content"],
                current,
                item.change_threshold,
            ):
                store.save_snapshot(item.url, current)
                changes.append(
                    {
                        "url": item.url,
                        "category": item.category,
                        "status": "changed",
                        "snippet": current[:500],
                    },
                )
            health.append((item.url, None, len(current)))
        except Exception as exc:
            error = sanitize_network_text(str(exc), load_network_proxy())
            logger.error("Change check failed for %s: %s", item.url, error)
            health.append((item.url, error, 0))
    return changes, health
