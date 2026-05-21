"""IndexService: capture → OCR → store → graph index pipeline."""

from __future__ import annotations

from typing import Optional

from screen_memory.models.uri import NocturneUri
from screen_memory.adapters.capture import ScreenCapture
from screen_memory.adapters.ocr import OCRChain
from screen_memory.storage.graph_repo import GraphRepo
from screen_memory.storage.screenshot_repo import ScreenshotRepo


class IndexService:
    def __init__(
        self,
        graph_repo: GraphRepo,
        screenshot_repo: ScreenshotRepo,
        capture: ScreenCapture,
        ocr: OCRChain,
    ) -> None:
        self._repo = graph_repo
        self._ss_repo = screenshot_repo
        self._capture = capture
        self._ocr = ocr

    def capture_and_index(
        self, link_uri: Optional[str] = None
    ) -> dict:
        """Capture screen, run OCR, store screenshot, optionally link to graph."""
        try:
            cap = self._capture.capture()
        except (ConnectionError, TimeoutError, OSError) as exc:
            return {"ok": False, "error": f"capture_unavailable: {exc}"}

        ocr_result = self._ocr.recognize(cap.image_data)

        uri_obj = NocturneUri.parse(link_uri) if link_uri else None
        if uri_obj:
            self._repo.create_node(uri_obj)
        s = self._ss_repo.insert(
            file_path=cap.file_path,
            ocr_text=ocr_result.text or None,
            uri=uri_obj,
        )

        if uri_obj and ocr_result.text:
            self._repo.write_memory(uri_obj, ocr_result.text)

        return s

    def search_screenshots(self, query: str) -> list[dict]:
        return self._ss_repo.search(query)

    def search_memories(self, query: str) -> list[dict]:
        return self._repo.search(query)
