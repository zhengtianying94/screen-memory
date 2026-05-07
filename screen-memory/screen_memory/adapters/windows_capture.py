"""Windows screen capture via PIL ImageGrab + Win32 API for active window info."""

from __future__ import annotations

import io
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image, ImageGrab

from screen_memory.adapters.capture import CaptureResult, ScreenCapture


class WindowsCapture(ScreenCapture):
    """Windows screen capture using PIL ImageGrab.

    Uses Win32 API (ctypes) to detect the foreground window title for app_name.
    No external dependencies beyond Pillow (which is already required).
    """

    def __init__(self, screenshot_dir: Optional[str] = None) -> None:
        super().__init__()
        self._screenshot_dir = Path(
            screenshot_dir
            or os.path.expandvars("D:\\ScreenMemo\\screen-memory\\screen_shoot")
        )
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)

    def capture(self, quality: int = 80, region: Optional[dict] = None) -> CaptureResult:
        """Capture the screen (full or region) and save as JPEG.

        Args:
            quality: JPEG quality 1-100.
            region: Optional {"x":, "y":, "width":, "height":}.
        """
        t0 = time.monotonic()
        bbox = None
        if region:
            bbox = (
                region["x"],
                region["y"],
                region["x"] + region["width"],
                region["y"] + region["height"],
            )
        img = ImageGrab.grab(bbox=bbox, all_screens=True)
        capture_ms = int((time.monotonic() - t0) * 1000)

        now = datetime.now()
        date_dir = self._screenshot_dir / f"{now.year}/{now.month:02d}/{now.day:02d}"
        date_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{now.hour:02d}{now.minute:02d}{now.second:02d}.jpg"
        file_path = str(date_dir / filename)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        image_data = buf.getvalue()

        with open(file_path, "wb") as f:
            f.write(image_data)

        app_name = _get_foreground_window_title()

        return CaptureResult(
            image_data=image_data,
            file_path=file_path,
            width=img.width,
            height=img.height,
            capture_time_ms=capture_ms,
            app_name=app_name,
        )


def _get_foreground_window_title() -> Optional[str]:
    """Get the foreground window title using Win32 API via ctypes."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return None
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value or None
    except Exception:
        return None
