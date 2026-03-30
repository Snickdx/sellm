"""
Neo4j loader utility.

Loads requirements data from Excel into Neo4j using environment configuration.
"""

import os


def main() -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        # Continue without .env support if python-dotenv is missing.
        pass

    excel_file = os.getenv("EXCEL_FILE", "data.xlsx")
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "password")

    print("Starting Neo4j load...")
    print(f"Excel file: {excel_file}")
    print(f"Neo4j URI: {neo4j_uri}")
    print(f"Neo4j User: {neo4j_user}")

    try:
        from rag_backend_neo4j import RequirementsRAGNeo4j

        rag = RequirementsRAGNeo4j(
            excel_file,
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
        )
        node_count = rag._count_nodes()
        print(f"Neo4j load complete. Node count: {node_count}")
        rag.close()
        return 0
    except Exception as e:
        print(f"Neo4j load failed: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
