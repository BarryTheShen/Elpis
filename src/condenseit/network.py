"""Central outbound network policy for proxying and bypass hosts.

The application builds URL-aware sync and async HTTPX transports and exports
the same policy through standard proxy variables for urllib, requests, and
yt-dlp. New outbound HTTPX call sites must use the shared constructors below.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from time import monotonic
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlsplit, urlunsplit

import httpx
import requests

if TYPE_CHECKING:
    from condenseit.store.database import ContentStore

logger = logging.getLogger(__name__)

_PROXY_ENV_NAMES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)
_NO_PROXY_ENV_NAMES = ("CONDENSEIT_NO_PROXY", "NO_PROXY", "no_proxy")
_PROXY_URL_ENV_NAMES = (
    "CONDENSEIT_PROXY_URL",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "ALL_PROXY",
    "https_proxy",
    "http_proxy",
    "all_proxy",
)
_YOUTUBE_PROXY_ENV = "CONDENSEIT_YOUTUBE_PROXY"
_NETWORK_PROXY_SECRET = "proxy_url"
_NETWORK_PROXY_ENABLED = "network_proxy_enabled"
_NETWORK_NO_PROXY = "network_no_proxy"
_DEFAULT_BYPASS_HOSTS = ("localhost", "127.0.0.1", "::1", "host.docker.internal")
_TEST_URL = "https://www.google.com/generate_204"
_PROXY_CREDENTIAL_URL_RE = re.compile(
    r"\b(?P<scheme>https?|socks5h?)://(?P<userinfo>[^/\s@]+)@"
    r"(?P<tail>[^\s\"'<>]+)",
    re.IGNORECASE,
)

ProxySource = Literal["database", "environment", "disabled"]


@dataclass(frozen=True)
class NetworkProxySettings:
    """Resolved proxy settings with no credential-bearing value exposed."""

    proxy_url: str = ""
    bypass_hosts: tuple[str, ...] = _DEFAULT_BYPASS_HOSTS
    source: ProxySource = "disabled"
    youtube_proxy_override: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.proxy_url)

    @property
    def youtube_override_configured(self) -> bool:
        return bool(self.youtube_proxy_override)

    def should_bypass(self, url: str) -> bool:
        """Return whether ``url`` matches one of the configured bypass hosts."""
        try:
            hostname = (urlsplit(url).hostname or "").lower().rstrip(".")
        except ValueError:
            return False
        if not hostname:
            return False
        for raw_pattern in self.bypass_hosts:
            pattern = raw_pattern.strip().lower().rstrip(".")
            if not pattern:
                continue
            if pattern == "*":
                return True
            if pattern.startswith("[") and "]" in pattern:
                pattern = pattern[1 : pattern.index("]")]
            elif pattern.count(":") == 1 and pattern.rsplit(":", 1)[1].isdigit():
                pattern = pattern.rsplit(":", 1)[0]
            else:
                pattern = pattern.lstrip("*.")
            if hostname == pattern or hostname.endswith(f".{pattern}"):
                return True
        return False

    def proxy_for_url(self, url: str, *, youtube: bool = False) -> str | None:
        """Return the proxy for a request, honoring local bypasses."""
        if youtube and self.youtube_proxy_override:
            return self.youtube_proxy_override
        if not self.proxy_url or self.should_bypass(url):
            return None
        return self.proxy_url

    def as_api_payload(self) -> dict[str, object]:
        """Return the safe UI representation; never return proxy credentials."""
        return {
            "enabled": self.enabled,
            "proxy_configured": self.enabled,
            "proxy_url_display": redact_proxy_url(self.proxy_url),
            "proxy_source": self.source,
            "bypass_hosts": list(self.bypass_hosts),
            "youtube_proxy_override": self.youtube_override_configured,
        }


def _environment_proxy() -> str:
    for name in _PROXY_URL_ENV_NAMES:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _environment_no_proxy() -> str:
    for name in _NO_PROXY_ENV_NAMES:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def parse_bypass_hosts(
    raw: str | list[str] | tuple[str, ...] | None,
) -> tuple[str, ...]:
    """Normalize comma/newline-separated NO_PROXY host patterns."""
    if isinstance(raw, str):
        values = re.split(r"[,\n\r]+", raw)
    else:
        values = list(raw or ())
    result: list[str] = []
    seen: set[str] = set()
    for value in [*_DEFAULT_BYPASS_HOSTS, *values]:
        item = str(value).strip()
        if not item:
            continue
        key = item.lower()
        if key not in seen:
            result.append(item)
            seen.add(key)
    return tuple(result)


def validate_proxy_url(raw: str) -> str:
    """Validate and normalize an HTTP(S) or SOCKS5 proxy URL."""
    value = raw.strip()
    if not value:
        raise ValueError("Proxy URL is required when the proxy is enabled.")
    if any(char.isspace() for char in value):
        raise ValueError("Proxy URL must not contain whitespace.")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Proxy URL has an invalid port.") from exc
    if parsed.scheme.lower() not in {"http", "https", "socks5", "socks5h"}:
        raise ValueError(
            "Proxy URL must use http://, https://, socks5://, or socks5h://."
        )
    if (
        not parsed.hostname
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "Proxy URL must contain only a scheme, host, port, and credentials."
        )
    if port is None:
        raise ValueError("Proxy URL must include a port.")
    return value


def redact_proxy_url(value: str) -> str | None:
    """Mask proxy credentials before a URL is returned to the browser/logs."""
    if not value:
        return None
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        if not hostname:
            return "***"
        host = f"[{hostname}]" if ":" in hostname else hostname
        if parsed.port is not None:
            host = f"{host}:{parsed.port}"
        if parsed.username is not None:
            userinfo = "***@"
        else:
            userinfo = ""
        return urlunsplit((parsed.scheme, userinfo + host, "", "", ""))
    except (ValueError, TypeError):
        return "***"


def _stored_proxy_url(store: ContentStore) -> str:
    from condenseit.store.secure_keys import SecureKeyStore

    return SecureKeyStore(store).get_secret(_NETWORK_PROXY_SECRET) or ""


def load_network_proxy(store: ContentStore | None = None) -> NetworkProxySettings:
    """Resolve the persisted policy, falling back to standard env settings."""
    db_enabled = store.get_setting(_NETWORK_PROXY_ENABLED, "") if store else ""
    if db_enabled == "1" and store is not None:
        proxy_url = _stored_proxy_url(store)
        source: ProxySource = "database" if proxy_url else "disabled"
        if not proxy_url:
            logger.warning("Network proxy is enabled but no proxy URL is stored")
    elif db_enabled == "0":
        proxy_url = ""
        source = "disabled"
    else:
        proxy_url = _environment_proxy()
        source = "environment" if proxy_url else "disabled"
    no_proxy = store.get_setting(_NETWORK_NO_PROXY, "") if store else ""
    bypass_hosts = parse_bypass_hosts(no_proxy or _environment_no_proxy())
    raw_youtube_override = os.environ.get(_YOUTUBE_PROXY_ENV, "").strip()
    youtube_override = ""
    if raw_youtube_override:
        try:
            youtube_override = validate_proxy_url(raw_youtube_override)
        except ValueError:
            logger.warning("Ignoring invalid %s value", _YOUTUBE_PROXY_ENV)
    return NetworkProxySettings(
        proxy_url=proxy_url,
        bypass_hosts=bypass_hosts,
        source=source,
        youtube_proxy_override=youtube_override,
    )


def configure_network_proxy(store: ContentStore) -> NetworkProxySettings:
    """Apply the resolved policy to the current process and return it.

    Lower- and upper-case variables are both set because different libraries
    prefer different spellings. A saved disabled policy removes inherited proxy
    variables rather than silently using a host-level proxy.
    """
    settings = load_network_proxy(store)
    proxy = settings.proxy_url
    for name in _PROXY_ENV_NAMES:
        if proxy:
            os.environ[name] = proxy
        else:
            os.environ.pop(name, None)
    no_proxy = ",".join(settings.bypass_hosts)
    for name in _NO_PROXY_ENV_NAMES:
        os.environ[name] = no_proxy
    if settings.source == "database":
        os.environ["CONDENSEIT_PROXY_URL"] = proxy
    elif settings.source == "disabled":
        os.environ.pop("CONDENSEIT_PROXY_URL", None)
    return settings


def save_network_proxy(
    store: ContentStore,
    *,
    enabled: bool,
    proxy_url: str,
    bypass_hosts: str | list[str] | tuple[str, ...] | None,
) -> NetworkProxySettings:
    """Persist and immediately apply the admin network policy."""
    from condenseit.store.secure_keys import SecureKeyStore

    keys = SecureKeyStore(store)
    current = load_network_proxy(store)
    if enabled:
        candidate = proxy_url.strip() or current.proxy_url
        candidate = validate_proxy_url(candidate)
        keys.store_secret(_NETWORK_PROXY_SECRET, candidate)
        store.set_setting(_NETWORK_PROXY_ENABLED, "1")
    else:
        keys.delete_secret(_NETWORK_PROXY_SECRET)
        store.set_setting(_NETWORK_PROXY_ENABLED, "0")
    normalized_bypass = parse_bypass_hosts(bypass_hosts)
    store.set_setting(_NETWORK_NO_PROXY, ",".join(normalized_bypass))
    return configure_network_proxy(store)


def network_subprocess_env(
    settings: NetworkProxySettings | None = None,
    *,
    youtube: bool = False,
) -> dict[str, str]:
    """Return a minimal yt-dlp environment with proxy policy applied.

    Do not inherit the application's complete environment: it contains LLM
    API keys and other credentials that an outbound helper must never receive.
    """
    resolved = settings or load_network_proxy()
    proxy = (
        resolved.youtube_proxy_override
        if youtube and resolved.youtube_proxy_override
        else resolved.proxy_url
    )
    allowed = (
        "PATH",
        "HOME",
        "TMPDIR",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "XDG_CACHE_HOME",
    )
    env = {
        name: value
        for name in allowed
        if (value := os.environ.get(name))
    }
    for name in _PROXY_ENV_NAMES:
        if proxy:
            env[name] = proxy
    if youtube and resolved.youtube_proxy_override:
        for name in _NO_PROXY_ENV_NAMES:
            env[name] = ""
    else:
        bypass = ",".join(resolved.bypass_hosts)
        for name in _NO_PROXY_ENV_NAMES:
            env[name] = bypass
    return env


class _PolicySession(requests.Session):
    """requests session that applies the current proxy to each URL."""

    def __init__(self, settings: NetworkProxySettings, *, youtube: bool) -> None:
        super().__init__()
        self._network_settings = settings
        self._youtube = youtube
        self.trust_env = False

    def send(self, request, **kwargs):  # type: ignore[no-untyped-def]
        proxy = self._network_settings.proxy_for_url(
            request.url,
            youtube=self._youtube,
        )
        kwargs["proxies"] = {"http": proxy, "https": proxy} if proxy else {}
        return super().send(request, **kwargs)


def requests_session(
    settings: NetworkProxySettings | None = None,
    *,
    youtube: bool = False,
) -> requests.Session:
    """Build a requests session for YouTubeTranscriptApi and similar clients."""
    return _PolicySession(settings or load_network_proxy(), youtube=youtube)


def _httpx_bypass_pattern(raw_pattern: str) -> str | None:
    """Convert a NO_PROXY host pattern into an HTTPX mount pattern."""
    pattern = raw_pattern.strip().lower().rstrip(".")
    if not pattern or pattern == "*":
        return None
    if pattern.startswith("[") and "]" in pattern:
        host = pattern
    elif pattern.count(":") > 1:
        host = f"[{pattern}]"
    else:
        host = pattern
    if host.startswith("[") or re.fullmatch(r"\d+(?:\.\d+){3}(?::\d+)?", host):
        return f"all://{host}"
    port = ""
    host_without_port = host
    if host.count(":") == 1:
        host_without_port, port = host.rsplit(":", 1)
        port = f":{port}"
    host_without_port = host_without_port.removeprefix("*.")
    host_without_port = host_without_port.removeprefix(".")
    if "." in host_without_port:
        return f"all://*{host_without_port}{port}"
    return f"all://{host_without_port}{port}"


def _httpx_mounts(
    settings: NetworkProxySettings,
    *,
    youtube: bool,
    async_client: bool,
) -> dict[str, Any]:
    """Build per-host proxy/direct transports for one HTTPX client."""
    proxy = (
        settings.youtube_proxy_override
        if youtube and settings.youtube_proxy_override
        else settings.proxy_url
    )
    if not proxy:
        return {}
    transport_type = httpx.AsyncHTTPTransport if async_client else httpx.HTTPTransport
    youtube_override = bool(youtube and settings.youtube_proxy_override)
    if not youtube_override and any(
        raw_pattern.strip() == "*" for raw_pattern in settings.bypass_hosts
    ):
        return {"all://": transport_type(trust_env=False)}
    mounts: dict[str, Any] = {
        "all://": transport_type(proxy=proxy, trust_env=False),
    }
    if not youtube_override:
        for raw_pattern in settings.bypass_hosts:
            pattern = _httpx_bypass_pattern(raw_pattern)
            if pattern:
                mounts[pattern] = transport_type(trust_env=False)
    return mounts


def httpx_client(
    *args: object,
    settings: NetworkProxySettings | None = None,
    youtube: bool = False,
    **kwargs: object,
) -> httpx.Client:
    """Create an HTTPX client with URL-aware proxy and bypass routing."""
    resolved = settings or load_network_proxy()
    kwargs["trust_env"] = False
    mounts = _httpx_mounts(resolved, youtube=youtube, async_client=False)
    if mounts:
        kwargs["mounts"] = mounts
    return httpx.Client(*args, **kwargs)


def async_httpx_client(
    *args: object,
    settings: NetworkProxySettings | None = None,
    youtube: bool = False,
    **kwargs: object,
) -> httpx.AsyncClient:
    """Create an async HTTPX client with URL-aware proxy routing."""
    resolved = settings or load_network_proxy()
    kwargs["trust_env"] = False
    mounts = _httpx_mounts(resolved, youtube=youtube, async_client=True)
    if mounts:
        kwargs["mounts"] = mounts
    return httpx.AsyncClient(*args, **kwargs)


def test_network_connection(
    settings: NetworkProxySettings,
    *,
    target_url: str = _TEST_URL,
) -> dict[str, object]:
    """Test one external endpoint with an isolated client and no env lookup."""
    proxy = settings.proxy_for_url(target_url)
    started = monotonic()
    with httpx_client(
        settings=settings,
        follow_redirects=False,
        timeout=10.0,
    ) as client:
        response = client.get(target_url)
        response.raise_for_status()
    return {
        "status_code": response.status_code,
        "elapsed_ms": round((monotonic() - started) * 1000),
        "proxy_used": bool(proxy),
        "target": target_url,
    }


def sanitize_network_text(text: str, settings: NetworkProxySettings) -> str:
    """Remove credential-bearing proxy URLs from third-party text."""

    def redact_match(match: re.Match[str]) -> str:
        return f"{match.group('scheme')}://***@{match.group('tail')}"

    message = _PROXY_CREDENTIAL_URL_RE.sub(redact_match, str(text))
    proxy_values = (
        settings.proxy_url,
        settings.youtube_proxy_override,
        os.environ.get(_YOUTUBE_PROXY_ENV, "").strip(),
    )
    for proxy_url in proxy_values:
        if proxy_url:
            message = message.replace(proxy_url, redact_proxy_url(proxy_url) or "***")
    return message


def safe_network_error(exc: Exception, settings: NetworkProxySettings) -> str:
    """Remove credential-bearing proxy URLs from an exception string."""
    return sanitize_network_text(str(exc), settings)


__all__ = [
    "NetworkProxySettings",
    "async_httpx_client",
    "httpx_client",
    "configure_network_proxy",
    "load_network_proxy",
    "network_subprocess_env",
    "parse_bypass_hosts",
    "redact_proxy_url",
    "sanitize_network_text",
    "requests_session",
    "safe_network_error",
    "save_network_proxy",
    "test_network_connection",
    "validate_proxy_url",
]
