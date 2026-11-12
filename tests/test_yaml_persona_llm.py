"""YAML persona chat should use selected LLM credentials and meta-question fallbacks."""

from __future__ import annotations

import asyncio

from app.chat.llm import HeuristicLLMProvider, OpenAILLMProvider, get_llm_provider
from app.settings import Settings


def _persona() -> dict:
    return {
        "id": "library_coordinator",
        "display_name": "Library Workshop Coordinator",
        "role": "Library staff who administers workshop booking.",
        "priorities": ["Avoid double-booking rooms", "Collect course code and headcount"],
        "referral_rules": ["Refer capacity-policy disputes that need escalation to administrator"],
    }


def _facts() -> list[dict]:
    return [
        {
            "id": "LIB-REQ-001",
            "statement": "Lecturers submit workshop booking requests with course code and headcount.",
        },
        {
            "id": "LIB-REQ-002",
            "statement": "The coordinator prevents double-booking of workshop rooms.",
        },
    ]


def test_heuristic_answers_who_are_you():
    provider = HeuristicLLMProvider()
    reply = asyncio.run(
        provider.generate_persona_reply(
            persona=_persona(),
            allowed_facts=_facts(),
            history=[],
            student_message="who are you",
        )
    )
    assert "Library Workshop Coordinator" in reply.answer
    assert reply.used_fact_ids
    assert "invent a policy" not in reply.answer.lower()


def test_heuristic_answers_features_meta_question():
    provider = HeuristicLLMProvider()
    reply = asyncio.run(
        provider.generate_persona_reply(
            persona=_persona(),
            allowed_facts=_facts(),
            history=[],
            student_message="what are the features",
        )
    )
    assert "double-booking" in reply.answer.lower() or "booking" in reply.answer.lower()
    assert reply.usage.get("meta_intro") is True


def test_get_llm_provider_uses_byok_openai():
    settings = Settings(llm_provider="heuristic", openai_api_key=None)
    provider = get_llm_provider(
        settings,
        provider="openai",
        api_key="sk-test",
        model="gpt-4o-mini",
    )
    assert isinstance(provider, OpenAILLMProvider)
    assert provider.api_key == "sk-test"
    assert provider.model_version == "gpt-4o-mini"


def test_get_llm_provider_falls_back_to_heuristic_without_key():
    settings = Settings(llm_provider="heuristic", openai_api_key=None)
    provider = get_llm_provider(settings, provider="openai", api_key=None, model="gpt-4o-mini")
    assert isinstance(provider, HeuristicLLMProvider)
