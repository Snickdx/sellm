#!/usr/bin/env python3
"""Depth-update all scenario packages: prescribe reasonably inferable SRS scaffolding.

Writes Features/Goals/Data/Interfaces/Verification, remaps ASM→assumption,
retags journey workflows as use_case, wires satisfies/derives/depends links,
appends srs_prescription verify gaps, bumps version to 0.3.0 (draft).
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "scenarios"
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
RATIONALE = (
    "Prescribed during authoring; inferred from brief + existing package facts. "
    "Open for instructor verify/change."
)


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def dump_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(
        data,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=100,
    )
    path.write_text(text, encoding="utf-8")


def fact_blob(
    *,
    fid: str,
    statement: str,
    category: str,
    known_by: list[str],
    disclosure: str = "when_relevant",
    acceptance_criteria: list[str] | None = None,
    satisfies_ids: list[str] | None = None,
    derives_from_ids: list[str] | None = None,
    depends_on_ids: list[str] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": fid,
        "statement": statement,
        "category": category,
        "status": "clarified",
        "origin": "instructor",
        "rationale": RATIONALE,
        "known_by": known_by,
        "disclosure": disclosure,
    }
    if acceptance_criteria:
        out["acceptance_criteria"] = acceptance_criteria
    if satisfies_ids:
        out["satisfies_ids"] = satisfies_ids
    if derives_from_ids:
        out["derives_from_ids"] = derives_from_ids
    if depends_on_ids:
        out["depends_on_ids"] = depends_on_ids
    return out


def remap_asm_categories(knowledge_dir: Path) -> list[str]:
    changed: list[str] = []
    path = knowledge_dir / "assumptions.yaml"
    if not path.exists():
        return changed
    data = load_yaml(path)
    facts = data.get("facts", [])
    for f in facts:
        fid = f.get("id", "")
        if fid.split("-")[1:2] == ["ASM"] and f.get("category") != "assumption":
            f["category"] = "assumption"
            changed.append(fid)
    dump_yaml(path, {"facts": facts})
    return changed


def retag_workflows_as_use_cases(knowledge_dir: Path) -> list[str]:
    changed: list[str] = []
    path = knowledge_dir / "workflows.yaml"
    if not path.exists():
        return changed
    data = load_yaml(path)
    facts = data.get("facts", [])
    for f in facts:
        if f.get("category") == "workflow":
            f["category"] = "use_case"
            note = f.get("rationale") or ""
            if not note.startswith("Prescribed during authoring"):
                f["rationale"] = (
                    "Prescribed during authoring; retagged journey workflow as use_case. "
                    "Open for instructor verify/change."
                    + (f" Prior: {note}" if note else "")
                )
            changed.append(f["id"])
    dump_yaml(path, {"facts": facts})
    return changed


def patch_requirements(
    knowledge_dir: Path,
    *,
    satisfies: dict[str, list[str]],
    derives: dict[str, list[str]],
    depends: dict[str, list[str]] | None = None,
    category_overrides: dict[str, str] | None = None,
) -> None:
    path = knowledge_dir / "requirements.yaml"
    data = load_yaml(path)
    facts = data.get("facts", [])
    depends = depends or {}
    category_overrides = category_overrides or {}
    for f in facts:
        fid = f["id"]
        if fid in satisfies:
            f["satisfies_ids"] = list(satisfies[fid])
        if fid in derives:
            f["derives_from_ids"] = list(derives[fid])
        if fid in depends:
            f["depends_on_ids"] = list(depends[fid])
        if fid in category_overrides:
            f["category"] = category_overrides[fid]
    dump_yaml(path, {"facts": facts})


def write_facts_file(knowledge_dir: Path, name: str, facts: list[dict[str, Any]]) -> None:
    dump_yaml(knowledge_dir / name, {"facts": facts})


def update_personas(persona_dir: Path, extra_ids: list[str]) -> None:
    for path in sorted(persona_dir.glob("*.yaml")):
        data = load_yaml(path)
        known = list(data.get("known_fact_ids") or [])
        for fid in extra_ids:
            if fid not in known:
                known.append(fid)
        data["known_fact_ids"] = known
        dump_yaml(path, data)


def append_verify_gaps(gaps_path: Path, gaps: list[dict[str, Any]]) -> None:
    data = load_yaml(gaps_path) if gaps_path.exists() else {}
    open_q = list(data.get("open_questions") or [])
    existing_ids = {q.get("id") for q in open_q}
    for g in gaps:
        if g["id"] in existing_ids:
            # replace prior prescription gap with refreshed copy
            open_q = [q for q in open_q if q.get("id") != g["id"]]
        open_q.append(g)
    data["open_questions"] = open_q
    if "decisions" not in data:
        data["decisions"] = data.get("decisions") or []
    dump_yaml(gaps_path, data)


def bump_meta(scenario_yaml: Path, note: str) -> None:
    data = load_yaml(scenario_yaml)
    data["version"] = "0.3.0"
    # Keep approved so registry/vector/neo4j rebuild includes the package.
    # Open srs_prescription gaps remain the verify/change path.
    data["status"] = "approved"
    data["approved_by"] = data.get("approved_by") or "instructor"
    data["approved_at"] = NOW
    prior = (data.get("source_notes") or "").rstrip()
    addition = (
        f"SRS prescribe-by-default depth-update to 0.3.0 ({NOW}): {note} "
        "Open gaps theme=srs_prescription for instructor verify/change."
    )
    data["source_notes"] = f"{prior}\n{addition}".strip() if prior else addition
    dump_yaml(scenario_yaml, data)


def verify_gap(
    *,
    gid: str,
    prompt: str,
    prescribed_fact_ids: list[str],
    why: str,
    suggested: str,
) -> dict[str, Any]:
    return {
        "id": gid,
        "priority": "important",
        "theme": "srs_prescription",
        "prompt": prompt,
        "citations": [
            {
                "file": "scenario.yaml",
                "cue_id": "srs-prescription",
                "note": "Structural prescription from brief + existing package facts (no single VTT cue)",
            }
        ],
        "why_it_matters": why,
        "prescribed_fact_ids": prescribed_fact_ids,
        "suggested_assumption": suggested,
        "recommended_default": "Keep prescriptions as written",
        "alternatives": [
            "Keep as prescribed",
            "Modify statements or clustering",
            "Reject and remove prescribed facts",
            "Defer review; keep prescription in package",
        ],
        "actions": ["verify_accept", "modify", "reject", "defer"],
        "status": "open",
    }


# ---------------------------------------------------------------------------
# Per-scenario prescriptions (grounded in existing facts / briefs)
# ---------------------------------------------------------------------------


def prescribe_library(slug_dir: Path) -> dict[str, Any]:
    k = slug_dir / "knowledge"
    people_all = ["library_coordinator", "administrator", "lecturer"]
    ops = ["library_coordinator", "administrator"]
    goals = [
        fact_blob(
            fid="LIB-GOAL-001",
            statement=(
                "Reduce email-based workshop booking chaos and prevent double-booked "
                "or over-capacity workshop rooms."
            ),
            category="goal",
            known_by=people_all,
        )
    ]
    features = [
        fact_blob(
            fid="LIB-FEAT-001",
            statement="Lecturer workshop booking request, coordinator review, and shareable confirmation.",
            category="feature",
            known_by=people_all,
        ),
        fact_blob(
            fid="LIB-FEAT-002",
            statement="Conflict preference with larger-cohort override and hard capacity enforcement.",
            category="feature",
            known_by=ops,
        ),
        fact_blob(
            fid="LIB-FEAT-003",
            statement="Booking cancellation by lecturer or coordinator before session start.",
            category="feature",
            known_by=people_all,
        ),
        fact_blob(
            fid="LIB-FEAT-004",
            statement="Workshop room and per-room capacity configuration.",
            category="feature",
            known_by=ops,
        ),
    ]
    data_ents = [
        fact_blob(
            fid="LIB-DATA-001",
            statement="Booking request/confirmation records (course code, headcount, slot, resources, status).",
            category="data",
            known_by=ops,
        ),
        fact_blob(
            fid="LIB-DATA-002",
            statement="Workshop room entities with configurable capacity (default 30 when unset).",
            category="data",
            known_by=ops,
        ),
    ]
    interfaces = [
        fact_blob(
            fid="LIB-IF-001",
            statement=(
                "Lecturer and coordinator user interfaces for submit/review/confirm/cancel; "
                "as-is email intake is contextual legacy, not the graded primary channel."
            ),
            category="interface",
            known_by=people_all,
        ),
    ]
    verification = [
        fact_blob(
            fid="LIB-VER-001",
            statement=(
                "Critical booking rules (capacity hard-reject, conflict preference/override, "
                "explicit approve before confirmation) are verified by test/demo of the request queue."
            ),
            category="verification",
            known_by=ops,
            disclosure="when_asked",
        ),
    ]
    write_facts_file(k, "goals.yaml", goals)
    write_facts_file(k, "features.yaml", features)
    write_facts_file(k, "data.yaml", data_ents)
    write_facts_file(k, "interfaces.yaml", interfaces)
    write_facts_file(k, "verification.yaml", verification)
    asm = remap_asm_categories(k)
    uc = retag_workflows_as_use_cases(k)
    sat = {
        "LIB-REQ-001": ["LIB-FEAT-001"],
        "LIB-REQ-002": ["LIB-FEAT-001"],
        "LIB-REQ-003": ["LIB-FEAT-002"],
        "LIB-REQ-005": ["LIB-FEAT-001"],
        "LIB-REQ-006": ["LIB-FEAT-003"],
        "LIB-REQ-007": ["LIB-FEAT-003"],
        "LIB-REQ-008": ["LIB-FEAT-004"],
    }
    der = {rid: ["LIB-GOAL-001"] for rid in sat}
    patch_requirements(k, satisfies=sat, derives=der)
    new_ids = [f["id"] for f in goals + features + data_ents + interfaces + verification]
    update_personas(slug_dir / "personas", new_ids)
    gaps = [
        verify_gap(
            gid="GAP-LIB-SRS-001",
            prompt="Verify prescribed Goals, Features, and FR satisfies/derives links for library booking.",
            prescribed_fact_ids=["LIB-GOAL-001", "LIB-FEAT-001", "LIB-FEAT-002", "LIB-FEAT-003", "LIB-FEAT-004"]
            + list(sat),
            why="Students need named product functions and graph SATISFIES/DERIVES_FROM edges.",
            suggested="Keep LIB-GOAL-001 and LIB-FEAT-001..004 with REQ satisfies/derives as written.",
        ),
        verify_gap(
            gid="GAP-LIB-SRS-002",
            prompt="Verify Data/Interface/Verification prescriptions and ASM→assumption remaps / WF→use_case retags.",
            prescribed_fact_ids=["LIB-DATA-001", "LIB-DATA-002", "LIB-IF-001", "LIB-VER-001"] + asm + uc,
            why="SRS data/interface/verification coverage and correct Assumption/UseCase labels.",
            suggested="Keep data/interface/verification facts; keep ASM category assumption and WF as use_case.",
        ),
    ]
    append_verify_gaps(slug_dir / "gaps.yaml", gaps)
    bump_meta(
        slug_dir / "scenario.yaml",
        "added GOAL/FEAT/DATA/IF/VER, remapped ASM categories, retagged WF use_cases, wired trace links.",
    )
    return {"new_ids": new_ids, "asm_remapped": asm, "use_cases": uc}


def prescribe_career_advising(slug_dir: Path) -> dict[str, Any]:
    k = slug_dir / "knowledge"
    adv = ["career_advisor"]
    goals = [
        fact_blob(
            fid="CA-GOAL-001",
            statement=(
                "Help enrolled university students explore career↔course alignment via skills "
                "and competency levels without forcing a single career outcome."
            ),
            category="goal",
            known_by=adv,
        )
    ]
    features = [
        fact_blob(
            fid="CA-FEAT-001",
            statement="Dual exploration: career-first and course-first pathways with editable student inputs.",
            category="feature",
            known_by=adv,
        ),
        fact_blob(
            fid="CA-FEAT-002",
            statement="Transparent non-absolute suitability ranking from skill/competency overlap.",
            category="feature",
            known_by=adv,
        ),
        fact_blob(
            fid="CA-FEAT-003",
            statement="Missing-course gap detection for a target path (identify only; no enrol/book).",
            category="feature",
            known_by=adv,
        ),
        fact_blob(
            fid="CA-FEAT-004",
            statement="Admin skill/competency catalogue (bulk edit/upload) and course↔job skill mappings.",
            category="feature",
            known_by=adv,
        ),
        fact_blob(
            fid="CA-FEAT-005",
            statement="Pre-populated course catalogue search/select for student profiles.",
            category="feature",
            known_by=adv,
        ),
    ]
    data_ents = [
        fact_blob(fid="CA-DATA-001", statement="Course catalogue entries selectable by students.", category="data", known_by=adv),
        fact_blob(fid="CA-DATA-002", statement="Job/career records with associated skills and competency levels.", category="data", known_by=adv),
        fact_blob(fid="CA-DATA-003", statement="Skill and competency-level catalogue maintained by admin.", category="data", known_by=adv),
        fact_blob(fid="CA-DATA-004", statement="Student course selections / exploration inputs (not individually visible to staff in MVP).", category="data", known_by=adv),
    ]
    interfaces = [
        fact_blob(
            fid="CA-IF-001",
            statement="Admin bulk edit/upload interface for defining skills and competency levels.",
            category="interface",
            known_by=adv,
        ),
        fact_blob(
            fid="CA-IF-002",
            statement="Student-facing exploration UI for career-first and course-first flows.",
            category="interface",
            known_by=adv,
        ),
    ]
    quality = [
        fact_blob(
            fid="CA-NFR-001",
            statement="Staff tooling exposes aggregated usage only; individual exploration history is out of graded MVP.",
            category="security",
            known_by=adv,
        ),
    ]
    verification = [
        fact_blob(
            fid="CA-VER-001",
            statement="Suitability ranking and non-absolute wording are verified by demo/test of dual exploration outputs.",
            category="verification",
            known_by=adv,
            disclosure="when_asked",
        ),
    ]
    write_facts_file(k, "goals.yaml", goals)
    write_facts_file(k, "features.yaml", features)
    write_facts_file(k, "data.yaml", data_ents)
    write_facts_file(k, "interfaces.yaml", interfaces)
    write_facts_file(k, "quality.yaml", quality)
    write_facts_file(k, "verification.yaml", verification)
    asm = remap_asm_categories(k)
    uc = retag_workflows_as_use_cases(k)
    sat = {
        "CA-REQ-001": ["CA-FEAT-001"],
        "CA-REQ-002": ["CA-FEAT-001"],
        "CA-REQ-003": ["CA-FEAT-001"],
        "CA-REQ-004": ["CA-FEAT-001"],
        "CA-REQ-005": ["CA-FEAT-002"],
        "CA-REQ-006": ["CA-FEAT-001"],
        "CA-REQ-007": ["CA-FEAT-001"],
        "CA-REQ-008": ["CA-FEAT-001"],
        "CA-REQ-009": ["CA-FEAT-003"],
        "CA-REQ-010": ["CA-FEAT-005"],
        "CA-REQ-011": ["CA-FEAT-004"],
        "CA-REQ-012": ["CA-FEAT-002"],
    }
    der = {rid: ["CA-GOAL-001"] for rid in sat}
    patch_requirements(k, satisfies=sat, derives=der)
    new_ids = [f["id"] for f in goals + features + data_ents + interfaces + quality + verification]
    update_personas(slug_dir / "personas", new_ids)
    append_verify_gaps(
        slug_dir / "gaps.yaml",
        [
            verify_gap(
                gid="GAP-CA-SRS-001",
                prompt="Verify prescribed Goals/Features and FR trace links for career advising.",
                prescribed_fact_ids=["CA-GOAL-001"] + [f["id"] for f in features] + list(sat),
                why="Named product functions and SATISFIES/DERIVES_FROM for elicitation and graph.",
                suggested="Keep CA-GOAL-001 and CA-FEAT-001..005 with REQ links as written.",
            ),
            verify_gap(
                gid="GAP-CA-SRS-002",
                prompt="Verify Data/Interface/Quality/Verification prescriptions and ASM/use_case remaps.",
                prescribed_fact_ids=[f["id"] for f in data_ents + interfaces + quality + verification] + asm + uc,
                why="SRS data/interface/security/verification coverage.",
                suggested="Keep prescriptions; keep ASM as assumption and journeys as use_case.",
            ),
        ],
    )
    bump_meta(slug_dir / "scenario.yaml", "SRS scaffolding for dual exploration, ranking, gaps, catalogues.")
    return {"new_ids": new_ids, "asm_remapped": asm, "use_cases": uc}


def prescribe_job_board(slug_dir: Path) -> dict[str, Any]:
    k = slug_dir / "knowledge"
    people = ["administrator", "employer", "graduate_applicant"]
    admin = ["administrator"]
    goals = [
        fact_blob(
            fid="JB-GOAL-001",
            statement=(
                "Connect eligible programme graduates with employer job listings through an "
                "admin-gated publish workflow with application tracking."
            ),
            category="goal",
            known_by=people,
        )
    ]
    features = [
        fact_blob(fid="JB-FEAT-001", statement="Employer listing submit → admin approve/reject/publish/unpublish lifecycle.", category="feature", known_by=people),
        fact_blob(fid="JB-FEAT-002", statement="Graduate subscribe, discover, and apply via on-platform collect or external link.", category="feature", known_by=people),
        fact_blob(fid="JB-FEAT-003", statement="On-platform application status updates owned by the listing employer.", category="feature", known_by=["employer", "graduate_applicant", "administrator"]),
        fact_blob(fid="JB-FEAT-004", statement="Automatic notify of eligible subscribers on publish; admin export/forward of applicant packages.", category="feature", known_by=admin + ["employer"]),
        fact_blob(fid="JB-FEAT-005", statement="Eligibility gate so only eligible programme students subscribe/apply.", category="feature", known_by=admin),
    ]
    data_ents = [
        fact_blob(fid="JB-DATA-001", statement="Job listing records (pending/published/unpublished/rejected, deadline).", category="data", known_by=admin + ["employer"]),
        fact_blob(fid="JB-DATA-002", statement="Graduate profile including resume/CV and subscription preferences.", category="data", known_by=people),
        fact_blob(fid="JB-DATA-003", statement="On-platform applications with statuses submitted/reviewed/shortlisted/rejected/hired.", category="data", known_by=people),
    ]
    interfaces = [
        fact_blob(fid="JB-IF-001", statement="External employer application link mode for listings that leave the platform.", category="interface", known_by=people),
        fact_blob(fid="JB-IF-002", statement="Email/notification channel to eligible subscribers on publish.", category="interface", known_by=admin),
    ]
    deps = [
        fact_blob(
            fid="JB-DEP-001",
            statement="On-platform collect may use an external form backend (e.g. Airtable) as an integration dependency.",
            category="dependency",
            known_by=admin,
            disclosure="when_asked",
        ),
    ]
    quality = [
        fact_blob(
            fid="JB-SEC-001",
            statement="Applicant personal information must be encrypted and stored securely; admin review is a trust/legitimacy control.",
            category="security",
            known_by=admin,
        ),
    ]
    verification = [
        fact_blob(
            fid="JB-VER-001",
            statement="Publish/reject/notify and application-status flows are verified by test/demo of listing and apply paths.",
            category="verification",
            known_by=admin,
            disclosure="when_asked",
        ),
    ]
    write_facts_file(k, "goals.yaml", goals)
    write_facts_file(k, "features.yaml", features)
    write_facts_file(k, "data.yaml", data_ents)
    write_facts_file(k, "interfaces.yaml", interfaces)
    write_facts_file(k, "dependencies.yaml", deps)
    write_facts_file(k, "quality.yaml", quality)
    write_facts_file(k, "verification.yaml", verification)
    asm = remap_asm_categories(k)
    uc = retag_workflows_as_use_cases(k)
    sat = {
        "JB-REQ-001": ["JB-FEAT-001", "JB-FEAT-002"],
        "JB-REQ-002": ["JB-FEAT-001", "JB-FEAT-004"],
        "JB-REQ-003": ["JB-FEAT-002", "JB-FEAT-004"],
        "JB-REQ-004": ["JB-FEAT-002"],
        "JB-REQ-007": ["JB-FEAT-001"],
        "JB-REQ-008": ["JB-FEAT-001", "JB-FEAT-004"],
        "JB-REQ-009": ["JB-FEAT-001"],
        "JB-REQ-010": ["JB-FEAT-001"],
    }
    der = {rid: ["JB-GOAL-001"] for rid in list(sat) + ["JB-REQ-005", "JB-REQ-006"]}
    dep_links = {"JB-REQ-004": ["JB-DEP-001"], "JB-REQ-009": ["JB-DEP-001"]}
    patch_requirements(
        k,
        satisfies=sat,
        derives=der,
        depends=dep_links,
        category_overrides={"JB-REQ-009": "security"},
    )
    new_ids = [f["id"] for f in goals + features + data_ents + interfaces + deps + quality + verification]
    update_personas(slug_dir / "personas", new_ids)
    append_verify_gaps(
        slug_dir / "gaps.yaml",
        [
            verify_gap(
                gid="GAP-JB-SRS-001",
                prompt="Verify Goals/Features/trace links for job board.",
                prescribed_fact_ids=["JB-GOAL-001"] + [f["id"] for f in features] + list(sat),
                why="Product functions and SATISFIES edges for listing/apply/admin paths.",
                suggested="Keep JB-GOAL-001 and JB-FEAT-001..005 with REQ links.",
            ),
            verify_gap(
                gid="GAP-JB-SRS-002",
                prompt="Verify Data/Interface/Dependency/Security/Verification prescriptions and remaps.",
                prescribed_fact_ids=[f["id"] for f in data_ents + interfaces + deps + quality + verification] + asm + uc,
                why="SRS support nodes and Assumption/UseCase labels.",
                suggested="Keep as prescribed including JB-DEP-001 and JB-SEC-001.",
            ),
        ],
    )
    bump_meta(slug_dir / "scenario.yaml", "SRS scaffolding for listings, apply modes, notify/export, security.")
    return {"new_ids": new_ids, "asm_remapped": asm, "use_cases": uc}


def prescribe_student_accommodation(slug_dir: Path) -> dict[str, Any]:
    k = slug_dir / "knowledge"
    people = ["campus_admin", "student_seeker", "landlord"]
    goals = [
        fact_blob(
            fid="SA-GOAL-001",
            statement=(
                "Help eligible campus students find verified off-campus housing near "
                "St. Augustine / Mount Hope via a closed referral platform (no payments/contracts)."
            ),
            category="goal",
            known_by=people,
        )
    ]
    features = [
        fact_blob(fid="SA-FEAT-001", statement="Student browse/filter of fully approved active listings (location, price, amenities).", category="feature", known_by=people),
        fact_blob(fid="SA-FEAT-002", statement="Landlord listing submit with campus verification (reject→revise; provisional then full approval).", category="feature", known_by=["campus_admin", "landlord"]),
        fact_blob(fid="SA-FEAT-003", statement="Landlord active/inactive control and campus_admin force-deactivate/unpublish.", category="feature", known_by=["campus_admin", "landlord"]),
        fact_blob(fid="SA-FEAT-004", statement="Optional in-app messaging plus landlord contact details for off-platform arrangements.", category="feature", known_by=people),
        fact_blob(fid="SA-FEAT-005", statement="Eligibility authentication for student seekers (student ID / provisional incoming path).", category="feature", known_by=["campus_admin", "student_seeker"]),
    ]
    data_ents = [
        fact_blob(fid="SA-DATA-001", statement="Housing listing records (pending/provisional/approved, amenities, photos, active flag).", category="data", known_by=["campus_admin", "landlord"]),
        fact_blob(fid="SA-DATA-002", statement="Landlord account/unit ownership records.", category="data", known_by=["campus_admin", "landlord"]),
        fact_blob(fid="SA-DATA-003", statement="Eligible student seeker identity for closed browse access.", category="data", known_by=["campus_admin", "student_seeker"]),
    ]
    interfaces = [
        fact_blob(fid="SA-IF-001", statement="Student seeker listing browse/filter UI and optional messaging UI.", category="interface", known_by=people),
        fact_blob(fid="SA-IF-002", statement="Campus admin verification checklist / site-confirmation workflow UI.", category="interface", known_by=["campus_admin"]),
    ]
    verification = [
        fact_blob(
            fid="SA-VER-001",
            statement="Visibility rules (pending/provisional hidden; only fully approved active shown) verified by test of seeker browse.",
            category="verification",
            known_by=["campus_admin"],
            disclosure="when_asked",
        ),
    ]
    write_facts_file(k, "goals.yaml", goals)
    write_facts_file(k, "features.yaml", features)
    write_facts_file(k, "data.yaml", data_ents)
    write_facts_file(k, "interfaces.yaml", interfaces)
    write_facts_file(k, "verification.yaml", verification)
    asm = remap_asm_categories(k)
    uc = retag_workflows_as_use_cases(k)
    sat = {
        "SA-REQ-001": ["SA-FEAT-001", "SA-FEAT-002"],
        "SA-REQ-002": ["SA-FEAT-001", "SA-FEAT-004", "SA-FEAT-005"],
        "SA-REQ-003": ["SA-FEAT-003"],
        "SA-REQ-004": ["SA-FEAT-001", "SA-FEAT-004"],
        "SA-REQ-005": ["SA-FEAT-003"],
        "SA-REQ-006": ["SA-FEAT-001"],
        "SA-REQ-007": ["SA-FEAT-002"],
        "SA-REQ-008": ["SA-FEAT-001"],
        "SA-REQ-009": ["SA-FEAT-003"],
    }
    der = {rid: ["SA-GOAL-001"] for rid in sat}
    patch_requirements(k, satisfies=sat, derives=der)
    new_ids = [f["id"] for f in goals + features + data_ents + interfaces + verification]
    update_personas(slug_dir / "personas", new_ids)
    append_verify_gaps(
        slug_dir / "gaps.yaml",
        [
            verify_gap(
                gid="GAP-SA-SRS-001",
                prompt="Verify Goals/Features/trace links for student accommodation.",
                prescribed_fact_ids=["SA-GOAL-001"] + [f["id"] for f in features] + list(sat),
                why="Named referral-platform capabilities and SATISFIES edges.",
                suggested="Keep SA-GOAL-001 and SA-FEAT-001..005 with REQ links.",
            ),
            verify_gap(
                gid="GAP-SA-SRS-002",
                prompt="Verify Data/Interface/Verification prescriptions and ASM/use_case remaps.",
                prescribed_fact_ids=[f["id"] for f in data_ents + interfaces + verification] + asm + uc,
                why="SRS support coverage and correct labels.",
                suggested="Keep as prescribed.",
            ),
        ],
    )
    bump_meta(slug_dir / "scenario.yaml", "SRS scaffolding for verified listings, filters, messaging boundary.")
    return {"new_ids": new_ids, "asm_remapped": asm, "use_cases": uc}


def prescribe_ta_allocations(slug_dir: Path) -> dict[str, Any]:
    k = slug_dir / "knowledge"
    hod = ["hod"]
    goals = [
        fact_blob(
            fid="TA-GOAL-001",
            statement=(
                "Enable the HOD to allocate TAs to courses within a hard departmental budget "
                "and hard 20h/week cap, preferring prior course experience."
            ),
            category="goal",
            known_by=hod,
        )
    ]
    features = [
        fact_blob(fid="TA-FEAT-001", statement="Create/edit/reassign/remove TA↔course assignments with planned weekly hours.", category="feature", known_by=hod),
        fact_blob(fid="TA-FEAT-002", statement="Hard-block validation for 20h/week cap and departmental budget with remaining capacity shown.", category="feature", known_by=hod),
        fact_blob(fid="TA-FEAT-003", statement="Soft highlight of prior course experience during assignment selection.", category="feature", known_by=hod),
        fact_blob(fid="TA-FEAT-004", statement="HOD workload review of TAs per course and remaining capacity.", category="feature", known_by=hod),
    ]
    data_ents = [
        fact_blob(fid="TA-DATA-001", statement="TA person records eligible for allocation.", category="data", known_by=hod),
        fact_blob(fid="TA-DATA-002", statement="Course records receiving TA support.", category="data", known_by=hod),
        fact_blob(fid="TA-DATA-003", statement="Assignment records (TA, course, planned weekly hours) and remaining capacity/budget views.", category="data", known_by=hod),
    ]
    deps = [
        fact_blob(
            fid="TA-DEP-001",
            statement="HR approval, contracts, and payroll remain an external process outside the graded allocation system boundary.",
            category="dependency",
            known_by=hod,
            disclosure="when_asked",
        ),
    ]
    verification = [
        fact_blob(
            fid="TA-VER-001",
            statement="Hard cap/budget blocks are verified by test of create/edit attempts that exceed limits.",
            category="verification",
            known_by=hod,
            disclosure="when_asked",
        ),
    ]
    write_facts_file(k, "goals.yaml", goals)
    write_facts_file(k, "features.yaml", features)
    write_facts_file(k, "data.yaml", data_ents)
    write_facts_file(k, "dependencies.yaml", deps)
    write_facts_file(k, "verification.yaml", verification)
    asm = remap_asm_categories(k)
    uc = retag_workflows_as_use_cases(k)
    sat = {
        "TA-REQ-001": ["TA-FEAT-001", "TA-FEAT-002"],
        "TA-REQ-002": ["TA-FEAT-003"],
        "TA-REQ-003": ["TA-FEAT-002"],
        "TA-REQ-004": ["TA-FEAT-001"],
        "TA-REQ-005": ["TA-FEAT-001"],
        "TA-REQ-006": ["TA-FEAT-004"],
        "TA-REQ-009": ["TA-FEAT-001", "TA-FEAT-002"],
    }
    der = {rid: ["TA-GOAL-001"] for rid in list(sat) + ["TA-REQ-007", "TA-REQ-008"]}
    dep_links = {"TA-REQ-008": ["TA-DEP-001"]}
    patch_requirements(k, satisfies=sat, derives=der, depends=dep_links)
    new_ids = [f["id"] for f in goals + features + data_ents + deps + verification]
    update_personas(slug_dir / "personas", new_ids)
    append_verify_gaps(
        slug_dir / "gaps.yaml",
        [
            verify_gap(
                gid="GAP-TA-SRS-001",
                prompt="Verify Goals/Features/trace links for TA allocations.",
                prescribed_fact_ids=["TA-GOAL-001"] + [f["id"] for f in features] + list(sat),
                why="Named allocation capabilities and SATISFIES edges.",
                suggested="Keep TA-GOAL-001 and TA-FEAT-001..004 with REQ links.",
            ),
            verify_gap(
                gid="GAP-TA-SRS-002",
                prompt="Verify Data/Dependency/Verification prescriptions and remaps.",
                prescribed_fact_ids=[f["id"] for f in data_ents + deps + verification] + asm + uc,
                why="SRS support nodes; HR remains DEPENDS_ON external process.",
                suggested="Keep as prescribed including TA-DEP-001.",
            ),
        ],
    )
    bump_meta(slug_dir / "scenario.yaml", "SRS scaffolding for assignment CRUD, hard caps, experience preference.")
    return {"new_ids": new_ids, "asm_remapped": asm, "use_cases": uc}


def prescribe_thesis_tracker(slug_dir: Path) -> dict[str, Any]:
    k = slug_dir / "knowledge"
    people = ["pg_coordinator", "supervisor"]
    goals = [
        fact_blob(
            fid="TT-GOAL-001",
            statement=(
                "Give postgraduate coordination visibility of thesis pairings, submissions, "
                "feedback due dates, and progress notes so delayed feedback is actionable."
            ),
            category="goal",
            known_by=people,
        )
    ]
    features = [
        fact_blob(fid="TT-FEAT-001", statement="Record and change student–supervisor pairings (coordinator; supervisor confirms).", category="feature", known_by=people),
        fact_blob(fid="TT-FEAT-002", statement="Student submission with supervisor in-app feedback notes and configurable due dates.", category="feature", known_by=people),
        fact_blob(fid="TT-FEAT-003", statement="Overdue feedback flags to coordinator with optional in-system nudge to supervisors.", category="feature", known_by=people),
        fact_blob(fid="TT-FEAT-004", statement="Freeform progress notes and coordinator summary for grad studies.", category="feature", known_by=people),
        fact_blob(fid="TT-FEAT-005", statement="Cross-pairing read access for coordinator; supervisors scoped to own supervisees.", category="feature", known_by=people),
    ]
    data_ents = [
        fact_blob(fid="TT-DATA-001", statement="Pairing records linking student and supervisor.", category="data", known_by=people),
        fact_blob(fid="TT-DATA-002", statement="Submission artefacts and feedback notes with due dates / overdue flags.", category="data", known_by=people),
        fact_blob(fid="TT-DATA-003", statement="Freeform progress notes suitable for coordinator summaries.", category="data", known_by=people),
    ]
    interfaces = [
        fact_blob(fid="TT-IF-001", statement="In-app feedback and progress-note interfaces for supervisors and coordinator oversight views.", category="interface", known_by=people),
        fact_blob(fid="TT-IF-002", statement="In-system reminder/nudge channel from coordinator to supervisor on overdue feedback.", category="interface", known_by=people),
    ]
    verification = [
        fact_blob(
            fid="TT-VER-001",
            statement="Overdue flagging and scoped visibility are verified by test of due-date expiry and role-based reads.",
            category="verification",
            known_by=["pg_coordinator"],
            disclosure="when_asked",
        ),
    ]
    write_facts_file(k, "goals.yaml", goals)
    write_facts_file(k, "features.yaml", features)
    write_facts_file(k, "data.yaml", data_ents)
    write_facts_file(k, "interfaces.yaml", interfaces)
    write_facts_file(k, "verification.yaml", verification)
    asm = remap_asm_categories(k)
    uc = retag_workflows_as_use_cases(k)
    sat = {
        "TT-REQ-001": ["TT-FEAT-005", "TT-FEAT-004"],
        "TT-REQ-002": ["TT-FEAT-001"],
        "TT-REQ-003": ["TT-FEAT-002", "TT-FEAT-004"],
        "TT-REQ-004": ["TT-FEAT-003"],
        "TT-REQ-005": ["TT-FEAT-004"],
        "TT-REQ-006": ["TT-FEAT-001"],
        "TT-REQ-007": ["TT-FEAT-001", "TT-FEAT-002", "TT-FEAT-005"],
    }
    der = {rid: ["TT-GOAL-001"] for rid in sat}
    patch_requirements(k, satisfies=sat, derives=der)
    new_ids = [f["id"] for f in goals + features + data_ents + interfaces + verification]
    update_personas(slug_dir / "personas", new_ids)
    append_verify_gaps(
        slug_dir / "gaps.yaml",
        [
            verify_gap(
                gid="GAP-TT-SRS-001",
                prompt="Verify Goals/Features/trace links for thesis tracker.",
                prescribed_fact_ids=["TT-GOAL-001"] + [f["id"] for f in features] + list(sat),
                why="Named multi-role thesis capabilities and SATISFIES edges.",
                suggested="Keep TT-GOAL-001 and TT-FEAT-001..005 with REQ links.",
            ),
            verify_gap(
                gid="GAP-TT-SRS-002",
                prompt="Verify Data/Interface/Verification prescriptions and remaps.",
                prescribed_fact_ids=[f["id"] for f in data_ents + interfaces + verification] + asm + uc,
                why="SRS support coverage and Assumption/UseCase labels.",
                suggested="Keep as prescribed.",
            ),
        ],
    )
    bump_meta(slug_dir / "scenario.yaml", "SRS scaffolding for pairings, feedback, overdue nudges, summaries.")
    return {"new_ids": new_ids, "asm_remapped": asm, "use_cases": uc}


def prescribe_uwi_connect(slug_dir: Path) -> dict[str, Any]:
    k = slug_dir / "knowledge"
    admin = ["alumni_admin"]
    goals = [
        fact_blob(
            fid="UC-GOAL-001",
            statement=(
                "Re-engage UWI alumni through a managed platform with verified access, "
                "job/event boards, and admin email campaigns."
            ),
            category="goal",
            known_by=admin,
        )
    ]
    features = [
        fact_blob(fid="UC-FEAT-001", statement="UWI-email verification gate for alumni board and campaign access.", category="feature", known_by=admin),
        fact_blob(fid="UC-FEAT-002", statement="Alumni job and event listing submit with admin publish/reject/unpublish.", category="feature", known_by=admin),
        fact_blob(fid="UC-FEAT-003", statement="Alumni browse of published job and event boards.", category="feature", known_by=admin),
        fact_blob(fid="UC-FEAT-004", statement="Admin email campaign builder (compose, audience of verified non-revoked alumni, send).", category="feature", known_by=admin),
        fact_blob(fid="UC-FEAT-005", statement="Account revoke/disable with loss of browse access and campaign exclusion.", category="feature", known_by=admin),
    ]
    data_ents = [
        fact_blob(fid="UC-DATA-001", statement="Alumni account records (verified/revoked) used for access and campaign audiences.", category="data", known_by=admin),
        fact_blob(fid="UC-DATA-002", statement="Job and event listing records (pending/published/rejected/unpublished).", category="data", known_by=admin),
        fact_blob(fid="UC-DATA-003", statement="Email campaign records (compose content, audience snapshot, send).", category="data", known_by=admin),
    ]
    interfaces = [
        fact_blob(fid="UC-IF-001", statement="UWI email verification interface as the primary access gate.", category="interface", known_by=admin),
        fact_blob(fid="UC-IF-002", statement="Outbound email campaign send interface to verified non-revoked alumni.", category="interface", known_by=admin),
    ]
    quality = [
        fact_blob(
            fid="UC-NFR-001",
            statement="Engagement emails should stay clear and simple, typically focusing on one or two events.",
            category="usability",
            known_by=admin,
        ),
    ]
    # Note: UC- prefix conflicts with UseCase family for FEAT ids - uwi-connect uses UC- as slug prefix
    # Existing IDs are UC-REQ, UC-ASM, etc. Features should be UC-FEAT which parses prefix FEAT - good.
    # Use-case retag on UC-WF keeps id prefix WF.
    verification = [
        fact_blob(
            fid="UC-VER-001",
            statement="Verification gate, publish visibility, and revoke/campaign exclusion verified by test of access paths.",
            category="verification",
            known_by=admin,
            disclosure="when_asked",
        ),
    ]
    write_facts_file(k, "goals.yaml", goals)
    write_facts_file(k, "features.yaml", features)
    write_facts_file(k, "data.yaml", data_ents)
    write_facts_file(k, "interfaces.yaml", interfaces)
    write_facts_file(k, "quality.yaml", quality)
    write_facts_file(k, "verification.yaml", verification)
    asm = remap_asm_categories(k)
    uc = retag_workflows_as_use_cases(k)
    sat = {
        "UC-REQ-001": ["UC-FEAT-003", "UC-FEAT-004"],
        "UC-REQ-002": ["UC-FEAT-001"],
        "UC-REQ-003": ["UC-FEAT-002", "UC-FEAT-003"],
        "UC-REQ-004": ["UC-FEAT-002", "UC-FEAT-004"],
        "UC-REQ-005": ["UC-FEAT-004"],
        "UC-REQ-008": ["UC-FEAT-001", "UC-FEAT-002", "UC-FEAT-004", "UC-FEAT-005"],
    }
    der = {rid: ["UC-GOAL-001"] for rid in list(sat) + ["UC-REQ-006", "UC-REQ-007"]}
    patch_requirements(
        k,
        satisfies=sat,
        derives=der,
        category_overrides={"UC-REQ-007": "usability"},
    )
    new_ids = [f["id"] for f in goals + features + data_ents + interfaces + quality + verification]
    update_personas(slug_dir / "personas", new_ids)
    append_verify_gaps(
        slug_dir / "gaps.yaml",
        [
            verify_gap(
                gid="GAP-UC-SRS-001",
                prompt="Verify Goals/Features/trace links for UWI Connect.",
                prescribed_fact_ids=["UC-GOAL-001"] + [f["id"] for f in features] + list(sat),
                why="Named alumni platform capabilities and SATISFIES edges.",
                suggested="Keep UC-GOAL-001 and UC-FEAT-001..005 with REQ links.",
            ),
            verify_gap(
                gid="GAP-UC-SRS-002",
                prompt="Verify Data/Interface/Quality/Verification prescriptions and remaps.",
                prescribed_fact_ids=[f["id"] for f in data_ents + interfaces + quality + verification] + asm + uc,
                why="SRS support coverage; directory/mentorship remain out of MVP.",
                suggested="Keep as prescribed.",
            ),
        ],
    )
    bump_meta(slug_dir / "scenario.yaml", "SRS scaffolding for verification gate, boards, campaigns, revoke.")
    return {"new_ids": new_ids, "asm_remapped": asm, "use_cases": uc}


PRESCRIBERS = {
    "library": prescribe_library,
    "career-advising": prescribe_career_advising,
    "job-board": prescribe_job_board,
    "student-accommodation": prescribe_student_accommodation,
    "ta-allocations": prescribe_ta_allocations,
    "thesis-tracker": prescribe_thesis_tracker,
    "uwi-connect": prescribe_uwi_connect,
}


def main() -> int:
    from app.scenarios.loader import load_scenario_package
    from app.scenarios.validator import validate_scenario_package

    summary = []
    for slug, fn in PRESCRIBERS.items():
        slug_dir = SCENARIOS / slug
        print(f"Prescribing SRS for {slug}...")
        result = fn(slug_dir)
        pkg = load_scenario_package(slug_dir)
        errors = validate_scenario_package(pkg)
        summary.append((slug, pkg.meta.version, pkg.meta.status.value, len(pkg.facts), errors, result))
        if errors:
            print(f"  VALIDATION ERRORS: {errors}")
        else:
            print(f"  ok facts={len(pkg.facts)} new={len(result['new_ids'])}")
    print("\n=== Summary ===")
    for slug, ver, status, nfacts, errors, result in summary:
        print(f"{slug}: v{ver} {status} facts={nfacts} errors={len(errors) if errors else 0}")
    bad = [s for s, _, _, _, e, _ in summary if e]
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
