"""Windows OCR via WinRT Windows.Media.Ocr (built-in Windows 10/11 OCR engine)."""

from __future__ import annotations

import asyncio
import io
import sys
from typing import Optional

from PIL import Image

from screen_memory.adapters.ocr import OCREngine, OCRResult

_WINRT_AVAILABLE: Optional[bool] = None


def _check_winrt() -> bool:
    """Lazy check if winrt OCR packages are importable."""
    global _WINRT_AVAILABLE
    if _WINRT_AVAILABLE is not None:
        return _WINRT_AVAILABLE
    if sys.platform != "win32":
        _WINRT_AVAILABLE = False
        return False
    try:
        from winrt.windows.media.ocr import OcrEngine  # noqa: F401
        from winrt.windows.graphics.imaging import SoftwareBitmap  # noqa: F401
        from winrt.windows.storage.streams import DataWriter  # noqa: F401
        _WINRT_AVAILABLE = True
    except ImportError:
        _WINRT_AVAILABLE = False
    return _WINRT_AVAILABLE


class WinRtOcr(OCREngine):
    """Windows built-in OCR using Windows.Media.Ocr via WinRT.

    Supports all languages installed on the system (including CJK).
    Requires: pip install winrt-Windows.Media.Ocr winrt-Windows.Graphics.Imaging
              winrt-Windows.Storage.Streams winrt-Windows.Foundation
    """

    def is_available(self) -> bool:
        return _check_winrt()

    def recognize(self, image_data: bytes) -> OCRResult:
        try:
            return asyncio.run(self._recognize_async(image_data))
        except Exception:
            return OCRResult(text="", confidence=0.0, engine="winrt", source="system")

    async def _recognize_async(self, image_data: bytes) -> OCRResult:
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat
        from winrt.windows.storage.streams import DataWriter

        img = Image.open(io.BytesIO(image_data)).convert("RGBA")
        writer = DataWriter()
        writer.write_bytes(img.tobytes())
        bitmap = SoftwareBitmap(BitmapPixelFormat.RGBA8, img.width, img.height)
        bitmap.copy_from_buffer(writer.detach_buffer())

        engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            return OCRResult(text="", confidence=0.0, engine="winrt", source="system")

        result = await engine.recognize_async(bitmap)

        if result is None or not result.text:
            return OCRResult(text="", confidence=0.0, engine="winrt", source="system")

        blocks = []
        for line in result.lines:
            for word in line.words:
                rect = word.bounding_rect
                blocks.append((word.text, (rect.x, rect.y, rect.width, rect.height), 1.0))

        confidence = 0.9 if blocks else 0.0
        return OCRResult(
            text=result.text,
            confidence=confidence,
            engine="winrt",
            blocks=tuple(blocks),
            source="system",
        )
