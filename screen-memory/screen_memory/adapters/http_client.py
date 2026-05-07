# screen_memory/adapters/http_client.py
"""Shared HTTP client for auxiliary APK communication."""

from __future__ import annotations

import json
import time
import urllib.request
import urllib.error


class ScreenMemoryHttpClient:
    """HTTP client using stdlib urllib with retry support."""

    def __init__(
        self,
        base_url: str,
        timeout: int = 10,
        retries: int = 2,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._retries = retries

    def get(self, path: str) -> dict:
        """GET request, returns parsed JSON response."""
        url = f"{self._base_url}{path}"
        return self._request_with_retry(url, data=None)

    def post(self, path: str, data: dict) -> dict:
        """POST request with JSON body, returns parsed JSON response."""
        url = f"{self._base_url}{path}"
        body = json.dumps(data).encode("utf-8")
        return self._request_with_retry(url, data=body)

    def is_reachable(self) -> bool:
        """Check if the server is reachable (no retry)."""
        try:
            req = urllib.request.Request(f"{self._base_url}/status")
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _request_with_retry(self, url: str, data: bytes | None) -> dict:
        last_error: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
                req.add_header("Content-Type", "application/json")
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception as exc:
                last_error = exc
                if attempt < self._retries:
                    time.sleep(1)
        raise ConnectionError(str(last_error)) from last_error
