"""Export a YAML scenario package to an Excel-shaped workbook.

Runtime chat no longer depends on ``data.xlsx``. This exporter produces a
legacy-compatible workbook (typed sheets + Relationships) for instructors who
want Excel parity artifacts, tooling, or offline review. Prefer reindex for
vector/graph modes; Excel exports are optional mirrors of package facts.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from app.scenarios.models import KnowledgeFact, ScenarioPackage
from app.scenarios.neo4j_graph import fact_kind_and_label


# Excel sheet name → fact kinds that land on that sheet (aligned with neo4j_graph sheets).
_KIND_TO_SHEET: dict[str, str] = {
    "requirement": "Requirement",
    "feature": "Feature",
    "goal": "Goal",
    "constraint": "Constraint",
    "limitation": "Constraint",
    "assumption": "Assumption",
    "dependency": "Dependency",
    "design_constraint": "Constraint",
    "standard": "Constraint",
    "workflow": "Task",
    "use_case": "Qual_Scenario",
    "interface": "Requirement",
    "data": "Requirement",
    "verification": "Requirement",
    "performance": "Qual_Scenario",
    "usability": "Qual_Scenario",
    "security": "Qual_Scenario",
    "quality": "Qual_Scenario",
    "non_functional": "Qual_Scenario",
    "glossary": "RequirementNode",
    "reference": "RequirementNode",
    "context": "RequirementNode",
    "knowledge": "RequirementNode",
}


def _enum_val(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value or "")


def _fact_row(fact: KnowledgeFact) -> dict[str, Any]:
    kind, label, sheet = fact_kind_and_label(fact)
    return {
        "id": fact.id,
        "statement": fact.statement,
        "category": fact.category or kind,
        "kind": kind,
        "label": label,
        "sheet": sheet,
        "status": _enum_val(fact.status),
        "origin": _enum_val(fact.origin),
        "disclosure": _enum_val(fact.disclosure),
        "known_by": ", ".join(fact.known_by or []),
        "acceptance_criteria": " | ".join(fact.acceptance_criteria or []),
        "satisfies_ids": ", ".join(fact.satisfies_ids or []),
        "derives_from_ids": ", ".join(fact.derives_from_ids or []),
        "depends_on_ids": ", ".join(fact.depends_on_ids or []),
    }


def _relationships(package: ScenarioPackage) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    fact_by_id = {f.id: f for f in package.facts}
    for persona in package.personas:
        for fact_id in persona.known_fact_ids or []:
            rows.append({"start_id": persona.id, "end_id": fact_id, "type": "KNOWS"})
            rows.append({"start_id": fact_id, "end_id": persona.id, "type": "OWNED_BY"})
    for fact in package.facts:
        kind, _, _ = fact_kind_and_label(fact)
        for target in fact.satisfies_ids or []:
            rows.append({"start_id": fact.id, "end_id": target, "type": "SATISFIES"})
        for target in fact.derives_from_ids or []:
            rows.append({"start_id": fact.id, "end_id": target, "type": "DERIVES_FROM"})
        for target in fact.depends_on_ids or []:
            rows.append({"start_id": fact.id, "end_id": target, "type": "DEPENDS_ON"})
            target_fact = fact_by_id.get(target)
            if target_fact is not None:
                target_kind, _, _ = fact_kind_and_label(target_fact)
                if target_kind == "verification":
                    rows.append({"start_id": fact.id, "end_id": target, "type": "VERIFIED_BY"})
        if kind == "verification":
            for target in (
                list(fact.satisfies_ids or [])
                + list(fact.derives_from_ids or [])
                + list(fact.depends_on_ids or [])
            ):
                rows.append({"start_id": target, "end_id": fact.id, "type": "VERIFIED_BY"})
    return rows


def build_workbook_frames(package: ScenarioPackage) -> dict[str, pd.DataFrame]:
    """Return sheet_name → DataFrame for one package (Excel-shaped)."""
    frames: dict[str, pd.DataFrame] = {}

    frames["Project"] = pd.DataFrame(
        [
            {
                "id": f"PROJ-{package.meta.slug}",
                "title": package.meta.title,
                "brief": package.meta.brief or "",
                "status": _enum_val(package.meta.status),
                "slug": package.meta.slug,
                "version": package.meta.version,
            }
        ]
    )

    stakeholder_rows = []
    role_rows = []
    for persona in package.personas:
        system_role = _enum_val(getattr(persona, "system_role", None))
        caps = list(getattr(persona, "admin_capabilities", None) or [])
        stakeholder_rows.append(
            {
                "id": persona.id,
                "name": persona.display_name,
                "role": persona.role,
                "system_role": system_role,
                "admin_capabilities": ", ".join(caps),
                "priorities": " | ".join(persona.priorities or []),
                "communication_style": persona.communication_style or "",
                "known_fact_ids": ", ".join(persona.known_fact_ids or []),
            }
        )
        if system_role:
            role_rows.append({"id": f"ROLE-{persona.id}", "name": system_role, "stakeholder_id": persona.id})
        elif persona.role:
            role_rows.append({"id": f"ROLE-{persona.id}", "name": persona.role, "stakeholder_id": persona.id})
    frames["Stakeholder"] = pd.DataFrame(stakeholder_rows)
    frames["Role"] = pd.DataFrame(role_rows) if role_rows else pd.DataFrame(columns=["id", "name", "stakeholder_id"])

    by_sheet: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fact in package.facts:
        row = _fact_row(fact)
        sheet = _KIND_TO_SHEET.get(row["kind"], row["sheet"] or "RequirementNode")
        by_sheet[sheet].append(row)

    preferred_order = [
        "Feature",
        "Goal",
        "Requirement",
        "Constraint",
        "Assumption",
        "Dependency",
        "Task",
        "Qual_Scenario",
        "RequirementNode",
    ]
    for sheet in preferred_order:
        if sheet in by_sheet:
            frames[sheet] = pd.DataFrame(by_sheet.pop(sheet))
    for sheet, rows in sorted(by_sheet.items()):
        frames[sheet] = pd.DataFrame(rows)

    frames["Relationships"] = pd.DataFrame(_relationships(package))
    return frames


def default_export_path(package: ScenarioPackage, *, scenarios_root: Path | None = None) -> Path:
    root = scenarios_root or Path("scenarios")
    return root / package.meta.slug / "exports" / f"{package.meta.slug}-workbook.xlsx"


def export_package_to_excel(
    package: ScenarioPackage,
    output_path: Path | str | None = None,
    *,
    scenarios_root: Path | None = None,
) -> Path:
    """Write Excel workbook for ``package``; return the path written."""
    path = Path(output_path) if output_path else default_export_path(package, scenarios_root=scenarios_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = build_workbook_frames(package)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, frame in frames.items():
            # Excel sheet names max 31 chars
            safe = sheet_name[:31]
            frame.to_excel(writer, sheet_name=safe, index=False)
    return path
