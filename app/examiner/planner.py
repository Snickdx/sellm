"""COMP 3613 contribution-oriented exit-interview question plan.

Ordered tree per student (one ask per question; follow_ups are skip alternates):
  1. special_feature_pattern
  2. design_to_code
  3. feature_ownership
  4. testing
  5. verification

`questions_per_student` takes the first N of that order (default: all five).
Skipping a question promotes the next follow_up into a replacement so quota can still be met.
"""

from __future__ import annotations

from typing import Any

from app.examiner.competencies import COMPETENCIES
from app.examiner.scenario_focus import resolve_scenario_focus


def _focus_rank(path: str, focus_paths: list[str]) -> int | None:
    """Lower rank = earlier (higher priority) focus path; None if no match."""
    p = path.replace("\\", "/").lower()
    for i, focus in enumerate(focus_paths):
        f = focus.replace("\\", "/").lower().lstrip("./")
        if p == f or p.endswith("/" + f) or f in p:
            return i
    return None


def _prefer_focus(items: list[dict[str, Any]], focus_paths: list[str] | None) -> list[dict[str, Any]]:
    if not focus_paths:
        return items
    ranked: list[tuple[int, dict[str, Any]]] = []
    for item in items:
        rank = _focus_rank(str(item.get("path") or ""), focus_paths)
        if rank is not None:
            ranked.append((rank, item))
    if not ranked:
        return items
    ranked.sort(key=lambda t: t[0])
    return [item for _, item in ranked]


def _pick_symbol(
    index: dict[str, Any],
    offset: int = 0,
    focus_paths: list[str] | None = None,
) -> dict[str, Any] | None:
    symbols = list(index.get("symbols") or [])
    if not symbols:
        return None
    pool = _prefer_focus(symbols, focus_paths)
    return pool[offset % len(pool)]


def _pick_test(index: dict[str, Any], offset: int = 0) -> dict[str, Any] | None:
    tests = index.get("tests") or []
    if not tests:
        return None
    return tests[offset % len(tests)]


def _pick_file(
    index: dict[str, Any],
    offset: int = 0,
    focus_paths: list[str] | None = None,
) -> dict[str, Any] | None:
    files = [
        f
        for f in (index.get("files") or [])
        if f.get("language") in {"python", "typescript", "javascript"}
    ]
    if not files:
        files = list(index.get("files") or [])
    if not files:
        return None
    pool = _prefer_focus(files, focus_paths)
    return pool[offset % len(pool)]


def _pick_app_file(
    index: dict[str, Any],
    offset: int = 0,
    focus_paths: list[str] | None = None,
) -> dict[str, Any] | None:
    """Prefer non-test application files for ownership / design questions."""
    files = list(index.get("files") or [])
    app_files = []
    for f in files:
        path = str(f.get("path") or "").lower()
        if (
            "/tests/" in f"/{path}"
            or "/__tests__/" in f"/{path}"
            or path.startswith("test_")
            or path.endswith("_test.py")
            or ".test." in path
            or ".spec." in path
        ):
            continue
        if f.get("language") in {"python", "typescript", "javascript"} or not f.get("language"):
            app_files.append(f)
    pool = app_files or files
    if not pool:
        return None
    pool = _prefer_focus(pool, focus_paths)
    return pool[offset % len(pool)]


def _code_ref(path: str, line_start: int, line_end: int, sha: str) -> dict[str, Any]:
    return {"path": path, "line_range": [line_start, line_end], "sha": sha}


def _empty_ref(sha: str) -> dict[str, Any]:
    return {"path": None, "line_range": None, "sha": sha}


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


def _build_pattern_question(
    *,
    uid: str,
    focus: dict[str, Any],
    index: dict[str, Any],
    offset: int,
    sha: str,
) -> tuple[dict[str, Any], str | None]:
    special = focus["special_feature"]
    title = focus["title"]
    paths = list(focus.get("focus_paths") or [])
    sym = _pick_symbol(index, offset, paths) or _pick_app_file(index, offset, paths)
    uncertainty: str | None = None

    if sym and "name" in sym:
        cite = (
            f"`{sym['name']}` in `{sym['path']}` "
            f"(lines {sym['line_start']}–{sym.get('line_end', sym['line_start'])})"
        )
        refs = _code_ref(
            sym["path"], sym["line_start"], sym.get("line_end", sym["line_start"]), sha
        )
        hypo = False
    elif sym:
        cite = f"`{sym['path']}`"
        refs = _code_ref(sym["path"], 1, min(40, sym.get("line_count") or 40), sha)
        hypo = False
    else:
        uncertainty = f"No indexed code for pattern question (student {uid})."
        cite = "your Sprint 1 class diagram or Sprint 2 code"
        refs = _empty_ref(sha)
        hypo = True

    # One ask; follow_ups are skip-alternates (still one ask each).
    prompt = f"For «{special}» in {title}, what inherited weakness did your team target?"
    follow_ups = [
        f"Which design pattern did you identify for «{special}» in {title}, and why that one?",
        f"Where do the pattern participants show up around {cite}?",
        f"What would break in «{special}» if you had kept the inherited structure?",
    ]

    q = _question(
        competency="special_feature_pattern",
        difficulty="hard",
        target_user_id=uid,
        prompt=prompt,
        code_refs=refs,
        expected_concepts=["special_feature", "design_pattern", "inherited_defect", "participants"],
        rubric=(
            "5 names special feature, defect, pattern, and concrete participants in design/code; "
            "3 names pattern vaguely without participants; 1 generic pattern talk or wrong feature."
        ),
        follow_ups=follow_ups,
        hypothetical=hypo,
    )
    return q, uncertainty


def _build_design_to_code_question(
    *,
    uid: str,
    focus: dict[str, Any],
    index: dict[str, Any],
    offset: int,
    sha: str,
) -> tuple[dict[str, Any], str | None]:
    special = focus["special_feature"]
    paths = list(focus.get("focus_paths") or [])
    file_rec = _pick_app_file(index, offset, paths) or _pick_file(index, offset, paths)
    uncertainty: str | None = None

    if file_rec:
        path = file_rec["path"]
        prompt = (
            f"Looking at `{path}`, what design decision from your Sprint 1 class diagram "
            f"for «{special}» does this file embody?"
        )
        refs = _code_ref(path, 1, min(40, file_rec.get("line_count") or 40), sha)
        hypo = False
        path_hint = f"`{path}`"
    else:
        uncertainty = f"No files for design_to_code question (student {uid})."
        prompt = (
            f"Name one class or relationship from your Sprint 1 diagram for «{special}» "
            "that you can still point to in the code."
        )
        refs = _empty_ref(sha)
        hypo = True
        path_hint = "the implementation"

    follow_ups = [
        f"What in the Sprint 1 class diagram for «{special}» changed during Sprint 2?",
        f"What forced that design change (or kept it stable) when you reached {path_hint}?",
        "Which relationship or class was hardest to keep faithful to the diagram?",
    ]

    q = _question(
        competency="design_to_code",
        difficulty="medium",
        target_user_id=uid,
        prompt=prompt,
        code_refs=refs,
        expected_concepts=["class_diagram", "refactor", "design_drift", "pattern_participants"],
        rubric=(
            "5 links a diagram element to concrete code and explains drift or fidelity; "
            "3 describes design vaguely; 1 cannot connect diagram to implementation."
        ),
        follow_ups=follow_ups,
        hypothetical=hypo,
    )
    return q, uncertainty


def _build_ownership_question(
    *,
    uid: str,
    focus: dict[str, Any],
    index: dict[str, Any],
    offset: int,
    sha: str,
) -> tuple[dict[str, Any], str | None]:
    special = focus["special_feature"]
    paths = list(focus.get("focus_paths") or [])
    sym = _pick_symbol(index, offset + 1, paths) or _pick_app_file(index, offset + 1, paths)
    uncertainty: str | None = None

    if sym and "name" in sym:
        prompt = (
            f"What did you personally change in `{sym['name']}` (`{sym['path']}`) "
            f"for «{special}» or another task you owned?"
        )
        refs = _code_ref(
            sym["path"],
            sym["line_start"],
            sym.get("line_end", sym["line_start"]) + 15,
            sha,
        )
        hypo = False
        cite = f"`{sym['name']}` in `{sym['path']}`"
    elif sym:
        prompt = (
            f"What did you personally contribute in `{sym['path']}` "
            f"for «{special}» or another task you owned?"
        )
        refs = _code_ref(sym["path"], 1, min(40, sym.get("line_count") or 40), sha)
        hypo = False
        cite = f"`{sym['path']}`"
    else:
        uncertainty = f"No code for feature_ownership question (student {uid})."
        prompt = (
            f"Name one code path you personally implemented for «{special}» "
            "or a related MVP gap."
        )
        refs = _empty_ref(sha)
        hypo = True
        cite = "that path"

    follow_ups = [
        f"Which Trello task or PR on main proves {cite} was your work?",
        f"How does that change relate to «{special}»?",
        f"What failure mode should callers of {cite} handle?",
    ]

    q = _question(
        competency="feature_ownership",
        difficulty="medium",
        target_user_id=uid,
        prompt=prompt,
        code_refs=refs,
        expected_concepts=["owned_commits", "control_flow", "task_traceability", "failure_modes"],
        rubric=(
            "5 traces own change with code and task link; 3 partial walkthrough; "
            "1 restates teammate work or file names only."
        ),
        follow_ups=follow_ups,
        hypothetical=hypo,
    )
    return q, uncertainty


def _build_testing_question(
    *,
    uid: str,
    focus: dict[str, Any],
    index: dict[str, Any],
    offset: int,
    sha: str,
) -> tuple[dict[str, Any], str | None]:
    special = focus["special_feature"]
    test = _pick_test(index, offset)
    uncertainty: str | None = None

    if test:
        prompt = (
            f"In `{test['path']}`, what behavior of «{special}» is this test protecting?"
        )
        refs = _code_ref(test["path"], 1, min(40, test.get("line_count") or 40), sha)
        hypo = False
        path = test["path"]
    else:
        uncertainty = f"No tests indexed; testing question hypothetical (student {uid})."
        prompt = (
            f"What first automated test would you add for «{special}», and why that one?"
        )
        refs = _empty_ref(sha)
        hypo = True
        path = "a new test file"

    follow_ups = [
        f"What important failure or edge case for «{special}» is still missing from `{path}`?",
        "How would a failing assertion tell the next developer what broke?",
        "Which failure would users notice first if this test were absent?",
    ]

    q = _question(
        competency="testing",
        difficulty="medium",
        target_user_id=uid,
        prompt=prompt,
        code_refs=refs,
        expected_concepts=["special_feature_tests", "regression", "coverage_gap", "assertion"],
        rubric=(
            "5 names protected special-feature behavior plus a concrete gap; "
            "3 one of those; 1 generic testing talk."
        ),
        follow_ups=follow_ups,
        hypothetical=hypo,
    )
    return q, uncertainty


def _build_verification_question(
    *,
    uid: str,
    focus: dict[str, Any],
    index: dict[str, Any],
    offset: int,
    sha: str,
) -> tuple[dict[str, Any], str | None]:
    special = focus["special_feature"]
    paths = list(focus.get("focus_paths") or [])
    file_rec = _pick_app_file(index, offset + 2, paths) or _pick_file(index, offset + 2, paths)
    path = file_rec["path"] if file_rec else None
    uncertainty: str | None = None

    if path and file_rec:
        prompt = (
            f"Where did AI assistance or a teammate's PR most influence code you claim "
            f"near `{path}` for «{special}»?"
        )
        refs = _code_ref(path, 1, min(25, file_rec.get("line_count") or 25), sha)
        hypo = False
    else:
        uncertainty = f"No files for verification question (student {uid})."
        prompt = (
            f"Where did AI assistance or a teammate's PR most influence code you claim "
            f"for «{special}»?"
        )
        refs = _empty_ref(sha)
        hypo = True

    follow_ups = [
        "How did you personally verify that change was correct and still explainable by you?",
        "What would you refuse to accept from an agent or teammate without tests?",
        "Which commits on main via PR show you reviewed or owned that change?",
    ]

    q = _question(
        competency="verification",
        difficulty="medium",
        target_user_id=uid,
        prompt=prompt,
        code_refs=refs,
        expected_concepts=["verification", "ownership", "review", "no_fabricated_evidence"],
        rubric=(
            "5 describes concrete verification steps on claimed work; "
            "3 mentions AI/teammate use only; 1 cannot defend comprehension."
        ),
        follow_ups=follow_ups,
        hypothetical=hypo,
    )
    return q, uncertainty


_BUILDERS = (
    ("special_feature_pattern", _build_pattern_question),
    ("design_to_code", _build_design_to_code_question),
    ("feature_ownership", _build_ownership_question),
    ("testing", _build_testing_question),
    ("verification", _build_verification_question),
)


def generate_question_plan(
    *,
    participant_user_ids: list[int],
    index: dict[str, Any],
    questions_per_student: int | None = None,
    scenario_slug: str | None = None,
) -> dict[str, Any]:
    """
    Build a COMP 3613 contribution tree per student.

    Order is fixed; `questions_per_student` takes the first N competencies
    (default: all five). Each prompt asks one thing; `follow_ups` are
    single-ask alternates injected when the student skips.
    """
    sha = str(index.get("commit_sha") or "")
    focus = resolve_scenario_focus(scenario_slug)
    tree = list(_BUILDERS)
    if questions_per_student is not None:
        tree = tree[: max(1, questions_per_student)]

    questions: list[dict[str, Any]] = []
    coverage: dict[str, list[str]] = {str(uid): [] for uid in participant_user_ids}
    uncertainties: list[str] = []

    if not (index.get("files") or []):
        uncertainties.append("Repository index has no files; questions marked hypothetical where needed.")

    if not focus["known"]:
        uncertainties.append(
            f"Unknown or missing scenario_slug={scenario_slug!r}; using generic special-feature wording."
        )
    elif not focus.get("has_judge_knowledge"):
        uncertainties.append(
            f"No examiner knowledge pack for scenario_slug={focus['slug']!r}; "
            "provisional scoring will lack pattern/defect gold."
        )

    for student_offset, user_id in enumerate(participant_user_ids):
        uid = str(user_id)
        for comp_offset, (competency, builder) in enumerate(tree):
            idx = student_offset + comp_offset
            q, uncertainty = builder(
                uid=uid,
                focus=focus,
                index=index,
                offset=idx,
                sha=sha,
            )
            assert q["competency"] == competency
            if uncertainty:
                uncertainties.append(uncertainty)
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
        "scenario_slug": focus["slug"],
        "special_feature": focus["special_feature"],
        "questions": ordered,
        "coverage": coverage,
        "uncertainties": uncertainties,
        "planner_version": "comp3613-planner-v3",
        "has_judge_knowledge": bool(focus.get("has_judge_knowledge")),
    }
