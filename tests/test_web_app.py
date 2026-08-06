from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from condenseit.store.database import ContentStore
from condenseit.web.app import _digest_cost_usd, create_app

# Operational APIs remain authenticated; publication reads are intentionally public.
_AUTH = {"Authorization": "Bearer elpis"}


def test_health_and_api_endpoints(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Core JSON API and health endpoints return expected shapes."""
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(tmp_path / "data"))
    client = TestClient(create_app())

    health = client.get("/health")
    assert health.json() == {"status": "ok"}

    unauthenticated_status = client.get("/api/digest/status")
    assert unauthenticated_status.status_code == 401

    status = client.get("/api/digest/status", headers=_AUTH)
    assert status.json()["state"] == "idle"

    # Publication reads are public, even before the first digest is generated.
    digests = client.get("/api/digests")
    assert digests.status_code == 200
    assert digests.json() == []

    latest = client.get("/api/digests/latest")
    assert latest.status_code == 200
    assert latest.json() is None


def test_health_reports_storage_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Health becomes unavailable when the data store cannot answer a query."""
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(tmp_path / "data"))
    app = create_app()

    def fail_execute(*_args, **_kwargs):
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(app.state.store.db, "execute", fail_execute)
    response = TestClient(app).get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


def test_spa_shell_served_for_ui_routes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """The SPA login route is public while admin routes require authorization."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(
        "<!DOCTYPE html><html>spa-shell-marker</html>",
        encoding="utf-8",
    )
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CONDENSEIT_FRONTEND_DIST", str(dist))
    client = TestClient(create_app())

    home = client.get("/")
    assert home.status_code == 200
    assert "spa-shell-marker" in home.text

    admin = client.get("/admin/sources", follow_redirects=False)
    assert admin.status_code == 303
    assert admin.headers["location"] == "/login"

    login = client.get("/login")
    assert login.status_code == 200
    assert "spa-shell-marker" in login.text

    authorized_admin = client.get("/admin/sources", headers=_AUTH)
    assert authorized_admin.status_code == 200
    assert "spa-shell-marker" in authorized_admin.text

    legacy_admin_write = client.post("/admin/sources")
    assert legacy_admin_write.status_code == 401

    session_login = client.post("/api/auth/login", json={"password": "elpis"})
    assert session_login.status_code == 200
    session_admin = client.get("/admin/sources")
    assert session_admin.status_code == 200
    assert "spa-shell-marker" in session_admin.text


def test_sources_api_updates_source_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """The source update endpoint persists editable source fields."""
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(tmp_path / "data"))
    client = TestClient(create_app())

    added = client.post(
        "/api/sources",
        headers=_AUTH,
        json={
            "source_type": "rss",
            "name": "Old Feed",
            "url": "https://example.com/old.xml",
            "category": "Old",
            "priority": 2,
        },
    )
    assert added.status_code == 200

    sources = client.get("/api/sources", headers=_AUTH).json()
    source_id = next(s["id"] for s in sources if s["name"] == "Old Feed")

    updated = client.put(
        f"/api/sources/{source_id}",
        headers=_AUTH,
        json={
            "source_type": "google_news",
            "name": "AI News",
            "query": "AI safety",
            "language": "en",
            "country": "GB",
            "category": "Research",
            "priority": 1,
        },
    )
    assert updated.status_code == 200

    rows = client.get("/api/sources", headers=_AUTH).json()
    row = next(s for s in rows if s["id"] == source_id)
    extra = json.loads(row["extra_json"])
    assert row["type"] == "google_news"
    assert row["name"] == "AI News"
    assert row["category"] == "Research"
    assert row["priority"] == 1
    assert "AI+safety" in row["url"]
    assert extra == {"query": "AI safety", "language": "en", "country": "GB"}


def test_digest_api_returns_items(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """The /api/digests/latest endpoint returns structured items."""
    data_root = tmp_path / "appdata"
    data_root.mkdir()
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(data_root))

    store = ContentStore()
    payload = {
        "articles_count": 1,
        "digest_items": [
            {
                "id": 0,
                "title": "Hello",
                "url": "https://example.com/a",
                "summary": (
                    "Here is a 2-3 sentence summary of the article: Summary text."
                ),
                "source": "Example Feed",
                "category": "News",
                "published_at": "2026-01-15T12:00:00+00:00",
                "kind": "article",
            },
        ],
    }
    digest_id = store.save_digest(
        "<script>window.pwned = true</script>\n# Hello",
        "<p>Hello</p>",
        json.dumps(payload),
    )
    store.rate_article("https://example.com/a", 5)
    client = TestClient(create_app())

    latest = client.get("/api/digests/latest")
    assert latest.status_code == 200
    data = latest.json()
    assert data is not None
    assert "html" not in data
    assert "<script>" not in json.dumps(data)
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["title"] == "Hello"
    # Summary should have LLM prefix stripped
    assert not item["summary"].startswith("Here is")
    assert "Summary text" in item["summary"]
    assert "rating" not in item

    detail = client.get(f"/api/digests/{digest_id}")
    assert detail.status_code == 200
    assert detail.json()["meta"]["id"] == digest_id
    assert "html" not in detail.json()
    assert "rating" not in detail.json()["items"][0]


def test_digest_cost_uses_explicit_spending_link(tmp_path) -> None:
    """Digest-linked spend rows should be preferred over timestamp inference."""
    store = ContentStore(db_path=tmp_path / "test.db")
    digest_id = store.save_digest(
        "# Costed",
        "<p>Costed</p>",
        json.dumps({"articles_count": 1}),
    )
    store.db["spending"].insert(
        {
            "amount_usd": 0.1234,
            "model": "openrouter/test",
            "tokens": 100,
            "recorded_at": "2026-05-17T07:00:00+00:00",
            "digest_id": digest_id,
            "digest_run_id": "run-1",
        },
    )

    cost = _digest_cost_usd(
        store,
        digest_id,
        "2026-05-17T07:05:00+00:00",
        {},
    )

    assert cost == pytest.approx(0.1234)


def test_digest_cost_falls_back_to_previous_digest_window(tmp_path) -> None:
    """Old spend rows without digest IDs are grouped by digest boundaries."""
    store = ContentStore(db_path=tmp_path / "test.db")
    first_id = store.save_digest(
        "# First",
        "<p>First</p>",
        json.dumps({"articles_count": 1}),
    )
    store.db.execute(
        "UPDATE digests SET created_at = ? WHERE id = ?",
        ["2026-05-17T07:00:00+00:00", first_id],
    )
    second_id = store.save_digest(
        "# Second",
        "<p>Second</p>",
        json.dumps({"articles_count": 1}),
    )
    store.db.execute(
        "UPDATE digests SET created_at = ? WHERE id = ?",
        ["2026-05-17T07:10:00+00:00", second_id],
    )
    store.db["spending"].insert_all(
        [
            {
                "amount_usd": 0.01,
                "model": "openrouter/test",
                "tokens": 10,
                "recorded_at": "2026-05-17T07:05:00+00:00",
            },
            {
                "amount_usd": 0.02,
                "model": "openrouter/test",
                "tokens": 20,
                "recorded_at": "2026-05-17T07:09:00+00:00",
            },
        ],
    )

    cost = _digest_cost_usd(
        store,
        second_id,
        "2026-05-17T07:10:00+00:00",
        {},
    )

    assert cost == pytest.approx(0.03)


def test_ratings_api_prefers_digest_items(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """The /api/ratings endpoint returns digest items, not raw articles."""
    data_root = tmp_path / "appdata"
    data_root.mkdir()
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(data_root))

    store = ContentStore()
    store.save_article(
        {
            "url": "https://legacy.example/x",
            "title": "Legacy Noise Title",
            "content": "x",
            "source": "s",
            "category": "General",
            "content_hash": ContentStore.content_hash("x"),
            "published_at": "",
            "collected_at": "2099-01-01T00:00:00+00:00",
        },
    )
    payload = {
        "digest_items": [
            {
                "id": 0,
                "title": "Digest Item Alpha",
                "url": "https://digest.example/a",
                "category": "Tech",
                "kind": "article",
            },
        ],
    }
    store.save_digest("# Hello", "<p>Hello</p>", json.dumps(payload))
    client = TestClient(create_app())

    ratings = client.get("/api/ratings", headers=_AUTH)
    assert ratings.status_code == 200
    items = ratings.json()
    titles = [r["title"] for r in items]
    assert "Digest Item Alpha" in titles
    assert "Legacy Noise Title" not in titles


def test_digest_config_api_persists_age_cutoff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """The admin digest settings API exposes and saves the age filter cutoff."""
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(tmp_path / "data"))
    client = TestClient(create_app())

    initial = client.get("/api/config/digest", headers=_AUTH)
    assert initial.status_code == 200
    assert initial.json()["max_article_age_hours"] == 36

    saved = client.put(
        "/api/config/digest",
        headers=_AUTH,
        json={"max_article_age_hours": 72},
    )
    assert saved.status_code == 200

    updated = client.get("/api/config/digest", headers=_AUTH)
    assert updated.status_code == 200
    assert updated.json()["max_article_age_hours"] == 72

    invalid = client.put(
        "/api/config/digest",
        headers=_AUTH,
        json={"max_article_age_hours": -1},
    )
    assert invalid.status_code == 422


def test_digest_run_history_api_exposes_outcomes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Run history exposes status, structured stats, and linked logs."""
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(tmp_path / "data"))
    app = create_app()
    store = app.state.store
    run_id = store.create_digest_run(
        started_at="2026-07-13T08:00:00Z",
        dry_run=True,
    )
    store.update_digest_run(
        run_id,
        state="completed",
        message="Done: 3 articles in 2s",
        finished_at="2026-07-13T08:00:02Z",
        digest_id=42,
        stats={"articles_count": 3, "processing_time": "2s"},
    )
    log_id = store.save_run_log(42, "run output", run_id=run_id)

    client = TestClient(app)
    response = client.get("/api/digest/runs", headers=_AUTH)

    assert response.status_code == 200
    rows = response.json()
    assert rows[0]["id"] == run_id
    assert rows[0]["state"] == "completed"
    assert rows[0]["stats"]["articles_count"] == 3
    assert rows[0]["dry_run"] is True
    assert rows[0]["log_id"] == log_id

    latest = client.get("/api/digest/runs/latest", headers=_AUTH)
    assert latest.status_code == 200
    assert latest.json()["id"] == run_id


def test_create_app_reconciles_interrupted_runs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """A restart converts orphaned running records into visible failures."""
    data_dir = tmp_path / "data"
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(data_dir))

    previous_store = ContentStore()
    run_id = previous_store.create_digest_run(
        started_at="2026-07-13T08:00:00Z",
    )
    previous_store.close()

    app = create_app()
    run = app.state.store.get_digest_run(run_id)
    assert run is not None
    assert run["state"] == "failed"
    assert run["message"] == "Digest interrupted by server restart."
    assert run["error"] == "Digest interrupted by server restart."
    assert run["finished_at"]

    client = TestClient(app)
    status = client.get("/api/digest/status", headers=_AUTH)
    assert status.status_code == 200
    assert status.json()["state"] == "idle"

    latest = client.get("/api/digest/runs/latest", headers=_AUTH)
    assert latest.json()["state"] == "failed"


def test_fresh_install_password_change_uses_default_credential(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """A fresh install can replace the built-in default password."""
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("CONDENSEIT_AUTH_PASSWORD", raising=False)
    monkeypatch.delenv("DIGEST_PWA_AUTH_PASSWORD", raising=False)
    app = create_app()
    client = TestClient(app)

    changed = client.put(
        "/api/config/password",
        headers=_AUTH,
        json={
            "current_password": "elpis",
            "new_password": "new-passphrase",
        },
    )
    assert changed.status_code == 200

    old_login = client.post("/api/auth/login", json={"password": "elpis"})
    assert old_login.status_code == 401

    new_login = client.post(
        "/api/auth/login",
        json={"password": "new-passphrase"},
    )
    assert new_login.status_code == 200


def test_password_change_revokes_other_sessions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Changing the password keeps the requester active and revokes peers."""
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("CONDENSEIT_AUTH_PASSWORD", raising=False)
    monkeypatch.delenv("DIGEST_PWA_AUTH_PASSWORD", raising=False)
    app = create_app()
    first = TestClient(app)
    second = TestClient(app)

    assert first.post("/api/auth/login", json={"password": "elpis"}).status_code == 200
    assert second.post("/api/auth/login", json={"password": "elpis"}).status_code == 200

    changed = first.put(
        "/api/config/password",
        json={
            "current_password": "elpis",
            "new_password": "rotated-passphrase",
        },
    )
    assert changed.status_code == 200
    assert first.get("/api/digest/status").status_code == 200
    assert second.get("/api/digest/status").status_code == 401

    assert (
        second.post(
            "/api/auth/login",
            json={"password": "rotated-passphrase"},
        ).status_code
        == 200
    )
