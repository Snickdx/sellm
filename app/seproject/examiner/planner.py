"""Evidence-grounded question plan generation from a frozen repository index."""

from __future__ import annotations

from typing import Any

from app.seproject.examiner.competencies import COMPETENCIES


def _pick_symbol(index: dict[str, Any], offset: int = 0) -> dict[str, Any] | None:
    symbols = index.get("symbols") or []
    if not symbols:
        return None
    return symbols[offset % len(symbols)]


def _pick_test(index: dict[str, Any], offset: int = 0) -> dict[str, Any] | None:
    tests = index.get("tests") or []
    if not tests:
        return None
    return tests[offset % len(tests)]


def _pick_file(index: dict[str, Any], offset: int = 0) -> dict[str, Any] | None:
    files = [f for f in (index.get("files") or []) if f.get("language") in {"python", "typescript", "javascript"}]
    if not files:
        files = list(index.get("files") or [])
    if not files:
        return None
    return files[offset % len(files)]


def _code_ref(path: str, line_start: int, line_end: int, sha: str) -> dict[str, Any]:
    return {"path": path, "line_range": [line_start, line_end], "sha": sha}


def _question(
    *,
    competency: str,
    difficulty: str,
    target_user_id: str,
    prompt: str,
    code_refs: dict[str, Any],
    expected_concepts: list[str],
    rubric: str,
    follow_ups: list[str],
    hypothetical: bool = False,
) -> dict[str, Any]:
    return {
        "competency": competency,
        "difficulty": difficulty,
        "target_user_id": target_user_id,
        "prompt": prompt,
        "code_refs": code_refs,
        "expected_concepts": expected_concepts,
        "rubric": rubric,
        "follow_ups": follow_ups,
        "hypothetical": hypothetical,
    }


def generate_question_plan(
    *,
    participant_user_ids: list[int],
    index: dict[str, Any],
    questions_per_student: int | None = None,
) -> dict[str, Any]:
    """
    Build a balanced plan: each student gets one question per competency by default
    (capped by questions_per_student if provided).
    """
    sha = str(index.get("commit_sha") or "")
    competencies = list(COMPETENCIES)
    if questions_per_student is not None:
        competencies = competencies[: max(1, questions_per_student)]

    questions: list[dict[str, Any]] = []
    coverage: dict[str, list[str]] = {str(uid): [] for uid in participant_user_ids}
    uncertainties: list[str] = []

    if not (index.get("files") or []):
        uncertainties.append("Repository index has no files; questions marked hypothetical.")

    for student_offset, user_id in enumerate(participant_user_ids):
        uid = str(user_id)
        for comp_offset, competency in enumerate(competencies):
            idx = student_offset + comp_offset
            if competency == "architecture":
                sym = _pick_symbol(index, idx)
                if sym:
                    q = _question(
                        competency=competency,
                        difficulty="medium",
                        target_user_id=uid,
                        prompt=(
                            f"Looking at `{sym['name']}` in `{sym['path']}` "
                            f"(lines {sym['line_start']}–{sym.get('line_end', sym['line_start'])}), "
                            "what responsibility does this unit own, and what would you keep outside it?"
                        ),
                        code_refs=_code_ref(
                            sym["path"], sym["line_start"], sym.get("line_end", sym["line_start"]), sha
                        ),
                        expected_concepts=["responsibility", "boundary", "cohesion"],
                        rubric="5 cites the unit and tradeoffs; 3 names role vaguely; 1 generic pattern talk only.",
                        follow_ups=["What breaks if this is inlined into a caller?"],
                    )
                else:
                    uncertainties.append(f"No symbols for architecture question (student {uid}).")
                    q = _question(
                        competency=competency,
                        difficulty="medium",
                        target_user_id=uid,
                        prompt="If you added a new module boundary in this repo, where would you place it and why?",
                        code_refs={"path": None, "line_range": None, "sha": sha},
                        expected_concepts=["modularity", "coupling"],
                        rubric="Score reasoning quality; no concrete citation available.",
                        follow_ups=["What dependency would you forbid across that boundary?"],
                        hypothetical=True,
                    )
            elif competency == "code":
                sym = _pick_symbol(index, idx + 1) or _pick_file(index, idx)
                if sym and "name" in sym:
                    q = _question(
                        competency=competency,
                        difficulty="medium",
                        target_user_id=uid,
                        prompt=(
                            f"Walk through `{sym['name']}` in `{sym['path']}`. "
                            "What inputs matter, and what failure modes should callers handle?"
                        ),
                        code_refs=_code_ref(
                            sym["path"], sym["line_start"], sym.get("line_end", sym["line_start"]) + 15, sha
                        ),
                        expected_concepts=["control_flow", "validation", "errors"],
                        rubric="5 traces behavior with code; 3 partial walkthrough; 1 restates names only.",
                        follow_ups=["What test would you add for a failure path?"],
                    )
                elif sym:
                    q = _question(
                        competency=competency,
                        difficulty="medium",
                        target_user_id=uid,
                        prompt=f"Open `{sym['path']}`. What is this file's main job in the system?",
                        code_refs=_code_ref(sym["path"], 1, min(40, sym.get("line_count") or 40), sha),
                        expected_concepts=["purpose", "dependencies"],
                        rubric="5 explains role with references; 3 vague; 1 off-topic.",
                        follow_ups=["Which function would you change first for a new requirement?"],
                    )
                else:
                    uncertainties.append(f"No code files for code question (student {uid}).")
                    q = _question(
                        competency=competency,
                        difficulty="easy",
                        target_user_id=uid,
                        prompt="Describe how you would locate the entry point for a new feature in an unfamiliar repo.",
                        code_refs={"path": None, "line_range": None, "sha": sha},
                        expected_concepts=["navigation", "readme", "tests"],
                        rubric="Process quality only; hypothetical.",
                        follow_ups=[],
                        hypothetical=True,
                    )
            elif competency == "testing":
                test = _pick_test(index, idx)
                if test:
                    q = _question(
                        competency=competency,
                        difficulty="medium",
                        target_user_id=uid,
                        prompt=(
                            f"In `{test['path']}`, what behavior is being protected, "
                            "and what important case is still missing?"
                        ),
                        code_refs=_code_ref(test["path"], 1, min(40, test.get("line_count") or 40), sha),
                        expected_concepts=["assertion", "coverage_gap", "regression"],
                        rubric="5 names protected behavior + gap; 3 one of those; 1 generic testing talk.",
                        follow_ups=["How would you make the failure message actionable?"],
                    )
                else:
                    uncertainties.append(f"No tests indexed; testing question hypothetical (student {uid}).")
                    q = _question(
                        competency=competency,
                        difficulty="medium",
                        target_user_id=uid,
                        prompt="This snapshot has little/no test evidence. What first tests would you add and why?",
                        code_refs={"path": None, "line_range": None, "sha": sha},
                        expected_concepts=["regression", "critical_path"],
                        rubric="Judge prioritization; mark hypothetical.",
                        follow_ups=["Which failure would users notice first?"],
                        hypothetical=True,
                    )
            elif competency == "requirements":
                file_rec = _pick_file(index, idx)
                path = file_rec["path"] if file_rec else None
                q = _question(
                    competency=competency,
                    difficulty="medium",
                    target_user_id=uid,
                    prompt=(
                        (
                            f"Given `{path}`, which stakeholder need does this implementation serve, "
                            "and what acceptance check would prove it?"
                        )
                        if path
                        else "Which stakeholder need did your team prioritize first, and how is it verified?"
                    ),
                    code_refs=_code_ref(path, 1, 30, sha) if path else {"path": None, "line_range": None, "sha": sha},
                    expected_concepts=["stakeholder", "acceptance", "traceability"],
                    rubric="5 links need→code→check; 3 partial link; 1 no stakeholder framing.",
                    follow_ups=["What requirement remains ambiguous?"],
                    hypothetical=path is None,
                )
            else:  # ai_engineering
                file_rec = _pick_file(index, idx + 2)
                path = file_rec["path"] if file_rec else None
                q = _question(
                    competency=competency,
                    difficulty="medium",
                    target_user_id=uid,
                    prompt=(
                        "Where did AI assistance most influence this codebase, and how did you verify "
                        f"the result{f' (consider `{path}`)' if path else ''}?"
                    ),
                    code_refs=_code_ref(path, 1, 25, sha) if path else {"path": None, "line_range": None, "sha": sha},
                    expected_concepts=["verification", "ownership", "review"],
                    rubric="5 describes verification steps; 3 mentions AI use only; 1 denies process entirely without reason.",
                    follow_ups=["What would you refuse to accept from an agent without tests?"],
                    hypothetical=path is None,
                )

            questions.append(q)
            coverage[uid].append(competency)

    ordered: list[dict[str, Any]] = []
    for user_id in participant_user_ids:
        uid = str(user_id)
        ordered.extend([q for q in questions if q["target_user_id"] == uid])

    for i, q in enumerate(ordered):
        q["sequence"] = i

    return {
        "repository_sha": sha,
        "competencies": list(COMPETENCIES),
        "questions": ordered,
        "coverage": coverage,
        "uncertainties": uncertainties,
        "planner_version": "m5-planner-v1",
    }
