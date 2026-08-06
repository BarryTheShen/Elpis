"""Background digest runs triggered from the web UI."""

import logging
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from condenseit.network import load_network_proxy, sanitize_network_text
from condenseit.services.digest_runner import execute_digest
from condenseit.store.database import ContentStore

logger = logging.getLogger(__name__)


class _ListHandler(logging.Handler):
    """Captures log records emitted during a digest run into a list."""

    def __init__(self) -> None:
        super().__init__()
        self._lines: list[str] = []
        self.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._lines.append(self.format(record))
        except Exception as exc:
            logger.debug("Log record formatting failed: %s", exc)

    def get_text(self) -> str:
        return "\n".join(self._lines)


@dataclass
class DigestJobSnapshot:
    state: str = "idle"
    run_id: int | None = None
    message: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    stats: dict[str, Any] | None = None
    post: dict[str, Any] | None = None
    post_display: str = ""
    digest_id: int | None = None
    error: str | None = None
    log_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DigestJobManager:
    """Single-flight background digest runner."""

    def __init__(
        self,
        config_path: str | None = None,
        store: Any | None = None,
    ) -> None:
        self._config_path = config_path
        self._store = store
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._snapshot = DigestJobSnapshot()

    def _open_persistence_store(self) -> Any | None:
        """Open a connection dedicated to this manager's persistence work."""
        if self._store is None:
            return None
        db_path = getattr(self._store, "db_path", None)
        if db_path is None:
            return None
        return ContentStore(db_path=db_path)

    def _close_persistence_store(self, persistence_store: Any | None) -> None:
        if persistence_store is not None and persistence_store is not self._store:
            persistence_store.close()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot.to_dict()

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._snapshot.state == "running"

    def start(
        self,
        *,
        dry_run: bool = False,
        skip_deploy: bool = False,
    ) -> tuple[bool, str]:
        with self._lock:
            if self._snapshot.state == "running":
                return False, "A digest is already running."

            started_at = _now_iso()
            run_id: int | None = None
            if self._store is not None:
                persistence_store: Any | None = None
                try:
                    persistence_store = self._open_persistence_store()
                    if persistence_store is None:
                        return False, "Digest state storage is unavailable."
                    run_id = persistence_store.create_digest_run(
                        started_at=started_at,
                        dry_run=dry_run,
                        skip_deploy=skip_deploy,
                    )
                except Exception:
                    logger.warning("Failed to persist digest run start", exc_info=True)
                    return (
                        False,
                        "Could not start digest because its run state "
                        "could not be saved.",
                    )
                finally:
                    self._close_persistence_store(persistence_store)

            self._snapshot = DigestJobSnapshot(
                state="running",
                run_id=run_id,
                message="Running...",
                started_at=started_at,
            )
            self._thread = threading.Thread(
                target=self._run,
                kwargs={
                    "dry_run": dry_run,
                    "skip_deploy": skip_deploy,
                    "run_id": run_id,
                    "started_at": started_at,
                },
                name="condenseit-digest",
                daemon=True,
            )
            self._thread.start()
        return True, "Digest started."

    def _run(
        self,
        *,
        dry_run: bool,
        skip_deploy: bool,
        run_id: int | None,
        started_at: str,
    ) -> None:
        handler = _ListHandler()
        root_logger = logging.getLogger("condenseit")
        root_logger.addHandler(handler)
        digest_id: int | None = None
        terminal: DigestJobSnapshot

        try:
            result = execute_digest(
                self._config_path,
                dry_run=dry_run,
                skip_deploy=skip_deploy,
            )
            digest_id = result.get("digest_id")
            stats = result["stats"]
            articles = stats.get("articles_count", 0)
            slim_stats = {k: v for k, v in stats.items() if k != "digest_items"}
            terminal = DigestJobSnapshot(
                state="completed",
                run_id=run_id,
                message=(
                    f"Done: {articles} articles in {stats.get('processing_time', '?')}"
                ),
                started_at=started_at,
                finished_at=_now_iso(),
                stats=slim_stats,
                post=result.get("post"),
                digest_id=digest_id,
            )
        except Exception as exc:
            error = sanitize_network_text(str(exc), load_network_proxy())
            logger.error("Digest job failed: %s", error)
            terminal = DigestJobSnapshot(
                state="failed",
                run_id=run_id,
                message="Digest failed.",
                started_at=started_at,
                finished_at=_now_iso(),
                error=error,
            )
        finally:
            root_logger.removeHandler(handler)
            log_text = sanitize_network_text(handler.get_text(), load_network_proxy())
            log_id: int | None = None
            persistence_store: Any | None = None

            if self._store is not None:
                try:
                    persistence_store = self._open_persistence_store()
                except Exception:
                    logger.warning(
                        "Failed to open digest-run persistence connection",
                        exc_info=True,
                    )

            if persistence_store is not None and run_id is not None:
                try:
                    persistence_store.update_digest_run(
                        run_id,
                        state=terminal.state,
                        message=terminal.message,
                        finished_at=terminal.finished_at or _now_iso(),
                        digest_id=terminal.digest_id,
                        stats=terminal.stats,
                        error=terminal.error,
                    )
                except Exception:
                    logger.warning("Failed to persist digest run result", exc_info=True)

            if persistence_store is not None and log_text:
                try:
                    log_id = persistence_store.save_run_log(
                        terminal.digest_id,
                        log_text,
                        run_id=run_id,
                    )
                except Exception:
                    logger.warning("Failed to persist run log", exc_info=True)

            self._close_persistence_store(persistence_store)
            terminal.log_id = log_id
            with self._lock:
                self._snapshot = terminal

    def dismiss(self) -> None:
        """Clear completed/failed state back to idle."""
        with self._lock:
            if self._snapshot.state == "running":
                return
            self._snapshot = DigestJobSnapshot()


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
