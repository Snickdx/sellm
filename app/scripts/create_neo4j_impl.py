"""App-local entrypoint for Neo4j graph loader."""

from setup.neo4j.load_graph import main


if __name__ == "__main__":
    raise SystemExit(main())

