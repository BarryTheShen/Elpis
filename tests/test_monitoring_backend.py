from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from condenseit.services.monitoring import GoogleNewsDiscovery, MonitoringService
from condenseit.store.database import ContentStore
from condenseit.web.app import create_app

_AUTH = {"Authorization": "Bearer elpis"}


def test_monitor_schema_crud_and_result_state(tmp_path: Path) -> None:
    store = ContentStore(tmp_path / "monitor.db")
    monitor_id = store.create_monitor_query(
        {
            "question": "  Qwen3.8 release?  ",
            "scope": "general_discovery",
            "include_keywords": ["Qwen"],
        }
    )
    monitor = store.get_monitor_query(monitor_id)
    assert monitor is not None
    assert monitor["question"] == "  Qwen3.8 release?  "
    assert monitor["include_keywords"] == ["Qwen"]
    assert monitor["status"] == "idle"

    result_id = store.upsert_monitor_result(
        monitor_id,
        {
            "url": "https://example.com/release",
            "title": "Qwen release",
            "evidence": {"matched_terms": ["Qwen"], "provider": "fake"},
        },
    )
    store.upsert_monitor_result(
        monitor_id,
        {
            "url": "https://example.com/release",
            "title": "Updated title",
        },
    )
    assert len(store.list_monitor_results(monitor_id)) == 1
    assert store.get_monitor_result(result_id)["title"] == "Updated title"
    assert store.monitor_new_count(monitor_id) == 1
    store.mark_monitor_result_seen(result_id, monitor_id=monitor_id)
    assert store.monitor_new_count(monitor_id) == 0
    store.dismiss_monitor_result(result_id, monitor_id=monitor_id)
    assert store.get_monitor_result(result_id)["state"] == "dismissed"
    store.close()


def test_monitor_check_deduplicates_and_preserves_evidence_on_error(
    tmp_path: Path,
) -> None:
    class FakeDiscovery:
        fail = False

        def search(self, *_args, **_kwargs):
            if self.fail:
                raise RuntimeError("upstream unavailable")
            return [
                {
                    "url": "https://example.com/a",
                    "title": "A",
                    "snippet": "Snippet",
                    "evidence": {
                        "matched_terms": ["Qwen"],
                        "provider": "fake",
                        "freshness": 1,
                        "reasoning": "must not persist",
                    },
                },
                {
                    "url": "https://example.com/a",
                    "title": "Duplicate",
                    "evidence": {"provider": "fake"},
                },
            ]

    store = ContentStore(tmp_path / "check.db")
    fake = FakeDiscovery()
    service = MonitoringService(
        store,
        discovery=fake,
        clock=lambda: datetime(2026, 8, 8, tzinfo=UTC),
    )
    monitor = service.create_monitor({"question": "Qwen release?"})
    first = service.check_now(monitor["id"])
    assert first["error"] is None
    assert first["monitor"]["status"] == "ok"
    assert len(store.list_monitor_results(monitor["id"])) == 1
    assert "reasoning" not in store.list_monitor_results(monitor["id"])[0]["evidence"]

    fake.fail = True
    failed = service.check_now(monitor["id"])
    assert failed["monitor"]["status"] == "error"
    assert failed["monitor"]["last_error"]
    assert len(store.list_monitor_results(monitor["id"])) == 1
    store.close()


def test_discovery_normalizes_fake_feed_without_digest_mutation(monkeypatch, tmp_path: Path) -> None:
    entries = [
        {
            "link": "https://example.com/story#tracking",
            "title": "A result",
            "summary": "<b>Snippet</b>",
            "published": "Sat, 08 Aug 2026 00:00:00 GMT",
        },
        {"link": "https://example.com/story", "title": "Duplicate"},
    ]
    monkeypatch.setattr(
        "condenseit.services.monitoring.feedparser.parse",
        lambda _text: SimpleNamespace(entries=entries),
    )

    class FakeResponse:
        text = "<rss />"

        def raise_for_status(self):
            return None

    class FakeClient:
        def get(self, _url):
            return FakeResponse()

    store = ContentStore(tmp_path / "discovery.db")
    before = store.db["digests"].count
    results = GoogleNewsDiscovery(client=FakeClient()).search("Qwen")
    assert len(results) == 1
    assert results[0]["url"] == "https://example.com/story"
    assert results[0]["snippet"] == "Snippet"
    assert store.db["digests"].count == before
    store.close()


def test_monitoring_api_requires_auth_and_validates_payload(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(tmp_path / "api-data"))
    client = TestClient(create_app())
    assert client.get("/api/monitoring").status_code == 401
    invalid = client.post(
        "/api/monitoring",
        headers=_AUTH,
        json={"question": "x", "scope": "invalid"},
    )
    assert invalid.status_code == 422
    created = client.post(
        "/api/monitoring",
        headers=_AUTH,
        json={"question": "Qwen release?", "cadence_minutes": 60},
    )
    assert created.status_code == 201
    monitor_id = created.json()["id"]
    results = client.get(
        f"/api/monitoring/{monitor_id}/results",
        headers=_AUTH,
    )
    assert results.status_code == 200
    assert results.json()["results"] == []


def test_candidates_api_is_authenticated_and_bounded(tmp_path: Path, monkeypatch) -> None:
    data_root = tmp_path / "candidate-data"
    data_root.mkdir()
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(data_root))
    store = ContentStore(data_root / "condenseit.db")
    store.save_digest(
        "digest",
        "<p>digest</p>",
        json.dumps(
            {
                "candidate_items": [
                    {
                        "rank": 1,
                        "url": "https://example.com/a#tracking",
                        "title": "A",
                        "excerpt": "<b>snippet</b>",
                        "score_breakdown": {"keyword": 1, "llm_reason": "secret"},
                        "evidence": {
                            "matched_terms": ["A"],
                            "relevance_reason": "title match",
                            "llm_reason": "secret",
                            "selected": True,
                        },
                    },
                    {"rank": 2, "url": "https://example.com/b", "title": "B"},
                ]
            }
        ),
    )
    store.close()
    client = TestClient(create_app())
    assert client.get("/api/candidates").status_code == 401
    response = client.get("/api/candidates", headers=_AUTH, params={"limit": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["has_more"] is True
    assert body["candidates"][0]["url"] == "https://example.com/a"
    assert "llm_reason" not in body["candidates"][0]["score_breakdown"]
    assert "llm_reason" not in body["candidates"][0]["evidence"]
    second_page = client.get(
        "/api/candidates",
        headers=_AUTH,
        params={"page": 2, "limit": 1},
    )
    assert second_page.status_code == 200
    assert second_page.json()["page"] == 2
    assert [item["rank"] for item in second_page.json()["candidates"]] == [2]
    assert second_page.json()["has_more"] is False


def test_discovery_api_paginates_without_auth_or_digest_writes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[int] = []

    def fake_search(self, _query, **kwargs):
        calls.append(int(kwargs["max_items"]))
        return [
            {
                "url": f"https://example.com/{idx}",
                "title": f"Result {idx}",
                "snippet": "Snippet",
                "evidence": {"provider": "fake", "freshness": 1},
            }
            for idx in range(5)
        ]

    monkeypatch.setattr(GoogleNewsDiscovery, "search", fake_search)
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(tmp_path / "discover-data"))
    client = TestClient(create_app())
    response = client.get(
        "/api/discover",
        params={"q": "Qwen", "page": 2, "limit": 1},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 2
    assert body["limit"] == 1
    assert body["results"][0]["url"] == "https://example.com/1"
    assert body["has_more"] is True
    assert calls == [3]
