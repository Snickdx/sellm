"""Encrypt API keys at rest and produce masked values for the UI."""

from __future__ import annotations

import base64
import hashlib
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

# Client sends this to keep an existing stored key unchanged.
API_KEY_UNCHANGED = "__UNCHANGED__"


def _fernet() -> Fernet:
    raw = (os.getenv("SECRETS_ENCRYPTION_KEY") or "").strip()
    if raw:
        try:
            return Fernet(raw.encode() if isinstance(raw, str) else raw)
        except Exception:
            pass
    # Dev fallback — set SECRETS_ENCRYPTION_KEY in production.
    seed = (os.getenv("CONVERSATION_DB_URL") or "sellm-local-secrets").encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(seed).digest())
    return Fernet(key)


def encrypt_secret(plain: str) -> str:
    text = (plain or "").strip()
    if not text:
        return ""
    return _fernet().encrypt(text.encode()).decode()


def decrypt_secret(stored: str) -> str:
    text = (stored or "").strip()
    if not text:
        return ""
    try:
        return _fernet().decrypt(text.encode()).decode()
    except (InvalidToken, ValueError):
        # Legacy plaintext rows written before encryption was enabled.
        return text


def mask_secret(value: str) -> str:
    """Masked string shown in password fields (not the real secret)."""
    text = (value or "").strip()
    if not text:
        return ""
    if len(text) <= 8:
        return "•" * 12
    return f"{text[:4]}{'•' * min(len(text) - 7, 16)}{text[-3:]}"


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
