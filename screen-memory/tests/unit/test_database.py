"""Tests for SQLite database schema initialization.

TDD order: schema creation → idempotency → FTS5 → constraints
"""

import sqlite3

import pytest

from screen_memory.storage.database import Database


@pytest.fixture
def db(tmp_path):
    """Create an in-memory Database with all tables initialized."""
    d = Database(":memory:")
    d.initialize()
    return d


class TestSchemaCreation:
    """Verify all four core tables + FTS5 exist after init."""

    def test_nodes_table_exists(self, db):
        rows = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='nodes'"
        ).fetchall()
        assert len(rows) == 1

    def test_memories_table_exists(self, db):
        rows = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memories'"
        ).fetchall()
        assert len(rows) == 1

    def test_edges_table_exists(self, db):
        rows = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='edges'"
        ).fetchall()
        assert len(rows) == 1

    def test_paths_table_exists(self, db):
        rows = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='paths'"
        ).fetchall()
        assert len(rows) == 1

    def test_fts_index_exists(self, db):
        rows = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memories_fts'"
        ).fetchall()
        assert len(rows) == 1

    def test_screenshots_table_exists(self, db):
        rows = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='screenshots'"
        ).fetchall()
        assert len(rows) == 1


class TestSchemaIdempotent:
    """Running initialize() twice must not raise."""

    def test_double_init(self, db):
        db.initialize()  # second call — should succeed silently

    def test_double_init_preserves_data(self, db):
        db.execute("INSERT INTO nodes (uri, domain, path) VALUES ('core://a', 'core', 'a')")
        db.initialize()
        rows = db.execute("SELECT uri FROM nodes WHERE uri='core://a'").fetchall()
        assert len(rows) == 1


class TestNodeConstraints:
    """Verify node table constraints."""

    def test_uri_unique(self, db):
        db.execute("INSERT INTO nodes (uri, domain, path) VALUES ('core://a', 'core', 'a')")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO nodes (uri, domain, path) VALUES ('core://a', 'core', 'a')")

    def test_domain_not_null(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO nodes (uri, path) VALUES ('core://a', 'a')")

    def test_path_not_null(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO nodes (uri, domain) VALUES ('core://a', 'core')")


class TestMemoryConstraints:
    """Verify memory table constraints."""

    def test_node_uri_fk(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO memories (node_uri, content, version, status) "
                "VALUES ('nonexistent://x', 'text', 1, 'active')"
            )

    def test_version_default(self, db):
        db.execute("INSERT INTO nodes (uri, domain, path) VALUES ('core://a', 'core', 'a')")
        db.execute(
            "INSERT INTO memories (node_uri, content, status) VALUES ('core://a', 'hello', 'active')"
        )
        row = db.execute("SELECT version FROM memories WHERE node_uri='core://a'").fetchone()
        assert row[0] == 1


class TestEdgeConstraints:
    """Verify edge table constraints."""

    def test_self_loop_rejected(self, db):
        db.execute("INSERT INTO nodes (uri, domain, path) VALUES ('core://a', 'core', 'a')")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO edges (source_uri, target_uri, relation) "
                "VALUES ('core://a', 'core://a', 'related')"
            )

    def test_unique_edge(self, db):
        db.execute("INSERT INTO nodes (uri, domain, path) VALUES ('core://a', 'core', 'a')")
        db.execute("INSERT INTO nodes (uri, domain, path) VALUES ('core://b', 'core', 'b')")
        db.execute(
            "INSERT INTO edges (source_uri, target_uri, relation) "
            "VALUES ('core://a', 'core://b', 'related')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO edges (source_uri, target_uri, relation) "
                "VALUES ('core://a', 'core://b', 'related')"
            )
