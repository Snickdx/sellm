"""Mint LiveKit-compatible participant JWTs (no LiveKit SDK required)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from jose import jwt

from app.settings import Settings


def mint_livekit_token(
    *,
    settings: Settings,
    identity: str,
    name: str,
    room_name: str,
    can_publish: bool = True,
    can_subscribe: bool = True,
) -> str:
    if not settings.livekit_configured:
        raise RuntimeError("LiveKit is not configured")
    assert settings.livekit_api_key and settings.livekit_api_secret
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=settings.voice_token_ttl_minutes)
    claims: dict[str, Any] = {
        "iss": settings.livekit_api_key,
        "sub": identity,
        "name": name,
        "nbf": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "video": {
            "roomJoin": True,
            "room": room_name,
            "canPublish": can_publish,
            "canSubscribe": can_subscribe,
            "canPublishData": False,
        },
    }
    return jwt.encode(claims, settings.livekit_api_secret, algorithm="HS256")


def mint_livekit_api_token(*, settings: Settings, ttl_seconds: int = 600) -> str:
    """Server API JWT for egress / room admin calls."""
    if not settings.livekit_configured:
        raise RuntimeError("LiveKit is not configured")
    assert settings.livekit_api_key and settings.livekit_api_secret
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "iss": settings.livekit_api_key,
        "nbf": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
        "video": {
            "roomCreate": True,
            "roomList": True,
            "roomRecord": True,
            "roomAdmin": True,
        },
    }
    return jwt.encode(claims, settings.livekit_api_secret, algorithm="HS256")


def room_name_for_session(session_id: str) -> str:
    return f"exit-{session_id}"


def livekit_http_base(settings: Settings) -> str:
    assert settings.livekit_url
    url = settings.livekit_url.strip().rstrip("/")
    if url.startswith("wss://"):
        return "https://" + url[len("wss://") :]
    if url.startswith("ws://"):
        return "http://" + url[len("ws://") :]
    return url
