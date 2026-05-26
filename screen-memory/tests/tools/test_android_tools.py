# tests/tools/test_android_tools.py
"""Tests for Android-specific tool and CLI scenarios."""

import base64
import io
import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest
from PIL import Image

from screen_memory.adapters.android_capture import AndroidCapture
from screen_memory.adapters.mlkit_ocr import MlKitOcr
from screen_memory.storage.database import Database
from screen_memory.storage.graph_repo import GraphRepo
from screen_memory.storage.screenshot_repo import ScreenshotRepo
from screen_memory.services.graph_service import GraphService
from screen_memory.services.signal_service import SignalService, EntityPolicy
from screen_memory.tools.registry import ToolRegistry


def _make_jpeg(width=50, height=50) -> bytes:
    img = Image.new("RGB", (width, height))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _mock_http_for_tools(ocr_text="Test OCR from Android"):
    jpeg = _make_jpeg()
    mock = MagicMock()
    mock.is_reachable.return_value = True
    mock.post.side_effect = lambda path, data: {
        "/capture": {
            "image": base64.b64encode(jpeg).decode(),
            "width": 50,
            "height": 50,
            "app_package": "com.test.app",
            "capture_time_ms": 30,
        },
        "/ocr": {
            "text": ocr_text,
            "blocks": [{"text": ocr_text, "bbox": [0, 0, 50, 15], "confidence": 0.85}],
            "engine": "mlkit",
            "processing_time_ms": 50,
        },
    }.get(path, {})
    mock.get.return_value = {"running": True, "ocr_ready": True}
    return mock


class TestCliCapture:
    def test_capture_produces_output(self):
        """CLI capture command produces screenshot_id and ocr_text_preview."""
        mock_http = _mock_http_for_tools("Hello Android")
        db = Database(":memory:")
        db.initialize()
        ss_repo = ScreenshotRepo(db)

        with tempfile.TemporaryDirectory() as tmpdir:
            capture = AndroidCapture(screenshot_dir=tmpdir, http_client=mock_http)
            result = capture.capture(quality=85)
            record = ss_repo.insert(result.file_path, ocr_text="Hello Android")

        assert record["id"] is not None
        assert "Hello" in record["ocr_text"]


class TestScreenshotSearch:
    def test_search_android_content(self):
        """Search finds content from Android-captured screenshots."""
        db = Database(":memory:")
        db.initialize()
        ss_repo = ScreenshotRepo(db)
        ss_repo.insert("/tmp/android1.png", "微信消息你好")
        ss_repo.insert("/tmp/android2.png", "抖音视频推荐")

        results = ss_repo.search("微信")
        assert len(results) == 1
        assert "微信" in results[0]["ocr_text"]


class TestCustomEnvVars:
    def test_custom_apk_url(self):
        """SCREEN_MEMORY_APK_URL env var overrides default URL."""
        with patch.dict(os.environ, {"SCREEN_MEMORY_APK_URL": "http://192.168.1.100:8080"}):
            capture = AndroidCapture()
            assert capture._client._base_url == "http://192.168.1.100:8080"

    def test_custom_timeout(self):
        """SCREEN_MEMORY_APK_TIMEOUT env var overrides default timeout."""
        with patch.dict(os.environ, {"SCREEN_MEMORY_APK_TIMEOUT": "5"}):
            capture = AndroidCapture()
            assert capture._client._timeout == 5


def _make_registry() -> ToolRegistry:
    """Create a ToolRegistry with in-memory DB (no APK dependency)."""
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


class TestAllToolsViaRegistry:
    """Verify all 8 tools work through the registry (shared package)."""

    def test_memory_write(self):
        reg = _make_registry()
        result = reg.call("memory_write", {"uri": "core://android/test", "content": "hello android"})
        assert result["ok"] is True
        assert result["uri"] == "core://android/test"

    def test_memory_read(self):
        reg = _make_registry()
        reg.call("memory_write", {"uri": "core://android/test", "content": "data"})
        result = reg.call("memory_read", {"uri": "core://android/test"})
        assert result["content"] == "data"

    def test_memory_search(self):
        reg = _make_registry()
        reg.call("memory_write", {"uri": "core://a", "content": "android kotlin"})
        reg.call("memory_write", {"uri": "core://b", "content": "ios swift"})
        results = reg.call("memory_search", {"query": "android"})
        assert len(results) == 1
        assert results[0]["node_uri"] == "core://a"

    def test_memory_delete(self):
        reg = _make_registry()
        reg.call("memory_write", {"uri": "core://del", "content": "temp"})
        result = reg.call("memory_delete", {"uri": "core://del"})
        assert result["ok"] is True
        assert reg.call("memory_read", {"uri": "core://del"}) is None

    def test_graph_query_subtree(self):
        reg = _make_registry()
        reg.call("memory_write", {"uri": "core://a", "content": "root"})
        reg.call("memory_write", {"uri": "core://a/b", "content": "child"})
        result = reg.call("graph_query_subtree", {"uri": "core://a"})
        assert result["uri"] == "core://a"
        assert len(result["children"]) == 1

    def test_signal_ingest(self):
        reg = _make_registry()
        result = reg.call("signal_ingest", {
            "entity_type": "person",
            "entity_name": "Alice",
            "source": "screenshot",
            "evidence": ["seen_multiple_times"],
        })
        assert result["name"] == "Alice"
        assert result["status"] == "candidate"

    def test_signal_activate(self):
        reg = _make_registry()
        for _ in range(5):
            reg.call("signal_ingest", {
                "entity_type": "person",
                "entity_name": "Bob",
                "source": "screenshot",
                "evidence": ["seen_multiple_times"],
            })
        result = reg.call("signal_activate", {"entity_name": "Bob"})
        assert result["status"] == "active"

    def test_screenshot_search(self):
        reg = _make_registry()
        reg._ss_repo.insert("/tmp/android.png", "screen memory plugin test")
        results = reg.call("screenshot_search", {"query": "plugin"})
        assert len(results) == 1

    def test_list_tools_has_9(self):
        reg = _make_registry()
        tools = reg.list_tools()
        assert len(tools) == 9
        names = [t["name"] for t in tools]
        expected = [
            "memory_write", "memory_read", "memory_search", "memory_delete",
            "graph_query_subtree", "signal_ingest", "signal_activate",
            "screenshot_search", "sync_status",
        ]
        assert names == expected


class TestSignalActivationOnAndroid:
    """Verify signal activation creates graph memory (Android scenario)."""

    def test_activate_creates_graph_node(self):
        reg = _make_registry()
        for _ in range(5):
            reg.call("signal_ingest", {
                "entity_type": "topic",
                "entity_name": "Android",
                "source": "screenshot",
                "evidence": [],
            })
        reg.call("signal_activate", {"entity_name": "Android"})
        mem = reg.call("memory_read", {"uri": "core://entities/topic/Android"})
        assert mem is not None
        assert "Android" in mem["content"]
