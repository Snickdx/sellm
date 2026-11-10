"""Load scenario packages from the scenarios/ directory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from app.scenarios.models import (
    EvaluationFile,
    GapsFile,
    KnowledgeFact,
    Persona,
    ScenarioMeta,
    ScenarioPackage,
    ScenarioStatus,
)
from app.scenarios.vtt import parse_vtt_file


def _read_yaml(path: Path) -> Any:
    text = path.read_text(encoding="utf-8-sig")
    return yaml.safe_load(text) or {}


def _load_facts_from_dir(knowledge_dir: Path) -> list[KnowledgeFact]:
    facts: list[KnowledgeFact] = []
    if not knowledge_dir.is_dir():
        return facts
    for path in sorted(knowledge_dir.glob("*.yaml")):
        data = _read_yaml(path)
        items = data.get("facts", data if isinstance(data, list) else [])
        if isinstance(data, dict) and "facts" not in data and "id" in data:
            items = [data]
        for item in items or []:
            facts.append(KnowledgeFact.model_validate(item))
    return facts


def _load_personas(personas_dir: Path) -> list[Persona]:
    personas: list[Persona] = []
    if not personas_dir.is_dir():
        return personas
    for path in sorted(personas_dir.glob("*.yaml")):
        data = _read_yaml(path)
        personas.append(Persona.model_validate(data))
    return personas


def _load_cues(scenario_dir: Path) -> dict[str, set[str]]:
    cue_ids: dict[str, set[str]] = {}
    normalized = scenario_dir / "normalized" / "cues.jsonl"
    if normalized.is_file():
        with normalized.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                source = row.get("source_file") or "unknown.vtt"
                cue_ids.setdefault(source, set()).add(row["cue_id"])
                # also key by relative path used in source_refs
                cue_ids.setdefault(f"sources/{Path(source).name}", set()).add(row["cue_id"])

    sources = scenario_dir / "sources"
    if sources.is_dir():
        for vtt in sources.glob("*.vtt"):
            for cue in parse_vtt_file(vtt):
                cue_ids.setdefault(vtt.name, set()).add(cue.cue_id)
                cue_ids.setdefault(f"sources/{vtt.name}", set()).add(cue.cue_id)
    return cue_ids


def load_scenario_package(scenario_dir: Path) -> ScenarioPackage:
    scenario_dir = scenario_dir.resolve()
    meta_path = scenario_dir / "scenario.yaml"
    if not meta_path.is_file():
        raise FileNotFoundError(f"Missing scenario.yaml in {scenario_dir}")

    meta = ScenarioMeta.model_validate(_read_yaml(meta_path))
    if meta.slug != scenario_dir.name and meta.status != ScenarioStatus.pending_source:
        # allow PENDING skeletons but warn via validator; still load
        pass

    gaps: GapsFile | None = None
    gaps_path = scenario_dir / "gaps.yaml"
    if gaps_path.is_file():
        gaps = GapsFile.model_validate(_read_yaml(gaps_path))

    evaluation: EvaluationFile | None = None
    eval_path = scenario_dir / "evaluation.yaml"
    if eval_path.is_file():
        evaluation = EvaluationFile.model_validate(_read_yaml(eval_path))

    return ScenarioPackage(
        meta=meta,
        personas=_load_personas(scenario_dir / "personas"),
        facts=_load_facts_from_dir(scenario_dir / "knowledge"),
        gaps=gaps,
        evaluation=evaluation,
        cue_ids_by_file=_load_cues(scenario_dir),
    )


def default_scenarios_root() -> Path:
    import os

    override = os.getenv("SCENARIOS_ROOT")
    if override:
        return Path(override).resolve()

    # loader.py -> scenarios -> app -> sellm root
    sellm_root = Path(__file__).resolve().parents[2]
    candidates = [
        sellm_root / "scenarios",
        Path("/app/scenarios"),
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    return (sellm_root / "scenarios").resolve()
