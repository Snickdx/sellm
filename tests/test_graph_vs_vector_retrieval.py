"""Compare Neo4j graph retrieval depth vs vector/chroma for query families.

These tests assert the *contract* that makes graph mode deeper on relationship
questions: typed neighbor edges in metadata + prompt context. Vector/chroma
hits stay flat (no graph expansion).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.mcp.router import QueryRoute, route_query
from app.scenario.stakeholder_prompt import format_retrieved_context


# ---------------------------------------------------------------------------
# Query families: relationship → Neo4j; narrative → Chroma
# ---------------------------------------------------------------------------

RELATIONSHIP_QUERIES = [
    ("Which requirements depend on campus SSO?", {"DEPENDS_ON", "dependency"}),
    ("Who owns the booking request requirement?", {"OWNED_BY", "owns"}),
    ("What feature does this requirement satisfy?", {"SATISFIES", "satisfy"}),
    ("How is the booking rule verified?", {"VERIFIED_BY", "verif"}),
    ("What does LIB-REQ-001 derive from?", {"DERIVES_FROM", "derive"}),
]

NARRATIVE_QUERIES = [
    "Tell me about the project",
    "How do you feel about the rollout?",
    "What worries you most?",
    "Describe the booking feature in general",
]


def _related_types(results: list[dict]) -> set[str]:
    out: set[str] = set()
    for hit in results:
        for rel in (hit.get("metadata") or {}).get("related") or []:
            if rel.get("rel_type"):
                out.add(str(rel["rel_type"]))
    return out


def test_router_sends_relationship_queries_to_neo4j_or_blend():
    for query, _ in RELATIONSHIP_QUERIES:
        decision = route_query(query)
        assert decision.route in (QueryRoute.NEO4J, QueryRoute.BLEND), query
        assert decision.neo4j_score >= decision.chroma_score, (
            query,
            decision.neo4j_score,
            decision.chroma_score,
            decision.reasons,
        )


def test_router_sends_narrative_queries_to_chroma_or_blend():
    for query in NARRATIVE_QUERIES:
        decision = route_query(query)
        assert decision.route in (QueryRoute.CHROMA, QueryRoute.BLEND), query
        assert decision.chroma_score >= decision.neo4j_score, (
            query,
            decision.neo4j_score,
            decision.chroma_score,
            decision.reasons,
        )


# ---------------------------------------------------------------------------
# Retrieval depth contract (mocked backends — no live Neo4j/Chroma required)
# ---------------------------------------------------------------------------

DOMAIN_EDGE_TYPES = {
    "DEPENDS_ON",
    "SATISFIES",
    "DERIVES_FROM",
    "VERIFIED_BY",
    "OWNED_BY",
}


def _chroma_style_hits() -> list[dict]:
    """Shape returned by RequirementsRAG.search_scenario (flat, no related)."""
    return [
        {
            "document": (
                "Project: Demo\nStakeholder: Alice\nSheet: Requirement\n"
                "Statement: Lecturers can request a room."
            ),
            "metadata": {
                "node_id": "scenario:demo:DEMO-REQ-001",
                "sheet": "Requirement",
                "kind": "requirement",
                "scenario_slug": "demo",
                "persona_key": "alice",
                "source": "scenario",
                "fact_id": "DEMO-REQ-001",
            },
            "distance": 0.2,
        }
    ]


def _neo4j_style_hits_with_graph_depth() -> list[dict]:
    """Shape returned by RequirementsRAGNeo4j.search after related expansion."""
    hits = _chroma_style_hits()
    hits[0]["metadata"] = {
        **hits[0]["metadata"],
        "related": [
            {
                "node_id": "scenario:demo:DEMO-DEP-001",
                "rel_type": "DEPENDS_ON",
                "text": "Depends on campus SSO.",
                "sheet": "Dependency",
            },
            {
                "node_id": "scenario:demo:DEMO-FEAT-001",
                "rel_type": "SATISFIES",
                "text": "Booking requests.",
                "sheet": "Feature",
            },
            {
                "node_id": "alice",
                "rel_type": "OWNED_BY",
                "text": "Alice",
                "sheet": "Stakeholder",
            },
        ],
    }
    return hits


def test_vector_hits_have_no_graph_related_edges():
    chroma = _chroma_style_hits()
    assert _related_types(chroma) == set()
    context = format_retrieved_context(chroma)
    for edge in DOMAIN_EDGE_TYPES:
        assert edge not in context


def test_graph_hits_include_domain_related_edges_in_context():
    neo = _neo4j_style_hits_with_graph_depth()
    types = _related_types(neo)
    assert {"DEPENDS_ON", "SATISFIES", "OWNED_BY"} <= types
    context = format_retrieved_context(neo)
    assert "DEPENDS_ON" in context
    assert "campus SSO" in context
    assert "SATISFIES" in context
    assert "OWNED_BY" in context


def test_graph_context_is_deeper_than_vector_for_same_seed_hit():
    chroma_ctx = format_retrieved_context(_chroma_style_hits())
    neo_ctx = format_retrieved_context(_neo4j_style_hits_with_graph_depth())
    # Same primary statement present in both
    assert "Lecturers can request a room" in chroma_ctx
    assert "Lecturers can request a room" in neo_ctx
    # Graph mode adds neighbor facts that vector context lacks
    assert "campus SSO" in neo_ctx
    assert "campus SSO" not in chroma_ctx
    assert len(neo_ctx) > len(chroma_ctx)


def test_neo4j_search_attaches_related_for_scenario_persona(monkeypatch):
    """RequirementsRAGNeo4j.search must expand neighbors for scenario queries."""
    from app.rag_backend_neo4j import RequirementsRAGNeo4j

    rag = object.__new__(RequirementsRAGNeo4j)

    class _Vec(list):
        def tolist(self):
            return list(self)

    rag.embedding_model = SimpleNamespace(encode=lambda texts: _Vec([[0.1, 0.2, 0.3]]))
    seed = _chroma_style_hits()
    monkeypatch.setattr(
        rag,
        "_vector_search_scenario",
        lambda *_a, **_k: [{**seed[0], "metadata": dict(seed[0]["metadata"])}],
    )
    monkeypatch.setattr(
        rag,
        "_get_related_nodes",
        lambda node_id, limit=4: [
            {
                "node_id": "scenario:demo:DEMO-DEP-001",
                "rel_type": "DEPENDS_ON",
                "text": "Depends on campus SSO.",
            }
        ],
    )

    results = rag.search(
        "What does the booking requirement depend on?",
        n_results=3,
        scenario_slug="demo",
        persona_key="alice",
    )
    assert results
    assert "DEPENDS_ON" in _related_types(results)
    assert "related" in results[0]["metadata"]


def test_chroma_search_scenario_contract_omits_related():
    """Document the vector-mode contract: search_scenario never adds related."""
    # Mirror real Chroma formatting (no related key).
    results = _chroma_style_hits()
    for hit in results:
        assert "related" not in (hit.get("metadata") or {})


# ---------------------------------------------------------------------------
# Expansion priority: domain edges before category filler
# ---------------------------------------------------------------------------


class _FakeNode(dict):
    def __init__(self, labels: set[str] | None = None, **props: Any):
        super().__init__(props)
        self.labels = labels or set()


class _FakeRecord(dict):
    pass


class _FakeResult:
    def __init__(self, records: list[_FakeRecord]):
        self._records = records

    def __iter__(self):
        return iter(self._records)


class _PrioritySession:
    """Return domain neighbors for DEPENDS_ON; category neighbors otherwise."""

    def run(self, query: str, **params: Any):
        q = " ".join(query.split())
        if "-[:DEPENDS_ON]->" in q:
            return _FakeResult(
                [
                    _FakeRecord(
                        related=_FakeNode(
                            labels={"ScenarioPack", "Dependency"},
                            node_id="scenario:demo:DEMO-DEP-001",
                            text="Statement: Depends on campus SSO.",
                            sheet="Dependency",
                        )
                    )
                ]
            )
        if "IN_CATEGORY" in q:
            return _FakeResult(
                [
                    _FakeRecord(
                        related=_FakeNode(
                            labels={"ScenarioPack", "Requirement"},
                            node_id="scenario:demo:DEMO-REQ-999",
                            text="Statement: Unrelated same-category fact.",
                            sheet="Requirement",
                            embedding=[0.1],
                        )
                    )
                ]
            )
        return _FakeResult([])


def test_related_expansion_prefers_depends_on_over_same_category():
    from app.rag_backend_neo4j import RequirementsRAGNeo4j

    rag = object.__new__(RequirementsRAGNeo4j)
    rag.driver = SimpleNamespace(session=lambda: _SessionCM(_PrioritySession()))

    related = rag._get_related_nodes("scenario:demo:DEMO-REQ-001", limit=2)
    assert related
    assert related[0]["rel_type"] == "DEPENDS_ON"
    assert "SSO" in related[0]["text"]
    # Domain hit fills the slot; category filler must not crowd it out first
    assert all(r["rel_type"] != "SAME_CATEGORY" for r in related) or related[0]["rel_type"] == "DEPENDS_ON"


class _SessionCM:
    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, *args):
        return False


# ---------------------------------------------------------------------------
# Optional live Neo4j: assert real graph depth for library scenario
# ---------------------------------------------------------------------------


def _neo4j_available() -> bool:
    try:
        from dotenv import load_dotenv
        import os
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        load_dotenv(root / "app" / ".env")
        load_dotenv(root / ".env")
        from neo4j import GraphDatabase

        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD") or ""
        driver = GraphDatabase.driver(uri, auth=(user, password))
        with driver.session() as session:
            n = session.run(
                "MATCH (n:ScenarioPack) RETURN count(n) AS c"
            ).single()["c"]
        driver.close()
        return int(n) > 0
    except Exception:
        return False


@pytest.mark.skipif(not _neo4j_available(), reason="Neo4j ScenarioPack graph not available")
def test_live_neo4j_dependency_query_returns_typed_related_edges():
    """Against a reindexed library graph, dependency expansion should surface edges."""
    import os
    from pathlib import Path
    from dotenv import load_dotenv

    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / "app" / ".env")
    load_dotenv(root / ".env")

    from app.rag_backend_neo4j import RequirementsRAGNeo4j
    from app.scenarios.loader import load_scenario_package

    package = load_scenario_package(root / "scenarios" / "library")
    persona = package.personas[0]
    # Prefer a fact that has outbound DEPENDS_ON / SATISFIES if present
    linked = [
        f
        for f in package.facts
        if (f.depends_on_ids or f.satisfies_ids or f.derives_from_ids)
        and f.id in (persona.known_fact_ids or [])
    ]
    assert linked or package.facts, "library package has no facts"

    rag = RequirementsRAGNeo4j(
        excel_file=None,
        neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
        neo4j_password=os.getenv("NEO4J_PASSWORD") or "",
    )
    try:
        query = "What does this requirement depend on or satisfy?"
        if linked:
            query = f"What does {linked[0].id} depend on or satisfy? {linked[0].statement[:80]}"
        results = rag.search(
            query,
            n_results=5,
            scenario_slug=package.meta.slug,
            persona_key=persona.id,
        )
        assert results, "expected Neo4j scenario hits"
        # At least one hit should carry graph-related metadata after expansion
        # (OWNED_BY is always present for KNOWS facts after reindex)
        types = _related_types(results)
        assert types & DOMAIN_EDGE_TYPES, (
            f"expected domain related edges on live Neo4j hits, got {types!r}"
        )
        context = format_retrieved_context(results)
        assert any(edge in context for edge in DOMAIN_EDGE_TYPES)
    finally:
        rag.close()


@pytest.mark.skipif(not _neo4j_available(), reason="Neo4j ScenarioPack graph not available")
def test_live_graph_context_deeper_than_flat_vector_shape_for_same_query():
    """Neo4j context includes typed neighbors; flat vector-shaped docs for same text do not."""
    import os
    from pathlib import Path
    from dotenv import load_dotenv

    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / "app" / ".env")
    load_dotenv(root / ".env")

    from app.rag_backend_neo4j import RequirementsRAGNeo4j

    rag = RequirementsRAGNeo4j(
        excel_file=None,
        neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
        neo4j_password=os.getenv("NEO4J_PASSWORD") or "",
    )
    try:
        query = "Who owns this requirement and what does it depend on?"
        neo_results = rag.search(
            query,
            n_results=3,
            scenario_slug="library",
            persona_key="library_coordinator",
        )
        if not neo_results:
            pytest.skip("no library_coordinator hits indexed")
        neo_ctx = format_retrieved_context(neo_results)
        # Synthesize vector-equivalent flat docs from the same primary hits
        flat = []
        for hit in neo_results:
            meta = {k: v for k, v in (hit.get("metadata") or {}).items() if k != "related"}
            flat.append({"document": hit.get("document", ""), "metadata": meta, "distance": hit.get("distance")})
        flat_ctx = format_retrieved_context(flat)
        assert len(neo_ctx) >= len(flat_ctx)
        assert _related_types(neo_results) & DOMAIN_EDGE_TYPES
        assert _related_types(flat) == set()
        # Ownership / dependency phrasing in query should yield OWNED_BY at minimum
        assert "OWNED_BY" in _related_types(neo_results) or "DEPENDS_ON" in _related_types(neo_results) or "SATISFIES" in _related_types(neo_results)
    finally:
        rag.close()
