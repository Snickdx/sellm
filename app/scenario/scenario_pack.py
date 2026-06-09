"""Compile full project scenario from data.xlsx for direct-model mode."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

# Sheet → human section title (order preserved)
_SECTION_SHEETS: List[tuple[str, List[str]]] = [
    ("Project summary", ["Project"]),
    ("Stakeholders and roles", ["Stakeholder", "Client", "Role"]),
    ("Goals", ["Goal"]),
    ("Features", ["Feature"]),
    ("Functional requirements", ["Requirement", "FunctioFFnal_Requirement"]),
    ("Quality and non-functional scenarios", ["Qual_Scenario"]),
    ("Constraints", ["Constraint"]),
    ("Risks", ["Risk"]),
    ("Budget", ["Budget", "Line_Item"]),
    ("Timeline and milestones", ["Timeline", "Milestone"]),
    ("Tasks", ["Task"]),
]

_MAX_ROWS_PER_SHEET = 40
_MAX_CELL_CHARS = 280


@dataclass
class ScenarioPack:
    text: str
    sections: Dict[str, str]
    source_file: str

    def as_prompt_block(self) -> str:
        return self.text


def _cell_str(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if text.lower() in ("nan", "none"):
        return ""
    if len(text) > _MAX_CELL_CHARS:
        return text[: _MAX_CELL_CHARS - 3] + "..."
    return text


def _format_row(row: pd.Series, columns: List[str]) -> str:
    parts: List[str] = []
    for col in columns:
        val = _cell_str(row.get(col))
        if val:
            parts.append(f"{col}: {val}")
    return " · ".join(parts) if parts else ""


def load_scenario_pack(excel_file: str) -> ScenarioPack:
    path = Path(excel_file)
    if not path.is_file():
        raise FileNotFoundError(f"Scenario workbook not found: {excel_file}")

    xls = pd.ExcelFile(excel_file, engine="openpyxl")
    sheet_set = set(xls.sheet_names)
    sections: Dict[str, str] = {}
    blocks: List[str] = []

    for section_title, sheet_names in _SECTION_SHEETS:
        section_lines: List[str] = []
        for sheet_name in sheet_names:
            if sheet_name not in sheet_set:
                continue
            try:
                df = pd.read_excel(excel_file, sheet_name=sheet_name, engine="openpyxl")
            except Exception:
                continue
            if df.empty:
                continue
            cols = [c for c in df.columns]
            count = 0
            for _, row in df.iterrows():
                if row.isna().all():
                    continue
                line = _format_row(row, cols)
                if line:
                    section_lines.append(f"  • {line}")
                    count += 1
                if count >= _MAX_ROWS_PER_SHEET:
                    section_lines.append("  • …")
                    break
        if section_lines:
            body = "\n".join(section_lines)
            sections[section_title] = body
            blocks.append(f"## {section_title}\n{body}")

    if not blocks:
        blocks.append("## Project\n(No structured rows loaded from the workbook.)")

    blocks.append(
        "## Role-play guidance\n"
        "You are a business stakeholder who knows this project informally. "
        "Reveal details gradually. Say when you are unsure. Do not cite internal document structure."
    )

    full_text = "\n\n".join(blocks)
    return ScenarioPack(text=full_text, sections=sections, source_file=str(path))
