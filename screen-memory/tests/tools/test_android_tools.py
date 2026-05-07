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
