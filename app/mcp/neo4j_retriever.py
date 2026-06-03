"""Neo4j retrieval via MCP Cypher tools with local RAG fallback."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.mcp.neo4j_mcp_client import Neo4jMCPClient


def _tokenize(query: str, max_words: int = 8) -> List[str]:
    words = re.findall(r"[a-z0-9]{3,}", query.lower())
    stop = {
        "the",
        "and",
        "for",
        "what",
        "who",
        "how",
        "are",
        "is",
        "about",
        "tell",
        "me",
        "your",
        "you",
        "that",
        "this",
        "with",
        "from",
    }
    return [w for w in words if w not in stop][:max_words]


def _rows_to_results(rows: List[Dict[str, Any]], source: str) -> List[Dict]:
    results: List[Dict] = []
    for row in rows:
        text = (
            row.get("text")
            or row.get("n.text")
            or row.get("source")
            or row.get("document")
        )
        if not text:
            parts = [f"{k}: {v}" for k, v in row.items() if v is not None]
            text = "\n".join(parts)
        if not text:
            continue
        results.append(
            {
                "document": str(text),
                "metadata": {
                    "source": source,
                    "backend": "neo4j",
                    **{k: v for k, v in row.items() if k != "text"},
                },
                "distance": row.get("distance"),
            }
        )
    return results


class Neo4jRetriever:
    def __init__(
        self,
        neo4j_rag: Any,
        mcp_client: Optional[Neo4jMCPClient] = None,
    ):
        self.neo4j_rag = neo4j_rag
        self.mcp_client = mcp_client

    async def search(self, query: str, n_results: int = 5) -> List[Dict]:
        if self.mcp_client and self.mcp_client.status == "connected":
            try:
                return await self._search_mcp(query, n_results)
            except Exception as exc:
                print(f"⚠ Neo4j MCP search failed, using local graph RAG: {exc}")
        return self._search_local(query, n_results)

    async def _search_mcp(self, query: str, n_results: int) -> List[Dict]:
        words = _tokenize(query)
        if not words:
            return self._search_local(query, n_results)

        # Keyword match on requirement nodes (works without APOC on read path)
        cypher = """
        MATCH (n)
        WHERE n.text IS NOT NULL
          AND any(w IN $words WHERE toLower(n.text) CONTAINS w)
        WITH n,
             size([w IN $words WHERE toLower(n.text) CONTAINS w]) AS hit_count
        ORDER BY hit_count DESC
        LIMIT $limit
        OPTIONAL MATCH (n)-[r]-(related)
        WITH n, hit_count, collect(DISTINCT {
            rel: type(r),
            sheet: related.sheet,
            text: substring(coalesce(related.text, ''), 0, 200),
            node_id: related.node_id
        })[0..3] AS related
        RETURN n.text AS text,
               n.node_id AS node_id,
               n.sheet AS sheet,
               hit_count AS hit_count,
               related AS related
        """
        rows = await self.mcp_client.read_cypher(
            cypher,
            {"words": words, "limit": n_results},
        )
        results = _rows_to_results(rows, source="neo4j-mcp")
        if results:
            return results

        # Relationship-focused fallback when keyword match is thin
        rel_cypher = """
        MATCH (a)-[r]->(b)
        WHERE a.text IS NOT NULL AND b.text IS NOT NULL
          AND any(w IN $words WHERE toLower(a.text) CONTAINS w OR toLower(b.text) CONTAINS w)
        RETURN a.text AS source,
               type(r) AS rel,
               b.text AS target,
               b.sheet AS sheet
        LIMIT $limit
        """
        rel_rows = await self.mcp_client.read_cypher(
            rel_cypher,
            {"words": words, "limit": n_results},
        )
        formatted: List[Dict] = []
        for row in rel_rows:
            doc = (
                f"Relationship ({row.get('rel', 'RELATED')}): "
                f"{row.get('source', '')} -> {row.get('target', '')}"
            )
            formatted.append(
                {
                    "document": doc,
                    "metadata": {"source": "neo4j-mcp-rel", "backend": "neo4j", **row},
                    "distance": None,
                }
            )
        return formatted or self._search_local(query, n_results)

    def _search_local(self, query: str, n_results: int) -> List[Dict]:
        if not self.neo4j_rag:
            return []
        hits = self.neo4j_rag.search(
            query, n_results=n_results, filter_by_sheet_type=True
        )
        for hit in hits:
            meta = hit.setdefault("metadata", {})
            meta.setdefault("source", "neo4j-local")
            meta.setdefault("backend", "neo4j")
        return hits
