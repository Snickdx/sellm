"""Auth helpers used by the API layer (Bearer or session cookie → user)."""

from __future__ import annotations

from typing import Optional

from fastapi import Request

from app.storage.conversation_store import ConversationStore, User
from app.web.session_cookie import cookie_token


class AuthService:
    def __init__(self, store: ConversationStore) -> None:
        self.store = store

    @staticmethod
    def token_from_request(request: Request) -> Optional[str]:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:].strip()
            if token:
                return token
        return cookie_token(request)

    def user_from_request(self, request: Request) -> Optional[User]:
        token = self.token_from_request(request)
        if not token:
            return None
        session = self.store.get_session(token)
        if not session:
            return None
        return self.store.get_user_by_id(session.user_id)

    def login(self, username: str, password: str) -> Optional[tuple[User, str]]:
        user = self.store.get_user_by_credentials(username, password)
        if not user:
            return None
        token = self.store.create_session(user.id)
        return user, token

    def logout(self, token: Optional[str]) -> None:
        if token:
            self.store.delete_session(token)
