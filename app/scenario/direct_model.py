"""Direct-model mode: full scenario pack in prompt, no retrieval."""

from __future__ import annotations

from typing import Dict, List, Optional

from app.scenario.scenario_pack import ScenarioPack
from app.scenario.stakeholder_prompt import build_stakeholder_user_message


def build_direct_context_block(pack: ScenarioPack) -> str:
    return pack.as_prompt_block()


def build_direct_user_message(
    query: str,
    pack: ScenarioPack,
    conversation_history: Optional[List[Dict]] = None,
) -> str:
    return build_stakeholder_user_message(
        query,
        context_block=build_direct_context_block(pack),
        conversation_history=conversation_history,
        context_label="Full project scenario (everything you know as this stakeholder)",
    )
