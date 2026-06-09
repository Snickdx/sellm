"""Test Neo4j bolt connectivity using app/.env credentials."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / "app" / ".env")
load_dotenv(ROOT / ".env")

try:
    from neo4j import GraphDatabase
except ImportError:
    print("neo4j package not installed. Run: pip install neo4j")
    raise SystemExit(1)

uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
user = os.getenv("NEO4J_USER", "neo4j")
password = os.getenv("NEO4J_PASSWORD", "password")

print(f"URI:      {uri}")
print(f"User:     {user}")
print(f"Password: {'*' * len(password) if password else '(empty)'}")
print()

try:
    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    with driver.session() as session:
        row = session.run("RETURN 1 AS ok").single()
        count = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
    driver.close()
    print(f"OK — connected. Node count: {count}")
    if count == 0:
        print("Graph is empty. Load data: python -m setup.neo4j.load_graph")
    raise SystemExit(0)
except Exception as exc:
    msg = str(exc)
    print(f"FAIL — {msg}")
    print()
    if "Unauthorized" in msg or "authentication" in msg.lower():
        print("Password mismatch. Your Neo4j server is up but NEO4J_PASSWORD in app/.env is wrong.")
        print()
        print("Fix:")
        print("  1. Open http://localhost:7474 and connect (user: neo4j, your real password).")
        print("  2. Set the same password in app/.env → NEO4J_PASSWORD=...")
        print("  3. python -m setup.neo4j.test_connection")
        print("  4. python -m setup.neo4j.load_graph")
        print("  5. Restart the sellm server.")
        print()
        print("Note: app/.env comments mention Docker (magical_napier/password).")
        print("Docker Desktop is not running; the Windows 'neo4j' service on :7687 is active instead.")
    elif "Connection refused" in msg or "ServiceUnavailable" in msg:
        print("Neo4j is not listening. Start the Windows service or Docker container first.")
    raise SystemExit(1)
