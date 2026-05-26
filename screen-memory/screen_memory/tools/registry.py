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
                "scope": {"type": "string", "description": "Query scope: local (default), remote, all", "default": "local"},
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
                "scope": {"type": "string", "description": "Query scope: local (default), remote, all", "default": "local"},
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
                "scope": {"type": "string", "description": "Query scope: local (default), remote, all", "default": "local"},
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
                "scope": {"type": "string", "description": "Query scope: local (default), remote, all", "default": "local"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "sync_status",
        "description": "Check sync status and list connected devices.",
        "parameters": {
            "type": "object",
            "properties": {},
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
        self._query_bridge = None
        self._sync_client = None
        self._dispatchers = {
            "memory_write": self._memory_write,
            "memory_read": self._memory_read,
            "memory_search": self._memory_search,
            "memory_delete": self._memory_delete,
            "graph_query_subtree": self._graph_query_subtree,
            "signal_ingest": self._signal_ingest,
            "signal_activate": self._signal_activate,
            "screenshot_search": self._screenshot_search,
            "sync_status": self._sync_status,
        }

    def list_tools(self) -> list[dict]:
        return list(_TOOL_DEFINITIONS)

    def call(self, tool_name: str, params: dict[str, Any]) -> Any:
        if tool_name not in self._dispatchers:
            raise ValueError(f"unknown tool: {tool_name}")
        return self._dispatchers[tool_name](params)

    def set_query_bridge(self, bridge) -> None:
        self._query_bridge = bridge

    def set_sync_client(self, client) -> None:
        self._sync_client = client

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
        scope = params.get("scope", "local")
        if scope == "remote":
            if self._query_bridge is None:
                return None
            results = self._query_bridge.query("memories", {"node_uri": uri})
            return results[0] if results else None
        if scope == "all":
            local = self._graph.read(uri)
            if local:
                return local
            if self._query_bridge is None:
                return None
            results = self._query_bridge.query("memories", {"node_uri": uri})
            return results[0] if results else None
        return self._graph.read(uri)

    def _memory_search(self, params: dict) -> list[dict]:
        query = params.get("query")
        if not query:
            raise ValueError("memory_search requires 'query'")
        limit = params.get("limit", 20)
        scope = params.get("scope", "local")
        if scope == "remote":
            if self._query_bridge is None:
                return []
            return self._query_bridge.query("memories_fts", {"query": query})
        if scope == "all":
            local = self._graph._repo.search(query, limit)
            if self._query_bridge is None:
                return local
            remote = self._query_bridge.query("memories_fts", {"query": query})
            seen = {r["node_uri"] for r in local}
            for r in remote:
                if r.get("node_uri") not in seen:
                    local.append(r)
                    seen.add(r["node_uri"])
            return local[:limit]
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
        scope = params.get("scope", "local")
        if scope != "local":
            if self._query_bridge is None:
                return {}
            results = self._query_bridge.query("nodes", {"uri": uri})
            return results[0] if results else {}
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
        scope = params.get("scope", "local")
        if scope == "remote":
            if self._query_bridge is None:
                return []
            return self._query_bridge.query("screenshots", {"ocr_text LIKE": f"%{query}%"})
        if scope == "all":
            local = self._ss_repo.search(query, limit)
            if self._query_bridge is None:
                return local
            remote = self._query_bridge.query("screenshots", {"ocr_text LIKE": f"%{query}%"})
            seen = {r.get("file_path") for r in local}
            for r in remote:
                if r.get("file_path") not in seen:
                    local.append(r)
                    seen.add(r.get("file_path"))
            return local[:limit]
        return self._ss_repo.search(query, limit)

    def _sync_status(self, params: dict) -> dict:
        result = {
            "device_id": None,
            "last_sync_time": None,
            "pending_changes": 0,
            "server_reachable": False,
            "devices": [],
        }
        if self._sync_client:
            result["device_id"] = self._sync_client.get_device_id()
            result["last_sync_time"] = self._sync_client._get_last_sync_time()
            changes = self._sync_client.detect_changes()
            result["pending_changes"] = sum(len(v) for v in changes.values())
        if self._query_bridge:
            devices = self._query_bridge.list_devices()
            result["server_reachable"] = True
            result["devices"] = devices
        return result
