# Neo4j MCP + hybrid routing

The app can use the official **[mcp-neo4j-cypher](https://github.com/neo4j-contrib/mcp-neo4j)** server for graph reads. In **hybrid** response mode, a router picks the best knowledge source per query:

| Route | When | Backend |
|-------|------|---------|
| `neo4j` | Relationships, dependencies, paths, timelines, “how is X connected to Y” | Neo4j MCP (or local graph RAG fallback) |
| `chroma` | Broad / semantic / narrative questions (“tell me about goals…”) | Chroma vector index |
| `blend` | Close scores | Primary backend + secondary enrichment |

`mode_used` in chat responses looks like `hybrid:neo4j`, `hybrid:chroma`, or `hybrid:blend`.

## Cursor / Claude Desktop (stdio)

Copy env values from `app/.env` into [`config/mcp/neo4j-mcp.json`](../config/mcp/neo4j-mcp.json) or merge into your MCP config:

```json
{
  "mcpServers": {
    "sellm-neo4j": {
      "command": "uvx",
      "args": ["mcp-neo4j-cypher@0.6.0", "--transport", "stdio", "--read-only"],
      "env": {
        "NEO4J_URI": "neo4j+s://YOUR.databases.neo4j.io",
        "NEO4J_USERNAME": "neo4j",
        "NEO4J_PASSWORD": "YOUR_PASSWORD",
        "NEO4J_DATABASE": "neo4j",
        "NEO4J_READ_ONLY": "true"
      }
    }
  }
}
```

`get_neo4j_schema` requires **APOC** on the Neo4j instance. Read queries used by sellm’s hybrid router work without APOC.

## Docker Compose (HTTP MCP sidecar)

```bash
docker compose --profile mcp up --build
```

Set in `.env`:

```env
NEO4J_MCP_ENABLED=true
NEO4J_MCP_URL=http://mcp-neo4j:8000/mcp/
NEO4J_URI=bolt://host.docker.internal:7687
```

The `app` service connects to the sidecar over the internal network.

## App environment

| Variable | Default | Description |
|----------|---------|-------------|
| `NEO4J_MCP_ENABLED` | `true` if `NEO4J_MCP_URL` set | Use MCP for Neo4j reads in hybrid/neo4j paths |
| `NEO4J_MCP_URL` | — | e.g. `http://mcp-neo4j:8000/mcp/` |
| `NEO4J_MCP_NAMESPACE` | — | Tool prefix (e.g. `local-read_neo4j_cypher`) |
| `NEO4J_MCP_READ_ONLY` | `true` | Documented; server should run read-only |
| `HYBRID_ROUTE_MARGIN` | `0.15` | Score gap to pick a single backend vs blend |
| `HYBRID_NEO4J_TOP_K` | `3` | Neo4j hits per query |
| `HYBRID_CHROMA_TOP_K` | `3` | Chroma hits per query |

## Health / config API

- `GET /api/health` — includes `mcp.neo4j` status
- `GET /api/config` — hybrid routing settings and MCP URL (no secrets)

## Load graph data

```bash
python -m setup.neo4j.load_graph
```
