"""Encrypted API key storage."""

import os
from datetime import UTC, datetime
from pathlib import Path

from cryptography.fernet import Fernet

from condenseit.config import get_data_dir
from condenseit.store.database import ContentStore

_SECRET_PREFIX = "_secret:"


def _secret_service(name: str) -> str:
    return f"{_SECRET_PREFIX}{name}"


def _secret_preview() -> str:
    return "***"


class SecureKeyStore:
    def __init__(self, store: ContentStore) -> None:
        self.store = store
        self._fernet = self._get_fernet()

    def _key_path(self) -> Path:
        return get_data_dir() / ".encryption.key"

    def _get_fernet(self) -> Fernet:
        path = self._key_path()
        if path.exists():
            key = path.read_bytes()
        else:
            key = Fernet.generate_key()
            path.write_bytes(key)
            path.chmod(0o600)
        return Fernet(key)

    def store_key(self, service: str, key_value: str, key_name: str = "") -> None:
        encrypted = self._fernet.encrypt(key_value.encode()).decode()
        if len(key_value) > 12:
            preview = f"{key_value[:6]}...{key_value[-4:]}"
        else:
            preview = "***"
        self.store.db["api_keys"].upsert(
            {
                "service": service,
                "key_name": key_name or service,
                "encrypted_value": encrypted,
                "key_preview": preview,
                "updated_at": datetime.now(UTC).isoformat(),
            },
            pk="service",
        )

    def store_secret(self, name: str, value: str) -> None:
        """Store a non-UI secret under a private service namespace."""
        self.store_key(_secret_service(name), value, key_name=name)
        self.store.db["api_keys"].update(
            _secret_service(name),
            {"key_preview": _secret_preview()},
        )

    def get_secret(self, name: str) -> str | None:
        """Return a private secret without falling back to an API-key env var."""
        try:
            row = self.store.db["api_keys"].get(_secret_service(name))
            return self._fernet.decrypt(row["encrypted_value"].encode()).decode()
        except Exception:
            return None

    def delete_secret(self, name: str) -> None:
        try:
            self.store.db["api_keys"].delete(_secret_service(name))
        except Exception:
            pass

    def get_key(self, service: str) -> str | None:
        try:
            row = self.store.db["api_keys"].get(service)
            return self._fernet.decrypt(row["encrypted_value"].encode()).decode()
        except Exception:
            return _env_fallback(service)

    def list_keys(self) -> list[dict[str, str]]:
        if "api_keys" not in self.store.db.table_names():
            return []
        return [
            dict(row)
            for row in self.store.db["api_keys"].rows
            if not str(row["service"]).startswith(_SECRET_PREFIX)
        ]

    def delete_key(self, service: str) -> None:
        self.store.db["api_keys"].delete(service)


def _env_fallback(service: str) -> str | None:
    mapping = {
        "openrouter": "OPENROUTER_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "groq": "GROQ_API_KEY",
        "mistral": "MISTRAL_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "together_ai": "TOGETHERAI_API_KEY",
        "custom": "CUSTOM_OPENAI_API_KEY",
    }
    var = mapping.get(service, f"{service.upper()}_API_KEY")
    return os.environ.get(var)
