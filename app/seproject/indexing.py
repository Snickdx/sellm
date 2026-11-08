"""Index YAML scenario persona facts into Chroma (vector) and Neo4j (graph)."""

from __future__ import annotations

from typing import Any, Optional

from app.seproject.scenarios.filter import facts_for_persona
from app.seproject.scenarios.models import ScenarioPackage
from app.seproject.scenarios.registry import scenario_registry


def _fact_document(package: ScenarioPackage, persona_id: str, fact) -> tuple[str, dict[str, Any], str]:
    statement = fact.statement.strip()
    category = fact.category or "knowledge"
    text = (
        f"Scenario: {package.meta.title}\n"
        f"Persona: {persona_id}\n"
        f"Category: {category}\n"
        f"Statement: {statement}"
    )
    meta = {
        "source": "yaml",
        "sheet": "Knowledge",
        "sheet_type": "requirements",
        "scenario_slug": package.meta.slug,
        "scenario_version": package.meta.version,
        "persona_key": persona_id,
        "fact_id": fact.id,
        "disclosure": fact.disclosure.value if hasattr(fact.disclosure, "value") else str(fact.disclosure),
        "category": category,
        "keywords": category.replace("_", ","),
        "row": 0,
    }
    doc_id = f"yaml:{package.meta.slug}:{package.meta.version}:{persona_id}:{fact.id}"
    return text, meta, doc_id


def build_persona_documents(package: ScenarioPackage) -> tuple[list[str], list[dict], list[str]]:
    """One Chroma doc per (persona, fact) so vector search can filter by persona_key."""
    documents: list[str] = []
    metadatas: list[dict] = []
    ids: list[str] = []
    for persona in package.personas:
        for fact in facts_for_persona(package, persona.id, include_never_student=False):
            text, meta, doc_id = _fact_document(package, persona.id, fact)
            documents.append(text)
            metadatas.append(meta)
            ids.append(doc_id)
    return documents, metadatas, ids


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
    rag.upsert_scenario_documents(all_docs, all_meta, all_ids)
    return len(all_docs)


def index_packages_to_neo4j(rag_neo4j, packages: Optional[list[ScenarioPackage]] = None) -> int:
    """Upsert persona/fact graph for YAML scenarios. Returns fact-edge count."""
    if rag_neo4j is None or not hasattr(rag_neo4j, "upsert_scenario_graph"):
        return 0
    packages = packages or list(scenario_registry._latest.values())
    return rag_neo4j.upsert_scenario_graph(packages)


def index_all_scenarios(*, vector_rag=None, neo4j_rag=None) -> dict[str, int]:
    packages = list(scenario_registry._latest.values())
    return {
        "packages": len(packages),
        "vector_docs": index_packages_to_vector(vector_rag, packages),
        "neo4j_edges": index_packages_to_neo4j(neo4j_rag, packages),
    }
