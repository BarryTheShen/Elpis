"""Stable third-party API base URLs used by collectors and providers."""

import os
from urllib.parse import urlsplit

OPENROUTER_API_BASE = os.environ.get(
    "OPENROUTER_API_BASE",
    "https://openrouter.ai/api/v1",
)
OPENROUTER_KEY_URL = f"{OPENROUTER_API_BASE}/key"
OPENROUTER_EMBEDDINGS_URL = f"{OPENROUTER_API_BASE}/embeddings"
OPENROUTER_TRANSCRIPTIONS_URL = f"{OPENROUTER_API_BASE}/audio/transcriptions"
OPENROUTER_MODELS_URL = f"{OPENROUTER_API_BASE}/models"

REDDIT_WEB_BASE = os.environ.get("REDDIT_WEB_BASE", "https://www.reddit.com")
YOUTUBE_BASE = os.environ.get("YOUTUBE_BASE", "https://www.youtube.com")
YOUTUBE_THUMBNAIL_BASE = os.environ.get(
    "YOUTUBE_THUMBNAIL_BASE",
    "https://img.youtube.com/vi",
)


def youtube_watch_url(video_id: str) -> str:
    return f"{YOUTUBE_BASE}/watch?v={video_id}"


def youtube_channel_feed_url(channel_id: str) -> str:
    return f"{YOUTUBE_BASE}/feeds/videos.xml?channel_id={channel_id}"


def youtube_handle_page_url(handle: str) -> str:
    raw = handle.strip()
    if raw.startswith("@"):
        return f"{YOUTUBE_BASE}/{raw}"
    return f"{YOUTUBE_BASE}/@{raw}"

def is_youtube_url(value: str) -> bool:
    """Return whether a supplied resolver URL stays on YouTube hosts."""
    if not isinstance(value, str) or not value or any(ord(ch) < 0x20 for ch in value):
        return False
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    host = (parsed.hostname or "").rstrip(".").lower()
    allowed = {"youtube.com", "www.youtube.com", "m.youtube.com"}
    base_host = (urlsplit(YOUTUBE_BASE).hostname or "").rstrip(".").lower()
    if base_host:
        allowed.add(base_host)
    return (
        parsed.scheme.lower() in {"http", "https"}
        and parsed.username is None
        and parsed.password is None
        and port is None
        and (host in allowed or host.endswith(".youtube.com"))
    )


def youtube_thumbnail_url(video_id: str) -> str:
    return f"{YOUTUBE_THUMBNAIL_BASE}/{video_id}/hqdefault.jpg"
