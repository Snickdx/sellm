"""Encrypt API keys at rest and produce masked values for the UI."""

from __future__ import annotations

import base64
import hashlib
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

# Client sends this to keep an existing stored key unchanged.
API_KEY_UNCHANGED = "__UNCHANGED__"


def _env_flag(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_production() -> bool:
    env = (os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or os.getenv("SELLM_ENV") or "").strip().lower()
    if env in {"prod", "production"}:
        return True
    if env in {"dev", "development", "local", "test"}:
        return False
    return False


def secrets_encryption_required() -> bool:
    # Fail closed in production, or when explicitly required.
    return _is_production() or _env_flag("REQUIRE_SECRETS_ENCRYPTION_KEY")


def _fernet() -> Fernet:
    raw = (os.getenv("SECRETS_ENCRYPTION_KEY") or "").strip()
    if raw:
        try:
            return Fernet(raw.encode() if isinstance(raw, str) else raw)
        except Exception as exc:
            raise RuntimeError("Invalid SECRETS_ENCRYPTION_KEY") from exc
    if secrets_encryption_required():
        raise RuntimeError(
            "SECRETS_ENCRYPTION_KEY is required in production. "
            "Generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    # Local/dev fallback only when explicitly allowed or not production-like.
    seed = (os.getenv("CONVERSATION_DB_URL") or "sellm-local-secrets").encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(seed).digest())
    return Fernet(key)


def encrypt_secret(plain: str) -> str:
    text = (plain or "").strip()
    if not text:
        return ""
    return _fernet().encrypt(text.encode()).decode()


def decrypt_secret(stored: str, *, allow_plaintext_legacy: bool = False) -> str:
    text = (stored or "").strip()
    if not text:
        return ""
    try:
        return _fernet().decrypt(text.encode()).decode()
    except (InvalidToken, ValueError):
        # One-shot migration path for rows written before encryption.
        if allow_plaintext_legacy or _env_flag("ALLOW_PLAINTEXT_API_KEYS"):
            return text
        if secrets_encryption_required():
            raise RuntimeError("Stored API key is not decryptable with SECRETS_ENCRYPTION_KEY")
        return text


def mask_secret(value: str) -> str:
    """Masked string shown in password fields (not the real secret)."""
    text = (value or "").strip()
    if not text:
        return ""
    if len(text) <= 4:
        return "••••"
    # Reveal only last 4 characters — never the live key prefix.
    return f"{'•' * min(12, max(4, len(text) - 4))}{text[-4:]}"


def is_unchanged_api_key(value: Optional[str]) -> bool:
    if value is None:
        return True
    text = value.strip()
    if not text or text == API_KEY_UNCHANGED:
        return True
    # Masked display copied from GET should not overwrite storage.
    if "•" in text:
        return True
    return False
