"""QueryBridge: remote query wrapper for cross-device screen memory."""

from __future__ import annotations

import httpx


class QueryBridge:
    def __init__(self, server_url: str, token: str, device_id: str) -> None:
        self._server_url = server_url.rstrip("/")
        self._token = token
        self._device_id = device_id

    def query(self, table: str, filters: dict, exclude_self: bool = True) -> list[dict]:
        try:
            resp = httpx.post(
                f"{self._server_url}/api/v1/sync/query",
                json={
                    "device_id": self._device_id,
                    "table": table,
                    "query": filters,
                    "exclude_self": exclude_self,
                },
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=30.0,
            )
            if resp.status_code == 200:
                return resp.json().get("results", [])
            return []
        except Exception:
            return []

    def list_devices(self) -> list[dict]:
        try:
            resp = httpx.get(
                f"{self._server_url}/api/v1/sync/status",
                params={"device_id": self._device_id},
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=10.0,
            )
            if resp.status_code == 200:
                return resp.json().get("devices", [])
            return []
        except Exception:
            return []
