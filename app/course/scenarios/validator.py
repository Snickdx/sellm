"""Validate scenario packages for import readiness."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.seproject.scenarios.loader import load_scenario_package
from app.seproject.scenarios.models import FactOrigin, FactStatus, ScenarioPackage, ScenarioStatus


@dataclass(frozen=True)
class ValidationIssue:
    severity: str  # error | warning
    code: str
    message: str


def validate_scenario_package(package: ScenarioPackage) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if package.meta.status == ScenarioStatus.pending_source:
        if package.facts or package.personas:
            issues.append(
                ValidationIssue(
                    "warning",
                    "pending_with_content",
                    "PENDING_SOURCE package still has personas/facts; confirm intentional.",
                )
            )
        return issues

    fact_ids: set[str] = set()
    for fact in package.facts:
        if fact.id in fact_ids:
            issues.append(ValidationIssue("error", "duplicate_fact_id", f"Duplicate fact id {fact.id}"))
        fact_ids.add(fact.id)

        if fact.status == FactStatus.confirmed and fact.origin == FactOrigin.transcript:
            for ref in fact.source_refs:
                keys = [ref.file, Path(ref.file).name, f"sources/{Path(ref.file).name}"]
                found = any(ref.cue_id in package.cue_ids_by_file.get(key, set()) for key in keys)
                if not found and package.cue_ids_by_file:
                    issues.append(
                        ValidationIssue(
                            "error",
                            "missing_source_ref",
                            f"{fact.id} source_ref cue {ref.cue_id} not found for {ref.file}",
                        )
                    )
                elif not package.cue_ids_by_file:
                    issues.append(
                        ValidationIssue(
                            "error",
                            "missing_cues",
                            f"{fact.id} is confirmed but no normalized cues/sources were found",
                        )
                    )

        if fact.status == FactStatus.assumed and fact.origin != FactOrigin.instructor:
            issues.append(
                ValidationIssue(
                    "error",
                    "assumed_origin",
                    f"{fact.id}: assumed facts must have origin=instructor",
                )
            )

        if fact.status == FactStatus.confirmed and fact.origin == FactOrigin.instructor:
            issues.append(
                ValidationIssue(
                    "error",
                    "confirmed_instructor",
                    f"{fact.id}: instructor origin cannot be labeled confirmed; use clarified/assumed",
                )
            )

    persona_ids: set[str] = set()
    for persona in package.personas:
        if persona.id in persona_ids:
            issues.append(
                ValidationIssue("error", "duplicate_persona_id", f"Duplicate persona id {persona.id}")
            )
        persona_ids.add(persona.id)
        for fid in persona.known_fact_ids:
            if fid not in fact_ids:
                issues.append(
                    ValidationIssue(
                        "error",
                        "unknown_persona_fact",
                        f"Persona {persona.id} references unknown fact {fid}",
                    )
                )

    for fact in package.facts:
        for pid in fact.known_by:
            if package.personas and pid not in persona_ids:
                issues.append(
                    ValidationIssue(
                        "error",
                        "unknown_known_by",
                        f"Fact {fact.id} known_by unknown persona {pid}",
                    )
                )

    if package.meta.status == ScenarioStatus.approved:
        if package.evaluation is None:
            issues.append(
                ValidationIssue(
                    "warning",
                    "missing_evaluation",
                    "Approved package has no evaluation.yaml (instructor oracle).",
                )
            )
        critical_open = [
            g
            for g in (package.gaps.open_questions if package.gaps else [])
            if g.status == "open" and g.priority.value == "critical"
        ]
        if critical_open:
            issues.append(
                ValidationIssue(
                    "error",
                    "open_critical_gaps",
                    f"Approved package still has open critical gaps: {[g.id for g in critical_open]}",
                )
            )

    return issues


def validate_scenario_dir(scenario_dir: Path) -> tuple[ScenarioPackage, list[ValidationIssue]]:
    package = load_scenario_package(scenario_dir)
    return package, validate_scenario_package(package)


def has_errors(issues: list[ValidationIssue]) -> bool:
    return any(i.severity == "error" for i in issues)
