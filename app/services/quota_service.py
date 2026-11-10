"""Token quota / BYOK billing helpers."""

from __future__ import annotations

from typing import Optional

from app.storage.conversation_store import ConversationStore, User


class QuotaService:
    def __init__(self, store: ConversationStore) -> None:
        self.store = store

    @staticmethod
    def estimate_tokens(*parts: str) -> int:
        total_chars = sum(len(p or "") for p in parts)
        return max(1, total_chars // 4)

    def exhausted(self, user: User) -> bool:
        limit = int(getattr(user, "token_limit", 0) or 0)
        used = int(getattr(user, "tokens_used", 0) or 0)
        return limit > 0 and used >= limit

    def payload(self, user: User, *, has_byok: bool) -> dict:
        limit = int(getattr(user, "token_limit", 0) or 0)
        used = int(getattr(user, "tokens_used", 0) or 0)
        remaining = max(0, limit - used) if limit > 0 else None
        exhausted = self.exhausted(user)
        return {
            "token_limit": limit,
            "tokens_used": used,
            "tokens_remaining": remaining,
            "quota_exhausted": exhausted,
            "has_byok": has_byok,
            "billing_mode": "byok" if exhausted and has_byok else ("platform" if not exhausted else "blocked"),
        }

    def record_platform_usage(
        self,
        user: User,
        *,
        billing: str,
        prompt: str,
        response: str,
        usage_tokens: int = 0,
    ) -> None:
        if billing != "platform":
            return
        est = usage_tokens if usage_tokens > 0 else self.estimate_tokens(prompt, response)
        self.store.add_tokens_used(user.id, est)
