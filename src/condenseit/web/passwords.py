"""Password hashing and verification for the Elpis admin credential."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 600_000
_SALT_BYTES = 16
_DIGEST_BYTES = 32


def is_password_hash(value: str) -> bool:
    """Return whether ``value`` uses Elpis's encoded password format."""
    return value.startswith(f"{_ALGORITHM}$")


def hash_password(password: str) -> str:
    """Return a salted, iterated password hash suitable for DB storage."""
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _ITERATIONS,
        dklen=_DIGEST_BYTES,
    )
    encode = base64.urlsafe_b64encode
    return (
        f"{_ALGORITHM}${_ITERATIONS}$"
        f"{encode(salt).decode('ascii').rstrip('=')}$"
        f"{encode(digest).decode('ascii').rstrip('=')}"
    )


def verify_password(password: str, stored: str) -> bool:
    """Verify a password hash, accepting legacy plaintext during migration."""
    if not is_password_hash(stored):
        return hmac.compare_digest(password, stored)

    try:
        algorithm, iterations_text, salt_text, digest_text = stored.split("$", 3)
        if algorithm != _ALGORITHM:
            return False
        iterations = int(iterations_text)
        if iterations < 100_000 or iterations > 2_000_000:
            return False
        padding = "=" * (-len(salt_text) % 4)
        salt = base64.urlsafe_b64decode((salt_text + padding).encode("ascii"))
        padding = "=" * (-len(digest_text) % 4)
        expected = base64.urlsafe_b64decode((digest_text + padding).encode("ascii"))
    except (ValueError, TypeError, UnicodeError):
        return False

    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
        dklen=len(expected),
    )
    return hmac.compare_digest(actual, expected)


__all__ = ["hash_password", "is_password_hash", "verify_password"]
