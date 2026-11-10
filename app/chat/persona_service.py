"""Persona-aware fact retrieval and reply validation for YAML scenario mode."""

from __future__ import annotations

import re
from typing import Any

from app.chat.llm import PersonaReply, get_llm_provider
from app.scenarios.filter import facts_for_persona
from app.scenarios.models import KnowledgeFact, Persona, ScenarioPackage
from app.settings import Settings, get_settings

INJECTION_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r"ignore (all |any )?(previous|prior|above) (instructions|prompts)",
        r"reveal.*(evaluation|rubric|gaps\.yaml|hidden)",
        r"system prompt",
        r"developer message",
        r"jailbreak",
    ]
]


def looks_like_prompt_injection(text: str) -> bool:
    return any(p.search(text) for p in INJECTION_PATTERNS)


def get_persona(package: ScenarioPackage, persona_key: str) -> Persona | None:
    return next((p for p in package.personas if p.id == persona_key), None)


def allowed_facts_for_persona(package: ScenarioPackage, persona_key: str) -> list[KnowledgeFact]:
    return facts_for_persona(package, persona_key, include_never_student=False)


def facts_as_dicts(facts: list[KnowledgeFact]) -> list[dict[str, Any]]:
    return [
        {
            "id": f.id,
            "fact_key": f.id,
            "statement": f.statement,
            "text": f.statement,
            "disclosure": f.disclosure.value if hasattr(f.disclosure, "value") else f.disclosure,
            "status": f.status.value if hasattr(f.status, "value") else f.status,
            "origin": f.origin.value if hasattr(f.origin, "value") else f.origin,
        }
        for f in facts
    ]


def validate_reply(reply: PersonaReply, allowed_ids: set[str]) -> PersonaReply:
    clean_ids = [fid for fid in reply.used_fact_ids if fid in allowed_ids]
    dropped = [fid for fid in reply.used_fact_ids if fid not in allowed_ids]
    uncertainties = list(reply.uncertainties)
    if dropped:
        uncertainties.append("Dropped unsupported fact ids from model output.")
    answer = reply.answer.strip()
    if not answer:
        answer = "I'm not sure I can answer that from what I know."
        uncertainties.append("Empty model answer; used safe fallback.")
    if reply.used_fact_ids and not clean_ids:
        answer = (
            "I should not speculate beyond what I know in my role. "
            "Could you ask about something in my area, or I can refer you to another stakeholder?"
        )
        uncertainties.append("Model cited unauthorized facts; replaced with uncertainty fallback.")
    return PersonaReply(
        answer=answer,
        used_fact_ids=clean_ids,
        uncertainties=uncertainties,
        handoff_suggestion=reply.handoff_suggestion,
        model_version=reply.model_version,
        usage=reply.usage,
        raw=reply.raw,
    )


def history_for_model(history: list[dict[str, str]], limit: int) -> list[dict[str, str]]:
    recent = history[-limit:]
    out: list[dict[str, str]] = []
    for msg in recent:
        role = msg.get("role") or "user"
        if role == "assistant":
            role = "assistant"
        elif role in ("persona", "student"):
            role = "assistant" if role == "persona" else "user"
        out.append({"role": role, "content": msg.get("content") or msg.get("text") or ""})
    return out


async def generate_validated_reply(
    *,
    package: ScenarioPackage,
    persona_key: str,
    history: list[dict[str, str]],
    student_message: str,
    settings: Settings | None = None,
) -> PersonaReply:
    settings = settings or get_settings()
    persona = get_persona(package, persona_key)
    if persona is None:
        return PersonaReply(
            answer="I don't recognize that stakeholder role for this scenario.",
            used_fact_ids=[],
            uncertainties=["Unknown persona_key"],
            model_version="policy-guard",
            usage={"provider": "guard"},
        )

    facts = allowed_facts_for_persona(package, persona_key)
    allowed = facts_as_dicts(facts)
    allowed_ids = {f["id"] for f in allowed}

    if looks_like_prompt_injection(student_message):
        return PersonaReply(
            answer=(
                "I can only talk about the project from my stakeholder role. "
                "I don't have access to grading rubrics or hidden evaluation materials."
            ),
            used_fact_ids=[],
            uncertainties=["Treated message as potential prompt-injection / out-of-role request."],
            handoff_suggestion=None,
            model_version="policy-guard",
            usage={"provider": "guard", "prompt_injection_flag": True},
        )

    provider = get_llm_provider(settings)
    reply = await provider.generate_persona_reply(
        persona=persona.model_dump(),
        allowed_facts=allowed,
        history=history_for_model(history, settings.chat_history_limit),
        student_message=student_message,
    )
    return validate_reply(reply, allowed_ids)
