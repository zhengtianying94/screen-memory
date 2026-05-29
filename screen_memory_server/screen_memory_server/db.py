"""Server-side SQLite for cross-device screen memory sync."""

from __future__ import annotations

import sqlite3
from typing import Optional


_TABLE_SCHEMAS = {
    "nodes": """(
        uri         TEXT NOT NULL,
        domain      TEXT NOT NULL,
        path        TEXT NOT NULL,
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL,
        device_id   TEXT NOT NULL,
        synced_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
        PRIMARY KEY (uri, device_id)
    )""",
    "memories": """(
        id          INTEGER,
        node_uri    TEXT NOT NULL,
        content     TEXT NOT NULL,
        version     INTEGER NOT NULL,
        status      TEXT NOT NULL DEFAULT 'active',
        created_at  TEXT NOT NULL,
        device_id   TEXT NOT NULL,
        synced_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
        PRIMARY KEY (id, device_id)
    )""",
    "edges": """(
        id          INTEGER,
        source_uri  TEXT NOT NULL,
        target_uri  TEXT NOT NULL,
        relation    TEXT NOT NULL DEFAULT 'related',
        weight      REAL NOT NULL DEFAULT 1.0,
        created_at  TEXT NOT NULL,
        device_id   TEXT NOT NULL,
        synced_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
        PRIMARY KEY (id, device_id)
    )""",
    "paths": """(
        id              INTEGER,
        ancestor_uri    TEXT NOT NULL,
        descendant_uri  TEXT NOT NULL,
        depth           INTEGER NOT NULL DEFAULT 1,
        device_id       TEXT NOT NULL,
        synced_at       TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (id, device_id)
    )""",
    "entities": """(
        id              INTEGER,
        entity_type     TEXT NOT NULL,
        name            TEXT NOT NULL,
        status          TEXT NOT NULL DEFAULT 'candidate',
        score           REAL NOT NULL DEFAULT 0.0,
        signal_count    INTEGER NOT NULL DEFAULT 0,
        evidence        TEXT NOT NULL DEFAULT '[]',
        first_seen_at   TEXT NOT NULL,
        last_seen_at    TEXT NOT NULL,
        created_at      TEXT NOT NULL,
        updated_at      TEXT NOT NULL,
        device_id       TEXT NOT NULL,
        synced_at       TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (id, device_id)
    )""",
    "screenshots": """(
        id          INTEGER,
        file_path   TEXT NOT NULL,
        ocr_text    TEXT,
        captured_at TEXT NOT NULL,
        uri         TEXT,
        device_id   TEXT NOT NULL,
        synced_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
        PRIMARY KEY (id, device_id)
    )""",
}

_CREATE_SYNC_STATE = """
CREATE TABLE IF NOT EXISTS sync_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class SyncDatabase:
    def __init__(self, path: str = ":memory:") -> None:
        self._path = path
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._path, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def initialize(self) -> None:
        for table_name, columns in _TABLE_SCHEMAS.items():
            self.conn.execute(f"CREATE TABLE IF NOT EXISTS {table_name} {columns}")
        self.conn.execute(_CREATE_SYNC_STATE)
        self.conn.commit()

    def list_tables(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        return [r["name"] for r in rows]

    def push_records(self, device_id: str, table: str, records: list[dict]) -> int:
        if table not in _TABLE_SCHEMAS or not records:
            return 0
        cols = list(records[0].keys()) + ["device_id"]
        placeholders = ", ".join(["?"] * len(cols))
        col_str = ", ".join(cols)
        count = 0
        for rec in records:
            values = [rec.get(c) for c in records[0].keys()] + [device_id]
            self.conn.execute(
                f"INSERT OR REPLACE INTO {table} ({col_str}) VALUES ({placeholders})",
                values,
            )
            count += 1
        self.conn.commit()
        return count

    def query_records(
        self,
        table: str,
        exclude_device: Optional[str] = None,
        filters: Optional[dict] = None,
    ) -> list[dict]:
        if table not in _TABLE_SCHEMAS:
            return []
        sql = f"SELECT * FROM {table} WHERE 1=1"
        params: list = []
        if exclude_device:
            sql += " AND device_id != ?"
            params.append(exclude_device)
        if filters:
            for col_op, val in filters.items():
                sql += f" AND {col_op} ?"
                params.append(val)
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_status(self) -> list[dict]:
        result = []
        for table in _TABLE_SCHEMAS:
            rows = self.conn.execute(
                f"SELECT device_id, COUNT(*) as cnt, MAX(synced_at) as last_sync "
                f"FROM {table} GROUP BY device_id"
            ).fetchall()
            for r in rows:
                result.append({
                    "device_id": r["device_id"],
                    "table": table,
                    "record_count": r["cnt"],
                    "last_sync": r["last_sync"],
                })
        devices: dict[str, dict] = {}
        for r in result:
            did = r["device_id"]
            if did not in devices:
                devices[did] = {"device_id": did, "last_sync": r["last_sync"], "tables": {}}
            devices[did]["tables"][r["table"]] = r["record_count"]
            if r["last_sync"] > devices[did]["last_sync"]:
                devices[did]["last_sync"] = r["last_sync"]
        return list(devices.values())

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
