"""Sync configuration loaded from environment variables."""

from __future__ import annotations

import os


class SyncConfig:
    def __init__(
        self,
        server_url: str = "",
        token: str = "",
        interval: float = 30.0,
    ) -> None:
        self.server_url = server_url
        self.token = token
        self.interval = interval

    @classmethod
    def from_env(cls) -> SyncConfig:
        return cls(
            server_url=os.environ.get("SCREEN_MEMORY_SYNC_URL", ""),
            token=os.environ.get("SCREEN_MEMORY_SYNC_TOKEN", ""),
            interval=float(os.environ.get("SCREEN_MEMORY_SYNC_INTERVAL", "30")),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.server_url and self.token)
