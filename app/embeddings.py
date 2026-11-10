"""Shared SentenceTransformer singleton for Chroma + Neo4j RAG."""

from __future__ import annotations

from functools import lru_cache
from typing import Any


DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def get_embedding_model(model_name: str = DEFAULT_EMBEDDING_MODEL) -> Any:
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)
