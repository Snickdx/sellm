"""Build sellm ScenarioPack-like context from a YAML persona's facts (for direct mode)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from app.course.chat.persona_service import allowed_facts_for_persona, get_persona
from app.course.scenarios.models import ScenarioPackage


@dataclass
class YamlScenarioPack:
    """Duck-typed stand-in for Excel ScenarioPack used by direct-mode prompts."""

    title: str
    slug: str
    persona_key: str
    persona_name: str
    sections: Dict[str, str] = field(default_factory=dict)

    def as_markdown(self) -> str:
        parts = [
            f"# {self.title}",
            f"Persona: {self.persona_name} ({self.persona_key})",
            "",
        ]
        for name, body in self.sections.items():
            parts.append(f"## {name}")
            parts.append(body)
            parts.append("")
        return "\n".join(parts)

    def as_prompt_block(self) -> str:
        return self.as_markdown()


def pack_from_persona(package: ScenarioPackage, persona_key: str) -> YamlScenarioPack | None:
    persona = get_persona(package, persona_key)
    if persona is None:
        return None
    facts = allowed_facts_for_persona(package, persona_key)
    by_category: Dict[str, list[str]] = {}
    for fact in facts:
        by_category.setdefault(fact.category or "knowledge", []).append(f"- {fact.statement}")
    sections = {cat: "\n".join(lines) for cat, lines in sorted(by_category.items())}
    system_role = (
        persona.system_role.value
        if getattr(persona, "system_role", None) is not None and hasattr(persona.system_role, "value")
        else (str(persona.system_role) if getattr(persona, "system_role", None) else "")
    )
    caps = getattr(persona, "admin_capabilities", None) or []
    caps_line = ", ".join(caps) if caps else ""
    persona_lines = [
        f"Name: {persona.display_name}",
        f"Role: {persona.role}",
        f"Style: {persona.communication_style}",
        f"Uncertainty: {persona.uncertainty_policy}",
    ]
    if system_role:
        persona_lines.insert(2, f"System role: {system_role}")
    if caps_line:
        persona_lines.insert(3 if system_role else 2, f"Admin capabilities: {caps_line}")
    sections["Persona"] = "\n".join(persona_lines)
    return YamlScenarioPack(
        title=package.meta.title,
        slug=package.meta.slug,
        persona_key=persona_key,
        persona_name=persona.display_name,
        sections=sections,
    )
