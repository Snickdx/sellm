"""Persona-authorized fact filtering and student-safe views."""

from __future__ import annotations

from typing import Any

from app.course.scenarios.models import Disclosure, KnowledgeFact, ScenarioPackage


def facts_for_persona(
    package: ScenarioPackage,
    persona_id: str,
    *,
    include_never_student: bool = False,
) -> list[KnowledgeFact]:
    persona = next((p for p in package.personas if p.id == persona_id), None)
    if persona is None:
        return []

    allowed = set(persona.known_fact_ids)
    results: list[KnowledgeFact] = []
    for fact in package.facts:
        if fact.id not in allowed and persona_id not in fact.known_by:
            continue
        if fact.disclosure == Disclosure.never_student and not include_never_student:
            continue
        results.append(fact)
    return results


def student_safe_scenario_view(package: ScenarioPackage) -> dict[str, Any]:
    """Public metadata + personas without gaps/evaluation/hidden facts."""
    return {
        "slug": package.meta.slug,
        "title": package.meta.title,
        "version": package.meta.version,
        "status": package.meta.status.value,
        "brief": package.meta.brief,
        "personas": [
            {
                "id": p.id,
                "display_name": p.display_name,
                "role": p.role,
                "priorities": p.priorities,
                "communication_style": p.communication_style,
                # known_fact_ids intentionally omitted from student listing
            }
            for p in package.personas
        ],
    }


def instructor_preview(package: ScenarioPackage, persona_id: str | None = None) -> dict[str, Any]:
    """Instructor preview including provenance; still strips nothing essential for audit."""
    facts = (
        package.facts
        if persona_id is None
        else facts_for_persona(package, persona_id, include_never_student=True)
    )
    return {
        "meta": package.meta.model_dump(),
        "personas": [p.model_dump() for p in package.personas],
        "facts": [f.model_dump() for f in facts],
        "gaps": package.gaps.model_dump() if package.gaps else None,
        "evaluation": package.evaluation.model_dump() if package.evaluation else None,
        "fact_count": len(package.facts),
        "persona_count": len(package.personas),
    }
