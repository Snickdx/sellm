#!/usr/bin/env python3
"""Export YAML scenario packages to Excel-shaped workbooks.

Usage:
  python scripts/export_scenario_excel.py
  python scripts/export_scenario_excel.py library job-board
  python scripts/export_scenario_excel.py --all

Writes ``scenarios/<slug>/exports/<slug>-workbook.xlsx`` by default.
Runtime chat does not require these files; they are optional instructor mirrors.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export scenario packages to Excel workbooks")
    parser.add_argument("slugs", nargs="*", help="Scenario slugs (default: all under scenarios/)")
    parser.add_argument("--all", action="store_true", help="Export every package on disk")
    parser.add_argument(
        "--out-root",
        type=Path,
        default=None,
        help="Override scenarios root for output paths (default: SCENARIOS_ROOT / ./scenarios)",
    )
    args = parser.parse_args(argv)

    from app.scenarios.excel_export import export_package_to_excel
    from app.scenarios.loader import default_scenarios_root, load_scenario_package

    scenarios_root = args.out_root or default_scenarios_root()
    if args.slugs and not args.all:
        slugs = list(args.slugs)
    else:
        slugs = [
            child.name
            for child in sorted(scenarios_root.iterdir())
            if child.is_dir() and (child / "scenario.yaml").is_file()
        ]

    if not slugs:
        print("No scenarios to export", file=sys.stderr)
        return 1

    failed = 0
    for slug in slugs:
        path = scenarios_root / slug
        if not path.is_dir():
            print(f"✗ missing scenario dir: {path}", file=sys.stderr)
            failed += 1
            continue
        try:
            package = load_scenario_package(path)
            out = export_package_to_excel(package, scenarios_root=scenarios_root)
            print(f"✓ {package.meta.slug} → {out}")
        except Exception as exc:  # noqa: BLE001
            print(f"✗ {slug}: {exc}", file=sys.stderr)
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
