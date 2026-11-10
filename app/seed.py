"""Seed approved YAML scenarios into the registry and optional DB."""

from __future__ import annotations

from pathlib import Path

from sqlmodel import Session

from app.scenarios.importer import import_package_to_db
from app.scenarios.loader import default_scenarios_root
from app.scenarios.registry import scenario_registry


def seed_scenarios(*, engine=None) -> dict:
    root = default_scenarios_root()
    loaded = scenario_registry.load_from_disk(root)
    imported = 0
    if engine is not None and loaded:
        with Session(engine) as session:
            for package in scenario_registry._latest.values():
                source = str((root / package.meta.slug).resolve()) if root else None
                import_package_to_db(session, package, source_path=source)
                imported += 1
            session.commit()
    return {
        "root": str(root),
        "loaded": loaded,
        "imported": imported,
        "errors": list(scenario_registry.load_errors),
        "slugs": [p.meta.slug for p in scenario_registry._latest.values()],
    }
