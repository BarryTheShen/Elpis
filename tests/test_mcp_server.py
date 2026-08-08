from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from condenseit.services.mcp_server import SafeSettingsService, create_mcp_server
from condenseit.store.database import ContentStore
from condenseit.web.app import create_app


def _store(tmp_path) -> ContentStore:
    return ContentStore(tmp_path / "condenseit.db")


def test_safe_settings_validate_before_atomic_write(tmp_path) -> None:
    store = _store(tmp_path)
    service = SafeSettingsService(store)
    try:
        saved = service.set_settings(
            {
                "max_articles_per_digest": 42,
                "balance_digest_categories": True,
            }
        )
        assert saved == {
            "max_articles_per_digest": 42,
            "balance_digest_categories": True,
        }

        with pytest.raises(ValueError, match="unsupported setting"):
            service.set_settings(
                {"max_articles_per_digest": 99, "openrouter_api_key": "secret"}
            )
        assert store.get_setting("max_articles_per_digest") == "42"
        assert store.get_setting("openrouter_api_key") == ""

        with pytest.raises(ValueError):
            service.set_settings({"max_articles_per_digest": 0})
        assert store.get_setting("max_articles_per_digest") == "42"

        service.reset_settings(["max_articles_per_digest"])
        assert store.get_setting("max_articles_per_digest") == ""
    finally:
        store.close()


def test_mcp_server_uses_single_root_http_path(tmp_path) -> None:
    store = _store(tmp_path)
    try:
        server = create_mcp_server(store)
        assert server.settings.streamable_http_path == "/"
        assert server.settings.json_response is True
        assert server.settings.stateless_http is False
    finally:
        store.close()


def test_mcp_http_requires_bearer_and_supports_initialize(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CONDENSEIT_MCP_TOKEN", "test-mcp-token")
    monkeypatch.setenv("CONDENSEIT_MCP_ALLOWED_HOSTS", "testserver")
    app = create_app()
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "1"},
        },
    }
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    with TestClient(app) as client:
        assert client.get("/mcp").status_code == 401
        assert client.post("/mcp/", headers=headers, json=body).status_code == 401

        authorized = {
            **headers,
            "Authorization": "Bearer test-mcp-token",
        }
        response = client.post("/mcp/", headers=authorized, json=body)
        assert response.status_code == 200
        payload = response.json()
        assert payload["result"]["serverInfo"]["name"] == "Elpis"
        assert client.post(
            "/mcp/",
            headers={**authorized, "Host": "evil.example"},
            json=body,
        ).status_code == 421
