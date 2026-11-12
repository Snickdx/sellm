"""Scenario → Neo4j/vector domain translation (no live Neo4j required)."""

from __future__ import annotations

from pathlib import Path

from app.indexing import build_persona_documents
from app.scenarios.loader import load_scenario_package
from app.scenarios.neo4j_graph import (
    EXCEL_PARITY_GAPS,
    SCENARIO_PACK_LABEL,
    build_scenario_graph_plan,
    fact_kind_and_label,
)
from app.scenarios.models import (
    Disclosure,
    FactOrigin,
    FactStatus,
    KnowledgeFact,
)


def test_fact_kind_mapping_by_category_and_prefix():
    req = KnowledgeFact(
        id="LIB-REQ-001",
        statement="Lecturers can request bookings.",
        category="functional",
        status=FactStatus.confirmed,
        origin=FactOrigin.instructor,
        disclosure=Disclosure.when_relevant,
    )
    br = KnowledgeFact(
        id="LIB-BR-001",
        statement="No overbooking.",
        category="constraint",
        status=FactStatus.confirmed,
        origin=FactOrigin.instructor,
        disclosure=Disclosure.when_relevant,
    )
    assert fact_kind_and_label(req) == ("requirement", "Requirement", "Requirement")
    assert fact_kind_and_label(br) == ("constraint", "Constraint", "Constraint")


def test_library_plan_uses_domain_labels_not_yaml():
    package = load_scenario_package(Path("scenarios/library"))
    plan = build_scenario_graph_plan(package)

    assert plan.stats["facts"] > 0
    assert plan.stats.get("kind_requirement", 0) > 0
    assert plan.stats.get("kind_constraint", 0) > 0

    for node in plan.nodes:
        assert SCENARIO_PACK_LABEL in node.labels
        assert all(not label.startswith("Yaml") for label in node.labels)
        assert "yaml" not in str(node.key).lower()
        if "node_id" in node.key:
            assert not str(node.key["node_id"]).startswith("yaml:")

    fact_nodes = [n for n in plan.nodes if n.props.get("fact_id")]
    assert fact_nodes
    assert any("Requirement" in n.labels for n in fact_nodes)
    assert any("Constraint" in n.labels for n in fact_nodes)
    assert any(str(n.key.get("node_id", "")).startswith("scenario:") for n in fact_nodes)

    rel_types = {e.rel_type for e in plan.edges}
    assert {"HAS_FACT", "KNOWS", "IN_CATEGORY", "IN_FAMILY", "HAS_CRITERION"} <= rel_types
    assert any("Stakeholder" in n.labels for n in plan.nodes)
    assert any("Project" in n.labels for n in plan.nodes)
    assert any("AcceptanceCriterion" in n.labels for n in plan.nodes)


def test_vector_docs_use_domain_sheets_not_yaml_names():
    package = load_scenario_package(Path("scenarios/library"))
    docs, metas, ids = build_persona_documents(package)
    assert docs and metas and ids
    assert all(doc_id.startswith("scenario:") for doc_id in ids)
    assert all(not doc_id.startswith("yaml:") for doc_id in ids)
    sheets = {m["sheet"] for m in metas}
    assert "Requirement" in sheets
    assert "Constraint" in sheets
    assert "Knowledge" not in sheets
    for meta in metas:
        assert meta["source"] == "scenario"
        assert "yaml" not in meta["source"]
        assert meta["node_id"].startswith("scenario:")
        assert meta["sheet_type"]
        assert meta["kind"]


def test_excel_parity_gaps_documented():
    statuses = {g["status"] for g in EXCEL_PARITY_GAPS}
    assert "gap" in statuses
    assert "mapped" in statuses
    assert "partial" in statuses
    assert any("Feature" in g["excel"] for g in EXCEL_PARITY_GAPS)
