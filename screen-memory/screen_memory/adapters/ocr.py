"""OCR abstract interface and fallback chain."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True, slots=True)
class OCRResult:
    """Result of an OCR recognition attempt."""

    text: str
    confidence: float
    engine: str
    blocks: tuple = ()  # ((text, (x, y, w, h), confidence), ...)
    source: str = "system"  # "system" | "tesseract" | "ai"


class OCREngine(ABC):
    """Abstract OCR engine."""

    @abstractmethod
    def recognize(self, image_data: bytes) -> OCRResult:
        """Run OCR on image bytes."""

    def is_available(self) -> bool:
        """Return True if this engine is ready to use."""
        return True


class OCRChain:
    """Try multiple OCR engines in order, pick the best result."""

    def __init__(
        self,
        engines: list[OCREngine],
        min_confidence: float = 0.5,
    ) -> None:
        self._engines = engines
        self._min_confidence = min_confidence

    def recognize(self, image_data: bytes) -> OCRResult:
        """Run engines in order; return the first result above min_confidence."""
        best = OCRResult(text="", confidence=0.0, engine="none")
        for engine in self._engines:
            if not engine.is_available():
                continue
            result = engine.recognize(image_data)
            if result.confidence >= self._min_confidence and result.text:
                return result
            if result.confidence >= best.confidence and result.text:
                best = result
        return best
