"""Password hashing with argon2id and legacy SHA-256 verify/rehash."""

from __future__ import annotations

import hashlib
import hmac

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerifyMismatchError

_ph = PasswordHasher()
_LEGACY_SHA256_LEN = 64


def hash_password(password: str) -> str:
    return _ph.hash(password or "")


def _legacy_sha256(password: str) -> str:
    return hashlib.sha256((password or "").encode()).hexdigest()


def is_legacy_sha256_hash(stored: str) -> bool:
    text = (stored or "").strip()
    if len(text) != _LEGACY_SHA256_LEN:
        return False
    try:
        int(text, 16)
    except ValueError:
        return False
    return not text.startswith("$")


def verify_password(password: str, stored_hash: str) -> bool:
    stored = (stored_hash or "").strip()
    if not stored:
        return False
    if is_legacy_sha256_hash(stored):
        return hmac.compare_digest(_legacy_sha256(password), stored)
    try:
        return _ph.verify(stored, password or "")
    except (VerifyMismatchError, InvalidHash, ValueError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    stored = (stored_hash or "").strip()
    if not stored:
        return True
    if is_legacy_sha256_hash(stored):
        return True
    try:
        return _ph.check_needs_rehash(stored)
    except Exception:
        return True
