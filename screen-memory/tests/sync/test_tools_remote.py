import pytest
from unittest.mock import MagicMock, patch

from screen_memory.storage.database import Database
from screen_memory.storage.graph_repo import GraphRepo
from screen_memory.storage.screenshot_repo import ScreenshotRepo
from screen_memory.services.graph_service import GraphService
from screen_memory.services.signal_service import SignalService, EntityPolicy
from screen_memory.tools.registry import ToolRegistry


@pytest.fixture
def registry():
    db = Database(":memory:")
    db.initialize()
    repo = GraphRepo(db)
    ss_repo = ScreenshotRepo(db)
    graph_svc = GraphService(repo)
    policies = {"person": EntityPolicy("person", 3.0, 86400 * 7, [])}
    signal_svc = SignalService(repo, policies)
    return ToolRegistry(graph_svc, signal_svc, ss_repo)


class TestMemorySearchScope:
    def test_scope_local_default(self, registry):
        registry.call("memory_write", {"uri": "core://a", "content": "hello world"})
        result = registry.call("memory_search", {"query": "hello"})
        assert len(result) == 1

    def test_scope_local_explicit(self, registry):
        registry.call("memory_write", {"uri": "core://a", "content": "hello world"})
        result = registry.call("memory_search", {"query": "hello", "scope": "local"})
        assert len(result) == 1

    def test_scope_remote_with_bridge(self, registry):
        mock_bridge = MagicMock()
        mock_bridge.query.return_value = [{"node_uri": "core://x", "content": "remote data", "version": 1}]
        registry.set_query_bridge(mock_bridge)
        result = registry.call("memory_search", {"query": "remote", "scope": "remote"})
        assert len(result) == 1
        assert result[0]["content"] == "remote data"
        mock_bridge.query.assert_called_once()

    def test_scope_remote_without_bridge(self, registry):
        result = registry.call("memory_search", {"query": "test", "scope": "remote"})
        assert result == []

    def test_scope_all_merges(self, registry):
        registry.call("memory_write", {"uri": "core://a", "content": "local data"})
        mock_bridge = MagicMock()
        mock_bridge.query.return_value = [{"node_uri": "core://b", "content": "remote data", "version": 1}]
        registry.set_query_bridge(mock_bridge)
        result = registry.call("memory_search", {"query": "data", "scope": "all"})
        assert len(result) == 2


class TestScreenshotSearchScope:
    def test_scope_local_default(self, registry):
        registry._ss_repo.insert("/a.png", "screen text")
        result = registry.call("screenshot_search", {"query": "screen"})
        assert len(result) == 1

    def test_scope_remote_with_bridge(self, registry):
        mock_bridge = MagicMock()
        mock_bridge.query.return_value = [{"file_path": "/remote.png", "ocr_text": "remote screen"}]
        registry.set_query_bridge(mock_bridge)
        result = registry.call("screenshot_search", {"query": "remote", "scope": "remote"})
        assert len(result) == 1
        mock_bridge.query.assert_called_once()


class TestSyncStatusTool:
    def test_sync_status_listed(self, registry):
        tools = registry.list_tools()
        names = [t["name"] for t in tools]
        assert "sync_status" in names

    def test_sync_status_without_sync(self, registry):
        result = registry.call("sync_status", {})
        assert result["server_reachable"] is False

    def test_sync_status_with_sync(self, registry):
        mock_bridge = MagicMock()
        mock_bridge.list_devices.return_value = [
            {"device_id": "device-1", "last_sync": "2026-05-26 10:00:00", "tables": {"screenshots": 5}},
        ]
        mock_client = MagicMock()
        mock_client.get_device_id.return_value = "device-1"
        mock_client._get_last_sync_time.return_value = "2026-05-26 10:00:00"
        mock_client.detect_changes.return_value = {}
        registry.set_query_bridge(mock_bridge)
        registry.set_sync_client(mock_client)
        result = registry.call("sync_status", {})
        assert result["device_id"] == "device-1"
        assert result["server_reachable"] is True
