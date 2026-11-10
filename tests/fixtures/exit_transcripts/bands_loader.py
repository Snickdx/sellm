"""Load per-scenario exit-interview band fixtures and build SessionBundles."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.course.examiner.planner import generate_question_plan
from app.course.examiner.state import SessionBundle
from app.models.exit import (
    ExitInterviewSession,
    InterviewAnswer,
    InterviewParticipant,
    InterviewQuestion,
)

_ROOT = Path(__file__).resolve().parent
REQUIRED_COMPETENCIES = {
    "special_feature_pattern",
    "design_to_code",
    "feature_ownership",
    "testing",
    "verification",
}


def list_scenario_slugs() -> list[str]:
    return sorted(
        p.name
        for p in _ROOT.iterdir()
        if p.is_dir() and (p / "bands.yaml").is_file()
    )


def bands_path(scenario_slug: str) -> Path:
    return _ROOT / scenario_slug / "bands.yaml"


def load_bands(scenario_slug: str) -> dict[str, Any]:
    path = bands_path(scenario_slug)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid bands fixture: {path}")
    if data.get("scenario_slug") != scenario_slug:
        raise ValueError(
            f"{path}: scenario_slug={data.get('scenario_slug')!r} != {scenario_slug!r}"
        )
    return data


def build_band_bundle(
    scenario_slug: str,
    band_key: str,
) -> tuple[SessionBundle, dict[str, Any], dict[str, Any]]:
    fixture = load_bands(scenario_slug)
    bands = fixture.get("bands") or {}
    if band_key not in bands:
        raise KeyError(f"Unknown band {band_key!r} for {scenario_slug}; have {sorted(bands)}")
    band = bands[band_key]
    slug = fixture["scenario_slug"]
    sha = fixture.get("repository_sha") or fixture["index"]["commit_sha"]
    plan = generate_question_plan(
        participant_user_ids=[-1],
        index=fixture["index"],
        scenario_slug=slug,
    )

    session = ExitInterviewSession(
        id=f"fixture-{slug}-{band_key}",
        team_id="fixture-team",
        repository_submission_id="fixture-repo",
        status="lecturer_review",
    )
    participant = InterviewParticipant(
        session_id=session.id,
        user_id=-1,
        display_name=band.get("student_display_name") or f"{slug}-{band_key}",
        turn_order=0,
        consent_status="granted",
    )

    answers_by_q: dict[str, list[InterviewAnswer]] = {}
    questions: list[InterviewQuestion] = []
    answer_map: dict[str, str] = band.get("answers") or {}

    for q in plan["questions"]:
        comp = q["competency"]
        if comp not in answer_map:
            raise KeyError(f"{slug}/{band_key} missing answer for {comp}")
        text = str(answer_map[comp]).strip()
        iq = InterviewQuestion(
            id=f"q-{slug}-{band_key}-{comp}",
            session_id=session.id,
            target_user_id=-1,
            sequence=int(q["sequence"]),
            competency=comp,
            difficulty=q.get("difficulty") or "medium",
            prompt=q["prompt"],
            code_refs=q.get("code_refs") or {},
            expected_concepts=list(q.get("expected_concepts") or []),
            rubric=q.get("rubric") or "",
            follow_ups=list(q.get("follow_ups") or []),
            hypothetical=bool(q.get("hypothetical")),
            status="answered",
        )
        ans = InterviewAnswer(
            id=f"a-{slug}-{band_key}-{comp}",
            question_id=iq.id,
            user_id=-1,
            text=text,
            is_probe=False,
            modality="text",
        )
        questions.append(iq)
        answers_by_q[iq.id] = [ans]

    bundle = SessionBundle(
        session=session,
        participants=[participant],
        questions=questions,
        answers_by_question=answers_by_q,
        assessments=[],
        users_by_id={},
    )
    meta = {
        "scenario_slug": slug,
        "repository_sha": sha,
        "band_key": band_key,
        "label": band.get("label"),
        "expected_score_range": list(band.get("expected_score_range") or [1, 5]),
    }
    return bundle, plan, meta


def render_band_transcript(scenario_slug: str, band_key: str) -> str:
    bundle, _plan, meta = build_band_bundle(scenario_slug, band_key)
    title = scenario_slug.replace("-", " ").title()
    lines = [
        f"# {title} exit transcript — {meta['band_key']} ({meta.get('label')})",
        "",
        f"Scenario: `{meta['scenario_slug']}`  ",
        f"SHA: `{meta['repository_sha']}`  ",
        f"Expected provisional score range: {meta['expected_score_range']}",
        "",
    ]
    for q in sorted(bundle.questions, key=lambda x: x.sequence):
        ans = bundle.answers_for(q.id)[0]
        lines.append(f"## Q{q.sequence + 1}. `{q.competency}`")
        lines.append("")
        lines.append(f"**Examiner:** {q.prompt}")
        lines.append("")
        lines.append(f"**Student:** {ans.text}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# Back-compat aliases used by older library-only tests
def load_library_bands() -> dict[str, Any]:
    return load_bands("library")


def build_library_band_bundle(band_key: str):
    return build_band_bundle("library", band_key)
