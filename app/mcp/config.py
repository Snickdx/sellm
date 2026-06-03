"""MCP and hybrid routing configuration from environment."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "")
    if not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on", "enabled")


@dataclass(frozen=True)
class MCPSettings:
    neo4j_mcp_url: str
    neo4j_mcp_enabled: bool
    neo4j_mcp_namespace: str
    neo4j_mcp_read_only: bool
    hybrid_route_margin: float
    hybrid_neo4j_top_k: int
    hybrid_chroma_top_k: int

    @classmethod
    def from_env(cls) -> "MCPSettings":
        url = (os.getenv("NEO4J_MCP_URL") or "").strip().rstrip("/")
        if url and not url.endswith("/mcp") and not url.endswith("/mcp/"):
            url = f"{url}/mcp/"
        enabled = _flag("NEO4J_MCP_ENABLED", default=bool(url))
        return cls(
            neo4j_mcp_url=url,
            neo4j_mcp_enabled=enabled and bool(url),
            neo4j_mcp_namespace=(os.getenv("NEO4J_MCP_NAMESPACE") or "").strip(),
            neo4j_mcp_read_only=_flag("NEO4J_MCP_READ_ONLY", default=True),
            hybrid_route_margin=float(os.getenv("HYBRID_ROUTE_MARGIN", "0.15")),
            hybrid_neo4j_top_k=int(os.getenv("HYBRID_NEO4J_TOP_K", os.getenv("HYBRID_TOP_K", "3"))),
            hybrid_chroma_top_k=int(os.getenv("HYBRID_CHROMA_TOP_K", os.getenv("HYBRID_TOP_K", "3"))),
        )

    def tool_name(self, base: str) -> str:
        if self.neo4j_mcp_namespace:
            return f"{self.neo4j_mcp_namespace}-{base}"
        return base
