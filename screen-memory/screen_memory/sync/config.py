"""Sync configuration loaded from environment variables or config file."""

from __future__ import annotations

import os
from pathlib import Path


def _load_sync_config(path: Path) -> dict:
    """Load sync config from YAML file without requiring pyyaml."""
    if not path.exists():
        return {}
    data: dict = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key:
                    data[key] = value
    return data


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
        server_url = os.environ.get("SCREEN_MEMORY_SYNC_URL", "")
        token = os.environ.get("SCREEN_MEMORY_SYNC_TOKEN", "")
        interval = float(os.environ.get("SCREEN_MEMORY_SYNC_INTERVAL", "30"))

        # Fallback to config file if env vars not set
        if not server_url or not token:
            cfg_path = Path.home() / ".screenmemory" / "sync.yaml"
            data = _load_sync_config(cfg_path)
            if not server_url:
                server_url = data.get("url", "")
            if not token:
                token = data.get("token", "")
            if interval == 30.0:
                interval = float(data.get("interval", 30))

        return cls(server_url=server_url, token=token, interval=interval)

    @property
    def enabled(self) -> bool:
        return bool(self.server_url and self.token)
