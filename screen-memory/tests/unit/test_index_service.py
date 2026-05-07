"""Tests for the IndexService: capture → OCR → store → index pipeline.

TDD order: happy path → missing OCR → search after index → duplicate handling
"""

import pytest

from screen_memory.adapters.capture import CaptureResult, ScreenCapture
from screen_memory.adapters.ocr import OCRChain
from screen_memory.models.uri import NocturneUri
from screen_memory.storage.database import Database
from screen_memory.storage.graph_repo import GraphRepo
from screen_memory.storage.screenshot_repo import ScreenshotRepo
from screen_memory.services.index_service import IndexService


class _FakeCapture(ScreenCapture):
    _counter = 0

    def __init__(self, data: bytes = b""):
        self._data = data

    def capture(self) -> CaptureResult:
        _FakeCapture._counter += 1
        return CaptureResult(
            image_data=self._data,
            file_path=f"fake://capture_{_FakeCapture._counter}",
        )


class _FakeOCR:
    def __init__(self, text: str):
        self._text = text

    def recognize(self, image_data: bytes):
        from screen_memory.adapters.ocr import OCRResult
        return OCRResult(text=self._text, confidence=0.9, engine="FakeOCR")


@pytest.fixture
def svc():
    db = Database(":memory:")
    db.initialize()
    repo = GraphRepo(db)
    ss_repo = ScreenshotRepo(db)
    capture = _FakeCapture(b"png-bytes")
    ocr = OCRChain([_FakeOCR("recognized text")])
    return IndexService(repo, ss_repo, capture, ocr)


class TestCaptureAndIndex:
    def test_capture_and_store(self, svc):
        result = svc.capture_and_index()
        assert result["ocr_text"] == "recognized text"
        assert result["id"] == 1

    def test_capture_creates_screenshot(self, svc):
        svc.capture_and_index()
        screenshots = svc._ss_repo.list_all()
        assert len(screenshots) == 1

    def test_search_after_index(self, svc):
        svc.capture_and_index()
        results = svc.search_screenshots("recognized")
        assert len(results) == 1

    def test_search_graph(self, svc):
        svc.capture_and_index(link_uri="core://screen/test")
        results = svc.search_memories("recognized")
        assert len(results) >= 1


class TestCaptureWithLink:
    def test_link_to_uri(self, svc):
        result = svc.capture_and_index(link_uri="core://screen/test")
        assert result["uri"] == "core://screen/test"

    def test_link_creates_memory(self, svc):
        svc.capture_and_index(link_uri="core://screen/test")
        mem = svc._repo.read_memory(NocturneUri.parse("core://screen/test"))
        assert mem is not None
        assert "recognized" in mem["content"]


class TestNoOCR:
    def test_capture_with_empty_ocr(self):
        db = Database(":memory:")
        db.initialize()
        repo = GraphRepo(db)
        ss_repo = ScreenshotRepo(db)
        capture = _FakeCapture(b"img")
        ocr = OCRChain([])
        svc = IndexService(repo, ss_repo, capture, ocr)
        result = svc.capture_and_index()
        assert result["ocr_text"] is None
        assert result["id"] == 1


class TestMultipleCaptures:
    def test_multiple_captures(self, svc):
        svc.capture_and_index()
        svc.capture_and_index()
        assert len(svc._ss_repo.list_all()) == 2
