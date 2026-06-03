"""Hybrid retrieval: route to Neo4j MCP/graph or Chroma, then merge for the LLM."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.mcp.chroma_retriever import ChromaRetriever
from app.mcp.config import MCPSettings
from app.mcp.neo4j_mcp_client import Neo4jMCPClient
from app.mcp.neo4j_retriever import Neo4jRetriever
from app.mcp.router import QueryRoute, RouteDecision, route_query, route_to_dict


@dataclass
class HybridRetrievalResult:
    results: List[Dict]
    route: str
    backends_used: List[str]
    routing: Dict[str, object] = field(default_factory=dict)


class HybridKnowledgeService:
    def __init__(
        self,
        chroma_rag: Any,
        neo4j_rag: Any,
        mcp_client: Optional[Neo4jMCPClient] = None,
        settings: Optional[MCPSettings] = None,
    ):
        self.settings = settings or MCPSettings.from_env()
        self.chroma = ChromaRetriever(chroma_rag)
        self.neo4j = Neo4jRetriever(neo4j_rag, mcp_client=mcp_client)

    async def retrieve(self, query: str, top_k: Optional[int] = None) -> HybridRetrievalResult:
        k_neo = top_k or self.settings.hybrid_neo4j_top_k
        k_chroma = top_k or self.settings.hybrid_chroma_top_k
        decision = route_query(query, margin=self.settings.hybrid_route_margin)

        if decision.route == QueryRoute.NEO4J:
            results = await self.neo4j.search(query, n_results=k_neo)
            routing = route_to_dict(decision)
            if not results and self.chroma.chroma_rag:
                results = self.chroma.search(query, n_results=k_chroma)
                routing["fallback"] = "chroma"
            backends = _backends_from_results(results, default=["neo4j"])
            return HybridRetrievalResult(
                results=results,
                route=QueryRoute.NEO4J.value,
                backends_used=backends,
                routing=routing,
            )

        if decision.route == QueryRoute.CHROMA:
            results = self.chroma.search(query, n_results=k_chroma)
            routing = route_to_dict(decision)
            if not results and self.neo4j.neo4j_rag:
                results = await self.neo4j.search(query, n_results=k_neo)
                routing["fallback"] = "neo4j"
            backends = _backends_from_results(results, default=["chroma"])
            return HybridRetrievalResult(
                results=results,
                route=QueryRoute.CHROMA.value,
                backends_used=backends,
                routing=routing,
            )

        # Blend: primary by score, enrich from secondary
        if decision.neo4j_score >= decision.chroma_score:
            primary = await self.neo4j.search(query, n_results=k_neo)
            secondary = self.chroma.search(query, n_results=max(1, k_chroma // 2))
            primary_name, secondary_name = "neo4j", "chroma"
        else:
            primary = self.chroma.search(query, n_results=k_chroma)
            secondary = await self.neo4j.search(query, n_results=max(1, k_neo // 2))
            primary_name, secondary_name = "chroma", "neo4j"

        merged = _merge_results(primary, secondary, max_items=max(k_neo, k_chroma))
        backends = _backends_from_results(merged, default=[primary_name, secondary_name])
        routing = route_to_dict(decision)
        routing["blend_primary"] = primary_name
        routing["blend_secondary"] = secondary_name
        return HybridRetrievalResult(
            results=merged,
            route=QueryRoute.BLEND.value,
            backends_used=backends,
            routing=routing,
        )


def _backends_from_results(results: List[Dict], default: List[str]) -> List[str]:
    found = []
    for row in results:
        backend = (row.get("metadata") or {}).get("backend")
        if backend and backend not in found:
            found.append(backend)
    return found or default


def _merge_results(
    primary: List[Dict],
    secondary: List[Dict],
    max_items: int,
) -> List[Dict]:
    merged: List[Dict] = []
    seen_docs = set()
    for batch in (primary, secondary):
        for item in batch:
            doc = item.get("document", "")
            if not doc or doc in seen_docs:
                continue
            merged.append(item)
            seen_docs.add(doc)
            if len(merged) >= max_items:
                return merged
    return merged
