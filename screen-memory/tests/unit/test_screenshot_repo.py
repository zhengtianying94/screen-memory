"""Tests for ScreenshotRepo.

TDD order: error cases → CRUD → search
"""

import pytest

from screen_memory.models.uri import NocturneUri
from screen_memory.storage.database import Database
from screen_memory.storage.screenshot_repo import ScreenshotRepo


@pytest.fixture
def repo():
    db = Database(":memory:")
    db.initialize()
    return ScreenshotRepo(db)


class TestScreenshotCreate:
    def test_insert_basic(self, repo):
        s = repo.insert(file_path="/tmp/screen1.png", ocr_text="Hello world")
        assert s["id"] == 1
        assert s["file_path"] == "/tmp/screen1.png"
        assert s["ocr_text"] == "Hello world"

    def test_insert_without_ocr(self, repo):
        s = repo.insert(file_path="/tmp/screen2.png")
        assert s["ocr_text"] is None

    def test_insert_with_uri(self, repo):
        uri = NocturneUri.parse("core://a")
        # Create the node first so FK passes
        from screen_memory.storage.graph_repo import GraphRepo

        GraphRepo(repo._db).create_node(uri)
        s = repo.insert(file_path="/tmp/screen3.png", uri=uri)
        assert s["uri"] == "core://a"

    def test_duplicate_path_rejected(self, repo):
        repo.insert(file_path="/tmp/dup.png")
        with pytest.raises(Exception):  # IntegrityError
            repo.insert(file_path="/tmp/dup.png")


class TestScreenshotRead:
    def test_get_by_id(self, repo):
        repo.insert(file_path="/tmp/a.png", ocr_text="alpha")
        s = repo.get_by_id(1)
        assert s["ocr_text"] == "alpha"

    def test_get_missing_returns_none(self, repo):
        assert repo.get_by_id(999) is None

    def test_list_all(self, repo):
        repo.insert(file_path="/tmp/a.png")
        repo.insert(file_path="/tmp/b.png")
        assert len(repo.list_all()) == 2

    def test_list_by_time_range(self, repo):
        repo.insert(file_path="/tmp/a.png")
        # Query a very narrow range — should find 0
        results = repo.list_all(after="2099-01-01", before="2099-12-31")
        assert len(results) == 0


class TestScreenshotUpdate:
    def test_update_ocr(self, repo):
        repo.insert(file_path="/tmp/a.png")
        repo.update_ocr(1, "updated text")
        s = repo.get_by_id(1)
        assert s["ocr_text"] == "updated text"

    def test_link_uri(self, repo):
        from screen_memory.storage.graph_repo import GraphRepo

        uri = NocturneUri.parse("core://x")
        GraphRepo(repo._db).create_node(uri)
        repo.insert(file_path="/tmp/a.png")
        repo.link_uri(1, uri)
        s = repo.get_by_id(1)
        assert s["uri"] == "core://x"


class TestScreenshotSearch:
    def test_search_ocr_text(self, repo):
        repo.insert(file_path="/tmp/a.png", ocr_text="The quick brown fox")
        repo.insert(file_path="/tmp/b.png", ocr_text="Jumps over lazy dog")
        results = repo.search("quick")
        assert len(results) == 1

    def test_search_no_results(self, repo):
        repo.insert(file_path="/tmp/a.png", ocr_text="hello")
        assert len(repo.search("nonexistent")) == 0
