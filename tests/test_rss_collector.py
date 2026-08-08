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
    monkeypatch.setattr(
        "condenseit.services.source_discovery._host_resolves_publicly",
        lambda *_args: True,
    )
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



def test_collect_feed_deduplicates_canonical_links_before_limit(
    monkeypatch,
) -> None:
    entries = [
        {
            "link": "https://example.com/article",
            "title": "First",
            "summary": "Summary first",
        },
        {
            "link": "https://example.com/article#duplicate",
            "title": "Duplicate",
            "summary": "Summary duplicate",
        },
        {
            "link": "https://example.com/second/",
            "title": "Second",
            "summary": "Summary second",
        },
    ]
    parsed = SimpleNamespace(feed={"title": "Synthetic"}, entries=entries)
    monkeypatch.setattr(
        "condenseit.collectors.rss.feedparser.parse",
        lambda _text: parsed,
    )
    collector = RSSCollector(
        [FeedConfig(url="https://example.com/feed", max_items=2)]
    )
    monkeypatch.setattr(collector, "_fetch_feed_text", lambda _url: "<rss />")
    monkeypatch.setattr(
        collector,
        "_extract_content",
        lambda _url, entry: (entry["summary"], None),
    )

    articles = collector.collect_all()

    assert [article.url for article in articles] == [
        "https://example.com/article",
        "https://example.com/second",
    ]


def test_rss_article_fetch_rejects_unsafe_links_and_redirects(monkeypatch) -> None:
    monkeypatch.setattr(
        "condenseit.services.source_discovery._host_resolves_publicly",
        lambda *_args: True,
    )
    class FakeResponse:
        status_code = 302
        url = "https://example.com/article"
        text = ""
        headers = {"location": "http://127.0.0.1/private"}

        def raise_for_status(self) -> None:
            return None

    class RecordingClient:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def get(self, url: str, **_kwargs: object) -> FakeResponse:
            self.calls.append(url)
            return FakeResponse()

    collector = RSSCollector([])
    client = RecordingClient()
    collector.client = client
    entry = {"summary": "Safe fallback"}

    content, _image = collector._extract_content(
        "http://10.0.0.1/private",
        entry,
    )
    assert content == "Safe fallback"
    assert client.calls == []

    content, _image = collector._extract_content(
        "https://example.com/article",
        entry,
    )
    assert content == "Safe fallback"
    assert client.calls == ["https://example.com/article"]


def test_rss_feed_body_is_bounded(monkeypatch) -> None:
    monkeypatch.setattr(
        "condenseit.services.source_discovery._host_resolves_publicly",
        lambda *_args: True,
    )
    class FakeResponse:
        status_code = 200
        url = "https://example.com/feed"
        text = "x" * 600_000

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def get(self, _url: str, **_kwargs: object) -> FakeResponse:
            return FakeResponse()

    collector = RSSCollector([])
    collector.client = FakeClient()

    body = collector._fetch_feed_text("https://example.com/feed")

    assert len(body) == 512_000
