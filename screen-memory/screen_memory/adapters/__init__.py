"""Platform adapters for screen capture and OCR."""

from screen_memory.adapters.capture import CaptureResult, ScreenCapture
from screen_memory.adapters.ocr import OCRChain, OCREngine, OCRResult
from screen_memory.adapters.platform_factory import create_capture, create_ocr_chain, create_ocr_engines

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
