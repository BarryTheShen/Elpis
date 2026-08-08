from __future__ import annotations

import socket

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import condenseit.services.source_discovery as source_discovery_module
from condenseit.services.source_discovery import (
    SourceDiscoveryService,
    canonical_url,
    is_safe_url,
)
from condenseit.store.database import ContentStore
from condenseit.store.sources import SourceRegistry


class FakeResponse:
    def __init__(self, text: str, url: str, status_code: int = 200) -> None:
        self.text = text
        self.url = url
        self.status_code = status_code
        self.headers: dict[str, str] = {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("upstream failure")


class FakeClient:
    def __init__(self, responses: dict[str, FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def get(self, url: str, **_kwargs):
        self.calls.append(url)
        return self.responses.get(url, FakeResponse("", url, 404))


RSS = """<?xml version='1.0'?><rss version='2.0'><channel>
<title>Example</title><item><title>One</title></item>
<item><title>Two</title></item></channel></rss>"""

@pytest.fixture(autouse=True)
def _resolve_fixture_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    real_getaddrinfo = socket.getaddrinfo

    def resolve(host: str, port: object, *args: object, **kwargs: object):
        if host.endswith(".example"):
            return [
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    6,
                    "",
                    ("8.8.8.8", int(port) if isinstance(port, int) else 443),
                )
            ]
        return real_getaddrinfo(host, port, *args, **kwargs)

    monkeypatch.setattr(source_discovery_module.socket, "getaddrinfo", resolve)


def _service(
    page: str,
    rows: list[dict[str, object]],
    *,
    with_feed: bool = True,
) -> SourceDiscoveryService:
    responses = {
        "https://publisher.example/": FakeResponse(
            page, "https://publisher.example/"
        ),
    }
    if with_feed:
        responses["https://publisher.example/feed.xml"] = FakeResponse(
            RSS, "https://publisher.example/feed.xml"
        )
    client = FakeClient(responses)
    return SourceDiscoveryService(
        http_client=client,
        searcher=lambda _query, **_kwargs: rows,
    )


def test_discovery_parses_html_alternate_feed() -> None:
    service = _service(
        "<link rel='alternate' type='application/rss+xml' href='/feed.xml'>",
        [
            {
                "url": "https://publisher.example/article",
                "source": {
                    "title": "Publisher",
                    "href": "https://publisher.example/",
                },
                "title": "AI update",
                "summary": "A useful AI story",
            }
        ],
    )

    candidate = service.search("AI")["candidates"][0]

    assert candidate["source_type"] == "rss"
    assert candidate["feed_url"] == "https://publisher.example/feed.xml"
    assert candidate["health"] == {"status": "verified", "entry_count": 2}
    assert candidate["evidence"]["verification"] == "alternate"


def test_discovery_rejects_unsafe_and_unverified_urls() -> None:
    assert canonical_url("file:///etc/passwd") is None
    assert canonical_url("http://127.0.0.1/feed") is None
    assert canonical_url("https://user:secret@example.com/feed") is None

    service = _service(
        "<html><body>No feed here</body></html>",
        [
            {
                "url": "https://publisher.example/article",
                "source_url": "https://publisher.example/",
                "source": "Publisher",
                "title": "AI update",
            },
            {
                "url": "http://127.0.0.1/private",
                "source": "Private",
                "title": "Should be dropped",
            },
        ],
        with_feed=False,
    )


    candidate = service.search("AI")["candidates"][0]

    assert candidate["source_type"] == "google_news"
    assert candidate["query"] == "AI"
    assert candidate["evidence"]["feed_verified"] is False
    assert candidate["health"]["status"] in {"unverified", "error"}


def test_route_marks_existing_without_writing_preview_rows(
    tmp_path, monkeypatch
) -> None:
    from condenseit.web.admin.routes import create_admin_router
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(tmp_path / "data"))
    store = ContentStore()
    registry = SourceRegistry(store)
    registry.add("rss", "Publisher", "General", 2, "https://publisher.example/feed.xml")
    service = _service(
        "<link rel='alternate' type='application/rss+xml' href='/feed.xml'>",
        [
            {
                "url": "https://publisher.example/article",
                "source_url": "https://publisher.example/",
                "source": "Publisher",
                "title": "AI update",
            }
        ],
    )
    app = FastAPI()
    app.include_router(create_admin_router(None, store, source_discovery=service))
    before_sources = store.db.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    before_digests = store.db.execute("SELECT COUNT(*) FROM digests").fetchone()[0]

    response = TestClient(app).get("/api/sources/discover?q=AI")

    assert response.status_code == 200
    assert response.json()["candidates"][0]["existing"] is True
    assert (
        store.db.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        == before_sources
    )
    assert (
        store.db.execute("SELECT COUNT(*) FROM digests").fetchone()[0]
        == before_digests
    )
    store.close()


def test_canonical_url_preserves_public_ipv6_brackets() -> None:
    raw = "https://[2001:4860:4860::8888]/feed/"

    assert is_safe_url(raw) is True
    assert canonical_url(raw) == "https://[2001:4860:4860::8888]/feed"

def test_unresolved_public_host_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_lookup(*_args: object, **_kwargs: object):
        raise socket.gaierror("temporary failure")

    monkeypatch.setattr(source_discovery_module.socket, "getaddrinfo", fail_lookup)

    assert is_safe_url("https://unresolvable.example/feed") is False


def test_discovery_paginates_distinct_publishers_without_section_duplicates() -> None:
    section_rows = [
        {
            "url": f"https://publisher.example/article-{index}",
            "source": {
                "title": "Publisher",
                "href": f"https://publisher.example/section-{index}",
            },
            "title": f"AI update {index}",
        }
        for index in range(12)
    ]
    service = _service("<html><body>No feed here</body></html>", section_rows)

    first = service.search("AI")
    assert len(first["candidates"]) == 1
    assert first["has_more"] is False

    distinct_rows = [
        {
            "url": f"https://publisher-{index}.example/article",
            "source": {
                "title": f"Publisher {index}",
                "href": f"https://publisher-{index}.example/",
            },
            "title": "AI update",
        }
        for index in range(12)
    ]
    distinct = SourceDiscoveryService(
        http_client=FakeClient({}),
        searcher=lambda _query, **_kwargs: distinct_rows,
    )

    page_one = distinct.search("AI")
    page_two = distinct.search("AI", page=2)
    assert len(page_one["candidates"]) == 8
    assert page_one["has_more"] is True
    assert len(page_two["candidates"]) == 4
    assert page_two["has_more"] is False



def test_discovery_small_limit_pages_keep_unique_candidates() -> None:
    rows = [
        {
            "url": f"https://publisher-{index}.example/article",
            "source": {
                "title": f"Publisher {index}",
                "href": f"https://publisher-{index}.example/",
            },
            "title": "AI update",
        }
        for index in range(5)
    ]
    service = SourceDiscoveryService(
        http_client=FakeClient({}),
        searcher=lambda _query, **_kwargs: rows,
    )

    first = service.search("AI", limit=2)
    second = service.search("AI", page=2, limit=2)
    third = service.search("AI", page=3, limit=2)

    assert [row["url"] for row in first["candidates"]]
    assert len(first["candidates"]) == 2
    assert len(second["candidates"]) == 2
    assert len(third["candidates"]) == 1
    assert first["has_more"] is True
    assert second["has_more"] is True
    assert third["has_more"] is False
    assert {
        row["url"]
        for result in (first, second, third)
        for row in result["candidates"]
    } == {f"https://publisher-{index}.example/" for index in range(5)}


def test_discovery_bounds_generic_searcher_iterables() -> None:
    consumed: list[int] = []

    def rows():
        for index in range(100_000):
            consumed.append(index)
            yield index

    service = SourceDiscoveryService(
        searcher=lambda _query, **_kwargs: rows(),
    )

    result = service._search_rows(
        "AI",
        language="en",
        country="US",
        max_items=3,
    )

    assert result == [0, 1, 2]
    assert consumed == [0, 1, 2]
