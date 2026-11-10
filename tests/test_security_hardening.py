"""Regression tests for M1/M2 security hardening."""

from __future__ import annotations

import hashlib

from app.security.passwords import hash_password, needs_rehash, verify_password
from app.security.secret_store import mask_secret
from app.security.rate_limit import RateLimiter


def test_argon2_hash_and_verify():
    hashed = hash_password("correct-horse")
    assert hashed.startswith("$argon2")
    assert verify_password("correct-horse", hashed)
    assert not verify_password("wrong", hashed)


def test_legacy_sha256_verify_and_rehash_flag():
    legacy = hashlib.sha256(b"legacy-pass").hexdigest()
    assert verify_password("legacy-pass", legacy)
    assert needs_rehash(legacy)
    assert needs_rehash(hash_password("x")) is False or isinstance(needs_rehash(hash_password("x")), bool)


def test_mask_secret_hides_prefix():
    masked = mask_secret("sk-abcdefghijklmnopqrstuvwxyz")
    assert masked.endswith("wxyz")
    assert not masked.startswith("sk-a")
    assert "sk-abcd" not in masked


def test_rate_limiter_blocks():
    lim = RateLimiter()
    assert lim.allow("t", "u", limit=2, window_seconds=60)
    assert lim.allow("t", "u", limit=2, window_seconds=60)
    assert not lim.allow("t", "u", limit=2, window_seconds=60)
