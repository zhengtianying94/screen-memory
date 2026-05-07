"""Screen capture abstract interface and result model."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import time


@dataclass(frozen=True, slots=True)
class CaptureResult:
    """Result of a screen capture operation."""

    image_data: bytes
    file_path: str
    width: int = 0
    height: int = 0
    capture_time_ms: int = 0
    app_name: Optional[str] = None
    app_package: Optional[str] = None


class ScreenCapture(ABC):
    """Abstract screen capture adapter with timed capture support."""

    def __init__(self) -> None:
        self._timed_thread: Optional[threading.Thread] = None
        self._timed_stop = threading.Event()
        self._timed_count = 0
        self._timed_started_at: Optional[float] = None

    @abstractmethod
    def capture(self, quality: int = 80, region: Optional[dict] = None) -> CaptureResult:
        """Capture the full screen or a region.

        Args:
            quality: JPEG quality 1-100.
            region: Optional {"x":, "y":, "width":, "height":} dict.
        """

    def capture_region(self, x: int, y: int, w: int, h: int, quality: int = 80) -> CaptureResult:
        """Capture a screen region. Default: full capture then crop."""
        return self.capture(quality=quality, region={"x": x, "y": y, "width": w, "height": h})

    def start_timed_capture(
        self,
        interval_seconds: int = 30,
        quality: int = 80,
        callback=None,
    ) -> None:
        """Start periodic auto-capture in a background thread.

        Args:
            interval_seconds: Minimum 5 seconds between captures.
            quality: JPEG quality for each capture.
            callback: Called with CaptureResult after each capture.
        """
        if self.is_capturing():
            return
        interval_seconds = max(5, interval_seconds)
        self._timed_stop.clear()
        self._timed_count = 0
        self._timed_started_at = time.time()

        def _loop():
            while not self._timed_stop.is_set():
                result = self.capture(quality=quality)
                self._timed_count += 1
                if callback:
                    callback(result)
                self._timed_stop.wait(interval_seconds)

        self._timed_thread = threading.Thread(target=_loop, daemon=True)
        self._timed_thread.start()

    def stop_timed_capture(self) -> dict:
        """Stop timed capture and return status."""
        if not self.is_capturing():
            return self.timed_status()
        self._timed_stop.set()
        if self._timed_thread:
            self._timed_thread.join(timeout=10)
            self._timed_thread = None
        return self.timed_status()

    def is_capturing(self) -> bool:
        """Return True if timed capture is active."""
        return self._timed_thread is not None and self._timed_thread.is_alive()

    def timed_status(self) -> dict:
        """Return current timed capture status."""
        if not self.is_capturing():
            return {"status": "stopped", "captures_count": self._timed_count}
        return {
            "status": "running",
            "captures_count": self._timed_count,
            "started_at": self._timed_started_at,
        }
