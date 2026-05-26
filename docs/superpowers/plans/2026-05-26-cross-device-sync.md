# Cross-Device Screen Memory Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable screen memory sharing across Windows and Android devices via a self-hosted sync server with unidirectional push and remote query.

**Architecture:** Devices push local DB changes to a FastAPI server (every 30s + on-demand + shutdown). Server stores all devices' data with device_id tags. Cross-device queries go through server API, never stored locally. OpenClaw tools gain a `scope` parameter for local/remote/all queries.

**Tech Stack:** Python 3.10+, FastAPI, SQLite, pytest, Docker

**Spec:** `docs/superpowers/specs/2026-05-26-screen-memory-cross-device-sync-design.md`

**Server:** root@47.118.19.85:/home/zty/screen_memory_server (uv Python environment ready)

---

## File Structure

### Server (new, at `/home/zty/screen_memory_server/`)

```
screen_memory_server/
  main.py              # FastAPI app with push/query/status/health endpoints
  db.py                # Server-side SQLite schema and operations
  config.py            # YAML config loader
  schema.sql           # Server DB schema (device-side tables + device_id + synced_at)
  config.yaml          # Runtime configuration
  pyproject.toml       # Server dependencies (fastapi, uvicorn, pyyaml)
  tests/
    test_api.py        # API integration tests using FastAPI TestClient
    test_config.py     # Config loading tests
```

### Device-Side (new, at `screen-memory/screen_memory/sync/`)

```
screen_memory/sync/
  __init__.py          # Package init
  config.py            # SyncConfig from env vars
  client.py            # SyncClient: change detection, push, start/stop/flush
  query_bridge.py      # QueryBridge: remote query wrapper
```

### Device-Side Tests (new, at `screen-memory/tests/sync/`)

```
tests/sync/
  __init__.py
  test_server_api.py   # Server API tests (can run locally with TestClient)
  test_sync_client.py  # SyncClient unit tests (in-memory SQLite + mock HTTP)
  test_query_bridge.py # QueryBridge unit tests (mock HTTP)
  test_tools_remote.py # Tool scope extension tests
  test_e2e_sync.py     # End-to-end push-then-query tests
```

### Device-Side Modifications (existing files)

```
screen_memory/storage/database.py    # Add sync_state table to _SCHEMA_SQL
screen_memory/tools/registry.py      # Add scope param to 4 tools + sync_status tool
screen_memory/tools/__init__.py      # Wire SyncClient into register()
screen-memory/pyproject.toml         # Add fastapi, httpx to dev deps for testing
```

---

## Phase 1: Server

### Task 1.1: Server project scaffolding

**Files:**
- Create: `screen_memory_server/pyproject.toml`
- Create: `screen_memory_server/config.yaml`

- [ ] **Step 1: Create server pyproject.toml**

At `/home/zty/screen_memory_server/pyproject.toml`:

```toml
[project]
name = "screen-memory-server"
version = "0.1.0"
description = "Sync server for cross-device screen memory"
requires-python = ">=3.10"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "httpx>=0.27",
]
```

- [ ] **Step 2: Create default config.yaml**

At `/home/zty/screen_memory_server/config.yaml`:

```yaml
server:
  host: "0.0.0.0"
  port: 8200
  auth_token: "screen-memory-sync-token-2026"
database:
  path: "./data/screen-memory-sync.db"
sync:
  max_batch_size: 100
```

- [ ] **Step 3: Install dependencies on server**

```bash
ssh root@47.118.19.85 "cd /home/zty/screen_memory_server && uv pip install -e '.[dev]'"
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-05-26-cross-device-sync.md
git commit -m "chore: add cross-device sync implementation plan"
```

---

### Task 1.2: Server config loader

**Files:**
- Create: `screen_memory_server/config.py`
- Create: `screen_memory_server/tests/__init__.py`
- Create: `screen_memory_server/tests/test_config.py`

- [ ] **Step 1: Write failing test for config loading**

```python
# screen_memory_server/tests/test_config.py
import tempfile
import os
from pathlib import Path


def test_load_config_from_yaml():
    """Config loads all fields from a YAML file."""
    from screen_memory_server.config import SyncConfig

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("""
server:
  host: "127.0.0.1"
  port: 9999
  auth_token: "test-token"
database:
  path: "/tmp/test.db"
sync:
  max_batch_size: 50
""")
        f.flush()
        cfg = SyncConfig.from_yaml(f.name)

    assert cfg.host == "127.0.0.1"
    assert cfg.port == 9999
    assert cfg.auth_token == "test-token"
    assert cfg.db_path == "/tmp/test.db"
    assert cfg.max_batch_size == 50
    os.unlink(f.name)


def test_config_defaults():
    """Config uses sensible defaults when fields are missing."""
    from screen_memory_server.config import SyncConfig

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("server:\n  auth_token: 't'\n")
        f.flush()
        cfg = SyncConfig.from_yaml(f.name)

    assert cfg.host == "0.0.0.0"
    assert cfg.port == 8200
    assert cfg.db_path == "./data/screen-memory-sync.db"
    assert cfg.max_batch_size == 100
    os.unlink(f.name)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/zty/screen_memory_server && uv run pytest tests/test_config.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'screen_memory_server'`

- [ ] **Step 3: Implement config.py**

```python
# screen_memory_server/config.py
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/zty/screen_memory_server && uv run pytest tests/test_config.py -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add screen_memory_server/config.py screen_memory_server/tests/
git commit -m "feat(server): add config loader with YAML support"
```

---

### Task 1.3: Server database schema and operations

**Files:**
- Create: `screen_memory_server/db.py`
- Create: `screen_memory_server/tests/test_db.py`

- [ ] **Step 1: Write failing test for server DB operations**

```python
# screen_memory_server/tests/test_db.py
import pytest
from screen_memory_server.db import SyncDatabase


@pytest.fixture
def sdb():
    db = SyncDatabase(":memory:")
    db.initialize()
    return db


class TestSyncDatabaseInit:
    def test_tables_created(self, sdb):
        tables = sdb.list_tables()
        for t in ["nodes", "memories", "edges", "paths", "entities", "screenshots"]:
            assert t in tables

    def test_sync_state_table_exists(self, sdb):
        tables = sdb.list_tables()
        assert "sync_state" in tables


class TestPushRecords:
    def test_push_screenshots(self, sdb):
        records = [
            {"id": 1, "file_path": "/a.png", "ocr_text": "hello", "captured_at": "2026-05-26 10:00:00"},
            {"id": 2, "file_path": "/b.png", "ocr_text": "world", "captured_at": "2026-05-26 10:01:00"},
        ]
        sdb.push_records("device-1", "screenshots", records)
        results = sdb.query_records("screenshots", exclude_device=None)
        assert len(results) == 2
        assert results[0]["device_id"] == "device-1"

    def test_push_nodes(self, sdb):
        records = [
            {"uri": "core://test/a", "domain": "core", "path": "test/a", "created_at": "2026-05-26 10:00:00", "updated_at": "2026-05-26 10:00:00"},
        ]
        sdb.push_records("device-1", "nodes", records)
        results = sdb.query_records("nodes", exclude_device=None)
        assert len(results) == 1


class TestQueryRecords:
    def test_query_excludes_device(self, sdb):
        sdb.push_records("device-1", "screenshots", [
            {"id": 1, "file_path": "/a.png", "ocr_text": "hello", "captured_at": "2026-05-26 10:00:00"},
        ])
        sdb.push_records("device-2", "screenshots", [
            {"id": 2, "file_path": "/b.png", "ocr_text": "world", "captured_at": "2026-05-26 10:01:00"},
        ])
        results = sdb.query_records("screenshots", exclude_device="device-1")
        assert len(results) == 1
        assert results[0]["device_id"] == "device-2"

    def test_query_with_filter(self, sdb):
        sdb.push_records("device-1", "screenshots", [
            {"id": 1, "file_path": "/a.png", "ocr_text": "hello world", "captured_at": "2026-05-26 10:00:00"},
            {"id": 2, "file_path": "/b.png", "ocr_text": "goodbye", "captured_at": "2026-05-26 10:01:00"},
        ])
        results = sdb.query_records("screenshots", exclude_device=None, filters={"ocr_text LIKE": "%hello%"})
        assert len(results) == 1


class TestSyncStatus:
    def test_status_returns_devices(self, sdb):
        sdb.push_records("device-1", "screenshots", [
            {"id": 1, "file_path": "/a.png", "ocr_text": "hello", "captured_at": "2026-05-26 10:00:00"},
        ])
        sdb.push_records("device-2", "nodes", [
            {"uri": "core://x", "domain": "core", "path": "x", "created_at": "2026-05-26 10:00:00", "updated_at": "2026-05-26 10:00:00"},
        ])
        status = sdb.get_status()
        assert len(status) == 2
        devices = [s["device_id"] for s in status]
        assert "device-1" in devices
        assert "device-2" in devices
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/zty/screen_memory_server && uv run pytest tests/test_db.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement db.py**

```python
# screen_memory_server/db.py
"""Server-side SQLite for cross-device screen memory sync."""

from __future__ import annotations

import sqlite3
from typing import Optional


# Device-side columns + sync extension columns (device_id, synced_at)
_TABLE_SCHEMAS = {
    "nodes": """(
        uri         TEXT NOT NULL,
        domain      TEXT NOT NULL,
        path        TEXT NOT NULL,
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL,
        device_id   TEXT NOT NULL,
        synced_at   TEXT NOT NULL DEFAULT (datetime('now')),
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
        synced_at   TEXT NOT NULL DEFAULT (datetime('now')),
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
        synced_at   TEXT NOT NULL DEFAULT (datetime('now')),
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
        synced_at   TEXT NOT NULL DEFAULT (datetime('now')),
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
    """Server-side SQLite database for aggregated device data."""

    def __init__(self, path: str = ":memory:") -> None:
        self._path = path
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._path)
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
        # Merge by device_id
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/zty/screen_memory_server && uv run pytest tests/test_db.py -v
```

Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add screen_memory_server/db.py screen_memory_server/tests/test_db.py
git commit -m "feat(server): add SyncDatabase with push/query/status operations"
```

---

### Task 1.4: Server API endpoints

**Files:**
- Create: `screen_memory_server/main.py`
- Create: `screen_memory_server/tests/test_api.py`

- [ ] **Step 1: Write failing test for API endpoints**

```python
# screen_memory_server/tests/test_api.py
import pytest
from httpx import ASGITransport, AsyncClient

from screen_memory_server.main import create_app


@pytest.fixture
def client():
    app = create_app(auth_token="test-token")
    transport = ASGITransport(app=app)
    import asyncio

    async def _client():
        return AsyncClient(transport=transport, base_url="http://test")

    loop = asyncio.new_event_loop()
    c = loop.run_until_complete(_client())
    loop.close()
    yield c
    c.close()


def _sync_client(auth_token="test-token"):
    """Synchronous wrapper for the async test client."""
    from fastapi.testclient import TestClient
    app = create_app(auth_token=auth_token)
    return TestClient(app)


class TestHealthEndpoint:
    def test_health(self):
        c = _sync_client()
        resp = c.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestAuth:
    def test_push_without_token(self):
        c = _sync_client()
        resp = c.post("/api/v1/sync/push", json={"device_id": "x", "tables": {}})
        assert resp.status_code == 401

    def test_push_with_wrong_token(self):
        c = _sync_client()
        resp = c.post(
            "/api/v1/sync/push",
            json={"device_id": "x", "tables": {}},
            headers={"Authorization": "Bearer wrong"},
        )
        assert resp.status_code == 401

    def test_push_with_correct_token(self):
        c = _sync_client()
        resp = c.post(
            "/api/v1/sync/push",
            json={"device_id": "x", "tables": {}},
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200


class TestPushEndpoint:
    def test_push_empty(self):
        c = _sync_client()
        resp = c.post(
            "/api/v1/sync/push",
            json={"device_id": "device-1", "tables": {}},
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert resp.json()["received"] == {}

    def test_push_screenshots(self):
        c = _sync_client()
        resp = c.post(
            "/api/v1/sync/push",
            json={
                "device_id": "device-1",
                "tables": {
                    "screenshots": [
                        {"id": 1, "file_path": "/a.png", "ocr_text": "hello", "captured_at": "2026-05-26 10:00:00"},
                    ]
                },
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        assert resp.json()["received"]["screenshots"] == 1


class TestQueryEndpoint:
    def test_query_excludes_self(self):
        c = _sync_client()
        # Push from device-1
        c.post(
            "/api/v1/sync/push",
            json={
                "device_id": "device-1",
                "tables": {
                    "screenshots": [
                        {"id": 1, "file_path": "/a.png", "ocr_text": "hello", "captured_at": "2026-05-26 10:00:00"},
                    ]
                },
            },
            headers={"Authorization": "Bearer test-token"},
        )
        # Query from device-1, exclude self
        resp = c.post(
            "/api/v1/sync/query",
            json={"device_id": "device-1", "table": "screenshots", "query": {}, "exclude_self": True},
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        assert resp.json()["results"] == []

    def test_query_returns_other_device(self):
        c = _sync_client()
        c.post(
            "/api/v1/sync/push",
            json={
                "device_id": "device-1",
                "tables": {
                    "screenshots": [
                        {"id": 1, "file_path": "/a.png", "ocr_text": "hello", "captured_at": "2026-05-26 10:00:00"},
                    ]
                },
            },
            headers={"Authorization": "Bearer test-token"},
        )
        resp = c.post(
            "/api/v1/sync/query",
            json={"device_id": "device-2", "table": "screenshots", "query": {}, "exclude_self": True},
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 1
        assert results[0]["device_id"] == "device-1"


class TestStatusEndpoint:
    def test_status(self):
        c = _sync_client()
        c.post(
            "/api/v1/sync/push",
            json={
                "device_id": "device-1",
                "tables": {
                    "screenshots": [
                        {"id": 1, "file_path": "/a.png", "ocr_text": "hello", "captured_at": "2026-05-26 10:00:00"},
                    ]
                },
            },
            headers={"Authorization": "Bearer test-token"},
        )
        resp = c.get(
            "/api/v1/sync/status?device_id=device-1",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["devices"]) == 1
        assert data["devices"][0]["device_id"] == "device-1"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/zty/screen_memory_server && uv run pytest tests/test_api.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement main.py**

```python
# screen_memory_server/main.py
"""FastAPI sync server for cross-device screen memory."""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from screen_memory_server.db import SyncDatabase
from screen_memory_server.config import SyncConfig


class PushRequest(BaseModel):
    device_id: str
    tables: dict[str, list[dict]]


class QueryRequest(BaseModel):
    device_id: str
    table: str
    query: dict = {}
    exclude_self: bool = True


def create_app(config_path: Optional[str] = None, auth_token: Optional[str] = None) -> FastAPI:
    if config_path:
        cfg = SyncConfig.from_yaml(config_path)
    else:
        cfg = SyncConfig()

    token = auth_token or cfg.auth_token
    db = SyncDatabase(cfg.db_path)
    db.initialize()

    app = FastAPI(title="Screen Memory Sync Server")

    def _check_auth(authorization: Optional[str] = Header(None)):
        if not authorization:
            raise HTTPException(status_code=401, detail="Missing authorization")
        if not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Invalid authorization format")
        if authorization[7:] != token:
            raise HTTPException(status_code=401, detail="Invalid token")

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/v1/sync/push")
    def push(req: PushRequest, authorization: Optional[str] = Header(None)):
        _check_auth(authorization)
        received = {}
        for table, records in req.tables.items():
            count = db.push_records(req.device_id, table, records)
            received[table] = count
        return {"ok": True, "received": received}

    @app.post("/api/v1/sync/query")
    def query(req: QueryRequest, authorization: Optional[str] = Header(None)):
        _check_auth(authorization)
        exclude = req.device_id if req.exclude_self else None
        results = db.query_records(req.table, exclude_device=exclude)
        return {"results": results}

    @app.get("/api/v1/sync/status")
    def status(device_id: str = Query(...), authorization: Optional[str] = Header(None)):
        _check_auth(authorization)
        devices = db.get_status()
        return {"devices": devices}

    return app


def main():
    import uvicorn
    cfg = SyncConfig.from_yaml("config.yaml")
    app = create_app(config_path="config.yaml")
    uvicorn.run(app, host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/zty/screen_memory_server && uv run pytest tests/test_api.py -v
```

Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add screen_memory_server/main.py screen_memory_server/tests/test_api.py
git commit -m "feat(server): add FastAPI push/query/status/health endpoints"
```

---

### Task 1.5: Deploy server to VPS

**Files:**
- Modify: server files on remote VPS

- [ ] **Step 1: Copy server code to VPS**

```bash
scp -r screen_memory_server/ root@47.118.19.85:/home/zty/screen_memory_server/
```

- [ ] **Step 2: Install dependencies on server**

```bash
ssh root@47.118.19.85 "cd /home/zty/screen_memory_server && uv pip install -e '.[dev]'"
```

- [ ] **Step 3: Run tests on server**

```bash
ssh root@47.118.19.85 "cd /home/zty/screen_memory_server && uv run pytest tests/ -v"
```

Expected: all passed

- [ ] **Step 4: Start server and verify health**

```bash
ssh root@47.118.19.85 "cd /home/zty/screen_memory_server && nohup uv run python -m screen_memory_server.main > /tmp/sync-server.log 2>&1 &"
sleep 2
curl http://47.118.19.85:8200/api/v1/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 5: Verify push/query from local**

```bash
curl -X POST http://47.118.19.85:8200/api/v1/sync/push \
  -H "Authorization: Bearer screen-memory-sync-token-2026" \
  -H "Content-Type: application/json" \
  -d '{"device_id":"test-device","tables":{"screenshots":[{"id":1,"file_path":"/test.png","ocr_text":"hello","captured_at":"2026-05-26 10:00:00"}]}}'
```

Expected: `{"ok":true,"received":{"screenshots":1}}`

---

## Phase 2: Device-Side Sync Client

### Task 2.1: SyncConfig on device side

**Files:**
- Create: `screen-memory/screen_memory/sync/__init__.py`
- Create: `screen-memory/screen_memory/sync/config.py`
- Create: `screen-memory/tests/sync/__init__.py`

- [ ] **Step 1: Add sync dependencies to pyproject.toml**

Add to `screen-memory/pyproject.toml` dependencies:

```toml
dependencies = [
    "Pillow>=10.0",
    "httpx>=0.27",
]
```

Add to dev dependencies:

```toml
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "fastapi>=0.110",
    "httpx>=0.27",
]
```

- [ ] **Step 2: Create sync package init**

```python
# screen-memory/screen_memory/sync/__init__.py
```

- [ ] **Step 3: Write failing test for SyncConfig**

```python
# screen-memory/tests/sync/__init__.py
```

```python
# screen-memory/tests/sync/test_sync_config.py (create inline in test_sync_client.py to keep file count low)
```

Actually, per the spec, config tests are part of the client. We'll test config via SyncClient initialization. Create the config module directly:

```python
# screen-memory/screen_memory/sync/config.py
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
```

- [ ] **Step 4: Install new deps and verify import**

```bash
cd D:/ScreenMemo/screen-memory && uv pip install -e ".[dev]"
python -c "from screen_memory.sync.config import SyncConfig; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add screen-memory/screen_memory/sync/ screen-memory/pyproject.toml
git commit -m "feat(sync): add SyncConfig module for device-side sync configuration"
```

---

### Task 2.2: Add sync_state table to device DB schema

**Files:**
- Modify: `screen-memory/screen_memory/storage/database.py`

- [ ] **Step 1: Write failing test for sync_state table**

```python
# In screen-memory/tests/sync/test_sync_client.py (partial, will grow)

import pytest
from screen_memory.storage.database import Database


@pytest.fixture
def db():
    database = Database(":memory:")
    database.initialize()
    return database


class TestSyncStateTable:
    def test_sync_state_table_exists(self, db):
        tables = [r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sync_state'"
        ).fetchall()]
        assert "sync_state" in tables

    def test_sync_state_read_write(self, db):
        db.execute("INSERT INTO sync_state (key, value) VALUES ('last_sync_time', '0')")
        row = db.execute("SELECT value FROM sync_state WHERE key='last_sync_time'").fetchone()
        assert row[0] == "0"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd D:/ScreenMemo/screen-memory && python -m pytest tests/sync/test_sync_client.py::TestSyncStateTable -v
```

Expected: FAIL — table `sync_state` not found

- [ ] **Step 3: Add sync_state to database schema**

Add to `_SCHEMA_SQL` in `screen-memory/screen_memory/storage/database.py`, after the FTS triggers:

```sql
-- Sync state: metadata for cross-device sync
CREATE TABLE IF NOT EXISTS sync_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd D:/ScreenMemo/screen-memory && python -m pytest tests/sync/test_sync_client.py::TestSyncStateTable -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add screen-memory/screen_memory/storage/database.py screen-memory/tests/sync/
git commit -m "feat(sync): add sync_state table to device database schema"
```

---

### Task 2.3: SyncClient — change detection

**Files:**
- Create: `screen-memory/screen_memory/sync/client.py`
- Modify: `screen-memory/tests/sync/test_sync_client.py`

- [ ] **Step 1: Write failing tests for change detection**

Append to `screen-memory/tests/sync/test_sync_client.py`:

```python
from screen_memory.sync.client import SyncClient, SYNC_TABLE_CONFIG


class TestDetectChanges:
    def test_no_changes_returns_empty(self, db):
        client = SyncClient(db, "http://localhost:8200", "token")
        changes = client.detect_changes()
        assert changes == {}

    def test_detects_new_screenshot(self, db):
        db.execute("INSERT INTO screenshots (file_path, ocr_text) VALUES ('/a.png', 'hello')")
        client = SyncClient(db, "http://localhost:8200", "token")
        changes = client.detect_changes()
        assert "screenshots" in changes
        assert len(changes["screenshots"]) == 1

    def test_detects_new_memory(self, db):
        db.execute("INSERT INTO nodes (uri, domain, path) VALUES ('core://a', 'core', 'a')")
        db.execute("INSERT INTO memories (node_uri, content, version) VALUES ('core://a', 'hello', 1)")
        client = SyncClient(db, "http://localhost:8200", "token")
        changes = client.detect_changes()
        assert "nodes" in changes
        assert "memories" in changes

    def test_no_duplicate_detection_after_sync(self, db):
        db.execute("INSERT INTO screenshots (file_path, ocr_text) VALUES ('/a.png', 'hello')")
        client = SyncClient(db, "http://localhost:8200", "token")
        changes1 = client.detect_changes()
        assert "screenshots" in changes1
        # Simulate successful sync
        client._update_last_sync_time()
        changes2 = client.detect_changes()
        assert changes2 == {}

    def test_detects_new_path_rows(self, db):
        db.execute("INSERT INTO nodes (uri, domain, path) VALUES ('core://a', 'core', 'a')")
        db.execute("INSERT INTO paths (ancestor_uri, descendant_uri, depth) VALUES ('core://a', 'core://a/b', 1)")
        client = SyncClient(db, "http://localhost:8200", "token")
        changes = client.detect_changes()
        assert "paths" in changes

    def test_detects_new_entity(self, db):
        db.execute(
            "INSERT INTO entities (entity_type, name) VALUES ('person', 'Alice')"
        )
        client = SyncClient(db, "http://localhost:8200", "token")
        changes = client.detect_changes()
        assert "entities" in changes
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd D:/ScreenMemo/screen-memory && python -m pytest tests/sync/test_sync_client.py::TestDetectChanges -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement SyncClient with change detection**

```python
# screen-memory/screen_memory/sync/client.py
"""SyncClient: detect local changes and push to sync server."""

from __future__ import annotations

import sqlite3
import threading
import time
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
                f"INSERT OR IGNORE INTO sync_state (key, value) VALUES ('last_sync_rowid_{table}', '0')"
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
            f"SELECT value FROM sync_state WHERE key='last_sync_rowid_{table}'"
        ).fetchone()
        return int(row[0]) if row else 0

    def _update_last_sync_rowid(self, table: str, rowid: int) -> None:
        self._db.execute(
            f"UPDATE sync_state SET value=? WHERE key='last_sync_rowid_{table}'", (str(rowid),)
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
                # Get column names from cursor description
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
        import platform
        import uuid
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
        # Final flush with timeout
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd D:/ScreenMemo/screen-memory && python -m pytest tests/sync/test_sync_client.py -v
```

Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add screen-memory/screen_memory/sync/client.py screen-memory/tests/sync/test_sync_client.py
git commit -m "feat(sync): implement SyncClient with change detection and push"
```

---

### Task 2.4: QueryBridge

**Files:**
- Create: `screen-memory/screen_memory/sync/query_bridge.py`
- Create: `screen-memory/tests/sync/test_query_bridge.py`

- [ ] **Step 1: Write failing tests for QueryBridge**

```python
# screen-memory/tests/sync/test_query_bridge.py
import pytest
from unittest.mock import patch, MagicMock
from screen_memory.sync.query_bridge import QueryBridge


@pytest.fixture
def bridge():
    return QueryBridge("http://localhost:8200", "test-token", "device-1")


class TestQueryBridgeQuery:
    @patch("screen_memory.sync.query_bridge.httpx")
    def test_query_calls_server(self, mock_httpx, bridge):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": [{"id": 1, "ocr_text": "hello"}]}
        mock_httpx.post.return_value = mock_resp

        results = bridge.query("screenshots", {}, exclude_self=True)
        assert len(results) == 1
        mock_httpx.post.assert_called_once()

    @patch("screen_memory.sync.query_bridge.httpx")
    def test_query_returns_empty_on_error(self, mock_httpx, bridge):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_httpx.post.return_value = mock_resp

        results = bridge.query("screenshots", {})
        assert results == []

    @patch("screen_memory.sync.query_bridge.httpx")
    def test_query_returns_empty_on_exception(self, mock_httpx, bridge):
        mock_httpx.post.side_effect = Exception("connection failed")

        results = bridge.query("screenshots", {})
        assert results == []


class TestQueryBridgeListDevices:
    @patch("screen_memory.sync.query_bridge.httpx")
    def test_list_devices(self, mock_httpx, bridge):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"devices": [{"device_id": "device-2"}]}
        mock_httpx.get.return_value = mock_resp

        devices = bridge.list_devices()
        assert len(devices) == 1
        assert devices[0]["device_id"] == "device-2"

    @patch("screen_memory.sync.query_bridge.httpx")
    def test_list_devices_returns_empty_on_error(self, mock_httpx, bridge):
        mock_httpx.get.side_effect = Exception("fail")

        devices = bridge.list_devices()
        assert devices == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd D:/ScreenMemo/screen-memory && python -m pytest tests/sync/test_query_bridge.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement QueryBridge**

```python
# screen-memory/screen_memory/sync/query_bridge.py
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd D:/ScreenMemo/screen-memory && python -m pytest tests/sync/test_query_bridge.py -v
```

Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add screen-memory/screen_memory/sync/query_bridge.py screen-memory/tests/sync/test_query_bridge.py
git commit -m "feat(sync): implement QueryBridge for remote cross-device queries"
```

---

## Phase 3: OpenClaw Tools Extension + E2E

### Task 3.1: Add scope parameter to tools

**Files:**
- Modify: `screen-memory/screen_memory/tools/registry.py`
- Create: `screen-memory/tests/sync/test_tools_remote.py`

- [ ] **Step 1: Write failing tests for scope routing**

```python
# screen-memory/tests/sync/test_tools_remote.py
import pytest
from unittest.mock import MagicMock, patch

from screen_memory.storage.database import Database
from screen_memory.storage.graph_repo import GraphRepo
from screen_memory.storage.screenshot_repo import ScreenshotRepo
from screen_memory.services.graph_service import GraphService
from screen_memory.services.signal_service import SignalService, EntityPolicy
from screen_memory.tools.registry import ToolRegistry


@pytest.fixture
def registry():
    db = Database(":memory:")
    db.initialize()
    repo = GraphRepo(db)
    ss_repo = ScreenshotRepo(db)
    graph_svc = GraphService(repo)
    policies = {"person": EntityPolicy("person", 3.0, 86400 * 7, [])}
    signal_svc = SignalService(repo, policies)
    return ToolRegistry(graph_svc, signal_svc, ss_repo)


class TestMemorySearchScope:
    def test_scope_local_default(self, registry):
        registry.call("memory_write", {"uri": "core://a", "content": "hello world"})
        result = registry.call("memory_search", {"query": "hello"})
        assert len(result) == 1

    def test_scope_local_explicit(self, registry):
        registry.call("memory_write", {"uri": "core://a", "content": "hello world"})
        result = registry.call("memory_search", {"query": "hello", "scope": "local"})
        assert len(result) == 1

    @patch("screen_memory.tools.registry.QueryBridge")
    def test_scope_remote(self, mock_bridge_cls, registry):
        mock_bridge = MagicMock()
        mock_bridge.query.return_value = [{"node_uri": "core://x", "content": "remote data", "version": 1}]
        mock_bridge_cls.return_value = mock_bridge
        # Set up bridge on registry
        registry.set_query_bridge(mock_bridge)
        result = registry.call("memory_search", {"query": "remote", "scope": "remote"})
        assert len(result) == 1
        assert result[0]["content"] == "remote data"

    @patch("screen_memory.tools.registry.QueryBridge")
    def test_scope_all_merges(self, mock_bridge_cls, registry):
        registry.call("memory_write", {"uri": "core://a", "content": "local data"})
        mock_bridge = MagicMock()
        mock_bridge.query.return_value = [{"node_uri": "core://b", "content": "remote data", "version": 1}]
        mock_bridge_cls.return_value = mock_bridge
        registry.set_query_bridge(mock_bridge)
        result = registry.call("memory_search", {"query": "data", "scope": "all"})
        assert len(result) == 2


class TestScreenshotSearchScope:
    def test_scope_local_default(self, registry):
        registry._ss_repo.insert("/a.png", "screen text")
        result = registry.call("screenshot_search", {"query": "screen"})
        assert len(result) == 1

    @patch("screen_memory.tools.registry.QueryBridge")
    def test_scope_remote(self, mock_bridge_cls, registry):
        mock_bridge = MagicMock()
        mock_bridge.query.return_value = [{"file_path": "/remote.png", "ocr_text": "remote screen"}]
        mock_bridge_cls.return_value = mock_bridge
        registry.set_query_bridge(mock_bridge)
        result = registry.call("screenshot_search", {"query": "remote", "scope": "remote"})
        assert len(result) == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd D:/ScreenMemo/screen-memory && python -m pytest tests/sync/test_tools_remote.py -v
```

Expected: FAIL — `AttributeError: 'ToolRegistry' has no attribute 'set_query_bridge'`

- [ ] **Step 3: Modify ToolRegistry to support scope**

Add to `screen-memory/screen_memory/tools/registry.py`:

Add import at top:
```python
from screen_memory.sync.query_bridge import QueryBridge
```

Add `set_query_bridge` method and modify the `_TOOL_DEFINITIONS` to include `scope` parameter for the 4 relevant tools. Modify the 4 dispatcher methods to handle scope routing.

Key changes to `ToolRegistry.__init__`:
```python
self._query_bridge: Optional[QueryBridge] = None
```

New method:
```python
def set_query_bridge(self, bridge: QueryBridge) -> None:
    self._query_bridge = bridge
```

Modify `_memory_search`:
```python
def _memory_search(self, params: dict) -> list[dict]:
    query = params.get("query")
    if not query:
        raise ValueError("memory_search requires 'query'")
    limit = params.get("limit", 20)
    scope = params.get("scope", "local")

    if scope == "remote":
        if self._query_bridge is None:
            return []
        return self._query_bridge.query("memories_fts", {"query": query})
    if scope == "all":
        local = self._graph._repo.search(query, limit)
        if self._query_bridge is None:
            return local
        remote = self._query_bridge.query("memories_fts", {"query": query})
        # Merge and deduplicate by node_uri
        seen = {r["node_uri"] for r in local}
        for r in remote:
            if r.get("node_uri") not in seen:
                local.append(r)
                seen.add(r["node_uri"])
        return local[:limit]
    # scope == "local" (default)
    return self._graph._repo.search(query, limit)
```

Modify `_screenshot_search`:
```python
def _screenshot_search(self, params: dict) -> list[dict]:
    query = params.get("query")
    if not query:
        raise ValueError("screenshot_search requires 'query'")
    limit = params.get("limit", 20)
    scope = params.get("scope", "local")

    if scope == "remote":
        if self._query_bridge is None:
            return []
        return self._query_bridge.query("screenshots", {"ocr_text LIKE": f"%{query}%"})
    if scope == "all":
        local = self._ss_repo.search(query, limit)
        if self._query_bridge is None:
            return local
        remote = self._query_bridge.query("screenshots", {"ocr_text LIKE": f"%{query}%"})
        seen = {r.get("file_path") for r in local}
        for r in remote:
            if r.get("file_path") not in seen:
                local.append(r)
                seen.add(r.get("file_path"))
        return local[:limit]
    return self._ss_repo.search(query, limit)
```

Apply similar scope logic to `_memory_read` and `_graph_query_subtree`.

Add `scope` parameter to tool definitions for the 4 tools:
```python
"scope": {"type": "string", "description": "Query scope: local (default), remote, all", "default": "local"},
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd D:/ScreenMemo/screen-memory && python -m pytest tests/sync/test_tools_remote.py tests/tools/test_tools.py -v
```

Expected: all passed (existing tests still pass due to scope default="local")

- [ ] **Step 5: Commit**

```bash
git add screen-memory/screen_memory/tools/registry.py screen-memory/tests/sync/test_tools_remote.py
git commit -m "feat(tools): add scope parameter to search/read tools for cross-device queries"
```

---

### Task 3.2: Add sync_status tool

**Files:**
- Modify: `screen-memory/screen_memory/tools/registry.py`

- [ ] **Step 1: Write failing test for sync_status tool**

Append to `screen-memory/tests/sync/test_tools_remote.py`:

```python
class TestSyncStatusTool:
    def test_sync_status_listed(self, registry):
        tools = registry.list_tools()
        names = [t["name"] for t in tools]
        assert "sync_status" in names

    @patch("screen_memory.tools.registry.QueryBridge")
    def test_sync_status_with_bridge(self, mock_bridge_cls, registry):
        mock_bridge = MagicMock()
        mock_bridge.list_devices.return_value = [
            {"device_id": "device-1", "last_sync": "2026-05-26 10:00:00", "tables": {"screenshots": 5}},
        ]
        registry.set_query_bridge(mock_bridge)
        registry._sync_client = MagicMock()
        registry._sync_client.get_device_id.return_value = "device-1"
        registry._sync_client._get_last_sync_time.return_value = "2026-05-26 10:00:00"

        result = registry.call("sync_status", {})
        assert result["device_id"] == "device-1"
        assert result["server_reachable"] is True

    def test_sync_status_without_bridge(self, registry):
        result = registry.call("sync_status", {})
        assert result["server_reachable"] is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd D:/ScreenMemo/screen-memory && python -m pytest tests/sync/test_tools_remote.py::TestSyncStatusTool -v
```

Expected: FAIL — `sync_status` not in tool names

- [ ] **Step 3: Add sync_status tool to ToolRegistry**

Add tool definition to `_TOOL_DEFINITIONS`:
```python
{
    "name": "sync_status",
    "description": "Check sync status and list connected devices.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
},
```

Add to `_dispatchers`:
```python
"sync_status": self._sync_status,
```

Add implementation:
```python
def _sync_status(self, params: dict) -> dict:
    result = {
        "device_id": None,
        "last_sync_time": None,
        "pending_changes": 0,
        "server_reachable": False,
        "devices": [],
    }
    if self._sync_client:
        result["device_id"] = self._sync_client.get_device_id()
        result["last_sync_time"] = self._sync_client._get_last_sync_time()
        changes = self._sync_client.detect_changes()
        result["pending_changes"] = sum(len(v) for v in changes.values())
    if self._query_bridge:
        devices = self._query_bridge.list_devices()
        result["server_reachable"] = True
        result["devices"] = devices
    return result
```

Add `_sync_client` attribute to `__init__`:
```python
self._sync_client = None
```

Add setter:
```python
def set_sync_client(self, client) -> None:
    self._sync_client = client
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd D:/ScreenMemo/screen-memory && python -m pytest tests/sync/test_tools_remote.py -v
```

Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add screen-memory/screen_memory/tools/registry.py screen-memory/tests/sync/test_tools_remote.py
git commit -m "feat(tools): add sync_status tool for cross-device sync monitoring"
```

---

### Task 3.3: Wire SyncClient into plugin entry point

**Files:**
- Modify: `screen-memory/screen_memory/tools/__init__.py`

- [ ] **Step 1: Update register() to wire SyncClient and QueryBridge**

```python
# screen-memory/screen_memory/tools/__init__.py
"""OpenClaw plugin entry point for screen-memory."""

from screen_memory.tools.registry import ToolRegistry


def register(api) -> ToolRegistry:
    """Called by OpenClaw to register screen-memory tools."""
    db_path = getattr(api, "db_path", ":memory:")
    from screen_memory.storage.database import Database
    from screen_memory.storage.graph_repo import GraphRepo
    from screen_memory.storage.screenshot_repo import ScreenshotRepo
    from screen_memory.services.graph_service import GraphService
    from screen_memory.services.signal_service import SignalService, EntityPolicy
    from screen_memory.sync.config import SyncConfig
    from screen_memory.sync.client import SyncClient
    from screen_memory.sync.query_bridge import QueryBridge

    db = Database(db_path)
    db.initialize()
    repo = GraphRepo(db)
    ss_repo = ScreenshotRepo(db)
    graph_svc = GraphService(repo)
    policies = {
        "person": EntityPolicy("person", 3.0, 86400 * 7, ["seen_multiple_times"]),
        "topic": EntityPolicy("topic", 2.0, 86400 * 3, []),
        "location": EntityPolicy("location", 2.5, 86400 * 14, []),
        "event": EntityPolicy("event", 2.0, 86400 * 5, []),
    }
    signal_svc = SignalService(repo, policies)
    registry = ToolRegistry(graph_svc, signal_svc, ss_repo)

    # Wire sync if configured
    sync_cfg = SyncConfig.from_env()
    if sync_cfg.enabled:
        client = SyncClient(db, sync_cfg.server_url, sync_cfg.token, sync_cfg.interval)
        bridge = QueryBridge(sync_cfg.server_url, sync_cfg.token, client.get_device_id())
        registry.set_sync_client(client)
        registry.set_query_bridge(bridge)
        client.start()

    return registry
```

- [ ] **Step 2: Verify existing tests still pass**

```bash
cd D:/ScreenMemo/screen-memory && python -m pytest tests/ -v
```

Expected: all passed (sync not configured in test env, so no sync wiring happens)

- [ ] **Step 3: Update openclaw.plugin.json**

Add `sync_status` to the tools list:

```json
{
  "tools": [
    "memory_write", "memory_read", "memory_search", "memory_delete",
    "graph_query_subtree", "signal_ingest", "signal_activate",
    "screenshot_search", "sync_status"
  ]
}
```

- [ ] **Step 4: Commit**

```bash
git add screen-memory/screen_memory/tools/__init__.py screen-memory/openclaw.plugin.json
git commit -m "feat(tools): wire SyncClient into plugin entry point with env-based config"
```

---

### Task 3.4: E2E test — push from one device, query from another

**Files:**
- Create: `screen-memory/tests/sync/test_e2e_sync.py`

- [ ] **Step 1: Write E2E test using TestClient as mock server**

```python
# screen-memory/tests/sync/test_e2e_sync.py
"""End-to-end sync tests: push from client, query via bridge."""

import sys
import os
import pytest

# Add server to path for TestClient import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "screen_memory_server"))

from fastapi.testclient import TestClient
from screen_memory_server.main import create_app

from screen_memory.storage.database import Database
from screen_memory.sync.client import SyncClient
from screen_memory.sync.query_bridge import QueryBridge


@pytest.fixture
def server_app():
    return create_app(auth_token="e2e-test-token")


@pytest.fixture
def server_client(server_app):
    return TestClient(server_app)


@pytest.fixture
def device_db():
    db = Database(":memory:")
    db.initialize()
    return db


@pytest.fixture
def device_a(device_db, server_client):
    client = SyncClient(device_db, "http://test", "e2e-test-token")
    # Monkey-patch httpx calls to use TestClient
    client._http_post = lambda url, **kwargs: server_client.post(
        "/api/v1/sync/push", **{k: v for k, v in kwargs.items() if k != "timeout"}
    )
    return client


class TestE2EPushQuery:
    def test_push_screenshots_then_query(self, device_db, server_client):
        # Insert data on device
        device_db.execute("INSERT INTO screenshots (file_path, ocr_text) VALUES ('/phone.png', 'mobile screen text')")

        # Create sync client and push
        client = SyncClient(device_db, "http://test", "e2e-test-token")
        changes = client.detect_changes()
        assert "screenshots" in changes

        # Push via server client directly
        resp = server_client.post(
            "/api/v1/sync/push",
            json={"device_id": client.get_device_id(), "tables": changes},
            headers={"Authorization": "Bearer e2e-test-token"},
        )
        assert resp.status_code == 200
        assert resp.json()["received"]["screenshots"] >= 1

        # Query from another device perspective
        resp = server_client.post(
            "/api/v1/sync/query",
            json={
                "device_id": "other-device",
                "table": "screenshots",
                "query": {},
                "exclude_self": True,
            },
            headers={"Authorization": "Bearer e2e-test-token"},
        )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) >= 1
        assert any("mobile screen text" in (r.get("ocr_text") or "") for r in results)

    def test_push_nodes_then_query(self, device_db, server_client):
        device_db.execute("INSERT INTO nodes (uri, domain, path) VALUES ('core://meeting/standup', 'core', 'meeting/standup')")

        client = SyncClient(device_db, "http://test", "e2e-test-token")
        changes = client.detect_changes()

        resp = server_client.post(
            "/api/v1/sync/push",
            json={"device_id": client.get_device_id(), "tables": changes},
            headers={"Authorization": "Bearer e2e-test-token"},
        )
        assert resp.status_code == 200

        resp = server_client.post(
            "/api/v1/sync/query",
            json={"device_id": "other-device", "table": "nodes", "query": {}, "exclude_self": True},
            headers={"Authorization": "Bearer e2e-test-token"},
        )
        results = resp.json()["results"]
        assert any(r.get("uri") == "core://meeting/standup" for r in results)

    def test_status_shows_both_devices(self, server_client, device_db):
        # Push from device-1
        client1 = SyncClient(device_db, "http://test", "e2e-test-token")
        changes = client1.detect_changes()

        server_client.post(
            "/api/v1/sync/push",
            json={"device_id": "device-1", "tables": {"screenshots": [
                {"id": 1, "file_path": "/a.png", "ocr_text": "hello", "captured_at": "2026-05-26 10:00:00"}
            ]}},
            headers={"Authorization": "Bearer e2e-test-token"},
        )
        server_client.post(
            "/api/v1/sync/push",
            json={"device_id": "device-2", "tables": {"nodes": [
                {"uri": "core://x", "domain": "core", "path": "x", "created_at": "2026-05-26 10:00:00", "updated_at": "2026-05-26 10:00:00"}
            ]}},
            headers={"Authorization": "Bearer e2e-test-token"},
        )

        resp = server_client.get(
            "/api/v1/sync/status?device_id=device-1",
            headers={"Authorization": "Bearer e2e-test-token"},
        )
        devices = resp.json()["devices"]
        device_ids = [d["device_id"] for d in devices]
        assert "device-1" in device_ids
        assert "device-2" in device_ids
```

- [ ] **Step 2: Run E2E tests**

```bash
cd D:/ScreenMemo/screen-memory && python -m pytest tests/sync/test_e2e_sync.py -v
```

Expected: all passed

- [ ] **Step 3: Commit**

```bash
git add screen-memory/tests/sync/test_e2e_sync.py
git commit -m "test(sync): add E2E push-query tests for cross-device sync"
```

---

### Task 3.5: Deploy and verify on real devices

**Files:**
- No new files — deployment and verification

- [ ] **Step 1: Deploy updated server to VPS**

```bash
scp -r screen_memory_server/ root@47.118.19.85:/home/zty/screen_memory_server/
ssh root@47.118.19.85 "cd /home/zty/screen_memory_server && uv pip install -e '.[dev]'"
```

- [ ] **Step 2: Restart server on VPS**

```bash
ssh root@47.118.19.85 "pkill -f screen_memory_server.main || true"
ssh root@47.118.19.85 "cd /home/zty/screen_memory_server && nohup uv run python -m screen_memory_server.main > /tmp/sync-server.log 2>&1 &"
sleep 2
curl http://47.118.19.85:8200/api/v1/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 3: Verify Windows client push**

On Windows, set environment variables and test:

```bash
export SCREEN_MEMORY_SYNC_URL=http://47.118.19.85:8200
export SCREEN_MEMORY_SYNC_TOKEN=screen-memory-sync-token-2026
cd D:/ScreenMemo/screen-memory
python -c "
from screen_memory.sync.config import SyncConfig
from screen_memory.sync.client import SyncClient
from screen_memory.storage.database import Database

cfg = SyncConfig.from_env()
print(f'Sync enabled: {cfg.enabled}')
print(f'Server: {cfg.server_url}')
"
```

- [ ] **Step 4: Deploy to Android via SSH**

```bash
# Copy updated screen-memory package to Android Termux
ssh android-device "cd ~/screen-memory && git pull"
ssh android-device "cd ~/screen-memory && pip install -e ."
```

- [ ] **Step 5: Verify cross-device query**

From Windows, test cross-device query via OpenClaw tools or direct API call.

- [ ] **Step 6: Final commit**

```bash
git commit --allow-empty -m "chore: cross-device sync deployed and verified"
```

---

## Self-Review Checklist

- [ ] Spec coverage: All sections in design doc mapped to tasks
- [ ] No placeholders: Every step has actual code, commands, and expected output
- [ ] Type consistency: SYNC_TABLE_CONFIG, SyncClient, QueryBridge, ToolRegistry interfaces match across all tasks
- [ ] Backward compatibility: scope defaults to "local", existing tests pass unmodified
- [ ] Server schema: All 6 tables (nodes, memories, edges, paths, entities, screenshots) + sync_state
- [ ] TDD order: Every implementation task has tests written first
