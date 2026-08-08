"""Offline contract tests for persisted monitoring questions and results.

These tests exercise ContentStore directly with an isolated SQLite database.
No Google credentials, network access, scheduler, or delivery channel is
required.  Monitoring rows are intentionally separate from digest rows: a
check may update monitor state and result evidence without creating a digest.
"""

from __future__ import annotations

from pathlib import Path

from condenseit.store.database import ContentStore


def _monitor_payload() -> dict[str, object]:
    return {
        "question": "What changed in Qwen3.8 this week?",
        "search_query": "Qwen3.8 release",
        "scope": "general_discovery",
        "enabled": True,
        "cadence_minutes": 360,
        "include_keywords": ["qwen", "release"],
        "exclude_keywords": ["rumor"],
        "category": "AI Research",
        "language": "en",
        "country": "US",
        "max_items": 20,
    }


def _result_payload(url: str, *, state: str = "new") -> dict[str, object]:
    return {
        "url": url,
        "title": "Qwen3.8 release adds an inference benchmark",
        "snippet": "Researchers publish reproducible release measurements.",
        "source": "Synthetic News",
        "category": "AI Research",
        "published_at": "2026-08-08T09:00:00+00:00",
        "first_seen_at": "2026-08-08T10:00:00+00:00",
        "last_seen_at": "2026-08-08T10:00:00+00:00",
        "relevance_score": 0.92,
        "evidence": {
            "matched_terms": ["qwen", "release"],
            "provider": "fixture",
            "freshness": 1.0,
        },
        "state": state,
    }


def test_monitor_schema_is_idempotent_and_question_is_persisted(tmp_path: Path) -> None:
    db_path = tmp_path / "monitoring.db"
    store = ContentStore(db_path=db_path)
    monitor_id = store.create_monitor_query(**_monitor_payload())

    row = store.get_monitor_query(monitor_id)
    assert row is not None
    assert row["id"] == monitor_id
    assert row["question"] == "What changed in Qwen3.8 this week?"
    assert row["search_query"] == "Qwen3.8 release"
    assert row["scope"] == "general_discovery"
    assert row["include_keywords"] == ["qwen", "release"]
    assert row["exclude_keywords"] == ["rumor"]
    assert row["enabled"] is True
    assert row["cadence_minutes"] == 360
    assert row["status"] == "idle"
    assert row["new_count"] == 0

    # Updates accept a mapping and preserve the exact question text.
    updated = store.update_monitor_query(
        monitor_id,
        updates={"cadence_minutes": 60, "enabled": False},
    )
    assert updated is not None
    assert updated["question"] == row["question"]
    assert updated["cadence_minutes"] == 60
    assert updated["enabled"] is False
    assert store.list_monitor_queries(enabled_only=True) == []
    assert store.list_monitor_queries(enabled_only=False)[0]["id"] == monitor_id

    # Re-opening the same path reruns the idempotent schema migration and
    # retains monitor data independently of digest tables.
    store.close()
    reopened = ContentStore(db_path=db_path)
    assert "monitor_queries" in reopened.db.table_names()
    assert "monitor_results" in reopened.db.table_names()
    assert reopened.get_monitor_query(monitor_id)["question"] == row["question"]

    second_id = reopened.create_monitor_query(
        question="Track Kubernetes CVE advisories",
        search_query="Kubernetes CVE",
        scope="both",
        cadence_minutes=120,
    )
    assert second_id != monitor_id
    assert reopened.delete_monitor_query(second_id) is True
    assert reopened.get_monitor_query(second_id) is None
    reopened.close()


def test_monitor_results_are_deduplicated_and_state_is_explicit(tmp_path: Path) -> None:
    store = ContentStore(db_path=tmp_path / "results.db")
    monitor_id = store.create_monitor_query(**_monitor_payload())
    url = "https://fixture.test/qwen3-8"

    first_id = store.upsert_monitor_result(
        monitor_id,
        result=_result_payload(url),
    )
    second = _result_payload(url, state="dismissed")
    second["title"] = "Updated Qwen3.8 release headline"
    second["first_seen_at"] = "2026-08-09T10:00:00+00:00"
    second["last_seen_at"] = "2026-08-09T10:00:00+00:00"
    second_id = store.upsert_monitor_result(monitor_id, result=second)

    assert second_id == first_id
    stored = store.get_monitor_result(first_id)
    assert stored is not None
    assert stored["title"] == "Updated Qwen3.8 release headline"
    # URL deduplication keeps discovery history and the user's explicit state.
    assert stored["first_seen_at"] == "2026-08-08T10:00:00+00:00"
    assert stored["state"] == "new"
    assert stored["last_seen_at"] == "2026-08-09T10:00:00+00:00"
    assert stored["evidence"]["matched_terms"] == ["qwen", "release"]

    changed = store.update_monitor_result_state(first_id, "seen", monitor_id=monitor_id)
    assert changed["state"] == "seen"
    assert store.list_monitor_results(monitor_id, state="new") == []
    assert store.list_monitor_results(monitor_id, state="seen")[0]["url"] == url

    # A second result remains independently addressable and can be dismissed.
    second_url = "https://fixture.test/qwen3-8/benchmark"
    other_id = store.upsert_monitor_result(
        monitor_id,
        result=_result_payload(second_url),
    )
    assert other_id != first_id
    assert store.update_monitor_result_state(
        other_id,
        "dismissed",
        monitor_id=monitor_id,
    )["state"] == "dismissed"
    assert {item["state"] for item in store.list_monitor_results(monitor_id)} == {
        "seen",
        "dismissed",
    }
    store.close()


def test_check_now_persists_normalized_results_without_a_digest(
    tmp_path: Path,
) -> None:
    from datetime import UTC, datetime

    from condenseit.services.monitoring import MonitoringService

    class FakeDiscovery:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def search(self, query: str, **kwargs: object) -> list[dict[str, object]]:
            self.calls.append({"query": query, **kwargs})
            result = {
                "url": "https://fixture.test/qwen3-8/check",
                "title": "Qwen3.8 release check",
                "snippet": "A normalized monitoring result.",
                "source": "Fixture News",
                "published_at": "2026-08-08T11:00:00+00:00",
                "relevance_score": 0.88,
                "evidence": {
                    "matched_terms": ["qwen", "release"],
                    "provider": "fixture",
                    "freshness": 0.9,
                    "llm_reason": "must never be persisted",
                },
            }
            return [result, dict(result)]

    now = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    store = ContentStore(db_path=tmp_path / "service.db")
    monitor_id = store.create_monitor_query(**_monitor_payload())
    discovery = FakeDiscovery()
    service = MonitoringService(
        store,
        discovery=discovery,
        clock=lambda: now,
    )

    checked = service.check_now(monitor_id)
    assert checked["error"] is None
    assert checked["new_count"] == 1
    assert len(checked["results"]) == 1
    assert checked["monitor"]["status"] == "ok"
    assert checked["monitor"]["last_checked_at"] == now.isoformat()
    assert checked["monitor"]["last_success_at"] == now.isoformat()
    assert checked["monitor"]["next_check_at"] == "2026-08-08T18:00:00+00:00"
    assert discovery.calls[0]["query"] == "Qwen3.8 release"
    assert checked["results"][0]["evidence"] == {
        "matched_terms": ["qwen", "release"],
        "provider": "fixture",
        "freshness": 0.9,
    }

    # A repeated check updates the existing URL, not the result count.
    checked_again = service.check_now(monitor_id)
    assert checked_again["new_count"] == 1
    assert len(store.list_monitor_results(monitor_id)) == 1
    result_id = checked_again["results"][0]["id"]
    assert service.set_result_state(monitor_id, result_id, "seen")["state"] == "seen"
    assert store.monitor_new_count(monitor_id) == 0

    # Monitoring is separate from publication and must not create a digest row.
    digest_count = store.db.execute("SELECT COUNT(*) FROM digests").fetchone()[0]
    assert digest_count == 0
    store.close()
