"""Hybrid retrieval: query Chroma + Neo4j in parallel, merge results for the LLM."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.mcp.router import QueryRoute, RouteDecision, route_query, route_to_dict


@dataclass
class HybridRetrievalResult:
    results: List[Dict]
    route: str
    backends_used: List[str]
    routing: Dict[str, object] = field(default_factory=dict)


def _search_backend(rag: Any, query: str, n_results: int) -> List[Dict]:
    if not rag:
        return []
    return rag.search(query, n_results=n_results, filter_by_sheet_type=True)


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


def _tag_backend(results: List[Dict], tag: str) -> None:
    for hit in results:
        meta = hit.setdefault("metadata", {})
        meta["backend"] = tag


class HybridKnowledgeService:
    def __init__(
        self,
        chroma_rag: Any,
        neo4j_rag: Any,
        hybrid_top_k: int = 3,
        hybrid_route_margin: float = 0.15,
    ):
        self.chroma_rag = chroma_rag
        self.neo4j_rag = neo4j_rag
        self.hybrid_top_k = hybrid_top_k
        self.hybrid_route_margin = hybrid_route_margin

    def retrieve(self, query: str, top_k: Optional[int] = None) -> HybridRetrievalResult:
        k = top_k or self.hybrid_top_k
        decision = route_query(query, margin=self.hybrid_route_margin)

        if decision.route == QueryRoute.NEO4J:
            results = _search_backend(self.neo4j_rag, query, k)
            _tag_backend(results, "neo4j")
            routing = route_to_dict(decision)
            if not results:
                results = _search_backend(self.chroma_rag, query, k)
                _tag_backend(results, "chroma")
                routing["fallback"] = "chroma"
            return HybridRetrievalResult(
                results=results,
                route=QueryRoute.NEO4J.value,
                backends_used=list(dict.fromkeys(r.get("metadata", {}).get("backend", "") for r in results)),
                routing=routing,
            )

        if decision.route == QueryRoute.CHROMA:
            results = _search_backend(self.chroma_rag, query, k)
            _tag_backend(results, "chroma")
            routing = route_to_dict(decision)
            if not results:
                results = _search_backend(self.neo4j_rag, query, k)
                _tag_backend(results, "neo4j")
                routing["fallback"] = "neo4j"
            return HybridRetrievalResult(
                results=results,
                route=QueryRoute.CHROMA.value,
                backends_used=list(dict.fromkeys(r.get("metadata", {}).get("backend", "") for r in results)),
                routing=routing,
            )

        # Blend — primary by score, enrich from secondary
        if decision.neo4j_score >= decision.chroma_score:
            primary = _search_backend(self.neo4j_rag, query, k)
            _tag_backend(primary, "neo4j")
            secondary = _search_backend(self.chroma_rag, query, max(1, k // 2))
            _tag_backend(secondary, "chroma")
            primary_name, secondary_name = "neo4j", "chroma"
        else:
            primary = _search_backend(self.chroma_rag, query, k)
            _tag_backend(primary, "chroma")
            secondary = _search_backend(self.neo4j_rag, query, max(1, k // 2))
            _tag_backend(secondary, "neo4j")
            primary_name, secondary_name = "chroma", "neo4j"

        merged = _merge_results(primary, secondary, max_items=k)
        routing = route_to_dict(decision)
        routing["blend_primary"] = primary_name
        routing["blend_secondary"] = secondary_name
        return HybridRetrievalResult(
            results=merged,
            route=QueryRoute.BLEND.value,
            backends_used=list(dict.fromkeys(r.get("metadata", {}).get("backend", "") for r in merged)),
            routing=routing,
        )
