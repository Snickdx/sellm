"""COMP 3613 scenario special-feature focus for exit-interview prompts.

Maps sellm scenario slugs to the mandatory special feature from the 2026 project
spec (§2). The lecturer does not prescribe the design pattern — students identify
one; prompts only name the special-feature focus.

Judge-side gold (intended pattern, defect IDs) lives in
`app.examiner.knowledge` and must not be copied into student prompts.
"""

from __future__ import annotations

from typing import Any

from app.examiner.knowledge import focus_paths_for, resolve_judge_knowledge

# slug -> (title, special_feature) — student-safe prompt wording only
SCENARIO_SPECIAL_FEATURES: dict[str, tuple[str, str]] = {
    "job-board": ("Job board", "Application lifecycle / transitions"),
    "library": ("Library workshop booking", "Same-slot conflict resolution"),
    "uwi-connect": ("Campus networking / info sharing", "Notifications on publish / campaign send"),
    "thesis-tracker": ("Postgrad milestones", "Domain actions executed and audited"),
    "student-accommodation": ("Student housing", "Listing lifecycle / transitions"),
    "ta-allocations": ("TA allocation", "Auto-allocation ranking modes"),
    "career-advising": ("Career advising", "Exploration / advising pipelines"),
}


def resolve_scenario_focus(scenario_slug: str | None) -> dict[str, Any]:
    """Return display fields for prompts; unknown slug → generic wording.

    Includes `focus_paths` when a knowledge pack exists (paths are also named in
    ASSIGNMENT.md). Does **not** include intended_pattern or defect IDs.
    """
    slug = (scenario_slug or "").strip().lower() or None
    paths = focus_paths_for(slug)
    if slug and slug in SCENARIO_SPECIAL_FEATURES:
        title, special = SCENARIO_SPECIAL_FEATURES[slug]
        pack = resolve_judge_knowledge(slug)
        if pack and pack.get("special_feature"):
            special = str(pack["special_feature"])
        if pack and pack.get("title"):
            title = str(pack["title"])
        return {
            "slug": slug,
            "title": title,
            "special_feature": special,
            "focus_paths": paths,
            "known": True,
            "has_judge_knowledge": pack is not None,
        }
    return {
        "slug": slug,
        "title": "your chosen scenario",
        "special_feature": "your scenario's special feature",
        "focus_paths": paths,
        "known": False,
        "has_judge_knowledge": False,
    }
