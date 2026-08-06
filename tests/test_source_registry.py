"""Tests for source-registry candidate limits."""

from __future__ import annotations

import json

from condenseit.config import AppConfig, FeedConfig
from condenseit.store.database import ContentStore
from condenseit.store.sources import SourceRegistry


def test_source_registry_round_trips_rss_max_items(tmp_path) -> None:
    store = ContentStore(tmp_path / "condenseit.db")
    try:
        registry = SourceRegistry(store)
        registry.seed_from_config(
            AppConfig(
                feeds=[
                    FeedConfig(
                        url="https://example.com/feed.xml",
                        max_items=123,
                    )
                ]
            )
        )

        row = registry.list_enabled()[0]
        assert json.loads(row["extra_json"])["max_items"] == 123
        assert registry.feeds_for_config()[0].max_items == 123
    finally:
        store.close()


def test_source_registry_uses_defaults_for_legacy_and_db_source_rows(tmp_path) -> None:
    store = ContentStore(tmp_path / "condenseit.db")
    try:
        registry = SourceRegistry(store)
        registry.add(
            "rss",
            "Legacy RSS",
            "General",
            2,
            "https://example.com/legacy.xml",
        )
        registry.add(
            "google_news",
            "Google",
            "General",
            2,
            "https://news.google.com/rss/search?q=test",
            extra={"query": "test", "max_items": 77},
        )
        registry.add(
            "github_releases",
            "GitHub",
            "General",
            2,
            "https://github.com/owner/repo/releases.atom",
            extra={"repo": "owner/repo", "max_items": 88},
        )
        registry.add(
            "podcast",
            "Podcast",
            "General",
            2,
            "https://example.com/podcast.xml",
            extra={
                "feed_url": "https://example.com/podcast.xml",
                "max_items": 99,
            },
        )

        assert registry.feeds_for_config()[0].max_items == 50
        assert registry.google_news_for_config()[0].max_items == 77
        assert registry.github_releases_for_config()[0].max_items == 88
        assert registry.podcast_sources_for_config()[0].max_items == 99
    finally:
        store.close()
