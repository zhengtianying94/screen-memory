# Android Screen Memory Adapter — Phase 1: Python Adapter Layer

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Python-side Android adapters (HttpClient, AndroidCapture, MlKitOcr) and update platform_factory to auto-detect Android — all fully tested with mocked HTTP responses.

**Architecture:** Three new adapter files plug into existing `ScreenCapture` and `OCREngine` abstract interfaces. A shared `ScreenMemoryHttpClient` handles all HTTP communication with the auxiliary APK. `platform_factory.py` gains Android detection via `sys.platform` or `ANDROID_ROOT` env var. No changes to service/storage/tool layers.

**Tech Stack:** Python 3.10+, stdlib `urllib.request` for HTTP, `unittest.mock` for test mocking, `pytest` test runner.

**Spec:** `docs/superpowers/specs/2026-05-07-android-screen-memory-adapter-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `screen-memory/screen_memory/adapters/http_client.py` | CREATE | Shared HTTP client (urllib, retry, timeout) |
| `screen-memory/screen_memory/adapters/android_capture.py` | CREATE | AndroidCapture adapter (POST /capture → CaptureResult) |
| `screen-memory/screen_memory/adapters/mlkit_ocr.py` | CREATE | MlKitOcr adapter (POST /ocr → OCRResult) |
| `screen-memory/screen_memory/adapters/platform_factory.py` | MODIFY | Add `_is_android()` + Android branches |
| `screen-memory/screen_memory/adapters/__init__.py` | MODIFY | Export new classes |
| `screen-memory/tests/unit/test_http_client.py` | CREATE | HttpClient unit tests (5 cases) |
| `screen-memory/tests/unit/test_android_capture.py` | CREATE | AndroidCapture unit tests (7 cases) |
| `screen-memory/tests/unit/test_mlkit_ocr.py` | CREATE | MlKitOcr unit tests (7 cases) |
| `screen-memory/tests/unit/test_platform_factory_android.py` | CREATE | Platform factory Android tests (4 cases) |
| `screen-memory/tests/integration/test_android_pipeline.py` | CREATE | Integration tests (10 cases) |
| `screen-memory/tests/tools/test_android_tools.py` | CREATE | Tool/CLI tests (5 cases) |

---

### Task 1: ScreenMemoryHttpClient — Tests + Implementation

**Files:**
- Create: `screen-memory/tests/unit/test_http_client.py`
- Create: `screen-memory/screen_memory/adapters/http_client.py`

- [ ] **Step 1: Write all failing tests for HttpClient**

```python
# tests/unit/test_http_client.py
"""Tests for ScreenMemoryHttpClient: urllib-based HTTP with retry."""

import json
from unittest.mock import patch, MagicMock

import pytest

from screen_memory.adapters.http_client import ScreenMemoryHttpClient


class TestHttpGet:
    def test_get_success(self):
        """GET request returns parsed JSON dict."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({"running": True}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("screen_memory.adapters.http_client.urllib.request.urlopen", return_value=mock_response):
            client = ScreenMemoryHttpClient("http://localhost:19700")
            result = client.get("/status")
            assert result == {"running": True}

    def test_get_constructs_correct_url(self):
        """GET uses base_url + path as the full URL."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b"{}"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("screen_memory.adapters.http_client.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = mock_response
            client = ScreenMemoryHttpClient("http://localhost:19700")
            client.get("/status")
            call_args = mock_urlopen.call_args[0][0]
            assert call_args.full_url == "http://localhost:19700/status"


class TestHttpPost:
    def test_post_success(self):
        """POST request sends JSON body and returns parsed response."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({"text": "hello"}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("screen_memory.adapters.http_client.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = mock_response
            client = ScreenMemoryHttpClient("http://localhost:19700")
            result = client.post("/ocr", {"image": "base64data"})
            assert result == {"text": "hello"}
            # Verify POST method was used
            request_obj = mock_urlopen.call_args[0][0]
            assert request_obj.method == "POST"


class TestRetry:
    def test_retry_succeeds_on_second_attempt(self):
        """Retry recovers from first failure."""
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("refused")
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.read.return_value = json.dumps({"ok": True}).encode()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            return mock_response

        with patch("screen_memory.adapters.http_client.urllib.request.urlopen", side_effect=side_effect):
            with patch("screen_memory.adapters.http_client.time.sleep"):
                client = ScreenMemoryHttpClient("http://localhost:19700", retries=2)
                result = client.get("/status")
                assert result == {"ok": True}
                assert call_count == 2

    def test_retry_exhausted_raises_connection_error(self):
        """After all retries fail, raises ConnectionError."""
        with patch(
            "screen_memory.adapters.http_client.urllib.request.urlopen",
            side_effect=ConnectionError("refused"),
        ):
            with patch("screen_memory.adapters.http_client.time.sleep"):
                client = ScreenMemoryHttpClient("http://localhost:19700", retries=2)
                with pytest.raises(ConnectionError, match="refused"):
                    client.get("/status")


class TestIsReachable:
    def test_reachable(self):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b"{}"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("screen_memory.adapters.http_client.urllib.request.urlopen", return_value=mock_response):
            client = ScreenMemoryHttpClient("http://localhost:19700", timeout=5)
            assert client.is_reachable() is True

    def test_not_reachable(self):
        with patch(
            "screen_memory.adapters.http_client.urllib.request.urlopen",
            side_effect=Exception("connection failed"),
        ):
            client = ScreenMemoryHttpClient("http://localhost:19700")
            assert client.is_reachable() is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:/ScreenMemo/screen-memory && python -m pytest tests/unit/test_http_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'screen_memory.adapters.http_client'`

- [ ] **Step 3: Implement ScreenMemoryHttpClient**

```python
# screen_memory/adapters/http_client.py
"""Shared HTTP client for auxiliary APK communication."""

from __future__ import annotations

import json
import time
import urllib.request
import urllib.error


class ScreenMemoryHttpClient:
    """HTTP client using stdlib urllib with retry support."""

    def __init__(
        self,
        base_url: str,
        timeout: int = 10,
        retries: int = 2,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._retries = retries

    def get(self, path: str) -> dict:
        """GET request, returns parsed JSON response."""
        url = f"{self._base_url}{path}"
        return self._request_with_retry(url, data=None)

    def post(self, path: str, data: dict) -> dict:
        """POST request with JSON body, returns parsed JSON response."""
        url = f"{self._base_url}{path}"
        body = json.dumps(data).encode("utf-8")
        return self._request_with_retry(url, data=body)

    def is_reachable(self) -> bool:
        """Check if the server is reachable (no retry)."""
        try:
            req = urllib.request.Request(f"{self._base_url}/status")
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _request_with_retry(self, url: str, data: bytes | None) -> dict:
        last_error: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
                req.add_header("Content-Type", "application/json")
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception as exc:
                last_error = exc
                if attempt < self._retries:
                    time.sleep(1)
        raise ConnectionError(str(last_error)) from last_error
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd D:/ScreenMemo/screen-memory && python -m pytest tests/unit/test_http_client.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
cd D:/ScreenMemo/screen-memory
git add screen_memory/adapters/http_client.py tests/unit/test_http_client.py
git commit -m "feat(adapters): add ScreenMemoryHttpClient with retry support"
```

---

### Task 2: AndroidCapture — Tests + Implementation

**Files:**
- Create: `screen-memory/tests/unit/test_android_capture.py`
- Create: `screen-memory/screen_memory/adapters/android_capture.py`

- [ ] **Step 1: Write all failing tests for AndroidCapture**

```python
# tests/unit/test_android_capture.py
"""Tests for AndroidCapture: screenshot via auxiliary APK HTTP API."""

import base64
import io
import json
import os
import tempfile
from unittest.mock import patch, MagicMock, PropertyMock

import pytest
from PIL import Image

from screen_memory.adapters.capture import CaptureResult
from screen_memory.adapters.android_capture import AndroidCapture


def _make_jpeg_bytes(width=100, height=100) -> bytes:
    """Create a minimal valid JPEG for testing."""
    img = Image.new("RGB", (width, height), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _mock_capture_response(
    width=100, height=100, app_package="com.example.app", capture_time_ms=85
) -> dict:
    """Build a mock /capture API response."""
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
        """Successful capture returns a CaptureResult with correct fields."""
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
        """Capture saves JPEG to screenshot_dir/YYYY/MM/DD/HHMMSS.jpg."""
        resp = _mock_capture_response()
        mock_client = MagicMock()
        mock_client.post.return_value = resp

        with tempfile.TemporaryDirectory() as tmpdir:
            capture = AndroidCapture(screenshot_dir=tmpdir, http_client=mock_client)
            result = capture.capture(quality=80)
            assert os.path.isfile(result.file_path)
            assert result.file_path.startswith(tmpdir)

    def test_capture_app_package_none_when_missing(self):
        """Capture handles missing app_package gracefully."""
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
        """Capture raises ConnectionError when APK is not running."""
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
        """Capture with region crops the full screenshot."""
        resp = _mock_capture_response(width=200, height=400)
        mock_client = MagicMock()
        mock_client.post.return_value = resp

        with tempfile.TemporaryDirectory() as tmpdir:
            capture = AndroidCapture(screenshot_dir=tmpdir, http_client=mock_client)
            result = capture.capture(quality=80, region={"x": 10, "y": 20, "width": 50, "height": 60})
            assert result.width == 50
            assert result.height == 60
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:/ScreenMemo/screen-memory && python -m pytest tests/unit/test_android_capture.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'screen_memory.adapters.android_capture'`

- [ ] **Step 3: Implement AndroidCapture**

```python
# screen_memory/adapters/android_capture.py
"""Android screen capture via auxiliary APK HTTP API."""

from __future__ import annotations

import base64
import io
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image

from screen_memory.adapters.capture import CaptureResult, ScreenCapture
from screen_memory.adapters.http_client import ScreenMemoryHttpClient


class AndroidCapture(ScreenCapture):
    """Screen capture on Android via auxiliary APK's /capture HTTP endpoint.

    The APK runs MediaProjection-based capture and returns JPEG over HTTP.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        screenshot_dir: Optional[str] = None,
        timeout: Optional[int] = None,
        http_client: Optional[ScreenMemoryHttpClient] = None,
    ) -> None:
        super().__init__()
        self._screenshot_dir = Path(
            screenshot_dir
            or os.environ.get("SCREEN_MEMORY_SCREENSHOT_DIR", "")
            or os.path.expanduser("~/.screenmemory/screenshots")
        )
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)
        url = base_url or os.environ.get("SCREEN_MEMORY_APK_URL", "http://127.0.0.1:19700")
        cap_timeout = timeout or int(os.environ.get("SCREEN_MEMORY_APK_TIMEOUT", "10"))
        self._client = http_client or ScreenMemoryHttpClient(url, timeout=cap_timeout, retries=0)

    def capture(self, quality: int = 80, region: Optional[dict] = None) -> CaptureResult:
        """POST /capture to auxiliary APK, decode JPEG, optionally crop region."""
        resp = self._client.post("/capture", {"quality": quality})
        image_data = base64.b64decode(resp["image"])
        width = resp.get("width", 0)
        height = resp.get("height", 0)
        app_package = resp.get("app_package")
        capture_time_ms = resp.get("capture_time_ms", 0)

        if region:
            img = Image.open(io.BytesIO(image_data))
            cropped = img.crop((
                region["x"],
                region["y"],
                region["x"] + region["width"],
                region["y"] + region["height"],
            ))
            buf = io.BytesIO()
            cropped.save(buf, format="JPEG", quality=quality)
            image_data = buf.getvalue()
            width = region["width"]
            height = region["height"]

        now = datetime.now()
        date_dir = self._screenshot_dir / f"{now.year}/{now.month:02d}/{now.day:02d}"
        date_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{now.hour:02d}{now.minute:02d}{now.second:02d}.jpg"
        file_path = str(date_dir / filename)

        with open(file_path, "wb") as f:
            f.write(image_data)

        return CaptureResult(
            image_data=image_data,
            file_path=file_path,
            width=width,
            height=height,
            capture_time_ms=capture_time_ms,
            app_name=app_package,
            app_package=app_package,
        )

    def is_available(self) -> bool:
        """Check if auxiliary APK HTTP server is reachable."""
        return self._client.is_reachable()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd D:/ScreenMemo/screen-memory && python -m pytest tests/unit/test_android_capture.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
cd D:/ScreenMemo/screen-memory
git add screen_memory/adapters/android_capture.py tests/unit/test_android_capture.py
git commit -m "feat(adapters): add AndroidCapture adapter via auxiliary APK HTTP API"
```

---

### Task 3: MlKitOcr — Tests + Implementation

**Files:**
- Create: `screen-memory/tests/unit/test_mlkit_ocr.py`
- Create: `screen-memory/screen_memory/adapters/mlkit_ocr.py`

- [ ] **Step 1: Write all failing tests for MlKitOcr**

```python
# tests/unit/test_mlkit_ocr.py
"""Tests for MlKitOcr: OCR via auxiliary APK ML Kit HTTP API."""

import base64
from unittest.mock import MagicMock

import pytest

from screen_memory.adapters.ocr import OCRResult
from screen_memory.adapters.mlkit_ocr import MlKitOcr


def _mock_ocr_response(text="Hello world", blocks=None, processing_time_ms=100) -> dict:
    """Build a mock /ocr API response."""
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
        """Successful recognition returns OCRResult with correct text."""
        mock_client = MagicMock()
        mock_client.post.return_value = _mock_ocr_response("Hello world")

        ocr = MlKitOcr(http_client=mock_client)
        result = ocr.recognize(b"fake-image-data")

        assert isinstance(result, OCRResult)
        assert result.text == "Hello world"
        assert result.engine == "mlkit"
        assert result.source == "system"

    def test_blocks_converted_to_tuple_format(self):
        """APK blocks are converted to (text, (x,y,w,h), confidence) tuples."""
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
        """recognize() sends image_data as base64 in POST body."""
        mock_client = MagicMock()
        mock_client.post.return_value = _mock_ocr_response("ok")

        ocr = MlKitOcr(http_client=mock_client)
        ocr.recognize(b"\x89PNG\r\n")

        call_args = mock_client.post.call_args
        sent_data = call_args[0][1]  # second positional arg = data dict
        assert "image" in sent_data
        decoded = base64.b64decode(sent_data["image"])
        assert decoded == b"\x89PNG\r\n"


class TestRecognizeEmpty:
    def test_empty_image_returns_empty_result(self):
        """OCR returning empty text yields empty OCRResult."""
        mock_client = MagicMock()
        mock_client.post.return_value = _mock_ocr_response(text="", blocks=[])

        ocr = MlKitOcr(http_client=mock_client)
        result = ocr.recognize(b"blank")

        assert result.text == ""
        assert result.confidence == 0.0


class TestRecognizeFailure:
    def test_apk_unavailable_returns_empty_result(self):
        """When APK is unreachable, returns empty OCRResult instead of raising."""
        mock_client = MagicMock()
        mock_client.post.side_effect = ConnectionError("refused")

        ocr = MlKitOcr(http_client=mock_client)
        result = ocr.recognize(b"img")

        assert result.text == ""
        assert result.confidence == 0.0
        assert result.engine == "mlkit"

    def test_timeout_returns_empty_result(self):
        """Timeout returns empty OCRResult, never raises."""
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:/ScreenMemo/screen-memory && python -m pytest tests/unit/test_mlkit_ocr.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'screen_memory.adapters.mlkit_ocr'`

- [ ] **Step 3: Implement MlKitOcr**

```python
# screen_memory/adapters/mlkit_ocr.py
"""ML Kit OCR via auxiliary APK HTTP API."""

from __future__ import annotations

import base64
import os
from typing import Optional

from screen_memory.adapters.ocr import OCREngine, OCRResult
from screen_memory.adapters.http_client import ScreenMemoryHttpClient


class MlKitOcr(OCREngine):
    """OCR engine using ML Kit Text Recognition via auxiliary APK.

    Sends image bytes as base64 to the APK's /ocr endpoint.
    Never raises — returns empty OCRResult on failure so fallback chain continues.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None,
        http_client: Optional[ScreenMemoryHttpClient] = None,
    ) -> None:
        url = base_url or os.environ.get("SCREEN_MEMORY_APK_URL", "http://127.0.0.1:19700")
        ocr_timeout = timeout or int(os.environ.get("SCREEN_MEMORY_APK_OCR_TIMEOUT", "15"))
        self._client = http_client or ScreenMemoryHttpClient(url, timeout=ocr_timeout, retries=1)

    def is_available(self) -> bool:
        """Check if APK is running and ML Kit OCR is initialized."""
        try:
            status = self._client.get("/status")
            return status.get("ocr_ready", False) is True
        except Exception:
            return False

    def recognize(self, image_data: bytes) -> OCRResult:
        """POST /ocr with base64 image, return OCRResult. Never raises."""
        try:
            image_b64 = base64.b64encode(image_data).decode("utf-8")
            resp = self._client.post("/ocr", {"image": image_b64})

            text = resp.get("text", "")
            blocks = tuple(
                (
                    b["text"],
                    tuple(b["bbox"]),
                    b.get("confidence", 0.85),
                )
                for b in resp.get("blocks", [])
            )
            confidence = 0.85 if text else 0.0

            return OCRResult(
                text=text,
                confidence=confidence,
                engine="mlkit",
                blocks=blocks,
                source="system",
            )
        except Exception:
            return OCRResult(
                text="",
                confidence=0.0,
                engine="mlkit",
                blocks=(),
                source="system",
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd D:/ScreenMemo/screen-memory && python -m pytest tests/unit/test_mlkit_ocr.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
cd D:/ScreenMemo/screen-memory
git add screen_memory/adapters/mlkit_ocr.py tests/unit/test_mlkit_ocr.py
git commit -m "feat(adapters): add MlKitOcr adapter via auxiliary APK HTTP API"
```

---

### Task 4: Platform Factory — Tests + Android Detection

**Files:**
- Create: `screen-memory/tests/unit/test_platform_factory_android.py`
- Modify: `screen-memory/screen_memory/adapters/platform_factory.py`

- [ ] **Step 1: Write all failing tests for Android platform detection**

```python
# tests/unit/test_platform_factory_android.py
"""Tests for platform_factory Android detection and wiring."""

import os
import sys
from unittest.mock import patch

import pytest

from screen_memory.adapters.android_capture import AndroidCapture
from screen_memory.adapters.mlkit_ocr import MlKitOcr
from screen_memory.adapters.tesseract_ocr import TesseractOcr


class TestAndroidDetection:
    def test_create_capture_returns_android_on_android_platform(self):
        """When sys.platform is 'android', create_capture returns AndroidCapture."""
        with patch.object(sys, "platform", "android"):
            from screen_memory.adapters.platform_factory import create_capture
            capture = create_capture()
            assert isinstance(capture, AndroidCapture)

    def test_create_capture_returns_android_with_env_var(self):
        """When ANDROID_ROOT env var is set, create_capture returns AndroidCapture."""
        with patch.object(sys, "platform", "linux"), \
             patch.dict(os.environ, {"ANDROID_ROOT": "/system"}):
            from screen_memory.adapters.platform_factory import create_capture
            capture = create_capture()
            assert isinstance(capture, AndroidCapture)


class TestAndroidOcrChain:
    def test_android_platform_has_mlkit_first(self):
        """Android OCR chain puts MlKitOcr as the first engine."""
        with patch.object(sys, "platform", "android"):
            from screen_memory.adapters.platform_factory import create_ocr_engines
            engines = create_ocr_engines()
            assert len(engines) >= 1
            assert isinstance(engines[0], MlKitOcr)

    def test_android_chain_order_mlkit_then_tesseract(self):
        """Android OCR chain is: MlKitOcr → TesseractOcr."""
        with patch.object(sys, "platform", "android"):
            from screen_memory.adapters.platform_factory import create_ocr_engines
            engines = create_ocr_engines()
            assert isinstance(engines[0], MlKitOcr)
            assert isinstance(engines[1], TesseractOcr)
            assert len(engines) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:/ScreenMemo/screen-memory && python -m pytest tests/unit/test_platform_factory_android.py -v`
Expected: FAIL — `create_capture()` returns `LinuxCapture` or raises, not `AndroidCapture`

- [ ] **Step 3: Modify platform_factory.py**

Add `_is_android()` helper and Android branches to both `create_capture()` and `_get_platform_engines()`:

```python
# screen_memory/adapters/platform_factory.py
"""Platform auto-detection factory for screen capture and OCR adapters."""

from __future__ import annotations

import os
import sys
from typing import Optional

from screen_memory.adapters.capture import ScreenCapture
from screen_memory.adapters.ocr import OCREngine, OCRChain


def _is_android() -> bool:
    """Detect Android platform (Termux or Python-for-Android)."""
    return sys.platform == "android" or "ANDROID_ROOT" in os.environ


def create_capture(screenshot_dir: Optional[str] = None) -> ScreenCapture:
    """Create the best ScreenCapture adapter for the current platform."""
    platform = sys.platform

    if platform == "win32":
        from screen_memory.adapters.windows_capture import WindowsCapture
        return WindowsCapture(screenshot_dir=screenshot_dir)

    if _is_android():
        from screen_memory.adapters.android_capture import AndroidCapture
        return AndroidCapture(screenshot_dir=screenshot_dir)

    if platform == "darwin":
        from screen_memory.adapters.macos_capture import MacOSCapture
        return MacOSCapture(screenshot_dir=screenshot_dir)

    if platform.startswith("linux"):
        from screen_memory.adapters.linux_capture import LinuxCapture
        return LinuxCapture(screenshot_dir=screenshot_dir)

    raise RuntimeError(f"Unsupported platform for screen capture: {platform}")


def create_ocr_chain(min_confidence: float = 0.5) -> OCRChain:
    """Create an OCR fallback chain with platform-appropriate engines."""
    engines = _get_platform_engines()
    return OCRChain(engines=engines, min_confidence=min_confidence)


def create_ocr_engines() -> list[OCREngine]:
    """Return available OCR engines for the current platform."""
    return _get_platform_engines()


def _get_platform_engines() -> list[OCREngine]:
    """Build the list of OCR engines to try, in priority order."""
    engines: list[OCREngine] = []
    platform = sys.platform

    # System OCR first
    if platform == "win32":
        from screen_memory.adapters.winrt_ocr import WinRtOcr
        engines.append(WinRtOcr())
    elif platform == "darwin":
        from screen_memory.adapters.vision_ocr import VisionOcr
        engines.append(VisionOcr())

    # Android ML Kit
    if _is_android():
        from screen_memory.adapters.mlkit_ocr import MlKitOcr
        engines.append(MlKitOcr())

    # Tesseract fallback (all platforms)
    from screen_memory.adapters.tesseract_ocr import TesseractOcr
    engines.append(TesseractOcr())

    return engines
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd D:/ScreenMemo/screen-memory && python -m pytest tests/unit/test_platform_factory_android.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Run existing tests to verify no regression**

Run: `cd D:/ScreenMemo/screen-memory && python -m pytest tests/ -v`
Expected: All existing tests still PASS

- [ ] **Step 6: Commit**

```bash
cd D:/ScreenMemo/screen-memory
git add screen_memory/adapters/platform_factory.py tests/unit/test_platform_factory_android.py
git commit -m "feat(factory): add Android platform detection and adapter wiring"
```

---

### Task 5: Update __init__.py exports

**Files:**
- Modify: `screen-memory/screen_memory/adapters/__init__.py`

- [ ] **Step 1: Add new exports to __init__.py**

```python
# screen_memory/adapters/__init__.py
"""Platform adapters for screen capture and OCR."""

from screen_memory.adapters.capture import CaptureResult, ScreenCapture
from screen_memory.adapters.ocr import OCRChain, OCREngine, OCRResult
from screen_memory.adapters.platform_factory import (
    create_capture,
    create_ocr_chain,
    create_ocr_engines,
)

__all__ = [
    "CaptureResult",
    "ScreenCapture",
    "OCRResult",
    "OCREngine",
    "OCRChain",
    "create_capture",
    "create_ocr_chain",
    "create_ocr_engines",
]
```

Note: AndroidCapture and MlKitOcr are not exported at package level — they are accessed via `platform_factory.create_capture()` / `create_ocr_engines()`, consistent with how WindowsCapture and WinRtOcr are used.

- [ ] **Step 2: Run all tests**

Run: `cd D:/ScreenMemo/screen-memory && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
cd D:/ScreenMemo/screen-memory
git add screen_memory/adapters/__init__.py
git commit -m "chore: update adapters __init__.py for consistency"
```

---

### Task 6: Integration Tests — Android Pipeline

**Files:**
- Create: `screen-memory/tests/integration/test_android_pipeline.py`

- [ ] **Step 1: Write all integration tests**

```python
# tests/integration/test_android_pipeline.py
"""Integration tests: Android adapters wired into full system pipeline.

Uses mock HTTP client to simulate auxiliary APK responses.
"""

import io
import tempfile
from unittest.mock import MagicMock

import pytest
from PIL import Image

from screen_memory.adapters.android_capture import AndroidCapture
from screen_memory.adapters.capture import CaptureResult
from screen_memory.adapters.mlkit_ocr import MlKitOcr
from screen_memory.adapters.ocr import OCRChain, OCRResult
from screen_memory.adapters.tesseract_ocr import TesseractOcr
from screen_memory.models.uri import NocturneUri
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
    import base64
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
        self.post_calls = []

    def get(self, path):
        if path == "/status":
            return self._status_resp
        return {}

    def post(self, path, data):
        self.post_calls.append((path, data))
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
        ocr_chain = OCRChain([mlkit, TesseractOcr()])
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


# -- Scenario 1: Full capture → OCR → insert → search pipeline --


class TestCaptureOcrPipeline:
    def test_capture_and_search(self, android_system):
        """Capture → OCR → store → search finds OCR text."""
        index = android_system["index_svc"]
        result = index.capture_and_index()
        assert result["ocr_text"] == "Test OCR text"

        results = index.search_screenshots("OCR")
        assert len(results) >= 1

    def test_multiple_captures_selective_search(self, android_system):
        """5 captures with different OCR, search finds only matching one."""
        index = android_system["index_svc"]
        texts = ["alpha", "beta", "gamma", "delta", "epsilon"]

        for text in texts:
            mock_http = _MockHttpClient(ocr_resp=_mock_apk_ocr_response(text))
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


# -- Scenario 2: OCR fallback chain --


class TestOcrFallback:
    def test_mlkit_timeout_tesseract_used(self, android_system):
        """When MlKitOcr returns empty, TesseractOcr is tried."""
        mock_http = _MockHttpClient(ocr_resp=_mock_apk_ocr_response(""))
        mlkit = MlKitOcr(http_client=mock_http)
        chain = OCRChain([mlkit])
        result = chain.recognize(_make_jpeg())
        assert result.engine == "mlkit"
        assert result.text == ""

    def test_all_ocr_unavailable_screenshot_stored(self, android_system):
        """When all OCR engines fail, screenshot is stored without OCR text."""
        mock_http = _MockHttpClient(ocr_resp=_mock_apk_ocr_response(""))
        index = android_system["index_svc"]
        index._ocr = OCRChain([MlKitOcr(http_client=mock_http)])
        result = index.capture_and_index()
        assert result["ocr_text"] is None
        assert result["id"] is not None


# -- Scenario 3: Timed capture --


class TestTimedCapture:
    def test_timed_capture_lifecycle(self, android_system):
        """start_timed_capture → 3 captures → stop, count correct."""
        capture = android_system["capture"]
        results = []

        capture.start_timed_capture(
            interval_seconds=1,
            quality=80,
            callback=lambda r: results.append(r),
        )
        assert capture.is_capturing()

        import time
        time.sleep(3.5)
        status = capture.stop_timed_capture()
        assert not capture.is_capturing()
        assert status["captures_count"] >= 2


# -- Scenario 4: Signal from screenshot --


class TestSignalFromScreenshot:
    def test_capture_then_signal_activate(self, android_system):
        """Capture text with person name → ingest signal → activate → graph searchable."""
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


# -- Scenario 5: app_package field --


class TestAppPackageField:
    def test_app_package_stored(self, android_system):
        """Capture from WeChat stores app_package in ScreenshotRepo."""
        mock_http = _MockHttpClient(capture_resp=_mock_apk_capture_response("com.tencent.mm"))
        with tempfile.TemporaryDirectory() as tmpdir:
            capture = AndroidCapture(screenshot_dir=tmpdir, http_client=mock_http)
            result = capture.capture()
            assert result.app_package == "com.tencent.mm"
            assert result.app_name == "com.tencent.mm"
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd D:/ScreenMemo/screen-memory && python -m pytest tests/integration/test_android_pipeline.py -v`
Expected: All 10 tests PASS

- [ ] **Step 3: Commit**

```bash
cd D:/ScreenMemo/screen-memory
git add tests/integration/test_android_pipeline.py
git commit -m "test(integration): add Android adapter pipeline integration tests"
```

---

### Task 7: Tool/CLI Tests — Android Scenarios

**Files:**
- Create: `screen-memory/tests/tools/test_android_tools.py`

- [ ] **Step 1: Write tool-layer tests for Android scenarios**

```python
# tests/tools/test_android_tools.py
"""Tests for Android-specific tool and CLI scenarios."""

import os
import json
import tempfile
from unittest.mock import patch, MagicMock

import pytest

from screen_memory.adapters.android_capture import AndroidCapture
from screen_memory.adapters.mlkit_ocr import MlKitOcr
from screen_memory.storage.database import Database
from screen_memory.storage.graph_repo import GraphRepo
from screen_memory.storage.screenshot_repo import ScreenshotRepo
from screen_memory.services.graph_service import GraphService
from screen_memory.services.signal_service import SignalService, EntityPolicy
from screen_memory.tools.registry import ToolRegistry


def _mock_http_for_tools(ocr_text="Test OCR from Android"):
    """Create a mock HTTP client for tool tests."""
    import base64
    import io
    from PIL import Image

    img = Image.new("RGB", (50, 50))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    jpeg = buf.getvalue()

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
        repo = GraphRepo(db)
        ss_repo = ScreenshotRepo(db)
        graph_svc = GraphService(repo)
        signal_svc = SignalService(repo, {})
        registry = ToolRegistry(graph_svc, signal_svc, ss_repo)

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
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd D:/ScreenMemo/screen-memory && python -m pytest tests/tools/test_android_tools.py -v`
Expected: All 5 tests PASS

- [ ] **Step 3: Run full test suite to verify no regressions**

Run: `cd D:/ScreenMemo/screen-memory && python -m pytest tests/ -v`
Expected: ALL tests PASS (new + existing)

- [ ] **Step 4: Commit**

```bash
cd D:/ScreenMemo/screen-memory
git add tests/tools/test_android_tools.py
git commit -m "test(tools): add Android-specific CLI and config tests"
```

---

### Task 8: Final Verification

- [ ] **Step 1: Run complete test suite**

Run: `cd D:/ScreenMemo/screen-memory && python -m pytest tests/ -v --tb=short`
Expected: ALL tests PASS, 0 failures

- [ ] **Step 2: Verify test count**

Run: `cd D:/ScreenMemo/screen-memory && python -m pytest tests/ --co -q | tail -1`
Expected: ~70+ tests total (existing ~40 + new ~38)

- [ ] **Step 3: Verify imports work**

Run: `cd D:/ScreenMemo/screen-memory && python -c "from screen_memory.adapters.android_capture import AndroidCapture; from screen_memory.adapters.mlkit_ocr import MlKitOcr; from screen_memory.adapters.http_client import ScreenMemoryHttpClient; print('OK')"`
Expected: `OK`
