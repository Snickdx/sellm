"""Detect interviewer domain-learning questions vs stakeholder practice."""

from __future__ import annotations

import re
from typing import List, Pattern

# Stakeholder-practice cues: keep role-play even if the question looks definitional.
_STAKEHOLDER_CUES = re.compile(
    r"\b(you|your|yours|u)\b|"
    r"\b(what do you|how do you|can you tell me what you|do you want|would you)\b|"
    r"\bfrom your (perspective|point of view|side)\b|"
    r"\bwhat worries you\b|"
    r"\b(we|our)\s+(trying|building|delivering|accomplish|hoping|need)\b|"
    r"\boverall\s+(goal|objective|aim)\b|"
    r"\bany other user types?\b|"
    r"\bwhen a new\b|"
    r"\bwhat do you mean\b|"
    r"\bwhat does .+ mean\b",
    re.I,
)

_COACH_PATTERNS: List[Pattern[str]] = [
    re.compile(r"^\s*(define|definition\s+of)\b", re.I),
    re.compile(r"^\s*(explain|describe)\s+(a|an|the)?\s*\w", re.I),
    re.compile(r"^\s*help\s+me\s+understand\b", re.I),
    re.compile(r"\bwhat\s+does\s+.+\s+mean\b", re.I),
    re.compile(r"^\s*what\s+is\s+(a|an|the)\s+\w", re.I),
    re.compile(r"^\s*what\s+are\s+(a|an|the)\s+\w+", re.I),
    re.compile(
        r"^\s*what\s+are\s+(?!we\b|you\b|they\b|there\b|these\b|those\b)\w+",
        re.I,
    ),
    re.compile(
        r"^\s*tell\s+me\s+about\s+(the\s+)?(concept|domain|term|meaning|idea)\b",
        re.I,
    ),
    re.compile(r"^\s*domain\s+(overview|summary|context)\b", re.I),
]


def is_coach_query(query: str, *, force: bool = False) -> bool:
    """True when the user is learning the domain (interviewer), not interviewing the stakeholder."""
    if force:
        return True
    text = (query or "").strip()
    if not text:
        return False
    if _STAKEHOLDER_CUES.search(text):
        return False
    return any(p.search(text) for p in _COACH_PATTERNS)


def format_coach_context(context_results: List[dict], max_items: int = 6) -> str:
    """Full retrieved snippets for coach synthesis (not stakeholder field filtering)."""
    blocks: List[str] = []
    for result in context_results[:max_items]:
        doc = (result.get("document") or "").strip()
        if doc:
            blocks.append(doc)
    return "\n---\n".join(blocks) if blocks else "No matching project knowledge found."
