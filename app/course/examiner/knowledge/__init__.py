"""Instructor-only exit-interview gold for provisional judging.

Source of truth for defects/patterns: instructor/private/<slug>/defect-manifest.yaml
(and templates/<slug>/ASSIGNMENT.md for special-feature wording). Packs under this
directory are the runtime form used by the scorer.

Never put intended_pattern / defect IDs into student-facing prompts or API fields
(expected_concepts, plan_json, rubric text). Load this pack only inside the scorer
(and instructor tooling).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_DIR = Path(__file__).resolve().parent


def _norm_slug(scenario_slug: str | None) -> str | None:
    slug = (scenario_slug or "").strip().lower() or None
    return slug


@lru_cache(maxsize=32)
def _load_pack(slug: str) -> dict[str, Any] | None:
    path = _DIR / f"{slug}.yaml"
    if not path.is_file():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return None
    data["slug"] = slug
    return data


def list_knowledge_slugs() -> list[str]:
    return sorted(p.stem for p in _DIR.glob("*.yaml"))


def resolve_judge_knowledge(scenario_slug: str | None) -> dict[str, Any] | None:
    """Return gold pack for a scenario, or None if unknown."""
    slug = _norm_slug(scenario_slug)
    if not slug:
        return None
    return _load_pack(slug)


def focus_paths_for(scenario_slug: str | None) -> list[str]:
    """Public-ish focus file paths (also named in ASSIGNMENT.md). Safe for cite picking."""
    pack = resolve_judge_knowledge(scenario_slug)
    if not pack:
        return []
    paths = pack.get("focus_paths") or []
    return [str(p) for p in paths if p]


def judge_concepts_for(scenario_slug: str | None, competency: str) -> list[str]:
    """Token concepts used only at score time (not stored on InterviewQuestion)."""
    pack = resolve_judge_knowledge(scenario_slug)
    if not pack:
        return []
    concepts: list[str] = []
    by_comp = pack.get("judge_concepts") or {}
    concepts.extend(str(c) for c in (by_comp.get(competency) or []) if c)

    pattern = (pack.get("intended_pattern") or "").strip()
    if pattern and competency in {"special_feature_pattern", "design_to_code"}:
        concepts.append(pattern)
        concepts.extend(str(a) for a in (pack.get("intended_pattern_aliases") or []) if a)

    arch = pack.get("architecture_defect") or {}
    if arch and competency == "special_feature_pattern":
        if arch.get("id"):
            concepts.append(str(arch["id"]))
        summary = str(arch.get("summary") or "")
        # a few high-signal words from the architecture defect summary
        for token in ("lifecycle", "transition", "flags", "nested", "observer", "strategy", "command", "template"):
            if token in summary.lower():
                concepts.append(token)

    # Dedupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for c in concepts:
        key = c.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def gold_rationale_bits(scenario_slug: str | None) -> str:
    """Short instructor-facing gold summary for assessment rationale."""
    pack = resolve_judge_knowledge(scenario_slug)
    if not pack:
        return ""
    pattern = pack.get("intended_pattern") or "?"
    arch = pack.get("architecture_defect") or {}
    arch_id = arch.get("id") or "?"
    return f"gold_pattern={pattern}; arch_defect={arch_id}"
