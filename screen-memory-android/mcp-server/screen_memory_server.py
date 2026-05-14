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
