"""Lightweight settings for YAML scenario / persona mode."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass
class Settings:
    llm_provider: str = "heuristic"
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    chat_history_limit: int = 12


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        llm_provider=os.getenv("SCENARIO_LLM_PROVIDER", os.getenv("LLM_PROVIDER", "heuristic")).lower(),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        chat_history_limit=int(os.getenv("CHAT_HISTORY_LIMIT", "12")),
    )
