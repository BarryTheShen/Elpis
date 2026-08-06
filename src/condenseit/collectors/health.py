"""Helpers for per-source collector health reporting."""

import logging
from collections.abc import Callable
from typing import TypeVar

from condenseit.network import load_network_proxy, sanitize_network_text

logger = logging.getLogger(__name__)

T = TypeVar("T")
HealthEntry = tuple[str, str | None, int]


def collect_with_health(
    url: str,
    collect_fn: Callable[[], list[T]],
    *,
    log_label: str,
) -> tuple[list[T], HealthEntry]:
    """Run a collector callback and return items plus a health entry."""
    try:
        items = collect_fn()
    except Exception as exc:
        error = sanitize_network_text(str(exc), load_network_proxy())
        logger.error("%s: %s", log_label, error)
        return [], (url, error, 0)
    return items, (url, None, len(items))
