"""Tests for the GraphRepo (node/memory/edge CRUD operations).

TDD order: error cases → node CRUD → memory versioning → edges → queries
"""

import pytest

from screen_memory.models.uri import NocturneUri
from screen_memory.storage.database import Database
from screen_memory.storage.graph_repo import GraphRepo


@pytest.fixture
def repo():
    db = Database(":memory:")
    db.initialize()
    return GraphRepo(db)


# -- Node CRUD ---------------------------------------------------------------


class TestNodeCreate:
    def test_create_returns_uri(self, repo):
        uri = NocturneUri.parse("core://a")
        result = repo.create_node(uri)
        assert result == uri

    def test_create_duplicate_returns_existing(self, repo):
        uri = NocturneUri.parse("core://a")
        first = repo.create_node(uri)
        second = repo.create_node(uri)
        assert first == second

    def test_create_deep_path(self, repo):
        uri = NocturneUri.parse("core://a/b/c")
        result = repo.create_node(uri)
        assert result == uri


class TestNodeRead:
    def test_get_existing(self, repo):
        uri = NocturneUri.parse("core://a")
        repo.create_node(uri)
        node = repo.get_node(uri)
        assert node is not None
        assert node["uri"] == "core://a"
        assert node["domain"] == "core"
        assert node["path"] == "a"

    def test_get_missing_returns_none(self, repo):
        uri = NocturneUri.parse("core://nonexistent")
        assert repo.get_node(uri) is None

    def test_list_by_domain(self, repo):
        repo.create_node(NocturneUri.parse("core://a"))
        repo.create_node(NocturneUri.parse("core://b"))
        repo.create_node(NocturneUri.parse("dynamic://x"))
        nodes = repo.list_nodes("core")
        assert len(nodes) == 2

    def test_list_all(self, repo):
        repo.create_node(NocturneUri.parse("core://a"))
        repo.create_node(NocturneUri.parse("dynamic://x"))
        nodes = repo.list_nodes()
        assert len(nodes) == 2


class TestNodeDelete:
    def test_delete_removes_node(self, repo):
        uri = NocturneUri.parse("core://a")
        repo.create_node(uri)
        repo.delete_node(uri)
        assert repo.get_node(uri) is None

    def test_delete_cascades_memories(self, repo):
        uri = NocturneUri.parse("core://a")
        repo.create_node(uri)
        repo.write_memory(uri, "hello")
        repo.delete_node(uri)
        assert repo.read_memory(uri) is None

    def test_delete_missing_noop(self, repo):
        uri = NocturneUri.parse("core://ghost")
        repo.delete_node(uri)  # should not raise


# -- Memory versioning --------------------------------------------------------


class TestMemoryWrite:
    def test_write_first_version(self, repo):
        uri = NocturneUri.parse("core://a")
        repo.create_node(uri)
        mem = repo.write_memory(uri, "hello")
        assert mem["version"] == 1
        assert mem["content"] == "hello"

    def test_write_bumps_version(self, repo):
        uri = NocturneUri.parse("core://a")
        repo.create_node(uri)
        repo.write_memory(uri, "v1")
        mem = repo.write_memory(uri, "v2")
        assert mem["version"] == 2
        assert mem["content"] == "v2"

    def test_write_auto_creates_node(self, repo):
        uri = NocturneUri.parse("core://auto")
        repo.write_memory(uri, "auto content")
        assert repo.get_node(uri) is not None
        mem = repo.read_memory(uri)
        assert mem["content"] == "auto content"


class TestMemoryRead:
    def test_read_returns_latest(self, repo):
        uri = NocturneUri.parse("core://a")
        repo.write_memory(uri, "first")
        repo.write_memory(uri, "second")
        mem = repo.read_memory(uri)
        assert mem["content"] == "second"
        assert mem["version"] == 2

    def test_read_no_memory_returns_none(self, repo):
        uri = NocturneUri.parse("core://a")
        repo.create_node(uri)
        assert repo.read_memory(uri) is None

    def test_read_history(self, repo):
        uri = NocturneUri.parse("core://a")
        repo.write_memory(uri, "v1")
        repo.write_memory(uri, "v2")
        history = repo.memory_history(uri)
        assert len(history) == 2
        assert history[0]["content"] == "v2"  # newest first
        assert history[1]["content"] == "v1"


class TestMemoryDeprecate:
    def test_deprecate_old_version(self, repo):
        uri = NocturneUri.parse("core://a")
        repo.write_memory(uri, "v1")
        repo.write_memory(uri, "v2")
        repo.deprecate_memory(uri, 1)
        history = repo.memory_history(uri)
        assert history[1]["status"] == "deprecated"
        assert history[0]["status"] == "active"


# -- Edges -------------------------------------------------------------------


class TestEdgeCreate:
    def test_create_edge(self, repo):
        a = NocturneUri.parse("core://a")
        b = NocturneUri.parse("core://b")
        repo.create_node(a)
        repo.create_node(b)
        edge = repo.create_edge(a, b, "related")
        assert edge["relation"] == "related"

    def test_create_edge_duplicate_idempotent(self, repo):
        a = NocturneUri.parse("core://a")
        b = NocturneUri.parse("core://b")
        repo.create_node(a)
        repo.create_node(b)
        repo.create_edge(a, b, "related")
        edge2 = repo.create_edge(a, b, "related")
        assert edge2 is not None  # returns existing


class TestEdgeQuery:
    def test_get_neighbors(self, repo):
        a = NocturneUri.parse("core://a")
        b = NocturneUri.parse("core://b")
        c = NocturneUri.parse("core://c")
        repo.create_node(a)
        repo.create_node(b)
        repo.create_node(c)
        repo.create_edge(a, b, "related")
        repo.create_edge(a, c, "related")
        neighbors = repo.get_neighbors(a)
        assert len(neighbors) == 2

    def test_get_neighbors_directed(self, repo):
        a = NocturneUri.parse("core://a")
        b = NocturneUri.parse("core://b")
        repo.create_node(a)
        repo.create_node(b)
        repo.create_edge(a, b, "related")
        # a → b, so b has no outgoing neighbors
        assert len(repo.get_neighbors(b)) == 0

    def test_get_neighbors_by_relation(self, repo):
        a = NocturneUri.parse("core://a")
        b = NocturneUri.parse("core://b")
        c = NocturneUri.parse("core://c")
        repo.create_node(a)
        repo.create_node(b)
        repo.create_node(c)
        repo.create_edge(a, b, "related")
        repo.create_edge(a, c, "parent")
        neighbors = repo.get_neighbors(a, relation="related")
        assert len(neighbors) == 1


class TestEdgeDelete:
    def test_delete_edge(self, repo):
        a = NocturneUri.parse("core://a")
        b = NocturneUri.parse("core://b")
        repo.create_node(a)
        repo.create_node(b)
        repo.create_edge(a, b, "related")
        repo.delete_edge(a, b, "related")
        assert len(repo.get_neighbors(a)) == 0


# -- FTS search --------------------------------------------------------------


class TestFtsSearch:
    def test_search_memory(self, repo):
        repo.write_memory(NocturneUri.parse("core://a"), "The quick brown fox")
        repo.write_memory(NocturneUri.parse("core://b"), "Jumps over lazy dog")
        results = repo.search("quick")
        assert len(results) == 1
        assert results[0]["node_uri"] == "core://a"

    def test_search_no_results(self, repo):
        repo.write_memory(NocturneUri.parse("core://a"), "hello world")
        results = repo.search("nonexistent")
        assert len(results) == 0
