"""Shared pytest fixtures for Elpis tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def clear_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use an explicit opt-in for the legacy credential in isolated tests.

    Production startup fails closed when neither an environment nor database
    password is configured. The opt-in keeps existing endpoint fixtures
    deterministic without making the default deployable.
    """
    monkeypatch.setenv("DIGEST_PWA_AUTH_PASSWORD", "")
    monkeypatch.setenv("CONDENSEIT_AUTH_PASSWORD", "")
    monkeypatch.setenv("CONDENSEIT_ALLOW_INSECURE_DEFAULT", "1")
    monkeypatch.setenv("DIGEST_PWA_SESSION_SECRET", "")
