"""SQLite database schema for the Nocturne URI Graph memory."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional


_SCHEMA_SQL = """
-- Nodes: one row per unique URI in the graph
CREATE TABLE IF NOT EXISTS nodes (
    uri         TEXT PRIMARY KEY,
    domain      TEXT NOT NULL,
    path        TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Memories: append-only content versions per node
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

-- Edges: directed relationships between nodes
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

-- Paths: materialized ancestor-descendant relationships
CREATE TABLE IF NOT EXISTS paths (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ancestor_uri TEXT NOT NULL REFERENCES nodes(uri) ON DELETE CASCADE,
    descendant_uri TEXT NOT NULL REFERENCES nodes(uri) ON DELETE CASCADE,
    depth       INTEGER NOT NULL DEFAULT 1,

    UNIQUE (ancestor_uri, descendant_uri),
    CHECK (ancestor_uri != descendant_uri)
);

-- Entities: signal accumulation for entity lifecycle
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

-- Screenshots: captured screen data with OCR text
CREATE TABLE IF NOT EXISTS screenshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path   TEXT NOT NULL,
    ocr_text    TEXT,
    captured_at TEXT NOT NULL DEFAULT (datetime('now')),
    uri         TEXT REFERENCES nodes(uri) ON DELETE SET NULL,

    UNIQUE (file_path)
);

-- FTS5 full-text index on memory content
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
    USING fts5(content, content='memories', content_rowid='id');

-- Trigger: auto-sync FTS on insert
CREATE TRIGGER IF NOT EXISTS memories_fts_insert
    AFTER INSERT ON memories BEGIN
        INSERT INTO memories_fts (rowid, content)
        VALUES (new.id, new.content);
    END;

-- Trigger: auto-sync FTS on delete
CREATE TRIGGER IF NOT EXISTS memories_fts_delete
    AFTER DELETE ON memories BEGIN
        INSERT INTO memories_fts (memories_fts, rowid, content)
        VALUES ('delete', old.id, old.content);
    END;

-- Trigger: auto-sync FTS on update
CREATE TRIGGER IF NOT EXISTS memories_fts_update
    AFTER UPDATE ON memories BEGIN
        INSERT INTO memories_fts (memories_fts, rowid, content)
        VALUES ('delete', old.id, old.content);
        INSERT INTO memories_fts (rowid, content)
        VALUES (new.id, new.content);
    END;
"""


class Database:
    """Thin wrapper around an SQLite connection for the Nocturne graph."""

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
        """Create all tables/triggers if they don't exist yet. Idempotent."""
        self.conn.executescript(_SCHEMA_SQL)
        self.conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a single SQL statement and return the cursor."""
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        return cur

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
