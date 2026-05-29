# Android Screen Memory MCP Server — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a single-file Python MCP server on Android with full feature parity to the Windows screen-memory plugin: URI Graph, signal tracking, continuous capture, and screenshot search.

**Architecture:** Single file `screen-memory-android/mcp-server/screen_memory_server.py` (~800 lines) containing all modules inline. Pure stdlib (no pip dependencies). Tests in `screen-memory-android/mcp-server/tests/` use `:memory:` SQLite and mocked HTTP.

**Tech Stack:** Python 3.13 stdlib (sqlite3, threading, json, urllib, dataclasses, re)

---

## File Structure

```
screen-memory-android/mcp-server/
├── screen_memory_server.py       # Single-file MCP server, all modules inline
└── tests/
    ├── __init__.py
    ├── test_uri.py               # NocturneUri tests
    ├── test_storage.py           # Database + GraphRepo + ScreenshotRepo tests
    ├── test_services.py          # GraphService + SignalService tests
    ├── test_capture.py           # AndroidCapture + timed capture tests
    └── test_mcp.py               # MCP protocol + tool dispatch tests
```

---

### Task 1: Project skeleton + NocturneUri

**Files:**
- Create: `screen-memory-android/mcp-server/screen_memory_server.py`
- Create: `screen-memory-android/mcp-server/tests/__init__.py`
- Create: `screen-memory-android/mcp-server/tests/test_uri.py`

- [ ] **Step 1: Create test file with NocturneUri tests**

```python
# tests/test_uri.py
"""Tests for NocturneUri — copied from Windows models/uri.py logic."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from screen_memory_server import NocturneUri
import pytest


class TestNocturneUriParse:
    def test_simple(self):
        uri = NocturneUri.parse("core://my/topic")
        assert uri.domain == "core"
        assert uri.path == "my/topic"

    def test_root_uri(self):
        uri = NocturneUri.parse("core://")
        assert uri.domain == "core"
        assert uri.path == ""

    def test_trailing_slash_stripped(self):
        uri = NocturneUri.parse("core://my/topic/")
        assert uri.path == "my/topic"

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            NocturneUri.parse("")

    def test_whitespace_raises(self):
        with pytest.raises(ValueError):
            NocturneUri.parse("   ")

    def test_no_scheme_raises(self):
        with pytest.raises(ValueError):
            NocturneUri.parse("no-scheme")


class TestNocturneUriParent:
    def test_parent(self):
        uri = NocturneUri.parse("core://a/b/c")
        p = uri.parent()
        assert p == NocturneUri(domain="core", path="a/b")

    def test_parent_of_depth1(self):
        uri = NocturneUri.parse("core://a")
        p = uri.parent()
        assert p == NocturneUri(domain="core", path="")

    def test_root_has_no_parent(self):
        uri = NocturneUri.parse("core://")
        assert uri.parent() is None


class TestNocturneUriHierarchy:
    def test_leaf(self):
        uri = NocturneUri.parse("core://a/b/c")
        assert uri.leaf == "c"

    def test_leaf_root(self):
        uri = NocturneUri.parse("core://")
        assert uri.leaf == ""

    def test_is_child_of(self):
        child = NocturneUri.parse("core://a/b")
        parent = NocturneUri.parse("core://a")
        assert child.is_child_of(parent)

    def test_is_not_child_of_self(self):
        uri = NocturneUri.parse("core://a")
        assert not uri.is_child_of(uri)

    def test_is_child_of_domain_root(self):
        child = NocturneUri.parse("core://a/b")
        root = NocturneUri.parse("core://")
        assert child.is_child_of(root)

    def test_different_domain_not_child(self):
        a = NocturneUri.parse("core://a")
        b = NocturneUri.parse("other://a")
        assert not a.is_child_of(b)

    def test_str_roundtrip(self):
        raw = "core://my/topic"
        assert str(NocturneUri.parse(raw)) == raw
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd screen-memory-android/mcp-server && python -m pytest tests/test_uri.py -v`
Expected: FAIL — `cannot import 'NocturneUri' from 'screen_memory_server'`

- [ ] **Step 3: Write NocturneUri implementation in screen_memory_server.py**

```python
#!/usr/bin/env python3
"""Screen Memory MCP Server — full feature parity with Windows plugin.

Single-file implementation: URI Graph, signals, capture, MCP protocol.
Pure Python stdlib. No external dependencies.
"""
from __future__ import annotations

import base64
import json
import math
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.request
import urllib.error
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


# ─── NocturneUri ──────────────────────────────────────────────────────────

_PATTERN = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*)://(.*)$")


@dataclass(frozen=True)
class NocturneUri:
    """URI scheme: <domain>://<path> for the memory graph."""
    domain: str
    path: str

    @classmethod
    def parse(cls, raw: str) -> NocturneUri:
        if not raw or not raw.strip():
            raise ValueError("invalid: empty or whitespace")
        m = _PATTERN.match(raw)
        if m is None:
            raise ValueError(f"invalid: '{raw}' does not match domain://path")
        domain = m.group(1)
        path = m.group(2).rstrip("/") or ""
        return cls(domain=domain, path=path)

    @classmethod
    def make(cls, domain: str, path: str) -> NocturneUri:
        return cls(domain=domain, path=path.rstrip("/") or "")

    def parent(self) -> Optional[NocturneUri]:
        if not self.path:
            return None
        segments = self.path.rsplit("/", 1)
        return NocturneUri(domain=self.domain, path=segments[0] if len(segments) > 1 else "")

    @property
    def leaf(self) -> str:
        if not self.path:
            return ""
        return self.path.rsplit("/", 1)[-1]

    def is_child_of(self, parent: NocturneUri) -> bool:
        if self.domain != parent.domain:
            return False
        if self == parent:
            return False
        if not parent.path:
            return True
        return self.path.startswith(parent.path + "/")

    def __str__(self) -> str:
        return f"{self.domain}://{self.path}"

    def __repr__(self) -> str:
        return f"NocturneUri({self.domain!r}, {self.path!r})"
```

Also create `tests/__init__.py` as empty file.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd screen-memory-android/mcp-server && python -m pytest tests/test_uri.py -v`
Expected: PASS — all tests green

- [ ] **Step 5: Commit**

```bash
git add screen-memory-android/mcp-server/screen_memory_server.py screen-memory-android/mcp-server/tests/__init__.py screen-memory-android/mcp-server/tests/test_uri.py
git commit -m "feat(mcp-server): add NocturneUri with tests"
```

---

### Task 2: Database + GraphRepo

**Files:**
- Modify: `screen-memory-android/mcp-server/screen_memory_server.py` (add Database, GraphRepo classes)
- Create: `screen-memory-android/mcp-server/tests/test_storage.py`

- [ ] **Step 1: Write test file**

```python
# tests/test_storage.py
"""Tests for Database, GraphRepo, ScreenshotRepo."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from screen_memory_server import Database, GraphRepo, NocturneUri
import pytest


@pytest.fixture
def db():
    d = Database(":memory:")
    d.initialize()
    yield d
    d.close()


@pytest.fixture
def repo(db):
    return GraphRepo(db)


class TestDatabase:
    def test_initialize_idempotent(self, db):
        db.initialize()  # second call should not raise
        assert db.conn is not None


class TestGraphRepoNodes:
    def test_create_node(self, repo):
        uri = NocturneUri.parse("core://a/b")
        result = repo.create_node(uri)
        assert result == uri
        node = repo.get_node(uri)
        assert node is not None
        assert node["uri"] == "core://a/b"
        assert node["domain"] == "core"

    def test_create_node_idempotent(self, repo):
        uri = NocturneUri.parse("core://x")
        repo.create_node(uri)
        repo.create_node(uri)
        assert repo.get_node(uri) is not None

    def test_list_nodes(self, repo):
        repo.create_node(NocturneUri.parse("core://a"))
        repo.create_node(NocturneUri.parse("core://b"))
        repo.create_node(NocturneUri.parse("other://c"))
        assert len(repo.list_nodes()) == 3
        assert len(repo.list_nodes(domain="core")) == 2

    def test_delete_node(self, repo):
        uri = NocturneUri.parse("core://del")
        repo.create_node(uri)
        repo.delete_node(uri)
        assert repo.get_node(uri) is None


class TestGraphRepoMemories:
    def test_write_memory(self, repo):
        uri = NocturneUri.parse("core://topic")
        result = repo.write_memory(uri, "hello")
        assert result["version"] == 1
        assert result["content"] == "hello"

    def test_write_memory_auto_creates_node(self, repo):
        uri = NocturneUri.parse("core://auto")
        repo.write_memory(uri, "content")
        assert repo.get_node(uri) is not None

    def test_read_latest(self, repo):
        uri = NocturneUri.parse("core://v")
        repo.write_memory(uri, "v1")
        repo.write_memory(uri, "v2")
        mem = repo.read_memory(uri)
        assert mem["version"] == 2
        assert mem["content"] == "v2"

    def test_read_nonexistent(self, repo):
        assert repo.read_memory(NocturneUri.parse("core://none")) is None

    def test_memory_history(self, repo):
        uri = NocturneUri.parse("core://h")
        repo.write_memory(uri, "v1")
        repo.write_memory(uri, "v2")
        history = repo.memory_history(uri)
        assert len(history) == 2
        assert history[0]["version"] == 2  # newest first

    def test_deprecate_memory(self, repo):
        uri = NocturneUri.parse("core://dep")
        repo.write_memory(uri, "v1")
        repo.write_memory(uri, "v2")
        repo.deprecate_memory(uri, 2)
        mem = repo.read_memory(uri)
        assert mem["version"] == 1


class TestGraphRepoEdges:
    def test_create_edge(self, repo):
        a = NocturneUri.parse("core://a")
        b = NocturneUri.parse("core://b")
        repo.create_node(a)
        repo.create_node(b)
        result = repo.create_edge(a, b, "parent")
        assert result["relation"] == "parent"

    def test_get_neighbors(self, repo):
        a = NocturneUri.parse("core://a")
        b = NocturneUri.parse("core://b")
        repo.create_node(a)
        repo.create_node(b)
        repo.create_edge(a, b, "parent")
        neighbors = repo.get_neighbors(a)
        assert len(neighbors) == 1
        assert neighbors[0]["target_uri"] == "core://b"


class TestGraphRepoFTS:
    def test_search(self, repo):
        repo.write_memory(NocturneUri.parse("core://python"), "Python programming language")
        repo.write_memory(NocturneUri.parse("core://rust"), "Rust systems language")
        results = repo.search("python")
        assert len(results) == 1
        assert "Python" in results[0]["content"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd screen-memory-android/mcp-server && python -m pytest tests/test_storage.py -v`
Expected: FAIL — `ImportError: cannot import name 'Database'`

- [ ] **Step 3: Add Database and GraphRepo to screen_memory_server.py**

Append after the `NocturneUri` class:

```python
# ─── Database ─────────────────────────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS nodes (
    uri         TEXT PRIMARY KEY,
    domain      TEXT NOT NULL,
    path        TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS memories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    node_uri    TEXT NOT NULL REFERENCES nodes(uri) ON DELETE CASCADE,
    content     TEXT NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    status      TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'deprecated', 'deleted')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (node_uri, version)
);
CREATE TABLE IF NOT EXISTS edges (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_uri  TEXT NOT NULL REFERENCES nodes(uri) ON DELETE CASCADE,
    target_uri  TEXT NOT NULL REFERENCES nodes(uri) ON DELETE CASCADE,
    relation    TEXT NOT NULL DEFAULT 'related',
    weight      REAL NOT NULL DEFAULT 1.0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (source_uri, target_uri, relation),
    CHECK (source_uri != target_uri)
);
CREATE TABLE IF NOT EXISTS paths (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ancestor_uri TEXT NOT NULL REFERENCES nodes(uri) ON DELETE CASCADE,
    descendant_uri TEXT NOT NULL REFERENCES nodes(uri) ON DELETE CASCADE,
    depth       INTEGER NOT NULL DEFAULT 1,
    UNIQUE (ancestor_uri, descendant_uri),
    CHECK (ancestor_uri != descendant_uri)
);
CREATE TABLE IF NOT EXISTS entities (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type     TEXT NOT NULL,
    name            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'candidate'
                    CHECK (status IN ('candidate', 'active', 'archived')),
    score           REAL NOT NULL DEFAULT 0.0,
    signal_count    INTEGER NOT NULL DEFAULT 0,
    evidence        TEXT NOT NULL DEFAULT '[]',
    first_seen_at   TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at    TEXT NOT NULL DEFAULT (datetime('now')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (entity_type, name)
);
CREATE TABLE IF NOT EXISTS screenshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path   TEXT NOT NULL,
    ocr_text    TEXT,
    captured_at TEXT NOT NULL DEFAULT (datetime('now')),
    uri         TEXT REFERENCES nodes(uri) ON DELETE SET NULL,
    UNIQUE (file_path)
);
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
    USING fts5(content, content='memories', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS memories_fts_insert
    AFTER INSERT ON memories BEGIN
        INSERT INTO memories_fts (rowid, content) VALUES (new.id, new.content);
    END;
CREATE TRIGGER IF NOT EXISTS memories_fts_delete
    AFTER DELETE ON memories BEGIN
        INSERT INTO memories_fts (memories_fts, rowid, content)
        VALUES ('delete', old.id, old.content);
    END;
CREATE TRIGGER IF NOT EXISTS memories_fts_update
    AFTER UPDATE ON memories BEGIN
        INSERT INTO memories_fts (memories_fts, rowid, content)
        VALUES ('delete', old.id, old.content);
        INSERT INTO memories_fts (rowid, content) VALUES (new.id, new.content);
    END;
"""


class Database:
    def __init__(self, path: str = ":memory:") -> None:
        self._path = path
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._path)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def initialize(self) -> None:
        self.conn.executescript(_SCHEMA_SQL)
        self.conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        return cur

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


# ─── GraphRepo ────────────────────────────────────────────────────────────

class GraphRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def create_node(self, uri: NocturneUri) -> NocturneUri:
        existing = self.get_node(uri)
        if existing is not None:
            return uri
        self._db.execute(
            "INSERT INTO nodes (uri, domain, path) VALUES (?, ?, ?)",
            (str(uri), uri.domain, uri.path),
        )
        return uri

    def get_node(self, uri: NocturneUri) -> Optional[dict]:
        row = self._db.execute(
            "SELECT uri, domain, path, created_at, updated_at FROM nodes WHERE uri=?",
            (str(uri),),
        ).fetchone()
        if row is None:
            return None
        keys = ["uri", "domain", "path", "created_at", "updated_at"]
        return dict(zip(keys, row))

    def list_nodes(self, domain: Optional[str] = None) -> list[dict]:
        if domain:
            rows = self._db.execute(
                "SELECT uri, domain, path FROM nodes WHERE domain=?", (domain,)
            ).fetchall()
        else:
            rows = self._db.execute("SELECT uri, domain, path FROM nodes").fetchall()
        keys = ["uri", "domain", "path"]
        return [dict(zip(keys, r)) for r in rows]

    def delete_node(self, uri: NocturneUri) -> None:
        self._db.execute("DELETE FROM nodes WHERE uri=?", (str(uri),))

    def write_memory(self, uri: NocturneUri, content: str) -> dict:
        self.create_node(uri)
        row = self._db.execute(
            "SELECT MAX(version) FROM memories WHERE node_uri=?", (str(uri),)
        ).fetchone()
        version = (row[0] or 0) + 1
        self._db.execute(
            "INSERT INTO memories (node_uri, content, version, status) VALUES (?, ?, ?, 'active')",
            (str(uri), content, version),
        )
        return {"node_uri": str(uri), "content": content, "version": version, "status": "active"}

    def read_memory(self, uri: NocturneUri) -> Optional[dict]:
        row = self._db.execute(
            "SELECT id, node_uri, content, version, status, created_at "
            "FROM memories WHERE node_uri=? AND status='active' "
            "ORDER BY version DESC LIMIT 1",
            (str(uri),),
        ).fetchone()
        if row is None:
            return None
        keys = ["id", "node_uri", "content", "version", "status", "created_at"]
        return dict(zip(keys, row))

    def memory_history(self, uri: NocturneUri) -> list[dict]:
        rows = self._db.execute(
            "SELECT id, node_uri, content, version, status, created_at "
            "FROM memories WHERE node_uri=? ORDER BY version DESC",
            (str(uri),),
        ).fetchall()
        keys = ["id", "node_uri", "content", "version", "status", "created_at"]
        return [dict(zip(keys, r)) for r in rows]

    def deprecate_memory(self, uri: NocturneUri, version: int) -> None:
        self._db.execute(
            "UPDATE memories SET status='deprecated' WHERE node_uri=? AND version=?",
            (str(uri), version),
        )

    def create_edge(self, source: NocturneUri, target: NocturneUri,
                    relation: str = "related", weight: float = 1.0) -> dict:
        existing = self._db.execute(
            "SELECT id, source_uri, target_uri, relation FROM edges "
            "WHERE source_uri=? AND target_uri=? AND relation=?",
            (str(source), str(target), relation),
        ).fetchone()
        if existing:
            keys = ["id", "source_uri", "target_uri", "relation"]
            return dict(zip(keys, existing))
        self._db.execute(
            "INSERT INTO edges (source_uri, target_uri, relation, weight) VALUES (?, ?, ?, ?)",
            (str(source), str(target), relation, weight),
        )
        return {"source_uri": str(source), "target_uri": str(target), "relation": relation}

    def get_neighbors(self, uri: NocturneUri, relation: Optional[str] = None) -> list[dict]:
        if relation:
            rows = self._db.execute(
                "SELECT target_uri, relation, weight FROM edges WHERE source_uri=? AND relation=?",
                (str(uri), relation),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT target_uri, relation, weight FROM edges WHERE source_uri=?",
                (str(uri),),
            ).fetchall()
        keys = ["target_uri", "relation", "weight"]
        return [dict(zip(keys, r)) for r in rows]

    def delete_edge(self, source: NocturneUri, target: NocturneUri, relation: str) -> None:
        self._db.execute(
            "DELETE FROM edges WHERE source_uri=? AND target_uri=? AND relation=?",
            (str(source), str(target), relation),
        )

    def search(self, query: str, limit: int = 20) -> list[dict]:
        rows = self._db.execute(
            "SELECT m.node_uri, m.content, m.version "
            "FROM memories_fts f JOIN memories m ON m.id = f.rowid "
            "WHERE memories_fts MATCH ? AND m.status='active' "
            "ORDER BY rank LIMIT ?",
            (query, limit),
        ).fetchall()
        keys = ["node_uri", "content", "version"]
        return [dict(zip(keys, r)) for r in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd screen-memory-android/mcp-server && python -m pytest tests/test_storage.py tests/test_uri.py -v`
Expected: PASS — all tests green

- [ ] **Step 5: Commit**

```bash
git add screen-memory-android/mcp-server/screen_memory_server.py screen-memory-android/mcp-server/tests/test_storage.py
git commit -m "feat(mcp-server): add Database + GraphRepo with tests"
```

---

### Task 3: ScreenshotRepo

**Files:**
- Modify: `screen-memory-android/mcp-server/screen_memory_server.py` (add ScreenshotRepo class)
- Modify: `screen-memory-android/mcp-server/tests/test_storage.py` (add ScreenshotRepo tests)

- [ ] **Step 1: Add ScreenshotRepo tests to test_storage.py**

Append to `test_storage.py`:

```python
from screen_memory_server import ScreenshotRepo


@pytest.fixture
def ss_repo(db):
    return ScreenshotRepo(db)


class TestScreenshotRepo:
    def test_insert(self, ss_repo):
        result = ss_repo.insert("/tmp/test.jpg", "hello world")
        assert result["file_path"] == "/tmp/test.jpg"
        assert result["ocr_text"] == "hello world"
        assert result["id"] is not None

    def test_get_by_id(self, ss_repo):
        inserted = ss_repo.insert("/tmp/test.jpg", "text")
        fetched = ss_repo.get_by_id(inserted["id"])
        assert fetched["ocr_text"] == "text"

    def test_list_all(self, ss_repo):
        ss_repo.insert("/tmp/a.jpg", "alpha")
        ss_repo.insert("/tmp/b.jpg", "beta")
        all_ss = ss_repo.list_all()
        assert len(all_ss) == 2

    def test_search(self, ss_repo):
        ss_repo.insert("/tmp/a.jpg", "Python programming")
        ss_repo.insert("/tmp/b.jpg", "Rust systems")
        results = ss_repo.search("Python")
        assert len(results) == 1
        assert "Python" in results[0]["ocr_text"]

    def test_update_ocr(self, ss_repo):
        inserted = ss_repo.insert("/tmp/test.jpg", "old")
        ss_repo.update_ocr(inserted["id"], "new text")
        fetched = ss_repo.get_by_id(inserted["id"])
        assert fetched["ocr_text"] == "new text"

    def test_link_uri(self, ss_repo):
        inserted = ss_repo.insert("/tmp/test.jpg", "text")
        uri = NocturneUri.parse("core://screenshot")
        ss_repo.link_uri(inserted["id"], uri)
        fetched = ss_repo.get_by_id(inserted["id"])
        assert fetched["uri"] == "core://screenshot"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd screen-memory-android/mcp-server && python -m pytest tests/test_storage.py::TestScreenshotRepo -v`
Expected: FAIL — `ImportError: cannot import name 'ScreenshotRepo'`

- [ ] **Step 3: Add ScreenshotRepo to screen_memory_server.py**

Append after `GraphRepo` class:

```python
# ─── ScreenshotRepo ──────────────────────────────────────────────────────

class ScreenshotRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def insert(self, file_path: str, ocr_text: Optional[str] = None,
               uri: Optional[NocturneUri] = None) -> dict:
        uri_str = str(uri) if uri else None
        cur = self._db.execute(
            "INSERT INTO screenshots (file_path, ocr_text, uri) VALUES (?, ?, ?)",
            (file_path, ocr_text, uri_str),
        )
        return self.get_by_id(cur.lastrowid)

    def get_by_id(self, screenshot_id: int) -> Optional[dict]:
        row = self._db.execute(
            "SELECT id, file_path, ocr_text, captured_at, uri FROM screenshots WHERE id=?",
            (screenshot_id,),
        ).fetchone()
        if row is None:
            return None
        keys = ["id", "file_path", "ocr_text", "captured_at", "uri"]
        return dict(zip(keys, row))

    def list_all(self, after: Optional[str] = None, before: Optional[str] = None) -> list[dict]:
        sql = "SELECT id, file_path, ocr_text, captured_at, uri FROM screenshots WHERE 1=1"
        params: list = []
        if after:
            sql += " AND captured_at >= ?"
            params.append(after)
        if before:
            sql += " AND captured_at <= ?"
            params.append(before)
        sql += " ORDER BY captured_at DESC"
        rows = self._db.execute(sql, tuple(params)).fetchall()
        keys = ["id", "file_path", "ocr_text", "captured_at", "uri"]
        return [dict(zip(keys, r)) for r in rows]

    def update_ocr(self, screenshot_id: int, ocr_text: str) -> None:
        self._db.execute(
            "UPDATE screenshots SET ocr_text=? WHERE id=?",
            (ocr_text, screenshot_id),
        )

    def link_uri(self, screenshot_id: int, uri: NocturneUri) -> None:
        self._db.execute(
            "UPDATE screenshots SET uri=? WHERE id=?",
            (str(uri), screenshot_id),
        )

    def search(self, query: str, limit: int = 20) -> list[dict]:
        rows = self._db.execute(
            "SELECT id, file_path, ocr_text, captured_at, uri FROM screenshots "
            "WHERE ocr_text LIKE ? ORDER BY captured_at DESC LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        keys = ["id", "file_path", "ocr_text", "captured_at", "uri"]
        return [dict(zip(keys, r)) for r in rows]
```

- [ ] **Step 4: Run tests**

Run: `cd screen-memory-android/mcp-server && python -m pytest tests/test_storage.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add screen-memory-android/mcp-server/screen_memory_server.py screen-memory-android/mcp-server/tests/test_storage.py
git commit -m "feat(mcp-server): add ScreenshotRepo with tests"
```

---

### Task 4: GraphService + SignalService

**Files:**
- Modify: `screen-memory-android/mcp-server/screen_memory_server.py` (add GraphService, SignalService)
- Create: `screen-memory-android/mcp-server/tests/test_services.py`

- [ ] **Step 1: Write test_services.py**

```python
# tests/test_services.py
"""Tests for GraphService and SignalService."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from screen_memory_server import (Database, GraphRepo, GraphService,
                                   NocturneUri, SignalService, EntityPolicy)
import pytest


@pytest.fixture
def graph_svc():
    db = Database(":memory:")
    db.initialize()
    repo = GraphRepo(db)
    yield GraphService(repo)
    db.close()


@pytest.fixture
def signal_svc():
    db = Database(":memory:")
    db.initialize()
    repo = GraphRepo(db)
    policies = {
        "topic": EntityPolicy("topic", activation_threshold=2.0, decay_tau=86400, required_evidence=[]),
    }
    yield SignalService(repo, policies)
    db.close()


class TestGraphService:
    def test_write_creates_node(self, graph_svc):
        result = graph_svc.write("core://a/b", "content")
        assert result["version"] == 1

    def test_write_materializes_paths(self, graph_svc):
        graph_svc.write("core://a/b/c", "deep")
        ancestors = graph_svc.get_ancestors(NocturneUri.parse("core://a/b/c"))
        assert len(ancestors) >= 1

    def test_read_after_write(self, graph_svc):
        graph_svc.write("core://x", "hello")
        mem = graph_svc.read("core://x")
        assert mem["content"] == "hello"

    def test_get_subtree(self, graph_svc):
        graph_svc.write("core://parent", "root")
        graph_svc.write("core://parent/child1", "c1")
        graph_svc.write("core://parent/child2", "c2")
        tree = graph_svc.get_subtree(NocturneUri.parse("core://parent"))
        assert tree["content"] == "root"
        assert len(tree["children"]) == 2

    def test_get_subtree_with_depth(self, graph_svc):
        graph_svc.write("core://a", "root")
        graph_svc.write("core://a/b", "mid")
        graph_svc.write("core://a/b/c", "deep")
        tree = graph_svc.get_subtree(NocturneUri.parse("core://a"), max_depth=1)
        assert len(tree["children"]) == 1
        assert tree["children"][0]["children"] == []

    def test_get_children(self, graph_svc):
        graph_svc.write("core://p/c1", "a")
        graph_svc.write("core://p/c2", "b")
        graph_svc.write("core://other", "c")
        children = graph_svc.get_children(NocturneUri.parse("core://p"))
        assert len(children) == 2


class TestSignalService:
    def test_ingest_creates_entity(self, signal_svc):
        result = signal_svc.ingest_signal("topic", "Python", "screenshot")
        assert result["name"] == "Python"
        assert result["status"] == "candidate"
        assert result["signal_count"] == 1

    def test_ingest_accumulates(self, signal_svc):
        signal_svc.ingest_signal("topic", "Python", "screenshot1")
        signal_svc.ingest_signal("topic", "Python", "screenshot2")
        entity = signal_svc.get_entity("Python")
        assert entity["signal_count"] == 2

    def test_ingest_merges_evidence(self, signal_svc):
        signal_svc.ingest_signal("topic", "Python", "chat", ["code"])
        signal_svc.ingest_signal("topic", "Python", "chat", ["docs"])
        entity = signal_svc.get_entity("Python")
        assert "code" in entity["evidence"]
        assert "docs" in entity["evidence"]

    def test_can_activate_below_threshold(self, signal_svc):
        signal_svc.ingest_signal("topic", "Python", "screenshot")
        assert not signal_svc.can_activate("Python")

    def test_activate_after_threshold(self, signal_svc):
        for i in range(5):
            signal_svc.ingest_signal("topic", "Python", f"screenshot_{i}")
        assert signal_svc.can_activate("Python")
        result = signal_svc.activate("Python")
        assert result["status"] == "active"

    def test_list_entities(self, signal_svc):
        signal_svc.ingest_signal("topic", "A", "src")
        signal_svc.ingest_signal("person", "B", "src")
        assert len(signal_svc.list_entities()) == 2
        assert len(signal_svc.list_entities(entity_type="topic")) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd screen-memory-android/mcp-server && python -m pytest tests/test_services.py -v`
Expected: FAIL — `ImportError: cannot import name 'GraphService'`

- [ ] **Step 3: Add GraphService and SignalService to screen_memory_server.py**

Append after ScreenshotRepo:

```python
# ─── GraphService ─────────────────────────────────────────────────────────

class GraphService:
    def __init__(self, repo: GraphRepo) -> None:
        self._repo = repo

    def write(self, uri: str | NocturneUri, content: str) -> dict:
        if isinstance(uri, str):
            uri = NocturneUri.parse(uri)
        self._materialize_paths(uri)
        return self._repo.write_memory(uri, content)

    def read(self, uri: str | NocturneUri) -> Optional[dict]:
        if isinstance(uri, str):
            uri = NocturneUri.parse(uri)
        return self._repo.read_memory(uri)

    def list_nodes(self, domain: Optional[str] = None) -> list[dict]:
        return self._repo.list_nodes(domain)

    def get_subtree(self, uri: NocturneUri, max_depth: Optional[int] = None) -> Optional[dict]:
        node = self._repo.get_node(uri)
        if node is None:
            return None
        mem = self._repo.read_memory(uri)
        children = self.get_children(uri)
        result = {"uri": str(uri), "content": mem["content"] if mem else None, "children": []}
        if max_depth is not None and max_depth <= 0:
            return result
        next_depth = (max_depth - 1) if max_depth is not None else None
        for child_row in children:
            child_uri = NocturneUri.parse(child_row["uri"])
            subtree = self.get_subtree(child_uri, max_depth=next_depth)
            if subtree is not None:
                result["children"].append(subtree)
        return result

    def get_children(self, uri: NocturneUri) -> list[dict]:
        all_nodes = self._repo.list_nodes(uri.domain)
        prefix = uri.path + "/" if uri.path else ""
        children = []
        for n in all_nodes:
            p = n["path"]
            if not prefix:
                if p and "/" not in p:
                    children.append(n)
            else:
                if p.startswith(prefix) and "/" not in p[len(prefix):]:
                    children.append(n)
        return children

    def _materialize_paths(self, uri: NocturneUri) -> None:
        if not uri.path:
            return
        parts = uri.path.split("/")
        for i in range(len(parts)):
            ancestor_path = "/".join(parts[:i])
            ancestor = NocturneUri.make(uri.domain, ancestor_path)
            self._repo.create_node(ancestor)
        node = self._repo.get_node(uri)
        if node is None:
            self._repo.create_node(uri)
        for i in range(1, len(parts)):
            ancestor_path = "/".join(parts[:i])
            ancestor_uri_str = f"{uri.domain}://{ancestor_path}"
            depth = len(parts) - i
            self._repo._db.execute(
                "INSERT OR IGNORE INTO paths (ancestor_uri, descendant_uri, depth) VALUES (?, ?, ?)",
                (ancestor_uri_str, str(uri), depth),
            )

    def get_ancestors(self, uri: NocturneUri) -> list[dict]:
        rows = self._repo._db.execute(
            "SELECT ancestor_uri, descendant_uri, depth FROM paths WHERE descendant_uri=? ORDER BY depth ASC",
            (str(uri),),
        ).fetchall()
        keys = ["ancestor_uri", "descendant_uri", "depth"]
        return [dict(zip(keys, r)) for r in rows]

    def get_descendants(self, uri: NocturneUri) -> list[dict]:
        rows = self._repo._db.execute(
            "SELECT ancestor_uri, descendant_uri, depth FROM paths WHERE ancestor_uri=? ORDER BY depth ASC",
            (str(uri),),
        ).fetchall()
        keys = ["ancestor_uri", "descendant_uri", "depth"]
        return [dict(zip(keys, r)) for r in rows]


# ─── SignalService ────────────────────────────────────────────────────────

@dataclass
class EntityPolicy:
    entity_type: str
    activation_threshold: float
    decay_tau: float
    required_evidence: list[str]


class SignalService:
    def __init__(self, repo: GraphRepo, policies: Optional[dict[str, EntityPolicy]] = None,
                 base_signal_score: float = 1.0) -> None:
        self._repo = repo
        self._db: Database = repo._db
        self._policies = policies or {}
        self._base_score = base_signal_score

    def ingest_signal(self, entity_type: str, entity_name: str, source: str,
                      evidence: Optional[list[str]] = None) -> dict:
        evidence = evidence or []
        row = self._db.execute(
            "SELECT id, score, signal_count, evidence FROM entities WHERE entity_type=? AND name=?",
            (entity_type, entity_name),
        ).fetchone()
        if row is None:
            self._db.execute(
                "INSERT INTO entities (entity_type, name, score, signal_count, evidence, status) "
                "VALUES (?, ?, ?, 1, ?, 'candidate')",
                (entity_type, entity_name, self._base_score, json.dumps(evidence)),
            )
            return self.get_entity(entity_name)
        eid, old_score, count, old_evidence_json = row
        old_evidence = json.loads(old_evidence_json)
        merged_evidence = list(set(old_evidence + evidence))
        new_count = count + 1
        age = self._get_age_seconds(entity_name)
        policy = self._policies.get(entity_type)
        tau = policy.decay_tau if policy else 86400 * 7
        decayed = old_score * math.exp(-age / tau)
        new_score = decayed + self._base_score
        self._db.execute(
            "UPDATE entities SET score=?, signal_count=?, evidence=?, "
            "last_seen_at=datetime('now'), updated_at=datetime('now') WHERE id=?",
            (new_score, new_count, json.dumps(merged_evidence), eid),
        )
        return self.get_entity(entity_name)

    def get_entity_score(self, name: str) -> float:
        row = self._db.execute(
            "SELECT score, entity_type FROM entities WHERE name=?", (name,)
        ).fetchone()
        if row is None:
            return 0.0
        score, entity_type = row
        policy = self._policies.get(entity_type)
        if not policy:
            return score
        age = self._get_age_seconds(name)
        return score * math.exp(-age / policy.decay_tau)

    def _get_age_seconds(self, name: str) -> float:
        row = self._db.execute(
            "SELECT CAST((julianday('now') - julianday(last_seen_at)) * 86400 AS INTEGER) FROM entities WHERE name=?",
            (name,),
        ).fetchone()
        if row is None or row[0] is None:
            return 0.0
        return max(0, row[0])

    def can_activate(self, name: str) -> bool:
        row = self._db.execute(
            "SELECT entity_type, evidence, status FROM entities WHERE name=?", (name,)
        ).fetchone()
        if row is None:
            return False
        entity_type, evidence_json, status = row
        if status != "candidate":
            return False
        score = self.get_entity_score(name)
        policy = self._policies.get(entity_type)
        if not policy:
            return score > 0
        if score < policy.activation_threshold:
            return False
        evidence = json.loads(evidence_json)
        for req in policy.required_evidence:
            if req not in evidence:
                return False
        return True

    def activate(self, name: str) -> dict:
        if not self.can_activate(name):
            raise ValueError(f"Entity '{name}' cannot be activated yet")
        row = self._db.execute(
            "SELECT entity_type, score, evidence FROM entities WHERE name=?", (name,)
        ).fetchone()
        entity_type, score, evidence_json = row
        self._db.execute(
            "UPDATE entities SET status='active', updated_at=datetime('now') WHERE name=?", (name,)
        )
        uri = NocturneUri.make("core", f"entities/{entity_type}/{name}")
        content = f"Entity: {name} (type: {entity_type}, score: {score:.2f})"
        if evidence_json != "[]":
            evidence = json.loads(evidence_json)
            content += f" | Evidence: {', '.join(evidence)}"
        self._repo.write_memory(uri, content)
        return self.get_entity(name)

    def get_entity(self, name: str) -> Optional[dict]:
        row = self._db.execute(
            "SELECT id, entity_type, name, status, score, signal_count, evidence, "
            "first_seen_at, last_seen_at FROM entities WHERE name=?", (name,)
        ).fetchone()
        if row is None:
            return None
        keys = ["id", "entity_type", "name", "status", "score", "signal_count",
                "evidence", "first_seen_at", "last_seen_at"]
        result = dict(zip(keys, row))
        result["evidence"] = json.loads(result["evidence"])
        return result

    def list_entities(self, status: Optional[str] = None, entity_type: Optional[str] = None) -> list[dict]:
        sql = "SELECT id, entity_type, name, status, score, signal_count FROM entities WHERE 1=1"
        params: list = []
        if status:
            sql += " AND status=?"
            params.append(status)
        if entity_type:
            sql += " AND entity_type=?"
            params.append(entity_type)
        rows = self._db.execute(sql, tuple(params)).fetchall()
        keys = ["id", "entity_type", "name", "status", "score", "signal_count"]
        return [dict(zip(keys, r)) for r in rows]
```

- [ ] **Step 4: Run tests**

Run: `cd screen-memory-android/mcp-server && python -m pytest tests/test_services.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add screen-memory-android/mcp-server/screen_memory_server.py screen-memory-android/mcp-server/tests/test_services.py
git commit -m "feat(mcp-server): add GraphService + SignalService with tests"
```

---

### Task 5: AndroidCapture + timed capture

**Files:**
- Modify: `screen-memory-android/mcp-server/screen_memory_server.py` (add CaptureResult, AndroidCapture)
- Create: `screen-memory-android/mcp-server/tests/test_capture.py`

- [ ] **Step 1: Write test_capture.py**

```python
# tests/test_capture.py
"""Tests for AndroidCapture with mocked HTTP, and timed capture control."""
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from screen_memory_server import AndroidCapture, CaptureResult
import pytest


class FakeHTTPClient:
    """Mock APK HTTP client for testing."""
    def __init__(self, responses=None):
        self._responses = responses or {}
        self.calls = []

    def get(self, path):
        self.calls.append(("GET", path))
        return self._responses.get(path, {})

    def post(self, path, data):
        self.calls.append(("POST", path, data))
        if path == "/capture":
            return {"image": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==",
                    "width": 100, "height": 200, "app_package": "com.test", "capture_time_ms": 100}
        if path == "/capture-and-ocr":
            return {"image": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==",
                    "width": 100, "height": 200, "app_package": "com.test",
                    "text": "Hello World", "blocks": [{"text": "Hello World", "confidence": 0.9, "bbox": [0,0,100,50]}]}

    def is_reachable(self):
        return True


class TestAndroidCapture:
    def test_capture_returns_result(self, tmp_path):
        cap = AndroidCapture(http_client=FakeHTTPClient(), screenshot_dir=str(tmp_path))
        result = cap.capture(quality=80)
        assert isinstance(result, CaptureResult)
        assert result.width == 100
        assert result.height == 200
        assert result.app_package == "com.test"
        assert result.file_path.endswith(".jpg")

    def test_capture_saves_file(self, tmp_path):
        cap = AndroidCapture(http_client=FakeHTTPClient(), screenshot_dir=str(tmp_path))
        result = cap.capture(quality=80)
        with open(result.file_path, "rb") as f:
            data = f.read()
        assert len(data) > 0

    def test_capture_and_ocr(self, tmp_path):
        cap = AndroidCapture(http_client=FakeHTTPClient(), screenshot_dir=str(tmp_path))
        result = cap.capture_and_ocr(quality=80)
        assert result["text"] == "Hello World"
        assert len(result["blocks"]) == 1


class TestTimedCapture:
    def test_start_and_stop(self, tmp_path):
        cap = AndroidCapture(http_client=FakeHTTPClient(), screenshot_dir=str(tmp_path))
        assert not cap.is_capturing()
        cap.start_timed_capture(interval_seconds=1, quality=50)
        assert cap.is_capturing()
        time.sleep(0.3)  # let first capture happen
        status = cap.stop_timed_capture()
        assert status["status"] == "stopped"
        assert status["captures_count"] >= 0
        assert not cap.is_capturing()

    def test_timed_status(self, tmp_path):
        cap = AndroidCapture(http_client=FakeHTTPClient(), screenshot_dir=str(tmp_path))
        status = cap.timed_status()
        assert status["status"] == "stopped"
        assert status["captures_count"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd screen-memory-android/mcp-server && python -m pytest tests/test_capture.py -v`
Expected: FAIL — `ImportError: cannot import name 'AndroidCapture'`

- [ ] **Step 3: Add CaptureResult and AndroidCapture to screen_memory_server.py**

Append after SignalService:

```python
# ─── Capture ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CaptureResult:
    image_data: bytes
    file_path: str
    width: int = 0
    height: int = 0
    capture_time_ms: int = 0
    app_name: Optional[str] = None
    app_package: Optional[str] = None


class AndroidCapture:
    """Screen capture via APK HTTP API with timed capture support."""

    def __init__(self, base_url: Optional[str] = None, screenshot_dir: Optional[str] = None,
                 timeout: int = 15, http_client=None) -> None:
        self._screenshot_dir = Path(screenshot_dir or os.path.expanduser("~/.screenmemory/screenshots"))
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)
        self._base_url = base_url or os.environ.get("SCREEN_MEMORY_APK_URL", "http://127.0.0.1:19700")
        self._timeout = timeout
        self._client = http_client
        self._timed_thread: Optional[threading.Thread] = None
        self._timed_stop = threading.Event()
        self._timed_count = 0
        self._timed_started_at: Optional[float] = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        return _HttpClient(self._base_url, self._timeout)

    def _apk_post(self, path: str, data: dict) -> dict:
        return self._get_client().post(path, data)

    def capture(self, quality: int = 80, region: Optional[dict] = None) -> CaptureResult:
        resp = self._apk_post("/capture", {"quality": quality})
        if "error" in resp:
            raise RuntimeError(resp["error"])
        image_data = base64.b64decode(resp["image"])
        now = datetime.now()
        date_dir = self._screenshot_dir / f"{now.year}/{now.month:02d}/{now.day:02d}"
        date_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{now.hour:02d}{now.minute:02d}{now.second:02d}.jpg"
        file_path = str(date_dir / filename)
        with open(file_path, "wb") as f:
            f.write(image_data)
        return CaptureResult(
            image_data=image_data, file_path=file_path,
            width=resp.get("width", 0), height=resp.get("height", 0),
            capture_time_ms=resp.get("capture_time_ms", 0),
            app_name=resp.get("app_package"), app_package=resp.get("app_package"),
        )

    def capture_and_ocr(self, quality: int = 80) -> dict:
        resp = self._apk_post("/capture-and-ocr", {"quality": quality})
        if "error" in resp:
            raise RuntimeError(resp["error"])
        image_data = base64.b64decode(resp["image"])
        now = datetime.now()
        date_dir = self._screenshot_dir / f"{now.year}/{now.month:02d}/{now.day:02d}"
        date_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{now.hour:02d}{now.minute:02d}{now.second:02d}.jpg"
        file_path = str(date_dir / filename)
        with open(file_path, "wb") as f:
            f.write(image_data)
        clean_blocks = []
        for b in resp.get("blocks", []):
            clean_blocks.append({"text": b.get("text", ""), "confidence": b.get("confidence", 0),
                                 "bbox": b.get("bbox", [])})
        return {"file_path": file_path, "text": resp.get("text", ""), "blocks": clean_blocks,
                "block_count": len(clean_blocks), "app_package": resp.get("app_package")}

    def start_timed_capture(self, interval_seconds: int = 10, quality: int = 80, callback=None) -> None:
        if self.is_capturing():
            return
        interval_seconds = max(5, interval_seconds)
        self._timed_stop.clear()
        self._timed_count = 0
        self._timed_started_at = time.time()

        def _loop():
            while not self._timed_stop.is_set():
                try:
                    result = self.capture_and_ocr(quality=quality)
                    self._timed_count += 1
                    if callback:
                        callback(result)
                except Exception:
                    pass
                self._timed_stop.wait(interval_seconds)

        self._timed_thread = threading.Thread(target=_loop, daemon=True)
        self._timed_thread.start()

    def stop_timed_capture(self) -> dict:
        if not self.is_capturing():
            return self.timed_status()
        self._timed_stop.set()
        if self._timed_thread:
            self._timed_thread.join(timeout=10)
            self._timed_thread = None
        return self.timed_status()

    def is_capturing(self) -> bool:
        return self._timed_thread is not None and self._timed_thread.is_alive()

    def timed_status(self) -> dict:
        if not self.is_capturing():
            return {"status": "stopped", "captures_count": self._timed_count}
        return {"status": "running", "captures_count": self._timed_count,
                "started_at": self._timed_started_at}


class _HttpClient:
    """Minimal HTTP client for APK API."""
    def __init__(self, base_url: str, timeout: int = 15):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def get(self, path: str) -> dict:
        return self._request("GET", path)

    def post(self, path: str, data: dict) -> dict:
        return self._request("POST", path, data)

    def _request(self, method: str, path: str, data: Optional[dict] = None) -> dict:
        url = f"{self._base_url}{path}"
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, method=method,
                                     headers={"Content-Type": "application/json"} if body else {})
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read())
        except Exception as e:
            return {"error": str(e)}

    def is_reachable(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self._base_url}/status", timeout=5) as resp:
                return json.loads(resp.read()).get("running", False)
        except Exception:
            return False
```

- [ ] **Step 4: Run tests**

Run: `cd screen-memory-android/mcp-server && python -m pytest tests/test_capture.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add screen-memory-android/mcp-server/screen_memory_server.py screen-memory-android/mcp-server/tests/test_capture.py
git commit -m "feat(mcp-server): add AndroidCapture + timed capture with tests"
```

---

### Task 6: ToolRegistry + MCP Protocol

**Files:**
- Modify: `screen-memory-android/mcp-server/screen_memory_server.py` (add ToolRegistry, MCPServer)
- Create: `screen-memory-android/mcp-server/tests/test_mcp.py`

- [ ] **Step 1: Write test_mcp.py**

```python
# tests/test_mcp.py
"""Tests for MCP JSON-RPC protocol and tool dispatch."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from screen_memory_server import (Database, GraphRepo, GraphService, ScreenshotRepo,
                                   SignalService, EntityPolicy, ToolRegistry, NocturneUri)
import pytest


@pytest.fixture
def registry():
    db = Database(":memory:")
    db.initialize()
    repo = GraphRepo(db)
    graph_svc = GraphService(repo)
    signal_svc = SignalService(repo)
    ss_repo = ScreenshotRepo(db)
    return ToolRegistry(graph_svc, signal_svc, ss_repo)


class TestToolRegistry:
    def test_list_tools_has_11(self, registry):
        tools = registry.list_tools()
        assert len(tools) == 11
        names = [t["name"] for t in tools]
        assert "memory_write" in names
        assert "memory_read" in names
        assert "memory_search" in names
        assert "memory_delete" in names
        assert "graph_query_subtree" in names
        assert "signal_ingest" in names
        assert "signal_activate" in names
        assert "screenshot_search" in names
        assert "screen_capture" in names
        assert "screen_ocr" in names
        assert "capture_session" in names

    def test_memory_write_and_read(self, registry):
        registry.call("memory_write", {"uri": "core://test", "content": "hello"})
        result = registry.call("memory_read", {"uri": "core://test"})
        assert result["content"] == "hello"

    def test_memory_search(self, registry):
        registry.call("memory_write", {"uri": "core://python", "content": "Python programming"})
        results = registry.call("memory_search", {"query": "python"})
        assert len(results) == 1

    def test_memory_delete(self, registry):
        registry.call("memory_write", {"uri": "core://del", "content": "to delete"})
        result = registry.call("memory_delete", {"uri": "core://del"})
        assert result["ok"] is True
        assert registry.call("memory_read", {"uri": "core://del"}) is None

    def test_graph_query_subtree(self, registry):
        registry.call("memory_write", {"uri": "core://a", "content": "root"})
        registry.call("memory_write", {"uri": "core://a/b", "content": "child"})
        tree = registry.call("graph_query_subtree", {"uri": "core://a"})
        assert tree["content"] == "root"
        assert len(tree["children"]) == 1

    def test_signal_ingest_and_activate(self, registry):
        for i in range(5):
            registry.call("signal_ingest", {"entity_type": "topic", "entity_name": "AI",
                                            "source": f"src_{i}"})
        result = registry.call("signal_activate", {"entity_name": "AI"})
        assert result["status"] == "active"

    def test_screenshot_search(self, registry):
        registry._ss_repo.insert("/tmp/a.jpg", "Android home screen")
        results = registry.call("screenshot_search", {"query": "Android"})
        assert len(results) == 1

    def test_unknown_tool_raises(self, registry):
        with pytest.raises(ValueError):
            registry.call("nonexistent", {})


class TestMCPProtocol:
    def test_initialize(self, registry):
        from screen_memory_server import MCPServer
        server = MCPServer(registry)
        resp = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                              "params": {"protocolVersion": "2024-11-05",
                                         "capabilities": {},
                                         "clientInfo": {"name": "test", "version": "0.1"}}})
        assert resp["result"]["serverInfo"]["name"] == "screen-memory"

    def test_tools_list(self, registry):
        from screen_memory_server import MCPServer
        server = MCPServer(registry)
        resp = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        assert len(resp["result"]["tools"]) == 11

    def test_tools_call(self, registry):
        from screen_memory_server import MCPServer
        server = MCPServer(registry)
        resp = server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                              "params": {"name": "memory_write",
                                         "arguments": {"uri": "core://test", "content": "hi"}}})
        text = resp["result"]["content"][0]["text"]
        data = json.loads(text)
        assert data["ok"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd screen-memory-android/mcp-server && python -m pytest tests/test_mcp.py -v`
Expected: FAIL — `ImportError: cannot import name 'ToolRegistry'`

- [ ] **Step 3: Add ToolRegistry and MCPServer to screen_memory_server.py**

Append after `_HttpClient`:

```python
# ─── ToolRegistry ────────────────────────────────────────────────────────

_TOOL_DEFINITIONS = [
    {"name": "memory_write", "description": "Write a memory to the URI Graph. Creates the node if it doesn't exist.",
     "inputSchema": {"type": "object", "properties": {
         "uri": {"type": "string", "description": "Nocturne URI (e.g. core://my/topic)"},
         "content": {"type": "string", "description": "Memory content to store"}},
         "required": ["uri", "content"]}},
    {"name": "memory_read", "description": "Read the latest memory at a URI.",
     "inputSchema": {"type": "object", "properties": {
         "uri": {"type": "string", "description": "Nocturne URI"}},
         "required": ["uri"]}},
    {"name": "memory_search", "description": "Full-text search across all memories.",
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string", "description": "FTS5 search query"},
         "limit": {"type": "integer", "description": "Max results", "default": 20}},
         "required": ["query"]}},
    {"name": "memory_delete", "description": "Delete a node and all its memories from the graph.",
     "inputSchema": {"type": "object", "properties": {
         "uri": {"type": "string", "description": "Nocturne URI to delete"}},
         "required": ["uri"]}},
    {"name": "graph_query_subtree", "description": "Query the subtree rooted at a URI.",
     "inputSchema": {"type": "object", "properties": {
         "uri": {"type": "string", "description": "Root URI"},
         "max_depth": {"type": "integer", "description": "Max depth to traverse"}},
         "required": ["uri"]}},
    {"name": "signal_ingest", "description": "Ingest a signal for entity lifecycle tracking.",
     "inputSchema": {"type": "object", "properties": {
         "entity_type": {"type": "string", "description": "Entity type (person, topic, etc.)"},
         "entity_name": {"type": "string", "description": "Entity name/identifier"},
         "source": {"type": "string", "description": "Signal source (screenshot, chat, etc.)"},
         "evidence": {"type": "array", "items": {"type": "string"}, "description": "Evidence tags"}},
         "required": ["entity_type", "entity_name", "source"]}},
    {"name": "signal_activate", "description": "Activate an entity and materialize it into the graph.",
     "inputSchema": {"type": "object", "properties": {
         "entity_name": {"type": "string", "description": "Entity name to activate"}},
         "required": ["entity_name"]}},
    {"name": "screenshot_search", "description": "Search screenshots by OCR text.",
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string", "description": "Search query"},
         "limit": {"type": "integer", "description": "Max results", "default": 20}},
         "required": ["query"]}},
    {"name": "screen_capture", "description": "Capture the Android phone screen.",
     "inputSchema": {"type": "object", "properties": {
         "quality": {"type": "integer", "description": "JPEG quality 1-100 (default 80)", "default": 80}}}},
    {"name": "screen_ocr", "description": "Capture screen and run OCR. Returns text and blocks.",
     "inputSchema": {"type": "object", "properties": {
         "quality": {"type": "integer", "description": "JPEG quality (default 80)", "default": 80}}}},
    {"name": "capture_session", "description": "Start, stop, or query continuous screen capture.",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string", "description": "start, stop, or status"},
         "interval_seconds": {"type": "integer", "description": "Capture interval (default 10, min 5)", "default": 10},
         "quality": {"type": "integer", "description": "JPEG quality (default 80)", "default": 80}},
         "required": ["action"]}},
]


class ToolRegistry:
    def __init__(self, graph_service: GraphService, signal_service: SignalService,
                 screenshot_repo: ScreenshotRepo) -> None:
        self._graph = graph_service
        self._signal = signal_service
        self._ss_repo = screenshot_repo
        self._capture: Optional[AndroidCapture] = None
        self._dispatchers = {
            "memory_write": self._memory_write, "memory_read": self._memory_read,
            "memory_search": self._memory_search, "memory_delete": self._memory_delete,
            "graph_query_subtree": self._graph_query_subtree,
            "signal_ingest": self._signal_ingest, "signal_activate": self._signal_activate,
            "screenshot_search": self._screenshot_search,
            "screen_capture": self._screen_capture, "screen_ocr": self._screen_ocr,
            "capture_session": self._capture_session,
        }

    def list_tools(self) -> list[dict]:
        return list(_TOOL_DEFINITIONS)

    def call(self, tool_name: str, params: dict[str, Any]) -> Any:
        if tool_name not in self._dispatchers:
            raise ValueError(f"unknown tool: {tool_name}")
        return self._dispatchers[tool_name](params)

    def _get_capture(self) -> AndroidCapture:
        if self._capture is None:
            self._capture = AndroidCapture()
        return self._capture

    def _memory_write(self, p):
        uri, content = p.get("uri"), p.get("content")
        if not uri or content is None:
            raise ValueError("memory_write requires 'uri' and 'content'")
        result = self._graph.write(uri, content)
        return {"ok": True, "uri": str(NocturneUri.parse(uri)), "version": result["version"]}

    def _memory_read(self, p):
        uri = p.get("uri")
        if not uri:
            raise ValueError("memory_read requires 'uri'")
        return self._graph.read(uri)

    def _memory_search(self, p):
        q = p.get("query")
        if not q:
            raise ValueError("memory_search requires 'query'")
        return self._graph._repo.search(q, p.get("limit", 20))

    def _memory_delete(self, p):
        uri = p.get("uri")
        if not uri:
            raise ValueError("memory_delete requires 'uri'")
        self._graph._repo.delete_node(NocturneUri.parse(uri))
        return {"ok": True, "uri": uri}

    def _graph_query_subtree(self, p):
        uri = p.get("uri")
        if not uri:
            raise ValueError("graph_query_subtree requires 'uri'")
        return self._graph.get_subtree(NocturneUri.parse(uri), max_depth=p.get("max_depth")) or {}

    def _signal_ingest(self, p):
        et, en, src = p.get("entity_type"), p.get("entity_name"), p.get("source")
        if not et or not en or not src:
            raise ValueError("signal_ingest requires entity_type, entity_name, source")
        return self._signal.ingest_signal(et, en, src, p.get("evidence", []))

    def _signal_activate(self, p):
        en = p.get("entity_name")
        if not en:
            raise ValueError("signal_activate requires 'entity_name'")
        return self._signal.activate(en)

    def _screenshot_search(self, p):
        q = p.get("query")
        if not q:
            raise ValueError("screenshot_search requires 'query'")
        return self._ss_repo.search(q, p.get("limit", 20))

    def _screen_capture(self, p):
        cap = self._get_capture()
        result = cap.capture(quality=p.get("quality", 80))
        return {"width": result.width, "height": result.height,
                "app_package": result.app_package, "file_path": result.file_path,
                "image": base64.b64encode(result.image_data).decode()}

    def _screen_ocr(self, p):
        cap = self._get_capture()
        result = cap.capture_and_ocr(quality=p.get("quality", 80))
        self._ss_repo.insert(result["file_path"], result["text"])
        return {"full_text": result["text"], "text_blocks": result["blocks"],
                "block_count": result["block_count"], "app_package": result.get("app_package")}

    def _capture_session(self, p):
        action = p.get("action", "status")
        cap = self._get_capture()
        if action == "start":
            def _on_capture(result):
                self._ss_repo.insert(result["file_path"], result["text"])
                pkg = result.get("app_package")
                if pkg:
                    self._signal.ingest_signal("app", pkg, "screenshot")
            cap.start_timed_capture(
                interval_seconds=p.get("interval_seconds", 10),
                quality=p.get("quality", 80), callback=_on_capture)
            return {"status": "started", "interval_seconds": p.get("interval_seconds", 10)}
        elif action == "stop":
            return cap.stop_timed_capture()
        else:
            return cap.timed_status()


# ─── MCP Server ───────────────────────────────────────────────────────────

class MCPServer:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def handle(self, req: dict) -> Optional[dict]:
        method = req.get("method", "")
        msg_id = req.get("id")
        params = req.get("params", {})
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {
                "protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                "serverInfo": {"name": "screen-memory", "version": "0.2.0"}}}
        elif method == "notifications/initialized":
            return None
        elif method == "tools/list":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": self._registry.list_tools()}}
        elif method == "tools/call":
            name = params.get("name", "")
            args = params.get("arguments", {})
            try:
                result = self._registry.call(name, args)
            except Exception as e:
                return {"jsonrpc": "2.0", "id": msg_id,
                        "result": {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}],
                                   "isError": True}}
            return {"jsonrpc": "2.0", "id": msg_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}}
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}}

    def run(self) -> None:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                continue
            resp = self.handle(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()


if __name__ == "__main__":
    db_path = os.path.expanduser("~/.screenmemory/db/screenmemory.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    db = Database(db_path)
    db.initialize()
    repo = GraphRepo(db)
    graph_svc = GraphService(repo)
    signal_svc = SignalService(repo)
    ss_repo = ScreenshotRepo(db)
    registry = ToolRegistry(graph_svc, signal_svc, ss_repo)
    server = MCPServer(registry)
    server.run()
```

- [ ] **Step 4: Run all tests**

Run: `cd screen-memory-android/mcp-server && python -m pytest tests/ -v`
Expected: PASS — all tests green

- [ ] **Step 5: Commit**

```bash
git add screen-memory-android/mcp-server/screen_memory_server.py screen-memory-android/mcp-server/tests/test_mcp.py
git commit -m "feat(mcp-server): add ToolRegistry + MCP protocol with tests"
```

---

### Task 7: Integration test + deploy to phone

**Files:**
- Create: `screen-memory-android/mcp-server/tests/test_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_integration.py
"""End-to-end integration test: full workflow from capture to search."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from screen_memory_server import (Database, GraphRepo, GraphService, ScreenshotRepo,
                                   SignalService, EntityPolicy, ToolRegistry, MCPServer)
import pytest


@pytest.fixture
def server():
    db = Database(":memory:")
    db.initialize()
    repo = GraphRepo(db)
    graph_svc = GraphService(repo)
    signal_svc = SignalService(repo)
    ss_repo = ScreenshotRepo(db)
    registry = ToolRegistry(graph_svc, signal_svc, ss_repo)
    return MCPServer(registry)


def _call(server, method, params=None):
    resp = server.handle({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})
    if "error" in resp:
        raise RuntimeError(resp["error"])
    content = resp["result"]["content"][0]["text"]
    return json.loads(content)


class TestE2EWorkflow:
    def test_memory_lifecycle(self, server):
        # Write
        result = _call(server, "tools/call", {"name": "memory_write",
                       "arguments": {"uri": "core://project/android-mcp", "content": "Building MCP server for Android"}})
        assert result["ok"]
        # Read
        mem = _call(server, "tools/call", {"name": "memory_read",
                     "arguments": {"uri": "core://project/android-mcp"}})
        assert mem["content"] == "Building MCP server for Android"
        # Search
        results = _call(server, "tools/call", {"name": "memory_search",
                        "arguments": {"query": "Android"}})
        assert len(results) >= 1

    def test_signal_to_activation(self, server):
        # Ingest multiple signals
        for i in range(5):
            _call(server, "tools/call", {"name": "signal_ingest",
                  "arguments": {"entity_type": "topic", "entity_name": "Python", "source": f"screenshot_{i}"}})
        # Activate
        entity = _call(server, "tools/call", {"name": "signal_activate",
                       "arguments": {"entity_name": "Python"}})
        assert entity["status"] == "active"
        # Verify it created a graph node
        mem = _call(server, "tools/call", {"name": "memory_read",
                     "arguments": {"uri": "core://entities/topic/Python"}})
        assert mem is not None
        assert "Python" in mem["content"]

    def test_graph_hierarchy(self, server):
        _call(server, "tools/call", {"name": "memory_write",
              "arguments": {"uri": "core://projects", "content": "All projects"}})
        _call(server, "tools/call", {"name": "memory_write",
              "arguments": {"uri": "core://projects/android", "content": "Android app"}})
        _call(server, "tools/call", {"name": "memory_write",
              "arguments": {"uri": "core://projects/android/mcp", "content": "MCP server"}})
        tree = _call(server, "tools/call", {"name": "graph_query_subtree",
                     "arguments": {"uri": "core://projects"}})
        assert tree["content"] == "All projects"
        assert len(tree["children"]) == 1
        assert tree["children"][0]["children"][0]["content"] == "MCP server"

    def test_screenshot_search(self, server):
        server._registry._ss_repo.insert("/tmp/s1.jpg", "Settings app WiFi page")
        server._registry._ss_repo.insert("/tmp/s2.jpg", "Chrome browser Google search")
        results = _call(server, "tools/call", {"name": "screenshot_search",
                        "arguments": {"query": "WiFi"}})
        assert len(results) == 1
        assert "WiFi" in results[0]["ocr_text"]

    def test_mcp_initialize(self, server):
        resp = server.handle({"jsonrpc": "2.0", "id": 0, "method": "initialize",
                              "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                         "clientInfo": {"name": "test", "version": "1.0"}}})
        assert resp["result"]["protocolVersion"] == "2024-11-05"
        assert resp["result"]["serverInfo"]["name"] == "screen-memory"
```

- [ ] **Step 2: Run integration test**

Run: `cd screen-memory-android/mcp-server && python -m pytest tests/test_integration.py -v`
Expected: PASS

- [ ] **Step 3: Run all tests**

Run: `cd screen-memory-android/mcp-server && python -m pytest tests/ -v`
Expected: PASS — all tests across all files green

- [ ] **Step 4: Commit**

```bash
git add screen-memory-android/mcp-server/tests/test_integration.py
git commit -m "test(mcp-server): add integration tests for full workflow"
```

---

### Task 8: Deploy to phone and verify

**Files:**
- No new files — deploy existing `screen_memory_server.py`

- [ ] **Step 1: Copy to phone via SSH**

```bash
adb forward tcp:8022 tcp:8022
scp -P 8022 -i ~/.ssh/id_rsa screen-memory-android/mcp-server/screen_memory_server.py u0_a349@127.0.0.1:~/.openclaw/mcp-servers/screen-memory.py
```

- [ ] **Step 2: Restart OpenClaw gateway**

```bash
ssh -p 8022 -o StrictHostKeyChecking=no -i ~/.ssh/id_rsa u0_a349@127.0.0.1 \
  'lsof -i :3000 -t 2>/dev/null | xargs kill 2>/dev/null; sleep 2; tmux kill-session -t openclaw 2>/dev/null; tmux new-session -d -s openclaw; tmux send-keys -t openclaw "export PATH=\$HOME/.openclaw-android/bin:\$HOME/.openclaw-android/node/bin:\$HOME/.local/bin:\$PATH" Enter; sleep 1; tmux send-keys -t openclaw "openclaw gateway run" Enter'
```

- [ ] **Step 3: Test MCP server directly**

```bash
ssh -p 8022 -o StrictHostKeyChecking=no -i ~/.ssh/id_rsa u0_a349@127.0.0.1 \
  'printf '"'"'%s\n%s\n'"'"' '"'"'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0.1"}}}'"'"' '"'"'{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'"'"' | python3 ~/.openclaw/mcp-servers/screen-memory.py'
```

Expected: JSON responses showing 11 tools.

- [ ] **Step 4: Test via OpenClaw agent**

```bash
ssh -p 8022 -o StrictHostKeyChecking=no -i ~/.ssh/id_rsa u0_a349@127.0.0.1 \
  'export PATH="$HOME/.openclaw-android/bin:$HOME/.openclaw-android/node/bin:$HOME/.local/bin:$PATH"; \
   openclaw agent --local --thinking off --session-id deploy-test \
   --message "写入一条记忆到 core://test/hello 内容是 hello world，然后读取它"'
```

Expected: AI calls `memory_write` then `memory_read` and confirms the content.

- [ ] **Step 5: Commit**

```bash
git commit --allow-empty -m "deploy(mcp-server): full feature parity deployed to phone"
```

---

## Self-Review

**1. Spec coverage check:**
- NocturneUri: Task 1 ✅
- Database (6 tables + FTS + triggers): Task 2 ✅
- GraphRepo (all methods): Task 2 ✅
- ScreenshotRepo (all methods): Task 3 ✅
- GraphService (write, read, get_subtree, get_children, materialize_paths): Task 4 ✅
- SignalService (ingest, activate, entity policies): Task 4 ✅
- AndroidCapture (capture, capture_and_ocr, timed capture): Task 5 ✅
- ToolRegistry (11 tools, dispatch): Task 6 ✅
- MCPServer (JSON-RPC protocol): Task 6 ✅
- Integration test: Task 7 ✅
- Deploy to phone: Task 8 ✅

**2. Placeholder scan:** No TBD, TODO, or placeholder patterns found.

**3. Type consistency check:** All method signatures use consistent parameter names (uri, content, query, entity_type, entity_name, source, evidence). Return types are consistent (dict, Optional[dict], list[dict]). No naming mismatches across tasks.
