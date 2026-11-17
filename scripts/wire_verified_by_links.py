#!/usr/bin/env python3
"""Wire VER→FR depends_on_ids for VERIFIED_BY edges; bump package versions to 0.3.1."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# VER fact id → FR ids it verifies (from VER statement ↔ REQ statements).
VER_LINKS: dict[str, dict[str, list[str]]] = {
    "career-advising": {
        "CA-VER-001": ["CA-REQ-002", "CA-REQ-005", "CA-REQ-012"],
    },
    "job-board": {
        "JB-VER-001": ["JB-REQ-002", "JB-REQ-003", "JB-REQ-008", "JB-REQ-010"],
    },
    "library": {
        "LIB-VER-001": ["LIB-REQ-002", "LIB-REQ-003", "LIB-REQ-005", "LIB-REQ-008"],
    },
    "student-accommodation": {
        "SA-VER-001": ["SA-REQ-001", "SA-REQ-005", "SA-REQ-007", "SA-REQ-009"],
    },
    "ta-allocations": {
        "TA-VER-001": ["TA-REQ-001", "TA-REQ-003", "TA-REQ-009"],
    },
    "thesis-tracker": {
        "TT-VER-001": ["TT-REQ-004", "TT-REQ-005", "TT-REQ-007"],
    },
    "uwi-connect": {
        "UC-VER-001": ["UC-REQ-002", "UC-REQ-003", "UC-REQ-005", "UC-REQ-008"],
    },
}

# Extra REQ→IF/DATA/DEP depends_on where YAML lacked depends_on entirely.
REQ_DEPENDS: dict[str, dict[str, list[str]]] = {
    "career-advising": {
        "CA-REQ-011": ["CA-DATA-001", "CA-IF-001"],
    },
    "library": {
        "LIB-REQ-001": ["LIB-IF-001", "LIB-DATA-001"],
    },
    "student-accommodation": {
        "SA-REQ-002": ["SA-IF-001", "SA-DATA-001"],
    },
    "thesis-tracker": {
        "TT-REQ-004": ["TT-IF-001", "TT-DATA-001"],
    },
    "uwi-connect": {
        "UC-REQ-002": ["UC-IF-001"],
        "UC-REQ-005": ["UC-IF-002", "UC-DATA-001"],
    },
}


def _insert_depends_on(block: str, fact_id: str, deps: list[str]) -> str:
    if "depends_on_ids:" in block:
        return block
    dep_yaml = "  depends_on_ids:\n" + "".join(f"  - {d}\n" for d in deps)
    # Prefer insert before disclosure / known_by / end of fact
    for anchor in ("  disclosure:", "  known_by:", "  acceptance_criteria:"):
        if anchor in block:
            return block.replace(anchor, dep_yaml + anchor, 1)
    return block.rstrip() + "\n" + dep_yaml


def _patch_fact_file(path: Path, updates: dict[str, list[str]]) -> int:
    if not path.is_file() or not updates:
        return 0
    text = path.read_text(encoding="utf-8")
    changed = 0
    # Split on fact entries starting with "- id:"
    parts = re.split(r"(?m)^(- id: )", text)
    # parts[0] preamble, then pairs of (delimiter, rest)
    if len(parts) < 3:
        return 0
    out = [parts[0]]
    i = 1
    while i < len(parts):
        delim = parts[i]
        body = parts[i + 1]
        i += 2
        m = re.match(r"([A-Za-z0-9_-]+)\n(.*)$", body, re.S)
        if not m:
            out.extend([delim, body])
            continue
        fact_id, rest = m.group(1), m.group(2)
        block = delim + fact_id + "\n" + rest
        if fact_id in updates:
            new_block = _insert_depends_on(block, fact_id, updates[fact_id])
            if new_block != block:
                changed += 1
                if "-VER-" in fact_id and "rationale:" in new_block and "VERIFIED_BY" not in new_block:
                    new_block = re.sub(
                        r"(rationale: [^\n]*)",
                        r"\1 Linked FRs via depends_on_ids for VERIFIED_BY graph edges.",
                        new_block,
                        count=1,
                    )
                block = new_block
        out.append(block)
    if changed:
        path.write_text("".join(out), encoding="utf-8")
    return changed


def _patch_fact_file_v2(path: Path, updates: dict[str, list[str]]) -> int:
    """Patch facts by rewriting each `- id:` block independently."""
    if not path.is_file() or not updates:
        return 0
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r"(?m)^- id: ([A-Za-z0-9_-]+)\n(?:.*?\n)(?=^- id: |\Z)", re.S)
    changed = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal changed
        block = match.group(0)
        fact_id = match.group(1)
        if fact_id not in updates:
            return block
        if re.search(r"(?m)^  depends_on_ids:", block):
            return block
        new_block = _insert_depends_on(block, fact_id, updates[fact_id])
        if new_block != block:
            changed += 1
            if "-VER-" in fact_id and "rationale:" in new_block and "VERIFIED_BY" not in new_block:
                new_block = re.sub(
                    r"(rationale: [^\n]*)",
                    r"\1 Linked FRs via depends_on_ids for VERIFIED_BY graph edges.",
                    new_block,
                    count=1,
                )
        return new_block

    new_text = pattern.sub(repl, text)
    if changed:
        path.write_text(new_text, encoding="utf-8")
    return changed


def _bump_scenario_yaml(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if re.search(r"(?m)^version: 0\.3\.1\s*$", text):
        return
    text2 = re.sub(r"(?m)^version: 0\.3\.0\s*$", "version: 0.3.1", text, count=1)
    note = (
        "\n  Graph depth-update to 0.3.1: wired VER depends_on_ids → FRs for VERIFIED_BY; "
        "added sparse REQ depends_on where missing for graph traversal.\n"
    )
    if "Graph depth-update to 0.3.1" not in text2:
        # Append into source_notes if present
        if "source_notes:" in text2:
            text2 = re.sub(
                r"(source_notes: ')",
                r"\1" + note.strip() + "\n\n  ",
                text2,
                count=1,
            )
            if text2 == path.read_text(encoding="utf-8"):
                # folded style without leading quote after sub miss — try block
                text2 = re.sub(
                    r"(source_notes:\s*>?-?\s*\n)",
                    r"\1" + "  " + note.strip() + "\n",
                    text2,
                    count=1,
                )
    path.write_text(text2, encoding="utf-8")


def _ensure_gap(path: Path, slug: str, ver_ids: list[str]) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    gap_id = f"GAP-{slug.upper().replace('-', '')[:6]}-VERIFIED-BY-001"
    if gap_id in text or "verified_by_links" in text:
        return
    ids = ", ".join(ver_ids)
    entry = f"""
- id: {gap_id}
  priority: important
  prompt: Confirm VERIFIED_BY links from verification facts ({ids}) to the listed FRs are correct for classroom graph/neo4j mode.
  why_it_matters: Without these links Neo4j cannot emit VERIFIED_BY edges; hybrid/graph modes lose verification traversal.
  alternatives:
  - Keep prescribed FR links
  - Retarget VER depends_on_ids to a different FR set
  - Defer VERIFIED_BY for this package
  recommended_default: Keep prescribed FR links
  theme: srs_prescription
  actions:
  - verify_accept
  - modify
  - reject
  - defer
  status: open
"""
    if text.rstrip().endswith("open_questions:") or "open_questions: []" in text:
        text = text.replace("open_questions: []", "open_questions:\n" + entry.lstrip("\n"))
        if "open_questions: []" not in path.read_text(encoding="utf-8") and gap_id not in text:
            pass
    if gap_id not in text:
        text = re.sub(
            r"(?m)^open_questions:\s*\n",
            "open_questions:\n" + entry.lstrip("\n"),
            text,
            count=1,
        )
    path.write_text(text, encoding="utf-8")


def main() -> int:
    scenarios = ROOT / "scenarios"
    total = 0
    for slug, ver_map in VER_LINKS.items():
        folder = scenarios / slug
        ver_path = folder / "knowledge" / "verification.yaml"
        n = _patch_fact_file_v2(ver_path, ver_map)
        print(f"{slug}: verification.yaml patched {n} fact(s)")
        total += n

        req_updates = REQ_DEPENDS.get(slug, {})
        # Patch all knowledge yaml files for REQ depends
        req_changed = 0
        for path in (folder / "knowledge").glob("*.yaml"):
            req_changed += _patch_fact_file_v2(path, req_updates)
        if req_updates:
            print(f"{slug}: REQ depends_on patched {req_changed} fact(s)")
            total += req_changed

        _bump_scenario_yaml(folder / "scenario.yaml")
        _ensure_gap(folder / "gaps.yaml", slug, list(ver_map.keys()))

    print(f"done; fact patches={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
