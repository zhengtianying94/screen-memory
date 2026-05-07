"""GraphRepo: CRUD operations for the Nocturne URI Graph."""

from __future__ import annotations

from typing import Optional

from screen_memory.models.uri import NocturneUri
from screen_memory.storage.database import Database


class GraphRepo:
    """Repository for nodes, memories, edges, and full-text search."""

    def __init__(self, db: Database) -> None:
        self._db = db

    # -- Nodes ----------------------------------------------------------------

    def create_node(self, uri: NocturneUri) -> NocturneUri:
        """Insert a node if it doesn't exist; return the URI either way."""
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

    # -- Memories -------------------------------------------------------------

    def write_memory(self, uri: NocturneUri, content: str) -> dict:
        """Write a new memory version for *uri*. Auto-creates the node."""
        self.create_node(uri)
        # Check existing version count
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
        """Return the latest active memory for *uri*, or None."""
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

    # -- Edges ----------------------------------------------------------------

    def create_edge(
        self, source: NocturneUri, target: NocturneUri, relation: str = "related", weight: float = 1.0
    ) -> dict:
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

    def get_neighbors(
        self, uri: NocturneUri, relation: Optional[str] = None
    ) -> list[dict]:
        if relation:
            rows = self._db.execute(
                "SELECT target_uri, relation, weight FROM edges "
                "WHERE source_uri=? AND relation=?",
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

    # -- FTS ------------------------------------------------------------------

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
