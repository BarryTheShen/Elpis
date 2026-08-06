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


def test_digest_list_api_paginates_and_validates_queries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Digest history is exposed as ordered, validated pages."""
    data_root = tmp_path / "appdata"
    data_root.mkdir()
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(data_root))

    store = ContentStore()
    for _ in range(25):
        store.save_digest("# Digest", "<p>Digest</p>", "{}")
    store.close()

    client = TestClient(create_app())

    newest = client.get("/api/digests", params={"limit": 2})
    assert newest.status_code == 200
    assert [row["id"] for row in newest.json()] == [25, 24]
    assert set(newest.json()[0]) == {"id", "created_at"}

    default_page = client.get("/api/digests")
    assert default_page.status_code == 200
    assert [row["id"] for row in default_page.json()] == list(range(25, 5, -1))

    older = client.get(
        "/api/digests",
        params={"limit": 2, "before_id": 24},
    )
    assert older.status_code == 200
    assert [row["id"] for row in older.json()] == [23, 22]

    empty = client.get(
        "/api/digests",
        params={"limit": 2, "before_id": 1},
    )
    assert empty.status_code == 200
    assert empty.json() == []

    for invalid_limit in (0, 101, "not-an-integer"):
        response = client.get("/api/digests", params={"limit": invalid_limit})
        assert response.status_code == 422

    for invalid_cursor in ("not-an-integer", "1 OR 1=1"):
        response = client.get(
            "/api/digests",
            params={"before_id": invalid_cursor},
        )
        assert response.status_code == 422


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
            "max_items": 75,
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
    assert extra == {
        "query": "AI safety",
        "language": "en",
        "country": "GB",
        "max_items": 75,
    }

def test_sources_api_rejects_out_of_range_candidate_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(tmp_path / "data"))
    client = TestClient(create_app())

    response = client.post(
        "/api/sources",
        headers=_AUTH,
        json={
            "source_type": "rss",
            "name": "Too Large",
            "url": "https://example.com/feed.xml",
            "max_items": 201,
        },
    )

    assert response.status_code == 422
    assert "max_items" in response.json()["error"]


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
                "highlighted": True,
                "preference_score": 4.2,
                "relevance_to_you": "Matches your interests.",
                "score_breakdown": {"keyword_high": 2.0},
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
    for personal_field in (
        "highlighted",
        "preference_score",
        "relevance_to_you",
        "score_breakdown",
    ):
        assert personal_field not in item
    # Summary should have LLM prefix stripped
    assert not item["summary"].startswith("Here is")
    assert "Summary text" in item["summary"]
    assert "rating" not in item

    detail = client.get(f"/api/digests/{digest_id}")
    assert detail.status_code == 200
    assert detail.json()["meta"]["id"] == digest_id
    assert "html" not in detail.json()
    assert "rating" not in detail.json()["items"][0]

def test_digest_api_orders_items_by_preference_score(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Stored legacy digests are normalized to descending score order."""
    data_root = tmp_path / "appdata"
    data_root.mkdir()
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(data_root))

    store = ContentStore()
    store.save_digest(
        "# Ranking",
        "<p>Ranking</p>",
        json.dumps(
            {
                "digest_items": [
                    {
                        "title": "Lower score",
                        "url": "https://example.com/low",
                        "summary": "",
                        "preference_score": 2.0,
                        "score_breakdown": {},
                    },
                    {
                        "title": "Higher score",
                        "url": "https://example.com/high",
                        "summary": "",
                        "preference_score": 8.0,
                        "score_breakdown": {},
                    },
                ]
            }
        ),
    )

    response = TestClient(create_app()).get("/api/digests/latest")

    assert response.status_code == 200
    assert [item["title"] for item in response.json()["items"]] == [
        "Higher score",
        "Lower score",
    ]


def test_article_content_api_returns_stored_reader_text(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """The reader endpoint returns stored text and rejects unknown URLs."""
    data_root = tmp_path / "appdata"
    data_root.mkdir()
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(data_root))

    url = "https://example.com/reader"
    store = ContentStore()
    store.save_article(
        {
            "url": url,
            "title": "Reader article",
            "content": "First paragraph.\n\nSecond paragraph.",
            "source": "Example Feed",
            "category": "News",
            "published_at": "2026-01-15T12:00:00+00:00",
        }
    )
    store.save_digest(
        "# Reader",
        "<p>Reader</p>",
        json.dumps({"digest_items": [{"url": url}]}),
    )
    private_url = "https://example.com/not-published"
    store.save_article(
        {
            "url": private_url,
            "title": "Unpublished article",
            "content": "Should not be exposed.",
        }
    )
    client = TestClient(create_app())

    response = client.get("/api/articles/content", params={"url": url})
    assert response.status_code == 200
    assert response.json() == {
        "url": url,
        "title": "Reader article",
        "content": "First paragraph.\n\nSecond paragraph.",
        "source": "Example Feed",
        "category": "News",
        "published_at": "2026-01-15T12:00:00+00:00",
    }

    missing = client.get(
        "/api/articles/content",
        params={"url": "https://example.com/missing"},
    )
    assert missing.status_code == 404

    unpublished = client.get(
        "/api/articles/content",
        params={"url": private_url},
    )
    assert unpublished.status_code == 404

def test_summary_normalization_hides_reasoning_in_digest_and_saved_items(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Private provider reasoning never reaches publication or saved lists."""
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(tmp_path / "data"))
    store = ContentStore()
    url = "https://example.com/reasoning"
    raw = (
        "<think>private chain of thought with { distracting braces }</think>"
        '{"tldr":"Visible take","summary":"Visible summary.",'
        '"key_takeaways":["Visible point"]}'
    )
    store.save_digest(
        "# Reasoning",
        "<p>Reasoning</p>",
        json.dumps({"digest_items": [{"url": url, "title": "Visible", "summary": raw}]}),
    )
    client = TestClient(create_app())

    digest_item = client.get("/api/digests/latest").json()["items"][0]
    assert digest_item["tldr"] == "Visible take"
    assert digest_item["summary"] == "Visible summary."
    assert digest_item["key_takeaways"] == ["Visible point"]
    assert "private" not in json.dumps(digest_item).lower()

    saved = dict(digest_item)
    saved["summary"] = raw
    saved["tldr"] = ""
    saved["key_takeaways"] = []
    assert client.post("/api/read-later", headers=_AUTH, json=saved).status_code == 200

    saved_item = client.get("/api/read-later", headers=_AUTH).json()["items"][0]
    assert saved_item["summary"] == "Visible summary."
    assert saved_item["tldr"] == "Visible take"
    assert saved_item["key_takeaways"] == ["Visible point"]
    assert "private" not in json.dumps(saved_item).lower()

def test_summary_normalization_discards_plain_thinking_transcript(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """A plain model self-talk transcript never reaches publication."""
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(tmp_path / "data"))
    store = ContentStore()
    raw = (
        "Thinking Process:\n\n"
        "1. **Analyze the Request:** draft a JSON response.\n"
        "2. **Refine and Validate:** check the required fields.\n"
        "I will output the final JSON next."
    )
    store.save_digest(
        "# Plain reasoning",
        "<p>Plain reasoning</p>",
        json.dumps(
            {
                "digest_items": [
                    {
                        "url": "https://example.com/plain-reasoning",
                        "title": "Visible title",
                        "summary": raw,
                    }
                ]
            }
        ),
    )
    client = TestClient(create_app())

    item = client.get("/api/digests/latest").json()["items"][0]

    assert item["summary"] == ""
    assert "thinking process" not in json.dumps(item).lower()




def test_spa_catchall_does_not_serve_files_outside_dist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """The SPA fallback never serves paths outside the frontend directory."""
    data_root = tmp_path / "data"
    dist = tmp_path / "frontend-dist"
    dist.mkdir()
    (dist / "index.html").write_text("<app-shell>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("not public", encoding="utf-8")
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(data_root))
    monkeypatch.setenv("CONDENSEIT_FRONTEND_DIST", str(dist))

    response = TestClient(create_app()).get("/%2e%2e/secret.txt")

    assert response.status_code == 200
    assert response.text == "<app-shell>"

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
    assert initial.json()["digest_history_limit"] == 100
    saved = client.put(
        "/api/config/digest",
        headers=_AUTH,
        json={"max_article_age_hours": 72, "digest_history_limit": 2},
    )
    assert saved.status_code == 200

    updated = client.get("/api/config/digest", headers=_AUTH)
    assert updated.status_code == 200
    assert updated.json()["max_article_age_hours"] == 72
    assert updated.json()["digest_history_limit"] == 2
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
