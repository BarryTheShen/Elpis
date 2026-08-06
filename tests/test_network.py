"""Network proxy policy and transport coverage."""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.request import urlopen

import httpx
import pytest
from fastapi.testclient import TestClient

from condenseit.collectors.health import collect_with_health
from condenseit.collectors.rss import RSSCollector
from condenseit.network import (
    NetworkProxySettings,
    async_httpx_client,
    httpx_client,
    load_network_proxy,
    network_subprocess_env,
    parse_bypass_hosts,
    redact_proxy_url,
    requests_session,
    sanitize_network_text,
    save_network_proxy,
)
from condenseit.network import (
    test_network_connection as run_network_connection,
)
from condenseit.store.database import ContentStore
from condenseit.store.secure_keys import SecureKeyStore
from condenseit.web.app import create_app


class _ProxyHandler(BaseHTTPRequestHandler):
    paths: list[str] = []

    def do_GET(self) -> None:  # noqa: N802
        self.__class__.paths.append(self.path)
        self.send_response(204)
        self.end_headers()

    def log_message(self, *_args: object) -> None:
        return


class _DirectHandler(BaseHTTPRequestHandler):
    paths: list[str] = []

    def do_GET(self) -> None:  # noqa: N802
        self.__class__.paths.append(self.path)
        self.send_response(200)
        self.end_headers()

    def log_message(self, *_args: object) -> None:
        return


@pytest.fixture
def local_target() -> ThreadingHTTPServer:
    _DirectHandler.paths = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _DirectHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def local_proxy() -> tuple[ThreadingHTTPServer, str]:
    _ProxyHandler.paths = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ProxyHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class _SocksProxy:
    def __init__(self) -> None:
        self.targets: list[tuple[str, int]] = []
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind(("127.0.0.1", 0))
        self._socket.listen()
        self._socket.settimeout(0.2)
        self.port = self._socket.getsockname()[1]
        self._stopping = False
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _recv_exact(self, conn: socket.socket, size: int) -> bytes:
        data = b""
        while len(data) < size:
            chunk = conn.recv(size - len(data))
            if not chunk:
                raise ConnectionError("SOCKS client disconnected")
            data += chunk
        return data

    def _handle(self, conn: socket.socket) -> None:
        with conn:
            version, method_count = self._recv_exact(conn, 2)
            assert version == 5
            self._recv_exact(conn, method_count)
            conn.sendall(b"\x05\x00")
            version, command, _reserved, address_type = self._recv_exact(conn, 4)
            assert version == 5 and command == 1
            if address_type == 1:
                host = socket.inet_ntoa(self._recv_exact(conn, 4))
            elif address_type == 3:
                length = self._recv_exact(conn, 1)[0]
                host = self._recv_exact(conn, length).decode()
            elif address_type == 4:
                host = socket.inet_ntop(socket.AF_INET6, self._recv_exact(conn, 16))
            else:
                raise ValueError(f"Unsupported SOCKS address type: {address_type}")
            port = int.from_bytes(self._recv_exact(conn, 2), "big")
            self.targets.append((host, port))
            conn.sendall(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
            request = b""
            while b"\r\n\r\n" not in request:
                request += conn.recv(4096)
            conn.sendall(b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\n\r\n")

    def _serve(self) -> None:
        while not self._stopping:
            try:
                conn, _address = self._socket.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def close(self) -> None:
        self._stopping = True
        self._socket.close()
        self._thread.join(timeout=2)


@pytest.fixture
def socks_proxy() -> _SocksProxy:
    server = _SocksProxy()
    try:
        yield server
    finally:
        server.close()


def test_default_bypass_includes_ipv6_and_docker_host() -> None:
    settings = NetworkProxySettings(proxy_url="http://proxy.example:8080")

    assert settings.proxy_for_url("http://[::1]/api") is None
    assert settings.proxy_for_url("http://host.docker.internal:11434/api/tags") is None
    assert settings.proxy_for_url("https://outside.example/article") == (
        "http://proxy.example:8080"
    )


def test_httpx_client_routes_proxy_and_bypass_hosts(
    local_proxy,
    local_target,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _proxy_server, proxy = local_proxy
    settings = NetworkProxySettings(
        proxy_url=proxy,
        bypass_hosts=("www.google.com", "example.com", "localhost", "127.0.0.1"),
    )
    real_getaddrinfo = socket.getaddrinfo

    def resolve_test_domains(host, port, *args, **kwargs):
        if host in {"example.com", "api.example.com"}:
            host = "127.0.0.1"
        return real_getaddrinfo(host, port, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", resolve_test_domains)
    monkeypatch.setenv("HTTP_PROXY", proxy)
    monkeypatch.setenv("HTTPS_PROXY", proxy)
    port = local_target.server_port
    with httpx_client(settings=settings) as client:
        proxied = client.get("http://outside.test/proxy")
        apex = client.get(f"http://example.com:{port}/apex")
        subdomain = client.get(f"http://api.example.com:{port}/subdomain")

    assert proxied.status_code == 204
    assert apex.status_code == 200
    assert subdomain.status_code == 200
    assert _ProxyHandler.paths == ["http://outside.test/proxy"]
    assert _DirectHandler.paths == ["/apex", "/subdomain"]


def test_async_httpx_client_routes_proxy_and_bypass_hosts(
    local_proxy,
    local_target,
) -> None:
    _proxy_server, proxy = local_proxy
    settings = NetworkProxySettings(
        proxy_url=proxy,
        bypass_hosts=("localhost", "127.0.0.1"),
    )
    port = local_target.server_port

    async def fetch() -> tuple[int, int]:
        async with async_httpx_client(settings=settings) as client:
            proxied = await client.get("http://outside.test/async-proxy")
            direct = await client.get(f"http://127.0.0.1:{port}/async-direct")
            return proxied.status_code, direct.status_code

    proxied_status, direct_status = asyncio.run(fetch())
    assert proxied_status == 204
    assert direct_status == 200
    assert _ProxyHandler.paths == ["http://outside.test/async-proxy"]
    assert _DirectHandler.paths == ["/async-direct"]


def test_httpx_requests_and_urllib_use_proxy(local_proxy, monkeypatch) -> None:
    server, proxy = local_proxy
    settings = NetworkProxySettings(proxy_url=proxy, bypass_hosts=())

    result = run_network_connection(settings, target_url="http://example.test/ping")
    assert result["status_code"] == 204
    assert result["proxy_used"] is True
    assert _ProxyHandler.paths[-1] == "http://example.test/ping"

    session = requests_session(settings, youtube=True)
    response = session.get("http://example.test/transcript", timeout=5)
    assert response.status_code == 204
    assert _ProxyHandler.paths[-1] == "http://example.test/transcript"
    session.close()

    monkeypatch.setenv("HTTP_PROXY", proxy)
    monkeypatch.setenv("http_proxy", proxy)
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1,::1")
    monkeypatch.setenv("no_proxy", "localhost,127.0.0.1,::1")
    with urlopen("http://example.test/rss", timeout=5) as response:
        assert response.status == 204
    assert _ProxyHandler.paths[-1] == "http://example.test/rss"
    assert server.server_port > 0


def test_socks_transport_and_rss_fallback(
    socks_proxy: _SocksProxy,
    monkeypatch,
) -> None:
    proxy = f"socks5h://127.0.0.1:{socks_proxy.port}"
    settings = NetworkProxySettings(proxy_url=proxy, bypass_hosts=())

    result = run_network_connection(settings, target_url="http://example.test/ping")
    assert result["status_code"] == 204
    assert socks_proxy.targets[-1] == ("example.test", 80)

    session = requests_session(settings, youtube=True)
    response = session.get("http://example.test/transcript", timeout=5)
    assert response.status_code == 204
    session.close()

    for name in (
        "CONDENSEIT_PROXY_URL",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "CONDENSEIT_NO_PROXY",
        "NO_PROXY",
        "no_proxy",
    ):
        monkeypatch.setenv(name, proxy if "PROXY" in name else "")
    collector = RSSCollector([])
    request = httpx.Request("GET", "http://example.test/rss")
    response = httpx.Response(403, request=request)
    original_exc = httpx.HTTPStatusError(
        "forbidden",
        request=request,
        response=response,
    )
    feed_text = collector._fetch_feed_text_with_urllib(
        "http://example.test/rss",
        original_exc,
    )
    assert feed_text == ""
    assert socks_proxy.targets[-1] == ("example.test", 80)


def test_subprocess_environment_routes_proxy(local_proxy) -> None:
    _server, proxy = local_proxy
    settings = NetworkProxySettings(
        proxy_url=proxy,
        bypass_hosts=parse_bypass_hosts("internal.example"),
    )
    env = network_subprocess_env(settings, youtube=True)

    assert env["HTTP_PROXY"] == proxy
    assert env["HTTPS_PROXY"] == proxy
    assert "internal.example" in env["NO_PROXY"]
    result = subprocess.run(
        [sys.executable, "-c", "import os; print(os.environ['HTTPS_PROXY'])"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == proxy


def test_youtube_proxy_override_clears_subprocess_bypass() -> None:
    settings = NetworkProxySettings(
        proxy_url="http://global-proxy.example:8080",
        youtube_proxy_override="http://youtube-proxy.example:8080",
        bypass_hosts=("youtube.com",),
    )
    env = network_subprocess_env(settings, youtube=True)

    assert env["HTTPS_PROXY"] == settings.youtube_proxy_override
    assert env["NO_PROXY"] == ""
    assert env["no_proxy"] == ""
    assert env["CONDENSEIT_NO_PROXY"] == ""


def test_saved_proxy_routes_new_rss_client(
    local_proxy,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    for name in (
        "CONDENSEIT_PROXY_URL",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "CONDENSEIT_NO_PROXY",
        "NO_PROXY",
        "no_proxy",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(tmp_path / "data"))
    _server, proxy = local_proxy
    store = ContentStore(db_path=tmp_path / "proxy.db")
    collector: RSSCollector | None = None
    try:
        save_network_proxy(
            store,
            enabled=True,
            proxy_url=proxy,
            bypass_hosts="",
        )
        collector = RSSCollector([])
        response = collector.client.get("http://outside.test/after-save")
        assert response.status_code == 204
        assert _ProxyHandler.paths == ["http://outside.test/after-save"]
    finally:
        if collector is not None:
            collector.client.close()
        store.close()


def test_database_proxy_overrides_custom_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_proxy = "http://env-user:env-password@env.example:8080"
    db_proxy = "http://db-user:db-password@db.example:8080"
    for name in (
        "CONDENSEIT_PROXY_URL",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "CONDENSEIT_NO_PROXY",
        "NO_PROXY",
        "no_proxy",
    ):
        monkeypatch.setenv(name, env_proxy if "PROXY" in name else "")
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(tmp_path / "data"))

    store = ContentStore(db_path=tmp_path / "proxy.db")
    try:
        settings = save_network_proxy(
            store,
            enabled=True,
            proxy_url=db_proxy,
            bypass_hosts="example.internal",
        )
        assert settings.source == "database"
        assert settings.proxy_url == db_proxy
        assert os.environ["CONDENSEIT_PROXY_URL"] == db_proxy
        assert load_network_proxy().proxy_url == db_proxy
        assert redact_proxy_url(db_proxy) == "http://***@db.example:8080"
        rows = list(store.db["api_keys"].rows)
        secret_row = next(row for row in rows if row["service"] == "_secret:proxy_url")
        assert secret_row["encrypted_value"] != db_proxy
        assert secret_row["key_preview"] == "***"
        assert all(
            not row["service"].startswith("_secret:")
            for row in SecureKeyStore(store).list_keys()
        )

        disabled = save_network_proxy(
            store,
            enabled=False,
            proxy_url="",
            bypass_hosts="",
        )
        assert disabled.enabled is False
        assert "CONDENSEIT_PROXY_URL" not in os.environ
    finally:
        store.close()


def test_proxy_credentials_are_removed_from_third_party_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = NetworkProxySettings(
        proxy_url="http://user:secret-password@proxy.example:8080",
        youtube_proxy_override="http://yt:youtube-secret@yt-proxy.example:8080",
    )
    monkeypatch.setenv(
        "CONDENSEIT_YOUTUBE_PROXY",
        "http://bad:other-secret@invalid.example:8080/path?query=1",
    )
    message = sanitize_network_text(
        "yt-dlp failed using http://user:secret-password@proxy.example:8080 "
        "and http://yt:youtube-secret@yt-proxy.example:8080 "
        "and http://bad:other-secret@invalid.example:8080/path?query=1",
        settings,
    )
    assert "secret-password" not in message
    assert "youtube-secret" not in message
    assert "other-secret" not in message
    assert redact_proxy_url("http://bearer-token@proxy.example:8080") == (
        "http://***@proxy.example:8080"
    )
    generic = sanitize_network_text(
        "error at https://old-user:old-secret@old-proxy.example:8080/path",
        NetworkProxySettings(),
    )
    assert "old-secret" not in generic


def test_collect_with_health_scrubs_proxy_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proxy = "http://health-user:health-secret@proxy.example:8080"
    monkeypatch.setenv("CONDENSEIT_PROXY_URL", proxy)

    def fail_collection() -> list[object]:
        raise RuntimeError(f"feed failed via {proxy}")

    items, health = collect_with_health(
        "https://example.test/feed",
        fail_collection,
        log_label="feed",
    )
    assert items == []
    assert health[0][1] is not None
    assert "health-secret" not in health[0][1]


def test_network_api_tests_candidate_and_masks_saved_proxy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    for name in (
        "CONDENSEIT_PROXY_URL",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "CONDENSEIT_NO_PROXY",
        "NO_PROXY",
        "no_proxy",
    ):
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(tmp_path / "data"))

    from condenseit.web.admin import routes as admin_routes

    captured: dict[str, NetworkProxySettings] = {}

    def fake_test(settings: NetworkProxySettings) -> dict[str, object]:
        captured["settings"] = settings
        return {
            "status_code": 204,
            "elapsed_ms": 1,
            "proxy_used": bool(settings.proxy_url),
            "target": "http://test.invalid",
        }

    monkeypatch.setattr(admin_routes, "test_network_connection", fake_test)
    candidate = "http://candidate:secret@proxy.example:8080"
    app = create_app()
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer elpis"}
        tested = client.post(
            "/api/config/network/test",
            headers=headers,
            json={
                "enabled": True,
                "proxy_url": candidate,
                "bypass_hosts": "internal.example",
            },
        )
        assert tested.status_code == 200
        assert captured["settings"].proxy_url == candidate
        assert "secret" not in tested.text
        after_test = client.get("/api/config/network", headers=headers).json()
        assert after_test["enabled"] is False

        saved = client.put(
            "/api/config/network",
            headers=headers,
            json={
                "enabled": True,
                "proxy_url": candidate,
                "bypass_hosts": "internal.example",
            },
        )
        assert saved.status_code == 200
        assert saved.json()["proxy_url_display"] == ("http://***@proxy.example:8080")
        assert "secret" not in saved.text
        after_save = client.get("/api/config/network", headers=headers).json()
        assert after_save["proxy_source"] == "database"

    app.state.store.close()


def test_youtube_resolver_redacts_proxy_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    youtube_proxy = "http://yt-user:yt-secret@youtube-proxy.example:8080"
    monkeypatch.setenv("CONDENSEIT_YOUTUBE_PROXY", youtube_proxy)
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/yt-dlp")
    spawned: dict[str, object] = {}

    def failed_yt_dlp(*_args: object, **kwargs: object) -> SimpleNamespace:
        spawned["env"] = kwargs.get("env")
        return SimpleNamespace(
            returncode=1,
            stdout="",
            stderr=f"unable to connect through {youtube_proxy}",
        )

    monkeypatch.setattr(subprocess, "run", failed_yt_dlp)
    app = create_app()
    with TestClient(app) as client:
        response = client.get(
            "/api/sources/youtube/resolve",
            params={"handle": "@example"},
            headers={"Authorization": "Bearer elpis"},
        )
    assert response.status_code == 422
    assert "yt-secret" not in response.text
    assert "***" in response.text
    child_env = spawned["env"]
    assert isinstance(child_env, dict)
    assert child_env["HTTPS_PROXY"] == youtube_proxy
    app.state.store.close()
