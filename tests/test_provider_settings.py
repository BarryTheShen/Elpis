"""Admin API contract tests for providers and LLM settings."""

from __future__ import annotations

from fastapi.testclient import TestClient

from condenseit.web.app import create_app

_AUTH = {"Authorization": "Bearer elpis"}


def test_providers_api_exposes_catalog_and_custom_endpoint(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(tmp_path / "data"))
    client = TestClient(create_app())

    response = client.get("/api/config/providers", headers=_AUTH)
    assert response.status_code == 200
    payload = response.json()
    provider_ids = {provider["id"] for provider in payload["providers"]}
    assert {
        "openrouter",
        "openai",
        "anthropic",
        "gemini",
        "ollama",
        "custom",
    } <= provider_ids
    assert payload["active_provider"] == "openrouter"

    saved = client.put(
        "/api/config/providers",
        headers=_AUTH,
        json={
            "active_provider": "custom",
            "openrouter_pick_cheapest": False,
            "endpoints": {
                "custom": {"base_url": "http://localhost:8000/v1"},
            },
        },
    )
    assert saved.status_code == 200

    updated = client.get("/api/config/providers", headers=_AUTH).json()
    custom = next(
        provider for provider in updated["providers"] if provider["id"] == "custom"
    )
    assert updated["active_provider"] == "custom"
    assert custom["base_url"] == "http://localhost:8000/v1"


def test_delete_key_rejects_unknown_service(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(tmp_path / "data"))
    client = TestClient(create_app())

    response = client.delete("/api/config/keys/not-a-provider", headers=_AUTH)

    assert response.status_code == 422

def test_custom_provider_requires_endpoint(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(tmp_path / "data"))
    client = TestClient(create_app())

    response = client.put(
        "/api/config/providers",
        headers=_AUTH,
        json={
            "active_provider": "custom",
            "openrouter_pick_cheapest": False,
            "endpoints": {},
        },
    )
    assert response.status_code == 422


def test_llm_api_persists_reasoning_controls_without_endpoint_fields(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(tmp_path / "data"))
    client = TestClient(create_app())

    saved = client.put(
        "/api/config/llm",
        headers=_AUTH,
        json={
            "model": "qwen/qwen3.5-4b",
            "reasoning_effort": "high",
            "thinking_enabled": True,
            "thinking_budget_tokens": 4096,
        },
    )
    assert saved.status_code == 200

    payload = client.get("/api/config/llm", headers=_AUTH).json()
    assert payload == {
        "provider": "openrouter",
        "model": "qwen/qwen3.5-4b",
        "reasoning_effort": "high",
        "thinking_enabled": True,
        "thinking_budget_tokens": 4096,
    }
    assert "openai_base_url" not in payload
    assert "openrouter_model" not in payload
