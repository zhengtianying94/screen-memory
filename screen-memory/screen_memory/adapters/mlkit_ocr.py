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
        try:
            status = self._client.get("/status")
            return status.get("ocr_ready", False) is True
        except Exception:
            return False

    def recognize(self, image_data: bytes) -> OCRResult:
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
