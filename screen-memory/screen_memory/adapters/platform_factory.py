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
    """Create an OCR fallback chain with platform-appropriate engines.

    Priority order:
    1. System OCR (WinRT on Windows, Vision on macOS)
    2. Tesseract (if installed)
    """
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
