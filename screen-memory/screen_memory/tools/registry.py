"""ToolRegistry: OpenClaw tool interface registration and dispatch."""

from __future__ import annotations

from typing import Any, Optional

from screen_memory.models.uri import NocturneUri
from screen_memory.storage.screenshot_repo import ScreenshotRepo
from screen_memory.services.graph_service import GraphService
from screen_memory.services.signal_service import SignalService


_TOOL_DEFINITIONS = [
    {
        "name": "memory_write",
        "description": "Write a memory to the URI Graph. Creates the node if it doesn't exist.",
        "parameters": {
            "type": "object",
            "properties": {
                "uri": {"type": "string", "description": "Nocturne URI (e.g. core://my/topic)"},
                "content": {"type": "string", "description": "Memory content to store"},
            },
            "required": ["uri", "content"],
        },
    },
    {
        "name": "memory_read",
        "description": "Read the latest memory at a URI.",
        "parameters": {
            "type": "object",
            "properties": {
                "uri": {"type": "string", "description": "Nocturne URI"},
            },
            "required": ["uri"],
        },
    },
    {
        "name": "memory_search",
        "description": "Full-text search across all memories.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "FTS5 search query"},
                "limit": {"type": "integer", "description": "Max results", "default": 20},
            },
            "required": ["query"],
        },
    },
    {
        "name": "memory_delete",
        "description": "Delete a node and all its memories from the graph.",
        "parameters": {
            "type": "object",
            "properties": {
                "uri": {"type": "string", "description": "Nocturne URI to delete"},
            },
            "required": ["uri"],
        },
    },
    {
        "name": "graph_query_subtree",
        "description": "Query the subtree rooted at a URI.",
        "parameters": {
            "type": "object",
            "properties": {
                "uri": {"type": "string", "description": "Root URI"},
                "max_depth": {"type": "integer", "description": "Max depth to traverse"},
            },
            "required": ["uri"],
        },
    },
    {
        "name": "signal_ingest",
        "description": "Ingest a signal for entity lifecycle tracking.",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_type": {"type": "string", "description": "Entity type (person, topic, etc.)"},
                "entity_name": {"type": "string", "description": "Entity name/identifier"},
                "source": {"type": "string", "description": "Signal source (screenshot, chat, etc.)"},
                "evidence": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Evidence tags",
                },
            },
            "required": ["entity_type", "entity_name", "source"],
        },
    },
    {
        "name": "signal_activate",
        "description": "Activate an entity and materialize it into the graph.",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_name": {"type": "string", "description": "Entity name to activate"},
            },
            "required": ["entity_name"],
        },
    },
    {
        "name": "screenshot_search",
        "description": "Search screenshots by OCR text.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Max results", "default": 20},
            },
            "required": ["query"],
        },
    },
]


class ToolRegistry:
    """Registers tools for OpenClaw and dispatches calls."""

    def __init__(
        self,
        graph_service: GraphService,
        signal_service: SignalService,
        screenshot_repo: ScreenshotRepo,
    ) -> None:
        self._graph = graph_service
        self._signal = signal_service
        self._ss_repo = screenshot_repo
        self._dispatchers = {
            "memory_write": self._memory_write,
            "memory_read": self._memory_read,
            "memory_search": self._memory_search,
            "memory_delete": self._memory_delete,
            "graph_query_subtree": self._graph_query_subtree,
            "signal_ingest": self._signal_ingest,
            "signal_activate": self._signal_activate,
            "screenshot_search": self._screenshot_search,
        }

    def list_tools(self) -> list[dict]:
        return list(_TOOL_DEFINITIONS)

    def call(self, tool_name: str, params: dict[str, Any]) -> Any:
        if tool_name not in self._dispatchers:
            raise ValueError(f"unknown tool: {tool_name}")
        return self._dispatchers[tool_name](params)

    # -- Tool implementations -------------------------------------------------

    def _memory_write(self, params: dict) -> dict:
        uri = params.get("uri")
        content = params.get("content")
        if not uri or content is None:
            raise ValueError("memory_write requires 'uri' and 'content'")
        result = self._graph.write(uri, content)
        return {"ok": True, "uri": str(NocturneUri.parse(uri)), "version": result["version"]}

    def _memory_read(self, params: dict) -> Optional[dict]:
        uri = params.get("uri")
        if not uri:
            raise ValueError("memory_read requires 'uri'")
        return self._graph.read(uri)

    def _memory_search(self, params: dict) -> list[dict]:
        query = params.get("query")
        if not query:
            raise ValueError("memory_search requires 'query'")
        limit = params.get("limit", 20)
        return self._graph._repo.search(query, limit)

    def _memory_delete(self, params: dict) -> dict:
        uri = params.get("uri")
        if not uri:
            raise ValueError("memory_delete requires 'uri'")
        parsed = NocturneUri.parse(uri)
        self._graph._repo.delete_node(parsed)
        return {"ok": True, "uri": uri}

    def _graph_query_subtree(self, params: dict) -> dict:
        uri = params.get("uri")
        if not uri:
            raise ValueError("graph_query_subtree requires 'uri'")
        max_depth = params.get("max_depth")
        parsed = NocturneUri.parse(uri)
        result = self._graph.get_subtree(parsed, max_depth=max_depth)
        return result or {}

    def _signal_ingest(self, params: dict) -> dict:
        entity_type = params.get("entity_type")
        entity_name = params.get("entity_name")
        source = params.get("source")
        if not entity_type or not entity_name or not source:
            raise ValueError("signal_ingest requires entity_type, entity_name, source")
        evidence = params.get("evidence", [])
        return self._signal.ingest_signal(entity_type, entity_name, source, evidence)

    def _signal_activate(self, params: dict) -> dict:
        entity_name = params.get("entity_name")
        if not entity_name:
            raise ValueError("signal_activate requires 'entity_name'")
        return self._signal.activate(entity_name)

    def _screenshot_search(self, params: dict) -> list[dict]:
        query = params.get("query")
        if not query:
            raise ValueError("screenshot_search requires 'query'")
        limit = params.get("limit", 20)
        return self._ss_repo.search(query, limit)
