"""Persist validated scenario packages into the database."""

from __future__ import annotations

from sqlmodel import Session, select

from app.models.scenarios import Scenario, ScenarioFact, ScenarioPersona, ScenarioRecordStatus
from app.scenarios.models import ScenarioPackage


def import_package_to_db(session: Session, package: ScenarioPackage, *, source_path: str | None = None) -> Scenario:
    existing = session.exec(
        select(Scenario).where(Scenario.slug == package.meta.slug, Scenario.version == package.meta.version)
    ).first()
    if existing is not None:
        # cascade-delete children then parent
        for persona in session.exec(select(ScenarioPersona).where(ScenarioPersona.scenario_id == existing.id)).all():
            session.delete(persona)
        for fact in session.exec(select(ScenarioFact).where(ScenarioFact.scenario_id == existing.id)).all():
            session.delete(fact)
        session.delete(existing)
        session.flush()

    try:
        status = ScenarioRecordStatus(package.meta.status.value).value
    except ValueError:
        status = package.meta.status.value

    record = Scenario(
        slug=package.meta.slug,
        version=package.meta.version,
        title=package.meta.title,
        status=status,
        brief=package.meta.brief,
        source_manifest={
            "source_status": package.meta.source_status,
            "source_notes": package.meta.source_notes,
            "approved_by": package.meta.approved_by,
            "approved_at": package.meta.approved_at,
            "cue_files": sorted(package.cue_ids_by_file.keys()),
        },
        gaps_json=package.gaps.model_dump() if package.gaps else None,
        evaluation_json=package.evaluation.model_dump() if package.evaluation else None,
        source_path=source_path,
    )
    session.add(record)
    session.flush()

    for persona in package.personas:
        session.add(
            ScenarioPersona(
                scenario_id=record.id,
                persona_key=persona.id,
                config=persona.model_dump(),
            )
        )

    for fact in package.facts:
        session.add(
            ScenarioFact(
                scenario_id=record.id,
                fact_key=fact.id,
                text=fact.statement,
                provenance={
                    "category": fact.category,
                    "decision_id": fact.decision_id,
                    "approved_by": fact.approved_by,
                    "approved_at": fact.approved_at,
                    "rationale": fact.rationale,
                    "acceptance_criteria": fact.acceptance_criteria,
                },
                source_ref=[ref.model_dump() for ref in fact.source_refs],
                known_by=list(fact.known_by),
                disclosure=fact.disclosure.value,
                status=fact.status.value,
                origin=fact.origin.value,
            )
        )

    session.flush()
    return record
