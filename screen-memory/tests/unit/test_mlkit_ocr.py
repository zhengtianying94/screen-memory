# tests/unit/test_mlkit_ocr.py
"""Tests for MlKitOcr: OCR via auxiliary APK ML Kit HTTP API."""

import base64
from unittest.mock import MagicMock

import pytest

from screen_memory.adapters.ocr import OCRResult
from screen_memory.adapters.mlkit_ocr import MlKitOcr


def _mock_ocr_response(text="Hello world", blocks=None, processing_time_ms=100) -> dict:
    if blocks is None:
        blocks = [
            {"text": "Hello", "bbox": [10, 20, 100, 30], "confidence": 0.85},
            {"text": "world", "bbox": [120, 20, 80, 30], "confidence": 0.85},
        ]
    return {
        "text": text,
        "blocks": blocks,
        "engine": "mlkit",
        "processing_time_ms": processing_time_ms,
    }


class TestRecognizeSuccess:
    def test_returns_ocr_result_with_text(self):
        mock_client = MagicMock()
        mock_client.post.return_value = _mock_ocr_response("Hello world")

        ocr = MlKitOcr(http_client=mock_client)
        result = ocr.recognize(b"fake-image-data")

        assert isinstance(result, OCRResult)
        assert result.text == "Hello world"
        assert result.engine == "mlkit"
        assert result.source == "system"

    def test_blocks_converted_to_tuple_format(self):
        mock_client = MagicMock()
        mock_client.post.return_value = _mock_ocr_response(blocks=[
            {"text": "Hi", "bbox": [5, 10, 50, 20], "confidence": 0.9},
        ])

        ocr = MlKitOcr(http_client=mock_client)
        result = ocr.recognize(b"img")

        assert len(result.blocks) == 1
        text, bbox, conf = result.blocks[0]
        assert text == "Hi"
        assert bbox == (5, 10, 50, 20)
        assert conf == 0.9

    def test_sends_base64_encoded_image(self):
        mock_client = MagicMock()
        mock_client.post.return_value = _mock_ocr_response("ok")

        ocr = MlKitOcr(http_client=mock_client)
        ocr.recognize(b"\x89PNG\r\n")

        call_args = mock_client.post.call_args
        sent_data = call_args[0][1]
        assert "image" in sent_data
        decoded = base64.b64decode(sent_data["image"])
        assert decoded == b"\x89PNG\r\n"


class TestRecognizeEmpty:
    def test_empty_image_returns_empty_result(self):
        mock_client = MagicMock()
        mock_client.post.return_value = _mock_ocr_response(text="", blocks=[])

        ocr = MlKitOcr(http_client=mock_client)
        result = ocr.recognize(b"blank")

        assert result.text == ""
        assert result.confidence == 0.0


class TestRecognizeFailure:
    def test_apk_unavailable_returns_empty_result(self):
        mock_client = MagicMock()
        mock_client.post.side_effect = ConnectionError("refused")

        ocr = MlKitOcr(http_client=mock_client)
        result = ocr.recognize(b"img")

        assert result.text == ""
        assert result.confidence == 0.0
        assert result.engine == "mlkit"

    def test_timeout_returns_empty_result(self):
        mock_client = MagicMock()
        mock_client.post.side_effect = ConnectionError("timed out")

        ocr = MlKitOcr(http_client=mock_client)
        result = ocr.recognize(b"img")

        assert result.text == ""
        assert result.confidence == 0.0


class TestIsAvailable:
    def test_available_when_ocr_ready(self):
        mock_client = MagicMock()
        mock_client.get.return_value = {"running": True, "ocr_ready": True}

        ocr = MlKitOcr(http_client=mock_client)
        assert ocr.is_available() is True

    def test_not_available_when_ocr_not_ready(self):
        mock_client = MagicMock()
        mock_client.get.return_value = {"running": True, "ocr_ready": False}

        ocr = MlKitOcr(http_client=mock_client)
        assert ocr.is_available() is False
