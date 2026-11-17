"""HttpOnly session cookie helpers for HTML + API auth."""

from __future__ import annotations

import os
from typing import Optional

from fastapi import Request, Response

SESSION_COOKIE = "sellm_session"


def _cookie_secure() -> bool:
    raw = (os.getenv("COOKIE_SECURE") or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return (os.getenv("RENDER") or os.getenv("HTTPS") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(),
        path="/",
        max_age=60 * 60 * 24 * 14,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE, path="/")


def cookie_token(request: Request) -> Optional[str]:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    token = raw.strip()
    return token or None
