"""Index scenario persona facts into Chroma (vector) and Neo4j (graph)."""

from __future__ import annotations

import hashlib
from typing import Any, Optional

from app.scenarios.filter import facts_for_persona
from app.scenarios.models import ScenarioPackage
from app.scenarios.neo4j_graph import fact_family, fact_kind_and_label, fact_node_id
from app.scenarios.registry import scenario_registry


def _persona_system_role(persona) -> str:
    system_role = getattr(persona, "system_role", None)
    if system_role is None:
        return ""
    return system_role.value if hasattr(system_role, "value") else str(system_role)


def _fact_document(package: ScenarioPackage, persona, fact) -> tuple[str, dict[str, Any], str]:
    """Build one vector doc with Excel-aligned sheet/type metadata (no yaml names)."""
    statement = fact.statement.strip()
    kind, _label, sheet = fact_kind_and_label(fact)
    family = fact_family(fact)
    persona_id = persona.id
    system_role = _persona_system_role(persona)
    caps = list(getattr(persona, "admin_capabilities", None) or [])
    text_parts = [
        f"Project: {package.meta.title}",
        f"Stakeholder: {persona.display_name}",
        f"Stakeholder key: {persona_id}",
        f"Role: {persona.role}",
    ]
    if system_role:
        text_parts.append(f"System role: {system_role}")
    if caps:
        text_parts.append(f"Capabilities: {', '.join(caps)}")
    text_parts.extend(
        [
            f"Sheet: {sheet}",
            f"Kind: {kind}",
            f"Family: {family}",
            f"Category: {fact.category or kind}",
            f"Statement: {statement}",
        ]
    )
    for idx, criterion in enumerate(fact.acceptance_criteria or [], start=1):
        text_c = str(criterion).strip()
        if text_c:
            text_parts.append(f"Acceptance criterion {idx}: {text_c}")
    text = "\n".join(text_parts)
    meta = {
        "source": "scenario",
        "sheet": sheet,
        "sheet_type": kind,
        "kind": kind,
        "family": family,
        "category": fact.category or kind,
        "scenario_slug": package.meta.slug,
        "scenario_version": package.meta.version,
        "persona_key": persona_id,
        "fact_id": fact.id,
        "node_id": fact_node_id(package.meta.slug, fact.id),
        "disclosure": fact.disclosure.value if hasattr(fact.disclosure, "value") else str(fact.disclosure),
        "system_role": system_role,
        "keywords": ",".join(filter(None, [kind, family, (fact.category or "").replace("_", ",")])),
        "row": 0,
    }
    doc_id = (
        f"scenario:{package.meta.slug}:{package.meta.version}:{persona_id}:{fact.id}"
    )
    return text, meta, doc_id


def build_persona_documents(package: ScenarioPackage) -> tuple[list[str], list[dict], list[str]]:
    """One Chroma doc per (persona, fact) so vector search can filter by persona_key."""
    documents: list[str] = []
    metadatas: list[dict] = []
    ids: list[str] = []
    for persona in package.personas:
        for fact in facts_for_persona(package, persona.id, include_never_student=False):
            text, meta, doc_id = _fact_document(package, persona, fact)
            documents.append(text)
            metadatas.append(meta)
            ids.append(doc_id)
    return documents, metadatas, ids


def _packages_content_hash(packages: list[ScenarioPackage], *, kind: str) -> str:
    parts = [kind]
    for package in packages:
        docs, _, ids = build_persona_documents(package)
        parts.append(package.meta.slug)
        parts.append(package.meta.version)
        parts.extend(ids)
        parts.extend(docs)
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def index_packages_to_vector(rag, packages: Optional[list[ScenarioPackage]] = None) -> int:
    """Upsert persona-scoped facts into the RAG scenario collection. Returns doc count."""
    if rag is None or not hasattr(rag, "upsert_scenario_documents"):
        return 0
    packages = packages or list(scenario_registry._latest.values())
    all_docs: list[str] = []
    all_meta: list[dict] = []
    all_ids: list[str] = []
    for package in packages:
        docs, metas, ids = build_persona_documents(package)
        all_docs.extend(docs)
        all_meta.extend(metas)
        all_ids.extend(ids)
    if not all_docs:
        return 0
    content_hash = _packages_content_hash(packages, kind="vector")
    before = getattr(rag, "_scenario_index_hash", None)
    rag.upsert_scenario_documents(all_docs, all_meta, all_ids, content_hash=content_hash)
    if before == content_hash:
        return 0
    return len(all_docs)


def index_packages_to_neo4j(rag_neo4j, packages: Optional[list[ScenarioPackage]] = None) -> int:
    """Upsert persona/fact graph for scenario packages. Returns edge count."""
    if rag_neo4j is None or not hasattr(rag_neo4j, "upsert_scenario_graph"):
        return 0
    packages = packages or list(scenario_registry._latest.values())
    content_hash = _packages_content_hash(packages, kind="neo4j")
    return rag_neo4j.upsert_scenario_graph(packages, content_hash=content_hash)


def index_all_scenarios(*, vector_rag=None, neo4j_rag=None) -> dict[str, int]:
    packages = list(scenario_registry._latest.values())
    return {
        "packages": len(packages),
        "vector_docs": index_packages_to_vector(vector_rag, packages),
        "neo4j_edges": index_packages_to_neo4j(neo4j_rag, packages),
    }


def reload_and_index_scenarios(*, engine=None, vector_rag=None, neo4j_rag=None) -> dict[str, Any]:
    """Reload packages from disk, optionally re-seed DB, then refresh vector + graph indexes.

    Direct/scenario preprompt modes read the in-memory registry + persona pack adapter, so a
    reload is required before those modes see package edits without an app restart.
    """
    from app.seed import seed_scenarios

    seed_info = seed_scenarios(engine=engine)
    index_info = index_all_scenarios(vector_rag=vector_rag, neo4j_rag=neo4j_rag)
    return {
        "seed": seed_info,
        "index": index_info,
        "modes_refreshed": ["yaml", "direct", "vector", "neo4j", "hybrid"],
    }
