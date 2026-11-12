"""Translate scenario packages into a Neo4j domain graph plan.

Excel Neo4j RAG uses typed sheets (Requirement, Feature, Constraint, …) plus an
explicit Relationships sheet. Scenario packages store the same knowledge as flat
KnowledgeFact records. This module maps those facts onto Excel-aligned labels
and isolates them with a shared ``ScenarioPack`` marker label (no ``Yaml*`` /
``yaml:`` names in the graph).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from app.scenarios.filter import facts_for_persona
from app.scenarios.models import KnowledgeFact, ScenarioPackage

# Marker label on every node written from a scenario package (isolates from Excel).
SCENARIO_PACK_LABEL = "ScenarioPack"

# Category / id-prefix → domain kind + Neo4j/Excel-aligned label + vector sheet name.
CATEGORY_TO_KIND: dict[str, tuple[str, str, str]] = {
    "functional": ("requirement", "Requirement", "Requirement"),
    "feature": ("feature", "Feature", "Feature"),
    "goal": ("goal", "Goal", "Goal"),
    "non_functional": ("non_functional", "QualityAttribute", "Qual_Scenario"),
    "nonfunctional": ("non_functional", "QualityAttribute", "Qual_Scenario"),
    "quality": ("quality", "QualityAttribute", "Qual_Scenario"),
    "performance": ("performance", "PerformanceRequirement", "Qual_Scenario"),
    "usability": ("usability", "UsabilityRequirement", "Qual_Scenario"),
    "security": ("security", "QualityAttribute", "Qual_Scenario"),
    "constraint": ("constraint", "Constraint", "Constraint"),
    "limitation": ("limitation", "Limitation", "Constraint"),
    "assumption": ("assumption", "Assumption", "Assumption"),
    "dependency": ("dependency", "Dependency", "Dependency"),
    "design_constraint": ("design_constraint", "DesignConstraint", "Constraint"),
    "standard": ("standard", "Standard", "Constraint"),
    "workflow": ("workflow", "Task", "Task"),
    "use_case": ("use_case", "UseCase", "Qual_Scenario"),
    "interface": ("interface", "ExternalInterface", "Requirement"),
    "data": ("data", "DataEntity", "Requirement"),
    "verification": ("verification", "VerificationMethod", "Requirement"),
    "glossary": ("glossary", "GlossaryTerm", "RequirementNode"),
    "reference": ("reference", "Reference", "RequirementNode"),
    "contextual": ("context", "RequirementNode", "RequirementNode"),
}

PREFIX_TO_KIND: dict[str, tuple[str, str, str]] = {
    "REQ": ("requirement", "Requirement", "Requirement"),
    "FEAT": ("feature", "Feature", "Feature"),
    "GOAL": ("goal", "Goal", "Goal"),
    "BR": ("constraint", "Constraint", "Constraint"),
    "LIM": ("limitation", "Limitation", "Constraint"),
    "ASM": ("assumption", "Assumption", "Assumption"),
    "DEP": ("dependency", "Dependency", "Dependency"),
    "DES": ("design_constraint", "DesignConstraint", "Constraint"),
    "STD": ("standard", "Standard", "Constraint"),
    "WF": ("workflow", "Task", "Task"),
    "UC": ("use_case", "UseCase", "Qual_Scenario"),
    "IF": ("interface", "ExternalInterface", "Requirement"),
    "DATA": ("data", "DataEntity", "Requirement"),
    "PERF": ("performance", "PerformanceRequirement", "Qual_Scenario"),
    "USE": ("usability", "UsabilityRequirement", "Qual_Scenario"),
    "SEC": ("security", "QualityAttribute", "Qual_Scenario"),
    "NFR": ("quality", "QualityAttribute", "Qual_Scenario"),
    "VER": ("verification", "VerificationMethod", "Requirement"),
    "GLOSS": ("glossary", "GlossaryTerm", "RequirementNode"),
    "REF": ("reference", "Reference", "RequirementNode"),
    "CTX": ("context", "RequirementNode", "RequirementNode"),
}

EXCEL_PARITY_GAPS: list[dict[str, str]] = [
    {
        "excel": "Feature nodes + SATISFIES links",
        "scenario_provides": "Optional FEAT-* facts + satisfies_ids on requirements",
        "status": "mapped",
    },
    {
        "excel": "Goal sheet",
        "scenario_provides": "Optional GOAL-* facts (category goal)",
        "status": "mapped",
    },
    {
        "excel": "Risk / Budget / Milestone sheets",
        "scenario_provides": "Not modeled as first-class entities",
        "status": "gap",
    },
    {
        "excel": "Explicit Relationships sheet (OWNED_BY, HAS_CONSTRAINT, …)",
        "scenario_provides": "KNOWS + IN_CATEGORY / IN_FAMILY / HAS_CRITERION + SATISFIES / DERIVES_FROM / DEPENDS_ON",
        "status": "partial",
    },
    {
        "excel": "Stakeholder / Role / Client typed actors",
        "scenario_provides": "Stakeholder + Role + Capability from persona depth fields",
        "status": "partial",
    },
    {
        "excel": "Requirement / Constraint typed rows",
        "scenario_provides": "KnowledgeFact.category + id prefix (REQ/BR/ASM/WF)",
        "status": "mapped",
    },
    {
        "excel": "Acceptance criteria as free text in requirement rows",
        "scenario_provides": "acceptance_criteria list on facts",
        "status": "mapped",
    },
]

# Legacy labels wiped on reindex so old Yaml* graphs are removed.
LEGACY_SCENARIO_LABELS: tuple[str, ...] = (
    "YamlAcceptanceCriterion",
    "YamlSourceCue",
    "YamlDecision",
    "YamlCapability",
    "YamlSystemRole",
    "YamlCategory",
    "YamlFactFamily",
    "YamlFact",
    "YamlPersona",
    "YamlScenario",
    "YamlRequirement",
    "YamlConstraint",
    "YamlWorkflow",
    "YamlAssumption",
    "YamlContext",
    "YamlNonFunctionalRequirement",
    "YamlKnowledge",
)


@dataclass
class GraphNode:
    labels: list[str]
    key: dict[str, Any]
    props: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    rel_type: str
    from_labels: list[str]
    from_key: dict[str, Any]
    to_labels: list[str]
    to_key: dict[str, Any]
    props: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScenarioGraphPlan:
    """Deterministic Neo4j write plan for one scenario package."""

    slug: str
    version: str
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    gaps: list[dict[str, str]] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)


def fact_kind_and_label(fact: KnowledgeFact) -> tuple[str, str, str]:
    """Return (kind, neo4j_label, vector_sheet) for a knowledge fact."""
    category = (fact.category or "").strip().lower().replace("-", "_").replace(" ", "_")
    if category in CATEGORY_TO_KIND:
        return CATEGORY_TO_KIND[category]

    prefix = ""
    parts = (fact.id or "").split("-")
    if len(parts) >= 2:
        prefix = parts[1].upper()
    if prefix in PREFIX_TO_KIND:
        return PREFIX_TO_KIND[prefix]
    return ("knowledge", "RequirementNode", "RequirementNode")


def fact_family(fact: KnowledgeFact) -> str:
    parts = (fact.id or "").split("-")
    if len(parts) >= 2 and parts[1].isalpha():
        return parts[1].upper()
    kind, _, _ = fact_kind_and_label(fact)
    return kind.upper()


def fact_node_id(slug: str, fact_id: str) -> str:
    return f"scenario:{slug}:{fact_id}"


def _enum_val(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value or "")


def _pack_labels(*labels: str) -> list[str]:
    out = [SCENARIO_PACK_LABEL]
    for label in labels:
        if label and label not in out:
            out.append(label)
    return out


def _trace_edges(
    *,
    slug: str,
    from_label: str,
    from_node_id: str,
    target_ids: list[str],
    rel_type: str,
    visible_facts: dict[str, KnowledgeFact],
) -> list[GraphEdge]:
    edges: list[GraphEdge] = []
    for target_id in target_ids or []:
        target = visible_facts.get(target_id)
        if target is None:
            continue
        _, to_label, _ = fact_kind_and_label(target)
        edges.append(
            GraphEdge(
                rel_type=rel_type,
                from_labels=_pack_labels(from_label),
                from_key={"node_id": from_node_id},
                to_labels=_pack_labels(to_label),
                to_key={"node_id": fact_node_id(slug, target_id)},
            )
        )
    return edges


def build_scenario_graph_plan(package: ScenarioPackage) -> ScenarioGraphPlan:
    """Translate one scenario package into typed Neo4j nodes + domain relationships."""
    slug = package.meta.slug
    version = package.meta.version
    plan = ScenarioGraphPlan(slug=slug, version=version, gaps=list(EXCEL_PARITY_GAPS))

    status = _enum_val(package.meta.status)
    plan.nodes.append(
        GraphNode(
            labels=_pack_labels("Project"),
            key={"node_id": f"scenario:{slug}:project", "slug": slug, "version": version},
            props={
                "title": package.meta.title,
                "brief": package.meta.brief or "",
                "status": status,
                "scenario_slug": slug,
                "scenario_version": version,
                "sheet": "Project",
            },
        )
    )

    gaps = getattr(package, "gaps", None)
    decisions = list(getattr(gaps, "decisions", None) or [])
    for decision in decisions:
        plan.nodes.append(
            GraphNode(
                labels=_pack_labels("Decision"),
                key={
                    "decision_id": decision.decision_id,
                    "scenario_slug": slug,
                    "scenario_version": version,
                },
                props={
                    "gap_id": decision.gap_id,
                    "action": _enum_val(decision.action),
                    "chosen": decision.chosen or "",
                    "rationale": decision.rationale or "",
                    "sheet": "Decision",
                },
            )
        )
        plan.edges.append(
            GraphEdge(
                rel_type="HAS_DECISION",
                from_labels=_pack_labels("Project"),
                from_key={"node_id": f"scenario:{slug}:project", "slug": slug, "version": version},
                to_labels=_pack_labels("Decision"),
                to_key={
                    "decision_id": decision.decision_id,
                    "scenario_slug": slug,
                    "scenario_version": version,
                },
            )
        )

    visible_facts: dict[str, KnowledgeFact] = {}
    persona_fact_ids: dict[str, set[str]] = {}
    for persona in package.personas:
        known = facts_for_persona(package, persona.id, include_never_student=False)
        persona_fact_ids[persona.id] = {f.id for f in known}
        for fact in known:
            visible_facts[fact.id] = fact

    kind_counts: dict[str, int] = {}
    for fact in visible_facts.values():
        kind, label, sheet = fact_kind_and_label(fact)
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
        family = fact_family(fact)
        node_id = fact_node_id(slug, fact.id)
        status_val = _enum_val(fact.status)
        origin_val = _enum_val(fact.origin)
        disclosure_val = _enum_val(fact.disclosure)
        text = (
            f"Scenario: {package.meta.title}\n"
            f"Category: {fact.category}\n"
            f"Kind: {kind}\n"
            f"Family: {family}\n"
            f"Status: {status_val}\n"
            f"Statement: {fact.statement}"
        )
        plan.nodes.append(
            GraphNode(
                labels=_pack_labels(label),
                key={"node_id": node_id},
                props={
                    "text": text,
                    "sheet": sheet,
                    "sheet_type": kind,
                    "fact_id": fact.id,
                    "scenario_slug": slug,
                    "scenario_version": version,
                    "category": fact.category,
                    "kind": kind,
                    "family": family,
                    "status": status_val,
                    "origin": origin_val,
                    "disclosure": disclosure_val,
                    "decision_id": fact.decision_id or "",
                    "needs_embedding": True,
                },
            )
        )
        plan.edges.append(
            GraphEdge(
                rel_type="HAS_FACT",
                from_labels=_pack_labels("Project"),
                from_key={"node_id": f"scenario:{slug}:project", "slug": slug, "version": version},
                to_labels=_pack_labels(label),
                to_key={"node_id": node_id},
            )
        )

        plan.nodes.append(
            GraphNode(
                labels=_pack_labels("Category"),
                key={"name": fact.category, "scenario_slug": slug},
                props={"kind": kind, "sheet": "Category"},
            )
        )
        plan.edges.append(
            GraphEdge(
                rel_type="IN_CATEGORY",
                from_labels=_pack_labels(label),
                from_key={"node_id": node_id},
                to_labels=_pack_labels("Category"),
                to_key={"name": fact.category, "scenario_slug": slug},
            )
        )

        plan.nodes.append(
            GraphNode(
                labels=_pack_labels("FactFamily"),
                key={"name": family, "scenario_slug": slug},
                props={"kind": kind, "sheet": "FactFamily"},
            )
        )
        plan.edges.append(
            GraphEdge(
                rel_type="IN_FAMILY",
                from_labels=_pack_labels(label),
                from_key={"node_id": node_id},
                to_labels=_pack_labels("FactFamily"),
                to_key={"name": family, "scenario_slug": slug},
            )
        )

        for idx, criterion in enumerate(fact.acceptance_criteria or []):
            text_c = str(criterion).strip()
            if not text_c:
                continue
            criterion_id = f"{fact.id}:ac:{idx + 1}"
            plan.nodes.append(
                GraphNode(
                    labels=_pack_labels("AcceptanceCriterion"),
                    key={
                        "criterion_id": criterion_id,
                        "scenario_slug": slug,
                        "scenario_version": version,
                    },
                    props={"text": text_c, "fact_id": fact.id, "sheet": "AcceptanceCriterion"},
                )
            )
            plan.edges.append(
                GraphEdge(
                    rel_type="HAS_CRITERION",
                    from_labels=_pack_labels(label),
                    from_key={"node_id": node_id},
                    to_labels=_pack_labels("AcceptanceCriterion"),
                    to_key={
                        "criterion_id": criterion_id,
                        "scenario_slug": slug,
                        "scenario_version": version,
                    },
                )
            )

        if fact.decision_id:
            plan.edges.append(
                GraphEdge(
                    rel_type="FROM_DECISION",
                    from_labels=_pack_labels(label),
                    from_key={"node_id": node_id},
                    to_labels=_pack_labels("Decision"),
                    to_key={
                        "decision_id": fact.decision_id,
                        "scenario_slug": slug,
                        "scenario_version": version,
                    },
                )
            )
            plan.edges.append(
                GraphEdge(
                    rel_type="PRODUCED",
                    from_labels=_pack_labels("Decision"),
                    from_key={
                        "decision_id": fact.decision_id,
                        "scenario_slug": slug,
                        "scenario_version": version,
                    },
                    to_labels=_pack_labels(label),
                    to_key={"node_id": node_id},
                )
            )

        plan.edges.extend(
            _trace_edges(
                slug=slug,
                from_label=label,
                from_node_id=node_id,
                target_ids=list(getattr(fact, "satisfies_ids", None) or []),
                rel_type="SATISFIES",
                visible_facts=visible_facts,
            )
        )
        plan.edges.extend(
            _trace_edges(
                slug=slug,
                from_label=label,
                from_node_id=node_id,
                target_ids=list(getattr(fact, "derives_from_ids", None) or []),
                rel_type="DERIVES_FROM",
                visible_facts=visible_facts,
            )
        )
        plan.edges.extend(
            _trace_edges(
                slug=slug,
                from_label=label,
                from_node_id=node_id,
                target_ids=list(getattr(fact, "depends_on_ids", None) or []),
                rel_type="DEPENDS_ON",
                visible_facts=visible_facts,
            )
        )

        for ref in fact.source_refs or []:
            cue_id = getattr(ref, "cue_id", None) or ""
            file_name = getattr(ref, "file", None) or ""
            if not cue_id:
                continue
            plan.nodes.append(
                GraphNode(
                    labels=_pack_labels("SourceCue"),
                    key={"cue_id": cue_id, "file": file_name, "scenario_slug": slug},
                    props={
                        "start": getattr(ref, "start", None) or "",
                        "end": getattr(ref, "end", None) or "",
                        "speaker": getattr(ref, "speaker", None) or "",
                        "sheet": "SourceCue",
                    },
                )
            )
            plan.edges.append(
                GraphEdge(
                    rel_type="CITED_FROM",
                    from_labels=_pack_labels(label),
                    from_key={"node_id": node_id},
                    to_labels=_pack_labels("SourceCue"),
                    to_key={"cue_id": cue_id, "file": file_name, "scenario_slug": slug},
                )
            )

    for persona in package.personas:
        system_role = _enum_val(getattr(persona, "system_role", None))
        admin_capabilities = list(getattr(persona, "admin_capabilities", None) or [])
        plan.nodes.append(
            GraphNode(
                labels=_pack_labels("Stakeholder"),
                key={"key": persona.id, "scenario_slug": slug, "scenario_version": version},
                props={
                    "display_name": persona.display_name,
                    "role": persona.role,
                    "system_role": system_role,
                    "admin_capabilities": admin_capabilities,
                    "node_id": f"scenario:{slug}:stakeholder:{persona.id}",
                    "sheet": "Stakeholder",
                },
            )
        )
        plan.edges.append(
            GraphEdge(
                rel_type="HAS_PERSONA",
                from_labels=_pack_labels("Project"),
                from_key={"node_id": f"scenario:{slug}:project", "slug": slug, "version": version},
                to_labels=_pack_labels("Stakeholder"),
                to_key={"key": persona.id, "scenario_slug": slug, "scenario_version": version},
            )
        )
        if system_role:
            plan.nodes.append(
                GraphNode(
                    labels=_pack_labels("Role"),
                    key={"name": system_role},
                    props={"sheet": "Role"},
                )
            )
            plan.edges.append(
                GraphEdge(
                    rel_type="HAS_ROLE",
                    from_labels=_pack_labels("Stakeholder"),
                    from_key={
                        "key": persona.id,
                        "scenario_slug": slug,
                        "scenario_version": version,
                    },
                    to_labels=_pack_labels("Role"),
                    to_key={"name": system_role},
                )
            )
        for capability in admin_capabilities:
            name = str(capability).strip()
            if not name:
                continue
            plan.nodes.append(
                GraphNode(
                    labels=_pack_labels("Capability"),
                    key={"name": name},
                    props={"sheet": "Capability"},
                )
            )
            plan.edges.append(
                GraphEdge(
                    rel_type="CAN",
                    from_labels=_pack_labels("Stakeholder"),
                    from_key={
                        "key": persona.id,
                        "scenario_slug": slug,
                        "scenario_version": version,
                    },
                    to_labels=_pack_labels("Capability"),
                    to_key={"name": name},
                )
            )
        for fact_id in sorted(persona_fact_ids.get(persona.id, set())):
            fact = visible_facts[fact_id]
            _, label, _ = fact_kind_and_label(fact)
            plan.edges.append(
                GraphEdge(
                    rel_type="KNOWS",
                    from_labels=_pack_labels("Stakeholder"),
                    from_key={
                        "key": persona.id,
                        "scenario_slug": slug,
                        "scenario_version": version,
                    },
                    to_labels=_pack_labels(label),
                    to_key={"node_id": fact_node_id(slug, fact_id)},
                )
            )

    plan.stats = {
        "nodes": len(plan.nodes),
        "edges": len(plan.edges),
        "facts": len(visible_facts),
        "personas": len(package.personas),
        "decisions": len(decisions),
        **{f"kind_{k}": v for k, v in sorted(kind_counts.items())},
    }
    return plan


def summarize_excel_gaps() -> list[dict[str, str]]:
    return list(EXCEL_PARITY_GAPS)


def iter_embed_texts(plan: ScenarioGraphPlan) -> Iterable[tuple[str, str]]:
    """Yield (node_id, text) for knowledge nodes that need embeddings."""
    for node in plan.nodes:
        if node.props.get("needs_embedding") and node.key.get("node_id"):
            yield str(node.key["node_id"]), str(node.props.get("text") or "")
