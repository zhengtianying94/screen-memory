# tests/unit/test_android_capture.py
"""Tests for AndroidCapture: screenshot via auxiliary APK HTTP API."""

import base64
import io
import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest
from PIL import Image

from screen_memory.adapters.capture import CaptureResult
from screen_memory.adapters.android_capture import AndroidCapture


def _make_jpeg_bytes(width=100, height=100) -> bytes:
    img = Image.new("RGB", (width, height), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _mock_capture_response(
    width=100, height=100, app_package="com.example.app", capture_time_ms=85
) -> dict:
    jpeg = _make_jpeg_bytes(width, height)
    return {
        "image": base64.b64encode(jpeg).decode(),
        "width": width,
        "height": height,
        "app_package": app_package,
        "capture_time_ms": capture_time_ms,
    }


class TestCaptureSuccess:
    def test_capture_returns_capture_result(self):
        resp = _mock_capture_response(width=200, height=400, app_package="com.tencent.mm")
        mock_client = MagicMock()
        mock_client.post.return_value = resp

        with tempfile.TemporaryDirectory() as tmpdir:
            capture = AndroidCapture(screenshot_dir=tmpdir, http_client=mock_client)
            result = capture.capture(quality=80)

        assert isinstance(result, CaptureResult)
        assert result.width == 200
        assert result.height == 400
        assert result.app_package == "com.tencent.mm"
        assert len(result.image_data) > 0

    def test_capture_saves_file_to_disk(self):
        resp = _mock_capture_response()
        mock_client = MagicMock()
        mock_client.post.return_value = resp

        with tempfile.TemporaryDirectory() as tmpdir:
            capture = AndroidCapture(screenshot_dir=tmpdir, http_client=mock_client)
            result = capture.capture(quality=80)
            assert os.path.isfile(result.file_path)
            assert result.file_path.startswith(tmpdir)

    def test_capture_app_package_none_when_missing(self):
        resp = _mock_capture_response()
        del resp["app_package"]
        mock_client = MagicMock()
        mock_client.post.return_value = resp

        with tempfile.TemporaryDirectory() as tmpdir:
            capture = AndroidCapture(screenshot_dir=tmpdir, http_client=mock_client)
            result = capture.capture()
            assert result.app_package is None


class TestCaptureUnavailable:
    def test_capture_raises_on_connection_error(self):
        mock_client = MagicMock()
        mock_client.post.side_effect = ConnectionError("Connection refused")

        with tempfile.TemporaryDirectory() as tmpdir:
            capture = AndroidCapture(screenshot_dir=tmpdir, http_client=mock_client)
            with pytest.raises(ConnectionError, match="Connection refused"):
                capture.capture()


class TestIsAvailable:
    def test_available_when_apk_running(self):
        mock_client = MagicMock()
        mock_client.is_reachable.return_value = True
        capture = AndroidCapture(http_client=mock_client)
        assert capture.is_available() is True

    def test_not_available_when_apk_down(self):
        mock_client = MagicMock()
        mock_client.is_reachable.return_value = False
        capture = AndroidCapture(http_client=mock_client)
        assert capture.is_available() is False


class TestCaptureRegion:
    def test_region_crop(self):
        resp = _mock_capture_response(width=200, height=400)
        mock_client = MagicMock()
        mock_client.post.return_value = resp

        with tempfile.TemporaryDirectory() as tmpdir:
            capture = AndroidCapture(screenshot_dir=tmpdir, http_client=mock_client)
            result = capture.capture(quality=80, region={"x": 10, "y": 20, "width": 50, "height": 60})
            assert result.width == 50
            assert result.height == 60
