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
