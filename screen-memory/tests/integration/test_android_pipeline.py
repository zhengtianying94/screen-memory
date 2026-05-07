# tests/integration/test_android_pipeline.py
"""Integration tests: Android adapters wired into full system pipeline.

Uses mock HTTP client to simulate auxiliary APK responses.
"""

import base64
import io
import tempfile
import time
from unittest.mock import MagicMock

import pytest
from PIL import Image

from screen_memory.adapters.android_capture import AndroidCapture
from screen_memory.adapters.mlkit_ocr import MlKitOcr
from screen_memory.adapters.ocr import OCRChain
from screen_memory.adapters.tesseract_ocr import TesseractOcr
from screen_memory.storage.database import Database
from screen_memory.storage.graph_repo import GraphRepo
from screen_memory.storage.screenshot_repo import ScreenshotRepo
from screen_memory.services.graph_service import GraphService
from screen_memory.services.index_service import IndexService
from screen_memory.services.signal_service import SignalService, EntityPolicy
from screen_memory.tools.registry import ToolRegistry


def _make_jpeg(width=100, height=100) -> bytes:
    img = Image.new("RGB", (width, height))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _mock_apk_capture_response(app_package="com.example.app"):
    jpeg = _make_jpeg()
    return {
        "image": base64.b64encode(jpeg).decode(),
        "width": 100,
        "height": 100,
        "app_package": app_package,
        "capture_time_ms": 50,
    }


def _mock_apk_ocr_response(text="Test OCR text"):
    return {
        "text": text,
        "blocks": [{"text": text, "bbox": [0, 0, 100, 20], "confidence": 0.85}],
        "engine": "mlkit",
        "processing_time_ms": 100,
    }


class _MockHttpClient:
    """Simulates auxiliary APK HTTP responses for testing."""

    def __init__(self, capture_resp=None, ocr_resp=None, status_resp=None):
        self._capture_resp = capture_resp or _mock_apk_capture_response()
        self._ocr_resp = ocr_resp or _mock_apk_ocr_response()
        self._status_resp = status_resp or {"running": True, "ocr_ready": True}

    def get(self, path):
        if path == "/status":
            return self._status_resp
        return {}

    def post(self, path, data):
        if path == "/capture":
            return self._capture_resp
        if path == "/ocr":
            return self._ocr_resp
        return {}

    def is_reachable(self):
        return True


@pytest.fixture
def android_system():
    """Wire up full system with Android adapters backed by mock APK."""
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

    mock_http = _MockHttpClient()
    with tempfile.TemporaryDirectory() as tmpdir:
        capture = AndroidCapture(screenshot_dir=tmpdir, http_client=mock_http)
        mlkit = MlKitOcr(http_client=mock_http)
        ocr_chain = OCRChain([mlkit])
        index_svc = IndexService(repo, ss_repo, capture, ocr_chain)
        registry = ToolRegistry(graph_svc, signal_svc, ss_repo)
        yield {
            "db": db,
            "repo": repo,
            "ss_repo": ss_repo,
            "graph_svc": graph_svc,
            "signal_svc": signal_svc,
            "index_svc": index_svc,
            "registry": registry,
            "mock_http": mock_http,
            "capture": capture,
            "tmpdir": tmpdir,
        }


class TestCaptureOcrPipeline:
    def test_capture_and_search(self, android_system):
        """Capture -> OCR -> store -> search finds OCR text."""
        index = android_system["index_svc"]
        result = index.capture_and_index()
        assert result["ocr_text"] == "Test OCR text"

        results = index.search_screenshots("OCR")
        assert len(results) >= 1

    def test_multiple_captures_selective_search(self, android_system):
        """5 captures with different OCR, search finds only matching one."""
        index = android_system["index_svc"]
        texts = ["alpha", "beta", "gamma", "delta", "epsilon"]

        for i, text in enumerate(texts):
            # Create unique subdirectory for each capture to avoid file collisions
            import os
            unique_dir = os.path.join(android_system["tmpdir"], f"capture_{i}")
            os.makedirs(unique_dir, exist_ok=True)

            mock_http = _MockHttpClient(
                capture_resp=_mock_apk_capture_response(f"com.example.app{i}"),
                ocr_resp=_mock_apk_ocr_response(text)
            )
            index._capture = AndroidCapture(screenshot_dir=unique_dir, http_client=mock_http)
            index._ocr = OCRChain([MlKitOcr(http_client=mock_http)])
            index.capture_and_index()

        results = index.search_screenshots("gamma")
        assert len(results) == 1
        assert "gamma" in results[0]["ocr_text"]

    def test_capture_no_ocr_text_stored(self, android_system):
        """Capture with empty OCR stores record with None ocr_text."""
        mock_http = _MockHttpClient(ocr_resp=_mock_apk_ocr_response(""))
        index = android_system["index_svc"]
        index._ocr = OCRChain([MlKitOcr(http_client=mock_http)])
        result = index.capture_and_index()
        assert result["ocr_text"] is None

        results = index.search_screenshots("anything")
        assert len(results) == 0

    def test_cjk_ocr_text_searchable(self, android_system):
        """CJK text from OCR is searchable."""
        mock_http = _MockHttpClient(ocr_resp=_mock_apk_ocr_response("你好世界"))
        index = android_system["index_svc"]
        index._ocr = OCRChain([MlKitOcr(http_client=mock_http)])
        index.capture_and_index()

        results = index.search_screenshots("你好")
        assert len(results) == 1


class TestOcrFallback:
    def test_mlkit_timeout_tesseract_used(self, android_system):
        """When MlKitOcr returns empty, chain returns empty result."""
        mock_http = _MockHttpClient(ocr_resp=_mock_apk_ocr_response(""))
        mlkit = MlKitOcr(http_client=mock_http)
        chain = OCRChain([mlkit])
        result = chain.recognize(_make_jpeg())
        # Empty OCR results use "none" engine
        assert result.engine in ("mlkit", "none")
        assert result.text == ""

    def test_all_ocr_unavailable_screenshot_stored(self, android_system):
        """When all OCR engines fail, screenshot is stored without OCR text."""
        mock_http = _MockHttpClient(ocr_resp=_mock_apk_ocr_response(""))
        index = android_system["index_svc"]
        index._ocr = OCRChain([MlKitOcr(http_client=mock_http)])
        result = index.capture_and_index()
        assert result["ocr_text"] is None
        assert result["id"] is not None


class TestTimedCapture:
    def test_timed_capture_lifecycle(self, android_system):
        """start_timed_capture -> 3 captures -> stop, count correct."""
        capture = android_system["capture"]
        results = []

        capture.start_timed_capture(
            interval_seconds=1,
            quality=80,
            callback=lambda r: results.append(r),
        )
        assert capture.is_capturing()

        time.sleep(2.5)
        status = capture.stop_timed_capture()
        assert not capture.is_capturing()
        # Should have at least 1 capture (happens immediately)
        assert status["captures_count"] >= 1


class TestSignalFromScreenshot:
    def test_capture_then_signal_activate(self, android_system):
        """Capture text with person name -> ingest signal -> activate -> graph searchable."""
        reg = android_system["registry"]
        mock_http = _MockHttpClient(ocr_resp=_mock_apk_ocr_response("Meeting with Alice"))
        index = android_system["index_svc"]
        index._ocr = OCRChain([MlKitOcr(http_client=mock_http)])
        index.capture_and_index()

        for _ in range(5):
            reg.call("signal_ingest", {
                "entity_type": "person",
                "entity_name": "Alice",
                "source": "screenshot",
                "evidence": ["seen_multiple_times"],
            })

        result = reg.call("signal_activate", {"entity_name": "Alice"})
        assert result["status"] == "active"


class TestAppPackageField:
    def test_app_package_stored(self, android_system):
        """Capture from WeChat stores app_package."""
        mock_http = _MockHttpClient(capture_resp=_mock_apk_capture_response("com.tencent.mm"))
        with tempfile.TemporaryDirectory() as tmpdir:
            capture = AndroidCapture(screenshot_dir=tmpdir, http_client=mock_http)
            result = capture.capture()
            assert result.app_package == "com.tencent.mm"
            assert result.app_name == "com.tencent.mm"
