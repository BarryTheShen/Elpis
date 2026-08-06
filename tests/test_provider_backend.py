"""Tests for the unified provider backend and configuration wiring."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from condenseit.config import AppConfig, LlmConfig, load_config
from condenseit.providers.base import (
    CHAT_SYSTEM_PROMPT,
    build_chat_user_prompt,
)
from condenseit.providers.litellm_provider import LiteLLMSummarizer

# ---------------------------------------------------------------------------
# Shared helpers in base.py
# ---------------------------------------------------------------------------


class TestSharedPromptHelpers:
    def test_chat_system_prompt_is_exported(self) -> None:
        assert isinstance(CHAT_SYSTEM_PROMPT, str)
        assert "JSON" in CHAT_SYSTEM_PROMPT
        assert len(CHAT_SYSTEM_PROMPT) > 20

    def test_build_chat_user_prompt_contains_title_and_content(self) -> None:
        prompt = build_chat_user_prompt("My Title", "Some content here")
        assert "My Title" in prompt
        assert "Some content here" in prompt

    def test_build_chat_user_prompt_default_takeaways(self) -> None:
        prompt = build_chat_user_prompt("T", "C")
        for i in range(1, 6):
            assert f"<takeaway {i}>" in prompt

    def test_build_chat_user_prompt_custom_takeaways(self) -> None:
        prompt = build_chat_user_prompt("T", "C", max_key_takeaways=3)
        assert "<takeaway 3>" in prompt
        assert "<takeaway 4>" not in prompt

    def test_build_chat_user_prompt_paragraph_singular(self) -> None:
        prompt = build_chat_user_prompt("T", "C", max_summary_paragraphs=1)
        assert "1 paragraph" in prompt
        assert "paragraphs" not in prompt

    def test_build_chat_user_prompt_paragraph_plural(self) -> None:
        prompt = build_chat_user_prompt("T", "C", max_summary_paragraphs=3)
        assert "3 paragraphs" in prompt

# ---------------------------------------------------------------------------
# Config: new LlmConfig fields
# ---------------------------------------------------------------------------


class TestLlmConfigDefaults:
    def test_openai_fields_default_empty(self) -> None:
        cfg = LlmConfig()
        assert cfg.openai_base_url == ""
        assert cfg.openai_api_key == ""
        assert cfg.openai_model == ""

    def test_openai_fields_set_from_yaml(self) -> None:
        cfg = LlmConfig(
            openai_base_url="http://localhost:8080/v1",
            openai_model="llama4",
            openai_api_key="sk-x",
        )
        assert cfg.openai_base_url == "http://localhost:8080/v1"
        assert cfg.openai_model == "llama4"
        assert cfg.openai_api_key == "sk-x"


class TestLoadConfigOpenAIEnvOverrides:
    def test_openai_base_url_from_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        cfg_yaml = tmp_path / "cfg.yaml"
        cfg_yaml.write_text("llm:\n  provider: openai\n", encoding="utf-8")
        monkeypatch.setenv("OPENAI_API_BASE_URL", "http://remote:9000/v1")
        cfg = load_config(cfg_yaml)
        assert cfg.llm.openai_base_url == "http://remote:9000/v1"

    def test_openai_api_key_from_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        cfg_yaml = tmp_path / "cfg.yaml"
        cfg_yaml.write_text("llm:\n  provider: openai\n", encoding="utf-8")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
        cfg = load_config(cfg_yaml)
        assert cfg.llm.openai_api_key == "sk-from-env"

    def test_openai_model_from_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        cfg_yaml = tmp_path / "cfg.yaml"
        cfg_yaml.write_text("llm:\n  provider: openai\n", encoding="utf-8")
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
        cfg = load_config(cfg_yaml)
        assert cfg.llm.openai_model == "gpt-4o-mini"

    def test_env_overrides_yaml_value(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        cfg_yaml = tmp_path / "cfg.yaml"
        cfg_yaml.write_text(
            "llm:\n  provider: openai\n  openai_base_url: http://yaml:1111/v1\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("OPENAI_API_BASE_URL", "http://env:2222/v1")
        cfg = load_config(cfg_yaml)
        assert cfg.llm.openai_base_url == "http://env:2222/v1"

    def test_missing_openai_env_vars_leave_defaults(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        cfg_yaml = tmp_path / "cfg.yaml"
        cfg_yaml.write_text("llm:\n  provider: openai\n", encoding="utf-8")
        monkeypatch.delenv("OPENAI_API_BASE_URL", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_MODEL", raising=False)
        cfg = load_config(cfg_yaml)
        assert cfg.llm.openai_base_url == ""
        assert cfg.llm.openai_api_key == ""
        assert cfg.llm.openai_model == ""


# ---------------------------------------------------------------------------
# Factory: build_summarizer returns correct provider
# ---------------------------------------------------------------------------


class TestBuildSummarizerOpenAI:
    def _make_store(self) -> MagicMock:
        store = MagicMock()
        store.get_setting.return_value = ""
        return store

    def _make_config(self, **llm_kwargs: Any) -> AppConfig:
        cfg = AppConfig()
        for k, v in llm_kwargs.items():
            setattr(cfg.llm, k, v)
        return cfg

    def test_returns_openai_summarizer(self) -> None:
        from condenseit.providers.factory import build_summarizer

        cfg = self._make_config(
            provider="openai",
            openai_base_url="http://localhost:1234/v1",
            openai_api_key="sk-x",
            openai_model="my-model",
        )
        with patch("condenseit.providers.factory.SecureKeyStore") as mock_ks:
            mock_ks.return_value.get_key.return_value = ""
            summarizer = build_summarizer(cfg, self._make_store())

        assert isinstance(summarizer, LiteLLMSummarizer)

    def test_openai_summarizer_model_set(self) -> None:
        from condenseit.providers.factory import build_summarizer

        cfg = self._make_config(
            provider="openai",
            openai_base_url="http://localhost:1234/v1",
            openai_api_key="sk-x",
            openai_model="custom-llm",
        )
        with patch("condenseit.providers.factory.SecureKeyStore") as mock_ks:
            mock_ks.return_value.get_key.return_value = ""
            summarizer = build_summarizer(cfg, self._make_store())

        assert summarizer.model_name == "custom-llm"

    def test_openai_summarizer_falls_back_to_top_level_model(self) -> None:
        from condenseit.providers.factory import build_summarizer

        cfg = self._make_config(
            provider="openai",
            openai_base_url="http://localhost:1234/v1",
            openai_api_key="sk-x",
            openai_model="",  # not set
        )
        cfg.model = "fallback-model"
        with patch("condenseit.providers.factory.SecureKeyStore") as mock_ks:
            mock_ks.return_value.get_key.return_value = ""
            summarizer = build_summarizer(cfg, self._make_store())

        assert summarizer.model_name == "fallback-model"

    def test_missing_base_url_raises(self) -> None:
        from condenseit.providers.factory import build_summarizer

        cfg = self._make_config(
            provider="custom",
            openai_base_url="",
            openai_api_key="sk-x",
        )
        with patch("condenseit.providers.factory.SecureKeyStore") as mock_ks:
            mock_ks.return_value.get_key.return_value = ""
            with pytest.raises(ValueError, match="Custom OpenAI-compatible base URL"):
                build_summarizer(cfg, self._make_store())

    def test_api_key_from_secure_store_takes_precedence(self) -> None:
        from condenseit.providers.factory import build_summarizer

        cfg = self._make_config(
            provider="openai",
            openai_base_url="http://localhost:1234/v1",
            openai_api_key="sk-from-config",
        )
        with patch("condenseit.providers.factory.SecureKeyStore") as mock_ks:
            mock_ks.return_value.get_key.return_value = "sk-from-store"
            summarizer = build_summarizer(cfg, self._make_store())

        assert isinstance(summarizer, LiteLLMSummarizer)
        assert summarizer.api_key == "sk-from-store"

    def test_unknown_provider_still_raises(self) -> None:
        from condenseit.providers.factory import build_summarizer

        cfg = self._make_config(provider="nonexistent")
        # Provide a fake OR key so the factory gets past the key check and reaches
        # the "Unknown llm.provider" raise at the end of the function.
        cfg.llm.openrouter_api_key = "fake-or-key"
        with patch("condenseit.providers.factory.SecureKeyStore") as mock_ks:
            mock_ks.return_value.get_key.return_value = ""
            with patch("condenseit.providers.factory.BudgetTracker"):
                with pytest.raises(ValueError, match="Unknown llm.provider"):
                    build_summarizer(cfg, self._make_store())


# ---------------------------------------------------------------------------
# Settings overlay: DB overrides
# ---------------------------------------------------------------------------


class TestSettingsOverlayOpenAI:
    def _make_store(self, settings: dict[str, str]) -> MagicMock:
        store = MagicMock()
        store.get_setting.side_effect = lambda key, default="": settings.get(
            key, default
        )
        return store

    def test_openai_base_url_applied_from_db(self) -> None:
        from condenseit.settings_overlay import apply_db_settings

        cfg = AppConfig()
        store = self._make_store({"openai_base_url": "http://db:5000/v1"})
        result = apply_db_settings(cfg, store)
        assert result.llm.openai_base_url == "http://db:5000/v1"

    def test_openai_model_applied_from_db(self) -> None:
        from condenseit.settings_overlay import apply_db_settings

        cfg = AppConfig()
        store = self._make_store({"openai_model": "db-model"})
        result = apply_db_settings(cfg, store)
        assert result.llm.openai_model == "db-model"

    def test_empty_db_value_does_not_override(self) -> None:
        from condenseit.settings_overlay import apply_db_settings

        cfg = AppConfig()
        cfg.llm.openai_base_url = "http://yaml:1234/v1"
        store = self._make_store({})  # no DB value
        result = apply_db_settings(cfg, store)
        assert result.llm.openai_base_url == "http://yaml:1234/v1"
