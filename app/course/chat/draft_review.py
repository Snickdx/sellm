"""Persona-grounded requirements draft review (M3).

Uses only facts the selected persona is allowed to know. Never reads
evaluation.yaml / gaps / hidden rubrics. Returns conflicts as stakeholder
pushback and follow-up questions for coverage gaps.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from app.course.db_models import ScenarioFact

STOPWORDS = {
    "the",
    "and",
    "for",
    "that",
    "with",
    "this",
    "from",
    "have",
    "what",
    "when",
    "where",
    "which",
    "about",
    "would",
    "could",
    "should",
    "must",
    "need",
    "only",
    "their",
    "they",
    "them",
    "are",
    "can",
    "may",
    "will",
    "into",
    "onto",
}


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", text.lower()) if t not in STOPWORDS}


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text.strip())
    return [p.strip() for p in parts if len(p.strip()) > 12]


# (fact cue tokens that should co-occur, draft contradiction cues)
_CONTRADICTION_RULES: list[tuple[set[str], set[str], str]] = [
    (
        {"earlier", "request", "wins"},
        {"later", "wins"},
        "Draft prefers a later request winning the slot, which conflicts with earlier-request-wins.",
    ),
    (
        {"earlier", "request"},
        {"last", "served"},
        "Draft implies last-served / later-priority, which conflicts with earlier-request priority.",
    ),
    (
        {"course", "code", "headcount"},
        {"optional", "email"},
        "Draft treats required booking fields as optional or email-only.",
    ),
    (
        {"course", "code"},
        {"only", "date"},
        "Draft says only a date is needed; course code / headcount / resources are required.",
    ),
    (
        {"overbook"},
        {"allow", "overbook"},
        "Draft allows overbooking, which conflicts with capacity constraints.",
    ),
    (
        {"overbook"},
        {"insist"},
        "Draft lets insistence override capacity, which conflicts with no-overbook rules.",
    ),
    (
        {"capacity"},
        {"overbook"},
        "Draft mentions overbooking in a way that conflicts with capacity limits.",
    ),
    (
        {"confirmation"},
        {"no", "confirmation"},
        "Draft denies booking confirmation that stakeholders expect.",
    ),
    (
        {"administrator", "publish"},
        {"students", "publish"},
        "Draft assigns publishing openings to the wrong role.",
    ),
    (
        {"employer"},
        {"anyone", "post"},
        "Draft opens posting too broadly versus employer/admin controls.",
    ),
    (
        {"administrator", "publish"},
        {"students", "publish"},
        "Draft lets students publish openings without the administrator role I know.",
    ),
    (
        {"administrator", "publish"},
        {"without", "admin"},
        "Draft removes administrator involvement from publishing openings.",
    ),
    (
        {"moderator", "remove"},
        {"anyone", "delete"},
        "Draft lets anyone delete posts; moderation is restricted in my knowledge.",
    ),
    (
        {"verified", "administrator"},
        {"unverified"},
        "Draft allows unverified listings that should wait for administrator verification.",
    ),
    (
        {"workload"},
        {"unlimited"},
        "Draft ignores HOD workload limits that constrain TA allocations.",
    ),
    (
        {"prerequisites"},
        {"ignore"},
        "Draft ignores programme prerequisites that advising must respect.",
    ),
    (
        {"prerequisite"},
        {"ignore"},
        "Draft ignores programme prerequisites that advising must respect.",
    ),
    (
        {"supervisor", "feedback"},
        {"without", "supervisor"},
        "Draft skips supervisor feedback that milestones require.",
    ),
    (
        {"supervisor", "feedback"},
        {"skip", "milestone"},
        "Draft allows skipping milestones without required feedback.",
    ),
]


LEAK_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r"EVAL-[A-Z]+-\d+",
        r"hidden_checks",
        r"gaps\.yaml",
        r"evaluation\.yaml",
        r"\boracle\b",
        r"grading rubric",
        r"competency:\s*\w+",
    ]
]


@dataclass
class ConflictItem:
    fact_id: str
    draft_excerpt: str
    stakeholder_pushback: str


@dataclass
class QuestionItem:
    fact_id: str | None
    question: str
    reason: str


@dataclass
class DraftReviewResult:
    summary: str
    conflicts: list[ConflictItem] = field(default_factory=list)
    questions: list[QuestionItem] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    model_version: str = "draft-review-heuristic-v1"
    persona_reply_text: str = ""

    def as_student_safe_dict(self) -> dict[str, Any]:
        payload = {
            "summary": self.summary,
            "conflicts": [
                {
                    "fact_id": c.fact_id,
                    "draft_excerpt": c.draft_excerpt,
                    "stakeholder_pushback": c.stakeholder_pushback,
                }
                for c in self.conflicts
            ],
            "questions": [
                {
                    "fact_id": q.fact_id,
                    "question": q.question,
                    "reason": q.reason,
                }
                for q in self.questions
            ],
            "metrics": self.metrics,
            "model_version": self.model_version,
            "persona_reply_text": self.persona_reply_text,
        }
        blob = str(payload)
        for pat in LEAK_PATTERNS:
            if pat.search(blob):
                raise RuntimeError("Draft review output failed leak check")
        return payload


def _fact_supported(draft_tokens: set[str], fact: ScenarioFact | dict[str, Any]) -> bool:
    statement = fact.text if isinstance(fact, ScenarioFact) else str(fact.get("text") or fact.get("statement") or "")
    tokens = _tokenize(statement)
    if not tokens:
        return False
    overlap = draft_tokens & tokens
    return len(overlap) >= max(2, min(4, len(tokens) // 3))


def _find_conflicts(
    draft: str,
    facts: list[ScenarioFact] | list[dict[str, Any]],
) -> list[ConflictItem]:
    draft_l = draft.lower()
    draft_tokens = _tokenize(draft)
    sentences = _sentences(draft)
    conflicts: list[ConflictItem] = []

    for fact in facts:
        fact_id = fact.fact_key if isinstance(fact, ScenarioFact) else str(fact.get("id") or fact.get("fact_key"))
        statement = fact.text if isinstance(fact, ScenarioFact) else str(fact.get("text") or fact.get("statement") or "")
        fact_tokens = _tokenize(statement)
        if not fact_tokens:
            continue

        for cue_tokens, bad_tokens, explanation in _CONTRADICTION_RULES:
            if not cue_tokens <= fact_tokens and not (cue_tokens & fact_tokens):
                # soft match: at least half of cue tokens in fact
                if len(cue_tokens & fact_tokens) < max(1, len(cue_tokens) // 2):
                    continue
            if bad_tokens <= draft_tokens or all(t in draft_l for t in bad_tokens):
                excerpt = next(
                    (s for s in sentences if any(t in s.lower() for t in bad_tokens)),
                    sentences[0] if sentences else draft[:180],
                )
                conflicts.append(
                    ConflictItem(
                        fact_id=fact_id,
                        draft_excerpt=excerpt[:280],
                        stakeholder_pushback=explanation,
                    )
                )
                break

        # Negation near shared keywords: "not" / "never" / "no longer" + fact tokens
        shared = fact_tokens & draft_tokens
        if len(shared) >= 2:
            for sent in sentences:
                sl = sent.lower()
                if any(n in sl for n in (" not ", " never ", " no ", " instead ", " without ")):
                    if len(_tokenize(sent) & fact_tokens) >= 2:
                        # Avoid double-counting if already conflicted on this fact
                        if any(c.fact_id == fact_id for c in conflicts):
                            continue
                        # Skip if sentence clearly affirms the fact
                        if "must" in sl and "not" in sl and "overbook" in fact_tokens:
                            continue
                        conflicts.append(
                            ConflictItem(
                                fact_id=fact_id,
                                draft_excerpt=sent[:280],
                                stakeholder_pushback=(
                                    "This part of the draft appears to negate something I would "
                                    "expect from my role's knowledge of the process."
                                ),
                            )
                        )
                        break

    # de-dupe by fact_id keeping first
    seen: set[str] = set()
    unique: list[ConflictItem] = []
    for c in conflicts:
        if c.fact_id in seen:
            continue
        seen.add(c.fact_id)
        unique.append(c)
    return unique


def _coverage_questions(
    draft: str,
    facts: list[ScenarioFact] | list[dict[str, Any]],
    *,
    max_questions: int = 5,
) -> list[QuestionItem]:
    draft_tokens = _tokenize(draft)
    scored: list[tuple[int, QuestionItem]] = []
    for fact in facts:
        fact_id = fact.fact_key if isinstance(fact, ScenarioFact) else str(fact.get("id") or fact.get("fact_key"))
        statement = fact.text if isinstance(fact, ScenarioFact) else str(fact.get("text") or fact.get("statement") or "")
        disclosure = (
            fact.disclosure
            if isinstance(fact, ScenarioFact)
            else str(fact.get("disclosure") or "when_relevant")
        )
        if _fact_supported(draft_tokens, fact):
            continue
        # Prefer asking about when_asked facts first
        priority = 0 if disclosure == "when_asked" else 1
        scored.append(
            (
                priority,
                QuestionItem(
                    fact_id=fact_id,
                    question=f"Did you capture this: {statement}",
                    reason="Not clearly reflected in the draft from my perspective.",
                ),
            )
        )
    scored.sort(key=lambda item: item[0])
    return [q for _, q in scored[:max_questions]]


def review_draft(
    *,
    draft_text: str,
    persona_display_name: str,
    facts: list[ScenarioFact] | list[dict[str, Any]],
    filename: str | None = None,
) -> DraftReviewResult:
    started = time.perf_counter()
    cleaned = draft_text.strip()
    if not cleaned:
        raise ValueError("Draft text is empty")

    if not facts:
        latency_ms = int((time.perf_counter() - started) * 1000)
        result = DraftReviewResult(
            summary=(
                f"As {persona_display_name}, I do not have enough grounded knowledge "
                "loaded for this scenario yet to validate your draft claims."
            ),
            questions=[
                QuestionItem(
                    fact_id=None,
                    question="Can we continue the interview so I can confirm policies before you finalize the SRS?",
                    reason="Persona knowledge pack is empty or not imported.",
                )
            ],
            metrics={
                "factuality": 0.0,
                "coverage_opportunity": 1.0,
                "consistency": 1.0,
                "latency_ms": latency_ms,
                "cost_usd_estimate": 0.0,
                "fact_count": 0,
                "conflict_count": 0,
                "question_count": 1,
                "draft_chars": len(cleaned),
                "filename": filename,
                "provider": "heuristic",
            },
        )
        result.persona_reply_text = _format_persona_reply(result, persona_display_name)
        return result

    conflicts = _find_conflicts(cleaned, facts)
    questions = _coverage_questions(cleaned, facts)
    # Drop questions for facts already flagged as conflicts
    conflict_ids = {c.fact_id for c in conflicts}
    questions = [q for q in questions if q.fact_id not in conflict_ids]

    draft_tokens = _tokenize(cleaned)
    supported = sum(1 for f in facts if _fact_supported(draft_tokens, f))
    fact_n = max(len(facts), 1)
    factuality = max(0.0, min(1.0, (supported / fact_n) * (0.55 if conflicts else 1.0)))
    if conflicts:
        factuality = min(factuality, 0.45)
    coverage_opportunity = min(1.0, len(questions) / min(5, fact_n))
    consistency = 1.0 if not conflicts else max(0.0, 1.0 - (len(conflicts) / fact_n))

    latency_ms = int((time.perf_counter() - started) * 1000)
    if conflicts and not questions:
        summary = (
            f"I reviewed your draft as {persona_display_name}. "
            f"I see {len(conflicts)} place(s) that conflict with what I know."
        )
    elif conflicts:
        summary = (
            f"I reviewed your draft as {persona_display_name}. "
            f"There are conflicts to resolve and a few topics still missing from my view."
        )
    elif questions:
        summary = (
            f"I reviewed your draft as {persona_display_name}. "
            f"Nothing jumped out as contradictory, but some important points are still unclear."
        )
    else:
        summary = (
            f"I reviewed your draft as {persona_display_name}. "
            "It lines up with what I know from my role."
        )

    result = DraftReviewResult(
        summary=summary,
        conflicts=conflicts,
        questions=questions,
        metrics={
            "factuality": round(factuality, 3),
            "coverage_opportunity": round(coverage_opportunity, 3),
            "consistency": round(consistency, 3),
            "latency_ms": latency_ms,
            "cost_usd_estimate": 0.0,
            "fact_count": len(facts),
            "conflict_count": len(conflicts),
            "question_count": len(questions),
            "supported_fact_count": supported,
            "draft_chars": len(cleaned),
            "filename": filename,
            "provider": "heuristic",
        },
    )
    result.persona_reply_text = _format_persona_reply(result, persona_display_name)
    # final leak guard
    result.as_student_safe_dict()
    return result


def _format_persona_reply(result: DraftReviewResult, name: str) -> str:
    lines = [f"Requirements draft review ({name})", "", result.summary, ""]
    if result.conflicts:
        lines.append("Conflicts with what I know:")
        for c in result.conflicts:
            lines.append(f"- {c.stakeholder_pushback}")
            lines.append(f'  (from your draft: "{c.draft_excerpt}")')
        lines.append("")
    if result.questions:
        lines.append("Questions / gaps to clarify:")
        for q in result.questions:
            lines.append(f"- {q.question}")
        lines.append("")
    lines.append(
        "I am speaking only from my stakeholder knowledge — not from hidden evaluation materials."
    )
    return "\n".join(lines)


def facts_as_review_dicts(facts: list[ScenarioFact]) -> list[dict[str, Any]]:
    return [
        {
            "id": f.fact_key,
            "fact_key": f.fact_key,
            "text": f.text,
            "statement": f.text,
            "disclosure": f.disclosure,
        }
        for f in facts
    ]
