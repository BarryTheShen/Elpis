import sqlite3
from pathlib import Path

from click.testing import CliRunner

from condenseit.cli import cli
from condenseit.store.database import ContentStore


def test_migrate_applies_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    path = ContentStore.migrate(db_path=db_path)
    assert path == db_path
    assert db_path.is_file()
    store = ContentStore(db_path=db_path)
    assert "articles" in store.db.table_names()
    store.close()


def test_local_sqlite_run_state_survives_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "restart.db"
    store = ContentStore(db_path=db_path)
    run_id = store.create_digest_run(started_at="2026-07-13T12:00:00Z")
    store.update_digest_run(
        run_id,
        state="completed",
        message="Digest ready.",
        finished_at="2026-07-13T12:01:00Z",
        digest_id=7,
        stats={"articles_count": 3},
    )
    store.close()

    restarted = ContentStore(db_path=db_path)
    run = restarted.latest_digest_run()
    assert run is not None
    assert run["id"] == run_id
    assert run["state"] == "completed"
    assert run["stats"]["articles_count"] == 3
    restarted.close()


def test_migrate_cli(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(cli, ["migrate"])
    assert result.exit_code == 0, result.output
    assert "Migrations applied" in result.output
    assert (tmp_path / "condenseit.db").is_file()


def test_deduplicate_new_article(tmp_path: Path) -> None:
    store = ContentStore(db_path=tmp_path / "test.db")
    article = {
        "url": "https://example.com/a",
        "title": "Test",
        "content": "Hello world",
        "source": "Example",
        "category": "General",
        "content_hash": ContentStore.content_hash("Hello world"),
        "published_at": "2026-01-01T00:00:00+00:00",
        "collected_at": "2026-01-01T00:00:00+00:00",
    }
    fresh = store.deduplicate([article])
    assert len(fresh) == 1
    expected_hash = article["content_hash"]

    same_hash_again = {
        **article,
        "collected_at": "2026-06-01T12:00:00+00:00",
        "title": "Test renamed",
    }
    fresh_again = store.deduplicate([same_hash_again])
    assert len(fresh_again) == 0
    row = store.db["articles"].get(article["url"])
    # collected_at stays at first-seen time so same-day pooling is stable.
    assert row["collected_at"] == "2026-01-01T00:00:00+00:00"
    assert row["title"] == "Test renamed"
    assert row["content_hash"] == expected_hash


def test_existing_run_logs_get_run_id_column(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE digest_run_logs ("
        "id INTEGER PRIMARY KEY,"
        "digest_id INTEGER,"
        "log_text TEXT,"
        "created_at TEXT"
        ")",
    )
    connection.commit()
    connection.close()

    store = ContentStore(db_path=db_path)
    columns = {
        row[1]
        for row in store.db.execute(
            "PRAGMA table_info(digest_run_logs)",
        ).fetchall()
    }
    assert "run_id" in columns
    store.close()



def test_list_digests_uses_exclusive_cursor_and_default_page(tmp_path: Path) -> None:
    store = ContentStore(db_path=tmp_path / "digests.db")
    for _ in range(25):
        store.save_digest("# Digest", "<p>Digest</p>", "{}")

    assert [row["id"] for row in store.list_digests()] == list(range(25, 5, -1))
    assert [row["id"] for row in store.list_digests(limit=2, before_id=20)] == [
        19,
        18,
    ]
    assert store.list_digests(limit=2, before_id=1) == []
    store.close()


def test_prune_digests_retains_newest_issues(tmp_path: Path) -> None:
    store = ContentStore(db_path=tmp_path / "retention.db")
    ids = [
        store.save_digest(f"# Digest {index}", "<p>Digest</p>", "{}")
        for index in range(5)
    ]

    assert store.prune_digests(2) == 3
    assert [row["id"] for row in store.list_digests(limit=10)] == ids[-2:][::-1]
    assert store.prune_digests(2) == 0
    store.close()