"""YAML → Neo4j graph translation (no live Neo4j required)."""

from __future__ import annotations

from pathlib import Path

from app.scenarios.loader import load_scenario_package
from app.scenarios.neo4j_graph import (
    EXCEL_PARITY_GAPS,
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
    assert fact_kind_and_label(req) == ("requirement", "YamlRequirement")
    assert fact_kind_and_label(br) == ("constraint", "YamlConstraint")


def test_library_plan_has_typed_facts_and_domain_edges():
    package = load_scenario_package(Path("scenarios/library"))
    plan = build_scenario_graph_plan(package)

    assert plan.stats["facts"] > 0
    assert plan.stats.get("kind_requirement", 0) > 0
    assert plan.stats.get("kind_constraint", 0) > 0

    fact_nodes = [n for n in plan.nodes if "YamlFact" in n.labels]
    assert fact_nodes
    assert any("YamlRequirement" in n.labels for n in fact_nodes)
    assert any("YamlConstraint" in n.labels for n in fact_nodes)

    rel_types = {e.rel_type for e in plan.edges}
    assert {"HAS_FACT", "KNOWS", "IN_CATEGORY", "IN_FAMILY", "HAS_CRITERION"} <= rel_types

    assert any("YamlAcceptanceCriterion" in n.labels for n in plan.nodes)
    assert any("YamlCategory" in n.labels for n in plan.nodes)
    assert any("YamlFactFamily" in n.labels for n in plan.nodes)


def test_excel_parity_gaps_documented():
    statuses = {g["status"] for g in EXCEL_PARITY_GAPS}
    assert "gap" in statuses
    assert "mapped" in statuses
    assert "partial" in statuses
    assert any("Feature" in g["excel"] for g in EXCEL_PARITY_GAPS)
