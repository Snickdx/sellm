"""Chroma vector knowledge base retriever (semantic RAG)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class ChromaRetriever:
    def __init__(self, chroma_rag: Any):
        self.chroma_rag = chroma_rag

    def search(self, query: str, n_results: int = 5) -> List[Dict]:
        if not self.chroma_rag:
            return []
        hits = self.chroma_rag.search(
            query, n_results=n_results, filter_by_sheet_type=True
        )
        for hit in hits:
            meta = hit.setdefault("metadata", {})
            meta.setdefault("source", "chroma")
            meta.setdefault("backend", "chroma")
        return hits
