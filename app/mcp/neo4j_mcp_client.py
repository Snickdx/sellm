"""Client for the official mcp-neo4j-cypher server (HTTP or stdio)."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from app.mcp.config import MCPSettings

logger = logging.getLogger(__name__)


def _parse_tool_result(result: Any) -> List[Dict[str, Any]]:
    """Normalize MCP CallToolResult content into row dicts."""
    rows: List[Dict[str, Any]] = []
    content = getattr(result, "content", None) or []
    for block in content:
        text = getattr(block, "text", None)
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    rows.append(item)
        elif isinstance(parsed, dict):
            rows.append(parsed)
    return rows


class Neo4jMCPClient:
    """Persistent MCP session to mcp-neo4j-cypher over streamable HTTP."""

    def __init__(self, settings: MCPSettings):
        self.settings = settings
        self._session = None
        self._streams = None
        self._client_ctx = None
        self._http_client = None
        self.status = "not_configured"
        self.last_error: Optional[str] = None

    @property
    def enabled(self) -> bool:
        return self.settings.neo4j_mcp_enabled and bool(self.settings.neo4j_mcp_url)

    async def connect(self) -> None:
        if not self.enabled:
            self.status = "disabled"
            return
        try:
            import httpx
            from mcp import ClientSession

            try:
                from mcp.client.streamable_http import streamable_http_client
            except ImportError:
                from mcp.client.streamable_http import streamablehttp_client as streamable_http_client

            self._http_client = httpx.AsyncClient(timeout=60.0)
            self._client_ctx = streamable_http_client(
                self.settings.neo4j_mcp_url,
                http_client=self._http_client,
            )
            read, write, _ = await self._client_ctx.__aenter__()
            self._streams = (read, write)
            self._session = ClientSession(read, write)
            await self._session.__aenter__()
            await self._session.initialize()
            self.status = "connected"
            logger.info("Neo4j MCP connected at %s", self.settings.neo4j_mcp_url)
        except Exception as exc:
            self.status = f"error: {exc}"
            self.last_error = str(exc)
            logger.warning("Neo4j MCP connect failed: %s", exc)
            await self.close()

    async def close(self) -> None:
        try:
            if self._session is not None:
                await self._session.__aexit__(None, None, None)
        except Exception:
            pass
        self._session = None
        try:
            if self._client_ctx is not None:
                await self._client_ctx.__aexit__(None, None, None)
        except Exception:
            pass
        self._client_ctx = None
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> List[Dict[str, Any]]:
        if self._session is None:
            raise RuntimeError("Neo4j MCP session is not connected")
        tool = self.settings.tool_name(name)
        result = await self._session.call_tool(tool, arguments)
        return _parse_tool_result(result)

    async def read_cypher(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        return await self.call_tool(
            "read_neo4j_cypher",
            {"query": query, "params": params or {}},
        )

    async def get_schema(self, sample: int = 500) -> List[Dict[str, Any]]:
        return await self.call_tool("get_neo4j_schema", {"sample_param": sample})


# Module-level singleton used by FastAPI lifespan
neo4j_mcp_client = Neo4jMCPClient(MCPSettings.from_env())
