"""In-memory registry of approved YAML scenario packages."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.course.scenarios.filter import student_safe_scenario_view
from app.course.scenarios.loader import default_scenarios_root, load_scenario_package
from app.course.scenarios.models import ScenarioPackage, ScenarioStatus
from app.course.scenarios.validator import has_errors, validate_scenario_package


class ScenarioRegistry:
    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], ScenarioPackage] = {}
        self._latest: dict[str, ScenarioPackage] = {}
        self.root: Optional[Path] = None
        self.load_errors: list[str] = []

    def clear(self) -> None:
        self._by_key.clear()
        self._latest.clear()
        self.load_errors.clear()

    def load_from_disk(self, root: Path | None = None) -> int:
        self.clear()
        self.root = (root or default_scenarios_root()).resolve()
        if not self.root.is_dir():
            self.load_errors.append(f"SCENARIOS_ROOT not found: {self.root}")
            return 0

        loaded = 0
        for child in sorted(self.root.iterdir()):
            if not child.is_dir() or not (child / "scenario.yaml").is_file():
                continue
            try:
                package = load_scenario_package(child)
                issues = validate_scenario_package(package)
                if package.meta.status != ScenarioStatus.approved:
                    continue
                if has_errors(issues):
                    codes = [i.code for i in issues if i.severity == "error"]
                    self.load_errors.append(f"{child.name}: validation errors {codes}")
                    continue
                self.register(package)
                loaded += 1
            except Exception as exc:  # noqa: BLE001 — continue loading others
                self.load_errors.append(f"{child.name}: {exc}")
        return loaded

    def register(self, package: ScenarioPackage) -> None:
        key = (package.meta.slug, package.meta.version)
        self._by_key[key] = package
        current = self._latest.get(package.meta.slug)
        if current is None or package.meta.version >= current.meta.version:
            self._latest[package.meta.slug] = package

    def get(self, slug: str, version: str | None = None) -> ScenarioPackage | None:
        if version:
            return self._by_key.get((slug, version))
        return self._latest.get(slug)

    def list_student_safe(self) -> list[dict]:
        return [student_safe_scenario_view(p) for p in sorted(self._latest.values(), key=lambda p: p.meta.slug)]

    @property
    def count(self) -> int:
        return len(self._latest)


scenario_registry = ScenarioRegistry()
