"""
Warm Neo4j connection (scenario graph is loaded via reindex; Excel optional).
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.rag_backend_neo4j import RequirementsRAGNeo4j


def main() -> int:
    load_dotenv(ROOT / "app" / ".env")
    load_dotenv(ROOT / ".env")
    excel_raw = (os.getenv("EXCEL_FILE") or "").strip()
    excel_file = excel_raw if excel_raw and Path(excel_raw).is_file() else None
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "password")

    print("Connecting Neo4j...")
    print(f"Excel file: {excel_file or '(none — use scripts/reindex_scenarios.py)'}")
    print(f"Neo4j URI: {neo4j_uri}")
    print(f"Neo4j user: {neo4j_user}")

    rag = RequirementsRAGNeo4j(
        excel_file,
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_password,
    )
    print(f"Neo4j ready. Node count: {rag._count_nodes()}")
    rag.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
