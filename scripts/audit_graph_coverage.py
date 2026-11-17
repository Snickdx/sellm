#!/usr/bin/env python3
"""Audit live Neo4j ScenarioPack graph vs YAML authoring for the new edge model."""

from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / "app" / ".env")
    load_dotenv(ROOT / ".env")

    from neo4j import GraphDatabase

    from app.scenarios.loader import default_scenarios_root, load_scenario_package
    from app.scenarios.neo4j_graph import fact_kind_and_label

    root = default_scenarios_root()
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD") or ""
    driver = GraphDatabase.driver(uri, auth=(user, password))

    edge_types = [
        "KNOWS",
        "OWNED_BY",
        "SATISFIES",
        "DERIVES_FROM",
        "DEPENDS_ON",
        "VERIFIED_BY",
        "HAS_CRITERION",
        "HAS_FACT",
        "HAS_PERSONA",
    ]

    print("=== LIVE NEO4J (ScenarioPack) ===")
    with driver.session() as session:
        total = session.run("MATCH (n:ScenarioPack) RETURN count(n) AS c").single()["c"]
        print(f"nodes={total}")
        for record in session.run(
            """
            MATCH (n:ScenarioPack)
            WHERE n.scenario_slug IS NOT NULL
            RETURN n.scenario_slug AS slug, count(n) AS nodes
            ORDER BY slug
            """
        ):
            print(f"  nodes {record['slug']}: {record['nodes']}")

        print("edges by type/slug:")
        for edge_type in edge_types:
            rows = list(
                session.run(
                    f"""
                    MATCH (a:ScenarioPack)-[r:{edge_type}]->(b)
                    WITH coalesce(a.scenario_slug, b.scenario_slug) AS slug, count(r) AS c
                    WHERE slug IS NOT NULL
                    RETURN slug, c ORDER BY slug
                    """
                )
            )
            if not rows:
                print(f"  {edge_type}: 0")
                continue
            parts = ", ".join(f"{row['slug']}={row['c']}" for row in rows)
            print(f"  {edge_type}: {parts}")

    print()
    print("=== AUTHORING AUDIT (YAML) ===")
    needs_authoring: list[str] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or not (child / "scenario.yaml").is_file():
            continue
        package = load_scenario_package(child)
        slug = package.meta.slug
        facts = package.facts
        kinds = Counter(fact_kind_and_label(fact)[0] for fact in facts)
        with_sat = sum(1 for fact in facts if fact.satisfies_ids)
        with_der = sum(1 for fact in facts if fact.derives_from_ids)
        with_dep = sum(1 for fact in facts if fact.depends_on_ids)
        vers = [fact for fact in facts if fact_kind_and_label(fact)[0] == "verification"]
        ver_outbound = sum(
            1
            for fact in vers
            if fact.satisfies_ids or fact.derives_from_ids or fact.depends_on_ids
        )
        reqs_to_ver = 0
        for fact in facts:
            for target_id in fact.depends_on_ids or []:
                target = next((item for item in facts if item.id == target_id), None)
                if target and fact_kind_and_label(target)[0] == "verification":
                    reqs_to_ver += 1

        status = package.meta.status.value if hasattr(package.meta.status, "value") else str(package.meta.status)
        print(
            f"{slug}: facts={len(facts)} personas={len(package.personas)} status={status}"
        )
        print(f"  kinds={dict(kinds)}")
        print(
            f"  link fields: satisfies={with_sat} derives_from={with_der} depends_on={with_dep}"
        )
        print(
            f"  VER facts={len(vers)} with_outbound_links={ver_outbound} "
            f"facts_depending_on_VER={reqs_to_ver}"
        )

        gaps = []
        if len(vers) and ver_outbound == 0 and reqs_to_ver == 0:
            gaps.append("VERIFIED_BY needs VER↔FR link fields")
        if with_sat == 0:
            gaps.append("no satisfies_ids")
        if with_der == 0:
            gaps.append("no derives_from_ids")
        if with_dep == 0:
            gaps.append("no depends_on_ids")
        if gaps:
            needs_authoring.append(f"{slug}: " + "; ".join(gaps))

    print()
    print("=== VERDICT ===")
    if not needs_authoring:
        print("All scenarios have enough link fields for the new edge model.")
    else:
        print("Further authoring recommended:")
        for line in needs_authoring:
            print(f"  - {line}")
        print(
            "Reindex alone cannot create VERIFIED_BY without YAML link fields "
            "(depends_on_ids / satisfies_ids / derives_from_ids on VER or FR)."
        )

    driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
