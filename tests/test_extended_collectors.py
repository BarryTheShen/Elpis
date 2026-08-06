"""Tests for RSS-like source candidate limits."""

from __future__ import annotations

from types import SimpleNamespace

from condenseit.collectors.github_releases import GitHubReleasesCollector
from condenseit.collectors.google_news import GoogleNewsCollector
from condenseit.collectors.podcast import PodcastCollector
from condenseit.config import (
    GitHubReleasesConfig,
    GoogleNewsSearchConfig,
    PodcastConfig,
)


class _FakeResponse:
    text = "<feed />"

    def raise_for_status(self) -> None:
        return None


class _FakeClient:
    def get(self, _url: str) -> _FakeResponse:
        return _FakeResponse()


def test_rss_like_collectors_honor_configured_limits(monkeypatch) -> None:
    entries = [
        {
            "link": f"https://example.com/episode-{index}",
            "title": f"Episode {index}",
            "summary": f"Summary {index}",
        }
        for index in range(30)
    ]
    parsed = SimpleNamespace(feed={"title": "Synthetic"}, entries=entries)
    monkeypatch.setattr(
        "condenseit.collectors.google_news.feedparser.parse",
        lambda _text: parsed,
    )
    monkeypatch.setattr(
        "condenseit.collectors.github_releases.feedparser.parse",
        lambda _text: parsed,
    )
    monkeypatch.setattr(
        "condenseit.collectors.podcast.feedparser.parse",
        lambda _text: parsed,
    )
    monkeypatch.setattr(
        "condenseit.collectors.google_news.fetch_article_text",
        lambda *_args: "Article content",
    )

    google = GoogleNewsCollector(
        [GoogleNewsSearchConfig(query="synthetic", max_items=21)]
    )
    google._client = _FakeClient()
    github = GitHubReleasesCollector(
        [GitHubReleasesConfig(repo="owner/repo", max_items=22)]
    )
    github._client = _FakeClient()
    podcast = PodcastCollector(
        [
            PodcastConfig(
                feed_url="https://example.com/podcast.xml",
                max_items=23,
            )
        ]
    )
    podcast._client = _FakeClient()

    google_items, _ = google.collect_all_with_health()
    github_items, _ = github.collect_all_with_health()
    podcast_items, _ = podcast.collect_all_with_health()

    assert len(google_items) == 21
    assert len(github_items) == 22
    assert len(podcast_items) == 23
