"""Post-interview provisional scoring — separate from the live interviewer.

Scoring uses answer *text* only. Appearance, accent, vocal confidence,
and other audio cues must never influence provisional or final scores.
"""

from __future__ import annotations

import re
from typing import Any

from app.course.examiner.competencies import COMPETENCIES, COMPETENCY_WEIGHTS, RUBRIC_VERSION
from app.course.examiner.knowledge import gold_rationale_bits, judge_concepts_for
from app.course.examiner.state import SessionBundle
from app.course.exit_models import InterviewQuestion


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", text.lower())}


def _sufficiency(answer_text: str) -> str:
    words = len(answer_text.split())
    if words < 3:
        return "insufficient"
    if words < 8:
        return "low"
    if words < 40:
        return "moderate"
    return "high"


def _score_answer(answer_text: str, expected_concepts: list[str]) -> int:
    if not answer_text.strip():
        return 0
    words = len(answer_text.split())
    if words < 3:
        return 0

    tokens = _tokenize(answer_text)
    hit_score = 0.0
    for concept in expected_concepts:
        parts = _tokenize(concept.replace("_", " "))
        if not parts:
            continue
        if parts <= tokens:
            hit_score += 1.0
        elif any(p in tokens for p in parts):
            hit_score += 0.5

    base = 2
    if words >= 25:
        base = 3
    if words >= 60:
        base = 4
    if hit_score >= 1:
        base += 1
    if hit_score >= 2:
        base += 1
    return max(1, min(5, base))


def score_session(
    bundle: SessionBundle,
    repository_sha: str,
    *,
    scenario_slug: str | None = None,
) -> list[dict[str, Any]]:
    """Return provisional assessment payloads per participant (not yet persisted).

    When `scenario_slug` is provided, merges instructor knowledge-pack concepts
    into scoring (patterns/defects) without putting that gold on the live question.
    """
    by_user: dict[int, list[InterviewQuestion]] = {}
    for question in bundle.questions:
        by_user.setdefault(question.target_user_id, []).append(question)

    gold_bits = gold_rationale_bits(scenario_slug)
    reports: list[dict[str, Any]] = []
    for user_id, questions in by_user.items():
        competencies_out: list[dict[str, Any]] = []
        coverage_warnings: list[str] = []
        for competency in COMPETENCIES:
            comp_questions = [q for q in questions if q.competency == competency]
            answered = [
                q
                for q in comp_questions
                if any(a.text.strip() for a in bundle.answers_for(q.id))
            ]
            if not answered:
                coverage_warnings.append(f"No answered evidence for competency '{competency}'.")
                competencies_out.append(
                    {
                        "name": competency,
                        "score": None,
                        "max_score": 5,
                        "weight": COMPETENCY_WEIGHTS[competency],
                        "evidence_sufficiency": "insufficient",
                        "evidence": [],
                        "rationale": "No answer recorded; not scored. Follow-up recommended.",
                        "follow_up_recommended": True,
                    }
                )
                continue

            evidence_rows = []
            scores: list[int] = []
            sufficiencies: list[str] = []
            rationales: list[str] = []
            gold_concepts = judge_concepts_for(scenario_slug, competency)
            for q in answered:
                answers = sorted(bundle.answers_for(q.id), key=lambda a: a.created_at)
                primary = next((a for a in answers if not a.is_probe), answers[-1])
                # Generic prompt concepts + scenario gold (patterns/defects/focus terms).
                concepts = list(q.expected_concepts or []) + gold_concepts
                score = _score_answer(primary.text, concepts)
                suf = _sufficiency(primary.text)
                scores.append(score)
                sufficiencies.append(suf)
                code_refs = q.code_refs or {}
                evidence_rows.append(
                    {
                        "question_id": str(q.id),
                        "answer_id": str(primary.id),
                        "repository_path": code_refs.get("path"),
                        "line_range": code_refs.get("line_range"),
                        "sha": code_refs.get("sha") or repository_sha,
                        "prompt": q.prompt,
                        "answer_excerpt": primary.text[:400],
                    }
                )
                rationale = (
                    f"Q[{q.sequence}] score={score} sufficiency={suf}; "
                    f"prompt_concepts={q.expected_concepts}"
                )
                if gold_concepts:
                    rationale += f"; gold_hits_checked={len(gold_concepts)}"
                if gold_bits:
                    rationale += f"; {gold_bits}"
                rationales.append(rationale)

            order = ["insufficient", "low", "moderate", "high"]
            suf_final = min(sufficiencies, key=lambda s: order.index(s) if s in order else 0)
            scored_vals = [s for s in scores if s > 0]
            score_final = round(sum(scored_vals) / len(scored_vals)) if scored_vals else None
            competencies_out.append(
                {
                    "name": competency,
                    "score": score_final,
                    "max_score": 5,
                    "weight": COMPETENCY_WEIGHTS[competency],
                    "evidence_sufficiency": suf_final,
                    "evidence": evidence_rows,
                    "rationale": " | ".join(rationales),
                    "follow_up_recommended": suf_final in {"insufficient", "low"} or score_final is None,
                }
            )

        display_name = next(
            (p.display_name for p in bundle.participants if p.user_id == user_id and p.display_name),
            None,
        )
        if not display_name:
            user = bundle.users_by_id.get(user_id)
            display_name = user.username if user is not None else str(user_id)
        reports.append(
            {
                "student_id": str(user_id),
                "display_name": display_name,
                "repository_sha": repository_sha,
                "provisional": True,
                "competencies": competencies_out,
                "coverage_warnings": coverage_warnings,
                "review_status": "pending",
                "rubric_version": RUBRIC_VERSION,
            }
        )
    return reports
