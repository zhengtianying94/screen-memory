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
    """Screen capture on Android via auxiliary APK's /capture HTTP endpoint."""

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
        return self._client.is_reachable()
