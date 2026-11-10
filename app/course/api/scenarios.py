"""Student-safe scenario listing and persona endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.course.chat.draft_review import review_draft
from app.course.chat.persona_service import allowed_facts_for_persona, facts_as_dicts, get_persona
from app.course.scenarios.filter import facts_for_persona
from app.course.scenarios.registry import scenario_registry

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])


class PersonaPublic(BaseModel):
    id: str
    display_name: str
    role: str
    priorities: list[str] = []
    communication_style: str = ""


class ScenarioListItem(BaseModel):
    slug: str
    title: str
    version: str
    status: str
    brief: str
    personas: list[PersonaPublic]


class DraftReviewRequest(BaseModel):
    scenario_slug: str = Field(min_length=1)
    persona_key: str = Field(min_length=1)
    draft_text: str = Field(min_length=1, max_length=80_000)
    scenario_version: str | None = None
    filename: str | None = None


@router.get("", response_model=list[ScenarioListItem])
def list_scenarios() -> list[ScenarioListItem]:
    items: list[ScenarioListItem] = []
    for row in scenario_registry.list_student_safe():
        items.append(
            ScenarioListItem(
                slug=row["slug"],
                title=row["title"],
                version=row["version"],
                status=row["status"],
                brief=row["brief"],
                personas=[PersonaPublic(**p) for p in row.get("personas") or []],
            )
        )
    return items


@router.post("/draft-review")
def draft_review(body: DraftReviewRequest) -> dict:
    package = scenario_registry.get(body.scenario_slug, body.scenario_version)
    if package is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    persona = get_persona(package, body.persona_key)
    if persona is None:
        raise HTTPException(status_code=404, detail="Persona not found")
    facts = facts_as_dicts(allowed_facts_for_persona(package, body.persona_key))
    result = review_draft(
        draft_text=body.draft_text,
        persona_display_name=persona.display_name,
        facts=facts,
        filename=body.filename,
    )
    return result.as_student_safe_dict()


@router.get("/{slug}")
def get_scenario(slug: str, version: str | None = None) -> dict:
    package = scenario_registry.get(slug, version)
    if package is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    from app.course.scenarios.filter import student_safe_scenario_view

    return student_safe_scenario_view(package)


@router.get("/{slug}/personas/{persona_key}/facts")
def persona_facts(slug: str, persona_key: str, version: str | None = None) -> list[dict]:
    package = scenario_registry.get(slug, version)
    if package is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    if not any(p.id == persona_key for p in package.personas):
        raise HTTPException(status_code=404, detail="Persona not found")
    facts = facts_for_persona(package, persona_key, include_never_student=False)
    # Student-safe: statements only, no evaluation/gaps
    return [
        {
            "id": f.id,
            "statement": f.statement,
            "category": f.category,
            "status": f.status.value,
            "disclosure": f.disclosure.value,
        }
        for f in facts
        if f.disclosure.value != "never_student"
    ]
