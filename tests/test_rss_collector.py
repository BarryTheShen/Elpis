"""Tests for RSS collection fallbacks and candidate limits."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import httpx

from condenseit.collectors.rss import RSSCollector
from condenseit.config import FeedConfig


def test_collect_feed_falls_back_to_urllib_on_403(
    monkeypatch,
) -> None:
    feed_url = "https://blocked.example/feed"
    article_url = "https://blocked.example/post"

    class FakeClient:
        def get(self, url: str) -> httpx.Response:
            request = httpx.Request("GET", url)
            return httpx.Response(403, request=request, text="challenge")

    class FakeHeaders:
        def get_content_charset(self) -> str:
            return "utf-8"

    class FakeUrlopenResponse:
        headers = FakeHeaders()

        def __enter__(self) -> FakeUrlopenResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return f"""
                <?xml version="1.0" encoding="UTF-8"?>
                <rss version="2.0">
                  <channel>
                    <title>Blocked Feed</title>
                    <item>
                      <title>Recovered article</title>
                      <link>{article_url}</link>
                      <description>Recovered summary</description>
                      <pubDate>Sat, 16 May 2026 12:00:00 GMT</pubDate>
                    </item>
                  </channel>
                </rss>
            """.encode()

    def fake_urlopen(request: object, timeout: float) -> FakeUrlopenResponse:
        assert timeout == 30.0
        assert getattr(request, "full_url") == feed_url
        return FakeUrlopenResponse()

    def fake_extract_content(
        self: RSSCollector,
        url: str,
        entry: object,
    ) -> tuple[str, str | None]:
        assert url == article_url
        return "Recovered summary", None

    collector = RSSCollector([FeedConfig(url=feed_url, category="Test")])
    collector.client = FakeClient()

    monkeypatch.setattr("condenseit.collectors.rss.urlopen", fake_urlopen)
    monkeypatch.setattr(RSSCollector, "_extract_content", fake_extract_content)

    articles = collector._collect_feed(FeedConfig(url=feed_url, category="Test"))

    assert len(articles) == 1
    assert articles[0].title == "Recovered article"
    assert articles[0].url == article_url
    assert articles[0].category == "Test"


def test_collect_feed_honors_configured_max_items(
    monkeypatch,
) -> None:
    entries = [
        {
            "link": f"https://example.com/article-{index}",
            "title": f"Article {index}",
            "summary": f"Summary {index}",
        }
        for index in range(30)
    ]
    parsed = SimpleNamespace(feed={"title": "Synthetic"}, entries=entries)
    monkeypatch.setattr(
        "condenseit.collectors.rss.feedparser.parse",
        lambda _text: parsed,
    )

    collector = RSSCollector(
        [
            FeedConfig(
                url="https://example.com/feed",
                max_items=24,
            )
        ]
    )
    monkeypatch.setattr(collector, "_fetch_feed_text", lambda _url: "<rss />")
    monkeypatch.setattr(
        collector,
        "_extract_content",
        lambda _url, entry: (entry["summary"], None),
    )

    articles = collector.collect_all()

    assert len(articles) == 24
    assert [article.title for article in articles] == [
        f"Article {index}" for index in range(24)
    ]


def test_collect_feed_extracts_pages_concurrently_in_feed_order(
    monkeypatch,
) -> None:
    entries = [
        {
            "link": f"https://example.com/article-{index}",
            "title": f"Article {index}",
            "summary": f"Summary {index}",
        }
        for index in range(20)
    ]
    parsed = SimpleNamespace(feed={"title": "Synthetic"}, entries=entries)
    monkeypatch.setattr(
        "condenseit.collectors.rss.feedparser.parse",
        lambda _text: parsed,
    )

    active = 0
    max_active = 0
    lock = threading.Lock()

    def fake_extract(_url: str, entry: dict[str, str]) -> tuple[str, None]:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.01)
        with lock:
            active -= 1
        return entry["summary"], None

    collector = RSSCollector(
        [FeedConfig(url="https://example.com/feed", max_items=len(entries))]
    )
    monkeypatch.setattr(collector, "_fetch_feed_text", lambda _url: "<rss />")
    monkeypatch.setattr(collector, "_extract_content", fake_extract)

    articles = collector.collect_all()

    assert max_active > 1
    assert [article.url for article in articles] == [
        entry["link"] for entry in entries
    ]
