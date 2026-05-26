"""Sync server configuration."""

from __future__ import annotations

from dataclasses import dataclass

import yaml


@dataclass
class SyncConfig:
    host: str = "0.0.0.0"
    port: int = 8200
    auth_token: str = ""
    db_path: str = "./data/screen-memory-sync.db"
    max_batch_size: int = 100

    @classmethod
    def from_yaml(cls, path: str) -> SyncConfig:
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
        server = raw.get("server", {})
        db = raw.get("database", {})
        sync = raw.get("sync", {})
        return cls(
            host=server.get("host", cls.host),
            port=server.get("port", cls.port),
            auth_token=server.get("auth_token", cls.auth_token),
            db_path=db.get("path", cls.db_path),
            max_batch_size=sync.get("max_batch_size", cls.max_batch_size),
        )
