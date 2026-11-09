#!/usr/bin/env python3
"""Reload sellm/scenarios YAML into the registry and refresh vector + Neo4j indexes.

Use after editing scenario YAML so yaml/direct (preprompt), vector, and graph modes stay aligned.
Prefer the running admin API when the server is up:

  POST /api/admin/scenarios/reindex

This CLI is for offline/dev use when you can import app with RAG backends configured.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    # Lightweight path: reload registry only, then index if backends import cleanly.
    from app.seproject.indexing import reload_and_index_scenarios
    from app.seproject.scenarios.loader import default_scenarios_root

    vector_rag = None
    neo4j_rag = None
    excel = os.getenv("EXCEL_FILE") or str(ROOT / "data.xlsx")
    chroma = os.getenv("CHROMA_PERSIST_DIRECTORY") or str(ROOT / "storage" / "chroma")

    try:
        from app.rag_backend import RequirementsRAG

        if Path(excel).is_file():
            vector_rag = RequirementsRAG(excel, persist_directory=chroma)
    except Exception as exc:  # noqa: BLE001 — best-effort offline index
        print(f"⚠ vector backend unavailable: {exc}")

    try:
        if os.getenv("NEO4J_URI") or os.getenv("NEO4J_PASSWORD"):
            from app.rag_backend_neo4j import RequirementsRAGNeo4j

            neo4j_rag = RequirementsRAGNeo4j()
    except Exception as exc:  # noqa: BLE001
        print(f"⚠ neo4j backend unavailable: {exc}")

    result = reload_and_index_scenarios(vector_rag=vector_rag, neo4j_rag=neo4j_rag)
    print(f"scenarios root: {default_scenarios_root()}")
    print(f"seed: {result['seed']}")
    print(f"index: {result['index']}")
    print(f"modes refreshed: {result['modes_refreshed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
