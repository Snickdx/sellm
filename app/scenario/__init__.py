"""Legacy Excel scenario pack path.

Prefer YAML packages under ``app.scenarios`` for new work. This module remains
as a compatibility layer for Excel-backed RAG / direct modes until the importer
fully replaces ``data.xlsx``.
"""

from app.scenario.scenario_pack import ScenarioPack, load_scenario_pack
from app.scenario.stakeholder_prompt import (
    STAKEHOLDER_LLM_REQUIRED_MSG,
    STAKEHOLDER_SYSTEM_PROMPT,
    build_stakeholder_user_message,
    format_conversation_history,
    format_retrieved_context,
)

__all__ = [
    "ScenarioPack",
    "load_scenario_pack",
    "STAKEHOLDER_LLM_REQUIRED_MSG",
    "STAKEHOLDER_SYSTEM_PROMPT",
    "build_stakeholder_user_message",
    "format_conversation_history",
    "format_retrieved_context",
]
