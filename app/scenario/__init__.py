"""Stakeholder prompt helpers + optional Excel ScenarioPack tooling.

Primary knowledge is YAML under ``app.scenarios``. Excel workbooks are optional
exports from ``app.scenarios.excel_export`` (scenario-author), not runtime ground truth.
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
