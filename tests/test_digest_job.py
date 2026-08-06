"""Tests for background digest job manager."""

from __future__ import annotations

import time
from unittest.mock import patch

from condenseit.store.database import ContentStore
from condenseit.web.digest_job import DigestJobManager


def test_job_manager_rejects_concurrent_runs(tmp_path) -> None:
    store = ContentStore(db_path=tmp_path / "runs.db")
    manager = DigestJobManager(store=store)
    with patch("condenseit.web.digest_job.execute_digest") as mock_run:

        def slow_run(*_a: object, **_k: object) -> dict[str, object]:
            time.sleep(0.5)
            return {
                "stats": {"articles_count": 1, "processing_time": "1s"},
                "post": {},
                "digest_id": 1,
            }

        mock_run.side_effect = slow_run
        ok1, _ = manager.start()
        ok2, msg2 = manager.start()
        assert ok1 is True
        assert ok2 is False
        assert "already running" in msg2.lower()
        if manager._thread:
            manager._thread.join(timeout=2)
        assert len(store.list_digest_runs()) == 1
        store.close()


def test_job_manager_completes() -> None:
    manager = DigestJobManager()
    with patch("condenseit.web.digest_job.execute_digest") as mock_run:
        mock_run.return_value = {
            "stats": {"articles_count": 3, "processing_time": "2s"},
            "post": {},
            "digest_id": 42,
        }
        ok, _ = manager.start()
        assert ok is True
        if manager._thread:
            manager._thread.join(timeout=2)
        snap = manager.snapshot()
        assert snap["state"] == "completed"
        assert snap["digest_id"] == 42
        assert "post_display" in snap
        assert snap["post_display"] == ""


def test_job_manager_persists_completed_run(tmp_path) -> None:
    store = ContentStore(db_path=tmp_path / "runs.db")
    manager = DigestJobManager(store=store)
    with patch("condenseit.web.digest_job.execute_digest") as mock_run:
        mock_run.return_value = {
            "stats": {"articles_count": 3, "processing_time": "2s"},
            "post": {},
            "digest_id": 42,
        }
        ok, _ = manager.start()
        assert ok is True
        if manager._thread:
            manager._thread.join(timeout=2)

    run = store.latest_digest_run()
    assert run is not None
    assert run["state"] == "completed"
    assert run["digest_id"] == 42
    assert run["stats"]["articles_count"] == 3
    assert manager.snapshot()["run_id"] == run["id"]
    store.close()


def test_job_manager_persists_failed_run(tmp_path) -> None:
    store = ContentStore(db_path=tmp_path / "runs.db")
    manager = DigestJobManager(store=store)
    with patch("condenseit.web.digest_job.execute_digest") as mock_run:
        mock_run.side_effect = RuntimeError("proxy unavailable")
        ok, _ = manager.start()
        assert ok is True
        if manager._thread:
            manager._thread.join(timeout=2)

    run = store.latest_digest_run()
    assert run is not None
    assert run["state"] == "failed"
    assert run["error"] == "proxy unavailable"
    assert run["log_id"] is not None
    store.close()


def test_job_manager_completion_is_visible_while_polling(tmp_path) -> None:
    store = ContentStore(db_path=tmp_path / "runs.db")
    manager = DigestJobManager(store=store)
    with patch("condenseit.web.digest_job.execute_digest") as mock_run:

        def slow_run(*_args: object, **_kwargs: object) -> dict[str, object]:
            time.sleep(0.08)
            return {
                "stats": {"articles_count": 2, "processing_time": "1s"},
                "post": {},
                "digest_id": 7,
            }

        mock_run.side_effect = slow_run
        ok, _ = manager.start()
        assert ok is True

        observed_states: list[str] = []
        deadline = time.monotonic() + 2
        while manager._thread and manager._thread.is_alive():
            observed_states.append(manager.snapshot()["state"])
            # Simulate request-thread polling while the worker commits its result.
            store.list_digest_runs()
            if time.monotonic() >= deadline:
                break
            time.sleep(0.01)
        manager._thread.join(timeout=2)

    assert "running" in observed_states
    assert manager.snapshot()["state"] == "completed"
    assert store.latest_digest_run()["state"] == "completed"
    store.close()
