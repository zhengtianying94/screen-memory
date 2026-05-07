"""Tesseract OCR engine adapter (cross-platform fallback)."""

from __future__ import annotations

import io
from typing import Optional

from screen_memory.adapters.ocr import OCREngine, OCRResult

_TESSERACT_AVAILABLE: Optional[bool] = None


def _check_tesseract() -> bool:
    """Lazy check if pytesseract and tesseract binary are available."""
    global _TESSERACT_AVAILABLE
    if _TESSERACT_AVAILABLE is not None:
        return _TESSERACT_AVAILABLE
    try:
        import pytesseract  # noqa: F401
        pytesseract.get_tesseract_version()
        _TESSERACT_AVAILABLE = True
    except Exception:
        _TESSERACT_AVAILABLE = False
    return _TESSERACT_AVAILABLE


class TesseractOcr(OCREngine):
    """Tesseract OCR engine via pytesseract.

    Good cross-platform fallback with CJK language pack support.
    Requires: tesseract binary installed + pytesseract pip package.
    """

    def __init__(self, lang: str = "eng+chi_sim") -> None:
        self._lang = lang

    def is_available(self) -> bool:
        return _check_tesseract()

    def recognize(self, image_data: bytes) -> OCRResult:
        """Run Tesseract OCR on image bytes."""
        try:
            import pytesseract
            from PIL import Image

            img = Image.open(io.BytesIO(image_data))
            data = pytesseract.image_to_data(img, lang=self._lang, output_type=pytesseract.Output.DICT)

            texts = []
            blocks = []
            for i, txt in enumerate(data["text"]):
                conf = int(data["conf"][i])
                if conf > 0 and txt.strip():
                    texts.append(txt)
                    blocks.append((
                        txt,
                        (data["left"][i], data["top"][i], data["width"][i], data["height"][i]),
                        conf / 100.0,
                    ))

            full_text = " ".join(texts)
            avg_conf = sum(b[2] for b in blocks) / len(blocks) if blocks else 0.0

            return OCRResult(
                text=full_text,
                confidence=avg_conf,
                engine="tesseract",
                blocks=tuple(blocks),
                source="tesseract",
            )
        except Exception:
            return OCRResult(text="", confidence=0.0, engine="tesseract", source="tesseract")
