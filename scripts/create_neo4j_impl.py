"""Compatibility entrypoint for app Neo4j loader."""

from app.scripts.create_neo4j_impl import main


if __name__ == "__main__":
    raise SystemExit(main())
