"""Authenticated FastMCP tools for safe Elpis administration.

The HTTP bearer-token boundary is owned by :mod:`condenseit.web.app`.  This
module deliberately exposes only non-secret settings and read-only publication
metadata.  API keys, session secrets, proxy credentials, and filesystem paths
are not part of the tool contract.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from condenseit.config import load_config
from condenseit.settings_overlay import apply_db_settings
from condenseit.store.database import ContentStore
from condenseit.store.sources import SourceRegistry


@dataclass(frozen=True)
class _SettingRule:
    kind: str
    minimum: float | None = None
    maximum: float | None = None
    max_length: int = 256
    max_items: int = 100
    item_max_length: int = 120
    pattern: str | None = None


_SAFE_RULES: dict[str, _SettingRule] = {
    # Model and generation choices.  Credentials and provider endpoints are
    # intentionally absent.
    "model": _SettingRule("text", max_length=300),
    "llm_provider": _SettingRule("text", max_length=64),
    "openrouter_model": _SettingRule("text", max_length=300),
    "openrouter_pick_cheapest": _SettingRule("bool"),
    "reasoning_effort": _SettingRule("enum", max_length=16),
    "thinking_enabled": _SettingRule("bool"),
    "thinking_budget_tokens": _SettingRule("int", 0, 100_000),
    "openrouter_daily_budget_usd": _SettingRule("float", 0, 1_000_000),
    "openrouter_monthly_budget_usd": _SettingRule("float", 0, 10_000_000),
    # Digest composition and retention.
    "max_articles_per_digest": _SettingRule("int", 1, 200),
    "digest_history_limit": _SettingRule("int", 1, 1_000),
    "balance_digest_categories": _SettingRule("bool"),
    "max_articles_per_category": _SettingRule("int", 1, 50),
    "max_article_age_hours": _SettingRule("int", 0, 87_600),
    "digest_language": _SettingRule(
        "text", max_length=16, pattern=r"^[A-Za-z0-9_-]+$"
    ),
    "preferred_languages": _SettingRule(
        "list", max_items=8, item_max_length=16, pattern=r"^[A-Za-z0-9_-]+$"
    ),
    "exclude_keywords": _SettingRule("list", max_items=200),
    "max_key_takeaways": _SettingRule("int", 1, 10),
    "max_summary_paragraphs": _SettingRule("int", 1, 10),
    # Scheduler controls.  These do not execute jobs themselves.
    "schedule_times": _SettingRule(
        "times", max_items=24, item_max_length=5, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$"
    ),
    "schedule_timezone": _SettingRule(
        "text", max_length=64, pattern=r"^[A-Za-z0-9_+./-]+$"
    ),
    "scheduler_enabled": _SettingRule("bool"),
    # Relevance controls exposed by the admin settings page.
    "tfidf_preference_weight": _SettingRule("float", 0, 5),
    "category_preference_weight": _SettingRule("float", 0, 5),
    "source_preference_weight": _SettingRule("float", 0, 5),
    "implicit_signal_weight": _SettingRule("float", 0, 1),
    "embedding_preference_weight": _SettingRule("float", 0, 5),
    "topic_score_weight": _SettingRule("float", 0, 5),
    "llm_rerank_blend": _SettingRule("float", 0, 1),
    "semantic_dedup_threshold": _SettingRule("float", 0.5, 1),
    "category_exclude_threshold": _SettingRule("float", -5, 0),
    "category_demote_threshold": _SettingRule("float", -5, 0),
    "rating_decay_half_life_days": _SettingRule("int", 1, 3_650),
    "min_ratings_for_learning": _SettingRule("int", 1, 1_000),
    "llm_rerank_top_k": _SettingRule("int", 1, 200),
    "category_demote_cap": _SettingRule("int", 0, 50),
    "category_min_ratings": _SettingRule("int", 1, 1_000),
    "llm_rerank_enabled": _SettingRule("bool"),
    "semantic_dedup_enabled": _SettingRule("bool"),
    "embedding_provider": _SettingRule("text", max_length=64),
    "embedding_model": _SettingRule("text", max_length=300),
    "llm_rerank_model": _SettingRule("text", max_length=300),
    # YouTube transcription is a non-secret processing preference.
    "youtube_transcription_enabled": _SettingRule("bool"),
    "youtube_transcription_model": _SettingRule("text", max_length=300),
    "youtube_transcription_max_duration": _SettingRule("int", 60, 7_200),
}

_ENUMS = {
    "reasoning_effort": {"none", "minimal", "low", "medium", "high", "xhigh"},
}

# Values used only when a fresh configuration has not persisted an override.
_CONFIG_PATHS: dict[str, tuple[str, ...]] = {
    "model": ("model",),
    "llm_provider": ("llm", "provider"),
    "openrouter_model": ("llm", "openrouter_model"),
    "openrouter_pick_cheapest": ("llm", "openrouter_pick_cheapest"),
    "reasoning_effort": ("llm", "reasoning_effort"),
    "thinking_enabled": ("llm", "thinking_enabled"),
    "thinking_budget_tokens": ("llm", "thinking_budget_tokens"),
    "openrouter_daily_budget_usd": ("llm", "openrouter_daily_budget_usd"),
    "openrouter_monthly_budget_usd": ("llm", "openrouter_monthly_budget_usd"),
    "max_articles_per_digest": ("max_articles_per_digest",),
    "digest_history_limit": ("digest_history_limit",),
    "balance_digest_categories": ("balance_digest_categories",),
    "max_articles_per_category": ("max_articles_per_category",),
    "max_article_age_hours": ("max_article_age_hours",),
    "digest_language": ("digest_language",),
    "preferred_languages": ("preferred_languages",),
    "exclude_keywords": ("exclude_keywords",),
    "max_key_takeaways": ("max_key_takeaways",),
    "max_summary_paragraphs": ("max_summary_paragraphs",),
    "schedule_times": ("schedule", "times"),
    "schedule_timezone": ("schedule", "timezone"),
    "tfidf_preference_weight": ("relevance", "tfidf_preference_weight"),
    "category_preference_weight": ("relevance", "category_preference_weight"),
    "source_preference_weight": ("relevance", "source_preference_weight"),
    "implicit_signal_weight": ("relevance", "implicit_signal_weight"),
    "embedding_preference_weight": ("relevance", "embedding_preference_weight"),
    "topic_score_weight": ("relevance", "topic_score_weight"),
    "llm_rerank_blend": ("relevance", "llm_rerank_blend"),
    "semantic_dedup_threshold": ("relevance", "semantic_dedup_threshold"),
    "category_exclude_threshold": ("relevance", "category_exclude_threshold"),
    "category_demote_threshold": ("relevance", "category_demote_threshold"),
    "rating_decay_half_life_days": ("relevance", "rating_decay_half_life_days"),
    "min_ratings_for_learning": ("relevance", "min_ratings_for_learning"),
    "llm_rerank_top_k": ("relevance", "llm_rerank_top_k"),
    "category_demote_cap": ("relevance", "category_demote_cap"),
    "category_min_ratings": ("relevance", "category_min_ratings"),
    "llm_rerank_enabled": ("relevance", "llm_rerank_enabled"),
    "semantic_dedup_enabled": ("relevance", "semantic_dedup_enabled"),
    "embedding_provider": ("relevance", "embedding_provider"),
    "embedding_model": ("relevance", "embedding_model"),
    "llm_rerank_model": ("relevance", "llm_rerank_model"),
    "youtube_transcription_enabled": ("youtube_transcription", "enabled"),
    "youtube_transcription_model": ("youtube_transcription", "model"),
    "youtube_transcription_max_duration": (
        "youtube_transcription",
        "max_duration_seconds",
    ),
}


def _normalize_value(key: str, value: Any) -> str:
    rule = _SAFE_RULES[key]
    if rule.kind == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"{key} must be a boolean")
        return "1" if value else "0"
    if rule.kind in {"int", "float"}:
        if isinstance(value, bool):
            raise ValueError(f"{key} must be numeric")
        try:
            number = float(value) if rule.kind == "float" else int(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{key} must be numeric") from exc
        if isinstance(number, float) and not math.isfinite(number):
            raise ValueError(f"{key} must be finite")
        if rule.kind == "int" and isinstance(value, float) and not value.is_integer():
            raise ValueError(f"{key} must be an integer")
        if rule.minimum is not None and number < rule.minimum:
            raise ValueError(f"{key} is below its minimum")
        if rule.maximum is not None and number > rule.maximum:
            raise ValueError(f"{key} is above its maximum")
        return str(int(number) if rule.kind == "int" else number)
    if rule.kind in {"text", "enum"}:
        if not isinstance(value, str):
            raise ValueError(f"{key} must be text")
        text = value.strip()
        if not text or len(text) > rule.max_length:
            raise ValueError(f"{key} is empty or too long")
        if rule.pattern and not re.fullmatch(rule.pattern, text):
            raise ValueError(f"{key} has an invalid format")
        if key in _ENUMS and text.casefold() not in _ENUMS[key]:
            raise ValueError(f"{key} is not an allowed value")
        return text.casefold() if key in _ENUMS else text
    if rule.kind in {"list", "times"}:
        if not isinstance(value, (list, tuple)):
            raise ValueError(f"{key} must be a list")
        if not value or len(value) > rule.max_items:
            raise ValueError(f"{key} has an invalid item count")
        normalized: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError(f"{key} items must be text")
            text = item.strip()
            if not text or len(text) > rule.item_max_length:
                raise ValueError(f"{key} contains an invalid item")
            if rule.pattern and not re.fullmatch(rule.pattern, text):
                raise ValueError(f"{key} contains an invalid item")
            normalized.append(text)
        if rule.kind == "times":
            normalized = list(dict.fromkeys(normalized))
        return json.dumps(normalized, ensure_ascii=False)
    raise ValueError(f"unsupported setting: {key}")


def _decode_value(rule: _SettingRule, raw: str) -> Any:
    if rule.kind == "bool":
        return raw == "1"
    if rule.kind == "int":
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
    if rule.kind == "float":
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None
    if rule.kind in {"list", "times"}:
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return None
        return parsed if isinstance(parsed, list) else None
    return raw


def _config_value(config: Any, path: tuple[str, ...]) -> Any:
    current = config
    for part in path:
        if isinstance(current, Mapping):
            current = current.get(part)
        else:
            current = getattr(current, part, None)
        if current is None:
            return None
    return current


class SafeSettingsService:
    """Validate and persist the non-secret settings exposed through MCP."""

    def __init__(self, store: ContentStore, config_path: str | None = None) -> None:
        self.store = store
        self.config_path = config_path

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(_SAFE_RULES)

    def list_settings(self) -> list[dict[str, Any]]:
        return [
            {
                "key": key,
                "kind": rule.kind,
                "minimum": rule.minimum,
                "maximum": rule.maximum,
                "max_items": rule.max_items if rule.kind in {"list", "times"} else None,
            }
            for key, rule in _SAFE_RULES.items()
        ]

    def get_settings(self, keys: list[str] | None = None) -> dict[str, Any]:
        requested = self.keys if keys is None else tuple(keys)
        unknown = [key for key in requested if key not in _SAFE_RULES]
        if unknown:
            raise ValueError(f"unsupported setting: {unknown[0]}")
        try:
            config = apply_db_settings(load_config(self.config_path), self.store)
        except Exception:
            config = None
        values: dict[str, Any] = {}
        for key in requested:
            raw = self.store.get_setting(key, "")
            if raw:
                decoded = _decode_value(_SAFE_RULES[key], raw)
                if decoded is not None:
                    values[key] = decoded
                    continue
            if config is not None:
                values[key] = _config_value(config, _CONFIG_PATHS.get(key, ()))
        return values

    def set_settings(self, changes: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(changes, Mapping) or not changes:
            raise ValueError("settings must be a non-empty object")
        normalized: dict[str, str] = {}
        for key, value in changes.items():
            if not isinstance(key, str) or key not in _SAFE_RULES:
                raise ValueError(f"unsupported setting: {key}")
            normalized[key] = _normalize_value(key, value)
        self._write(normalized)
        if "digest_history_limit" in normalized:
            self.store.prune_digests(int(normalized["digest_history_limit"]))
        return self.get_settings(list(normalized))

    def reset_settings(self, keys: list[str]) -> dict[str, Any]:
        if not isinstance(keys, list) or not keys:
            raise ValueError("keys must be a non-empty list")
        unknown = [key for key in keys if key not in _SAFE_RULES]
        if unknown:
            raise ValueError(f"unsupported setting: {unknown[0]}")
        self._delete(list(dict.fromkeys(keys)))
        return self.get_settings(list(dict.fromkeys(keys)))

    def _write(self, values: Mapping[str, str]) -> None:
        conn = getattr(getattr(self.store, "db", None), "conn", None)
        if conn is None:
            for key, value in values.items():
                self.store.set_setting(key, value)
            return
        savepoint = "elpis_mcp_settings"
        conn.execute(f"SAVEPOINT {savepoint}")
        try:
            for key, value in values.items():
                conn.execute(
                    "INSERT INTO settings(key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, value),
                )
            conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        except Exception:
            conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            raise

    def _delete(self, keys: list[str]) -> None:
        conn = getattr(getattr(self.store, "db", None), "conn", None)
        if conn is None:
            # ContentStore intentionally exposes no delete_setting method; this
            # fallback is only for minimal test doubles.
            return
        savepoint = "elpis_mcp_reset"
        conn.execute(f"SAVEPOINT {savepoint}")
        try:
            conn.executemany(
                "DELETE FROM settings WHERE key = ?",
                ((key,) for key in keys),
            )
            conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        except Exception:
            conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            raise


def _json_result(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def create_mcp_server(
    store: ContentStore,
    config_path: str | None = None,
    *,
    transport_security: TransportSecuritySettings | None = None,
) -> FastMCP:
    """Create the MCP application; authentication is enforced by the caller."""
    settings = SafeSettingsService(store, config_path)
    server = FastMCP(
        name="Elpis",
        instructions=(
            "Use the safe settings tools to inspect or change Elpis preferences. "
            "Secrets, credentials, network policy, and filesystem paths are not "
            "available through this server."
        ),
        mount_path="/",
        streamable_http_path="/",
        json_response=True,
        stateless_http=False,
    )
    if transport_security is not None:
        server.settings.transport_security = transport_security

    @server.tool(description="List the non-secret settings that MCP can change.")
    def list_safe_settings() -> list[dict[str, Any]]:
        return settings.list_settings()

    @server.tool(description="Read effective values for selected safe settings.")
    def get_safe_settings(keys: list[str] | None = None) -> dict[str, Any]:
        return settings.get_settings(keys)

    @server.tool(
        description=(
            "Atomically validate and save one or more non-secret settings. "
            "Unknown keys and invalid ranges are rejected before any write."
        )
    )
    def set_safe_settings(changes: dict[str, Any]) -> dict[str, Any]:
        return settings.set_settings(changes)

    @server.tool(description="Reset selected safe settings to their config defaults.")
    def reset_safe_settings(keys: list[str]) -> dict[str, Any]:
        return settings.reset_settings(keys)

    @server.tool(description="List configured source records without writing them.")
    def list_sources() -> list[dict[str, Any]]:
        return [dict(row) for row in SourceRegistry(store).list_all()]

    @server.tool(description="Read the latest published digest metadata and items.")
    def get_latest_digest() -> dict[str, Any] | None:
        row = store.latest_digest()
        return dict(row) if row else None

    @server.resource(
        "elpis://settings",
        name="Elpis settings",
        description="Effective non-secret Elpis settings.",
        mime_type="application/json",
    )
    def settings_resource() -> str:
        return _json_result(settings.get_settings())

    @server.resource(
        "elpis://sources",
        name="Elpis sources",
        description="Configured source records.",
        mime_type="application/json",
    )
    def sources_resource() -> str:
        return _json_result(list_sources())

    return server


__all__ = ["SafeSettingsService", "create_mcp_server"]
