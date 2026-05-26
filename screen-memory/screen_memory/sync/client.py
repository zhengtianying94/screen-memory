"""SyncClient: detect local changes and push to sync server."""

from __future__ import annotations

import platform
import sqlite3
import threading
import uuid
from datetime import datetime
from typing import Optional

import httpx

from screen_memory.storage.database import Database


SYNC_TABLE_CONFIG = {
    "screenshots": {"column": "captured_at"},
    "nodes": {"column": "updated_at"},
    "memories": {"column": "created_at"},
    "edges": {"column": "created_at"},
    "paths": {"column": None},
    "entities": {"column": "updated_at"},
}


class SyncClient:
    def __init__(self, db: Database, server_url: str, token: str, interval: float = 30.0) -> None:
        self._db = db
        self._server_url = server_url.rstrip("/")
        self._token = token
        self._interval = interval
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._ensure_sync_state()

    def _ensure_sync_state(self) -> None:
        self._db.execute(
            "INSERT OR IGNORE INTO sync_state (key, value) VALUES ('last_sync_time', '2000-01-01 00:00:00')"
        )
        for table in SYNC_TABLE_CONFIG:
            self._db.execute(
                "INSERT OR IGNORE INTO sync_state (key, value) VALUES (?, '0')",
                (f"last_sync_rowid_{table}",),
            )

    def _get_last_sync_time(self) -> str:
        row = self._db.execute(
            "SELECT value FROM sync_state WHERE key='last_sync_time'"
        ).fetchone()
        return row[0] if row else "2000-01-01 00:00:00"

    def _update_last_sync_time(self) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._db.execute(
            "UPDATE sync_state SET value=? WHERE key='last_sync_time'", (now,)
        )

    def _get_last_sync_rowid(self, table: str) -> int:
        row = self._db.execute(
            "SELECT value FROM sync_state WHERE key=?", (f"last_sync_rowid_{table}",)
        ).fetchone()
        return int(row[0]) if row else 0

    def _update_last_sync_rowid(self, table: str, rowid: int) -> None:
        self._db.execute(
            "UPDATE sync_state SET value=? WHERE key=?", (str(rowid), f"last_sync_rowid_{table}")
        )

    def detect_changes(self) -> dict[str, list[dict]]:
        last_time = self._get_last_sync_time()
        changes: dict[str, list[dict]] = {}
        for table, config in SYNC_TABLE_CONFIG.items():
            if config["column"]:
                rows = self._db.execute(
                    f"SELECT * FROM {table} WHERE {config['column']} > ?", (last_time,)
                ).fetchall()
            else:
                last_rowid = self._get_last_sync_rowid(table)
                rows = self._db.execute(
                    f"SELECT * FROM {table} WHERE id > ?", (last_rowid,)
                ).fetchall()
            if rows:
                cursor = self._db.execute(f"SELECT * FROM {table} LIMIT 0")
                cols = [desc[0] for desc in cursor.description]
                changes[table] = [dict(zip(cols, r)) for r in rows]
        return changes

    def get_device_id(self) -> str:
        row = self._db.execute(
            "SELECT value FROM sync_state WHERE key='device_id'"
        ).fetchone()
        if row:
            return row[0]
        device_id = f"{platform.system().lower()}-{platform.node().lower()}-{uuid.uuid4().hex[:4]}"
        self._db.execute(
            "INSERT INTO sync_state (key, value) VALUES ('device_id', ?)", (device_id,)
        )
        return device_id

    def push(self, changes: dict[str, list[dict]]) -> bool:
        if not changes:
            return True
        try:
            resp = httpx.post(
                f"{self._server_url}/api/v1/sync/push",
                json={"device_id": self.get_device_id(), "tables": changes},
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=30.0,
            )
            if resp.status_code == 200:
                self._update_last_sync_time()
                for table in changes:
                    if not SYNC_TABLE_CONFIG[table]["column"]:
                        max_id = max(r.get("id", 0) for r in changes[table])
                        self._update_last_sync_rowid(table, max_id)
                return True
            return False
        except httpx.HTTPError:
            return False

    def flush(self) -> bool:
        changes = self.detect_changes()
        return self.push(changes)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        try:
            self.flush()
        except Exception:
            pass
        if self._thread:
            self._thread.join(timeout=10.0)

    def _run_loop(self) -> None:
        while not self._stop_event.wait(self._interval):
            try:
                self.flush()
            except Exception:
                pass
