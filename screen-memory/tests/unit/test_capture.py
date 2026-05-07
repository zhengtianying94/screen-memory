"""Tests for platform capture/OCR adapters.

TDD order: abstract interface → platform stubs → OCR fallback chain
"""

import pytest

from screen_memory.adapters.capture import (
    CaptureResult,
    ScreenCapture,
)
from screen_memory.adapters.ocr import OCRResult, OCRChain


# -- CaptureResult model -----------------------------------------------------


class TestCaptureResult:
    def test_basic_fields(self):
        r = CaptureResult(image_data=b"\x89PNG", file_path="/tmp/a.png")
        assert r.image_data == b"\x89PNG"
        assert r.file_path == "/tmp/a.png"

    def test_optional_metadata(self):
        r = CaptureResult(image_data=b"", file_path="", width=1920, height=1080)
        assert r.width == 1920
        assert r.height == 1080


# -- Mock capture adapter ----------------------------------------------------


class FakeCapture(ScreenCapture):
    """In-memory capture adapter for testing."""

    def __init__(self, data: bytes = b"fake-png"):
        self._data = data
        self.called = False

    def capture(self) -> CaptureResult:
        self.called = True
        return CaptureResult(image_data=self._data, file_path="fake://memory")

    def capture_region(self, x: int, y: int, w: int, h: int) -> CaptureResult:
        return CaptureResult(image_data=self._data, file_path="fake://region")


class TestFakeCapture:
    def test_capture(self):
        cap = FakeCapture()
        result = cap.capture()
        assert result.image_data == b"fake-png"
        assert cap.called

    def test_capture_region(self):
        cap = FakeCapture()
        result = cap.capture_region(0, 0, 100, 100)
        assert result.image_data == b"fake-png"


# -- OCR fallback chain ------------------------------------------------------


class FakeOCR:
    """Predictable OCR for testing."""

    def __init__(self, text: str | None = "hello"):
        self._text = text
        self.attempted = False

    def recognize(self, image_data: bytes) -> OCRResult:
        self.attempted = True
        if self._text is None:
            return OCRResult(text="", confidence=0.0, engine=self.__class__.__name__)
        return OCRResult(text=self._text, confidence=0.9, engine=self.__class__.__name__)


class FailOCR:
    """Always fails."""

    def recognize(self, image_data: bytes) -> OCRResult:
        return OCRResult(text="", confidence=0.0, engine="FailOCR")


class TestOCRChain:
    def test_first_engine_succeeds(self):
        chain = OCRChain([FakeOCR("primary")])
        result = chain.recognize(b"img")
        assert result.text == "primary"
        assert result.engine == "FakeOCR"

    def test_fallback_to_second(self):
        chain = OCRChain([FailOCR(), FakeOCR("fallback")])
        result = chain.recognize(b"img")
        assert result.text == "fallback"

    def test_all_fail_returns_empty(self):
        chain = OCRChain([FailOCR()])
        result = chain.recognize(b"img")
        assert result.text == ""
        assert result.confidence == 0.0

    def test_empty_chain(self):
        chain = OCRChain([])
        result = chain.recognize(b"img")
        assert result.text == ""

    def test_confidence_threshold(self):
        chain = OCRChain(
            [FakeOCR("low"), FakeOCR("high")],
            min_confidence=0.95,
        )
        # First returns 0.9 which is below threshold, second also 0.9
        result = chain.recognize(b"img")
        assert result.text == "high"  # takes last one that ran

    def test_chain_tries_all_on_low_confidence(self):
        ocr1 = FakeOCR("first")
        ocr2 = FakeOCR("second")
        chain = OCRChain([ocr1, ocr2], min_confidence=0.95)
        chain.recognize(b"img")
        assert ocr1.attempted
        assert ocr2.attempted
