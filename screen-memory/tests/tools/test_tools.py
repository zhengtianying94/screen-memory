"""Tests for OpenClaw tool interfaces.

TDD order: tool registration → individual tool calls → error handling
"""

import pytest

from screen_memory.models.uri import NocturneUri
from screen_memory.storage.database import Database
from screen_memory.storage.graph_repo import GraphRepo
from screen_memory.storage.screenshot_repo import ScreenshotRepo
from screen_memory.services.graph_service import GraphService
from screen_memory.services.signal_service import SignalService, EntityPolicy, EntityType
from screen_memory.tools.registry import ToolRegistry


@pytest.fixture
def registry():
    db = Database(":memory:")
    db.initialize()
    repo = GraphRepo(db)
    ss_repo = ScreenshotRepo(db)
    graph_svc = GraphService(repo)
    policies = {
        "person": EntityPolicy("person", 3.0, 86400 * 7, ["seen_multiple_times"]),
        "topic": EntityPolicy("topic", 2.0, 86400 * 3, []),
    }
    signal_svc = SignalService(repo, policies)
    return ToolRegistry(graph_svc, signal_svc, ss_repo)


# -- Registration ------------------------------------------------------------


class TestToolRegistration:
    def test_list_tools(self, registry):
        tools = registry.list_tools()
        names = [t["name"] for t in tools]
        assert "memory_write" in names
        assert "memory_read" in names
        assert "memory_search" in names
        assert "memory_delete" in names
        assert "graph_query_subtree" in names
        assert "signal_ingest" in names
        assert "signal_activate" in names
        assert "screenshot_search" in names

    def test_tool_has_schema(self, registry):
        tools = registry.list_tools()
        for t in tools:
            assert "name" in t
            assert "description" in t
            assert "parameters" in t


# -- memory_write tool -------------------------------------------------------


class TestMemoryWriteTool:
    def test_write_memory(self, registry):
        result = registry.call("memory_write", {
            "uri": "core://test/hello",
            "content": "Hello world",
        })
        assert result["ok"] is True
        assert result["uri"] == "core://test/hello"

    def test_write_validates_params(self, registry):
        with pytest.raises(ValueError):
            registry.call("memory_write", {"uri": "core://a"})  # missing content


# -- memory_read tool --------------------------------------------------------


class TestMemoryReadTool:
    def test_read_existing(self, registry):
        registry.call("memory_write", {"uri": "core://a", "content": "data"})
        result = registry.call("memory_read", {"uri": "core://a"})
        assert result["content"] == "data"

    def test_read_missing(self, registry):
        result = registry.call("memory_read", {"uri": "core://ghost"})
        assert result is None


# -- memory_search tool ------------------------------------------------------


class TestMemorySearchTool:
    def test_search(self, registry):
        registry.call("memory_write", {"uri": "core://a", "content": "quick brown fox"})
        registry.call("memory_write", {"uri": "core://b", "content": "lazy dog"})
        result = registry.call("memory_search", {"query": "brown"})
        assert len(result) == 1
        assert result[0]["node_uri"] == "core://a"


# -- memory_delete tool ------------------------------------------------------


class TestMemoryDeleteTool:
    def test_delete(self, registry):
        registry.call("memory_write", {"uri": "core://a", "content": "temp"})
        result = registry.call("memory_delete", {"uri": "core://a"})
        assert result["ok"] is True
        assert registry.call("memory_read", {"uri": "core://a"}) is None


# -- graph_query_subtree tool ------------------------------------------------


class TestGraphQuerySubtreeTool:
    def test_query_subtree(self, registry):
        registry.call("memory_write", {"uri": "core://a", "content": "root"})
        registry.call("memory_write", {"uri": "core://a/b", "content": "child"})
        result = registry.call("graph_query_subtree", {"uri": "core://a"})
        assert result["uri"] == "core://a"
        assert len(result["children"]) == 1

    def test_query_with_depth(self, registry):
        registry.call("memory_write", {"uri": "core://a", "content": "r"})
        registry.call("memory_write", {"uri": "core://a/b", "content": "c"})
        registry.call("memory_write", {"uri": "core://a/b/d", "content": "gc"})
        result = registry.call("graph_query_subtree", {
            "uri": "core://a", "max_depth": 1
        })
        assert len(result["children"]) == 1
        assert result["children"][0]["children"] == []


# -- signal_ingest tool ------------------------------------------------------


class TestSignalIngestTool:
    def test_ingest(self, registry):
        result = registry.call("signal_ingest", {
            "entity_type": "person",
            "entity_name": "Alice",
            "source": "screenshot",
            "evidence": ["seen_multiple_times"],
        })
        assert result["name"] == "Alice"
        assert result["status"] == "candidate"


# -- signal_activate tool ----------------------------------------------------


class TestSignalActivateTool:
    def test_activate(self, registry):
        for _ in range(5):
            registry.call("signal_ingest", {
                "entity_type": "person",
                "entity_name": "Bob",
                "source": "screenshot",
                "evidence": ["seen_multiple_times"],
            })
        result = registry.call("signal_activate", {"entity_name": "Bob"})
        assert result["status"] == "active"


# -- screenshot_search tool --------------------------------------------------


class TestScreenshotSearchTool:
    def test_search(self, registry):
        registry._ss_repo.insert("/tmp/a.png", "hello world")
        result = registry.call("screenshot_search", {"query": "hello"})
        assert len(result) == 1


# -- Error handling ----------------------------------------------------------


class TestToolErrors:
    def test_unknown_tool(self, registry):
        with pytest.raises(ValueError, match="unknown tool"):
            registry.call("nonexistent_tool", {})

    def test_invalid_uri(self, registry):
        with pytest.raises(ValueError):
            registry.call("memory_write", {"uri": "not_a_uri", "content": "x"})
