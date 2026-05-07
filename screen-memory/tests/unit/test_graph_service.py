"""Tests for GraphService: higher-level URI Graph operations.

TDD order: subtree queries → path materialization → bulk create → traversal
"""

import pytest

from screen_memory.models.uri import NocturneUri
from screen_memory.storage.database import Database
from screen_memory.storage.graph_repo import GraphRepo
from screen_memory.services.graph_service import GraphService


@pytest.fixture
def svc():
    db = Database(":memory:")
    db.initialize()
    repo = GraphRepo(db)
    return GraphService(repo)


def _u(raw: str) -> NocturneUri:
    return NocturneUri.parse(raw)


# -- Subtree read ------------------------------------------------------------


class TestGetSubtree:
    def test_single_node(self, svc):
        svc.write("core://a", "hello")
        tree = svc.get_subtree(_u("core://a"))
        assert tree["uri"] == "core://a"
        assert tree["content"] == "hello"
        assert tree["children"] == []

    def test_nested_children(self, svc):
        svc.write("core://a", "root")
        svc.write("core://a/b", "child1")
        svc.write("core://a/b/c", "grandchild")
        svc.write("core://a/d", "child2")
        tree = svc.get_subtree(_u("core://a"))
        assert len(tree["children"]) == 2
        # child1 has its own child
        child1 = next(c for c in tree["children"] if c["uri"] == "core://a/b")
        assert len(child1["children"]) == 1

    def test_empty_subtree(self, svc):
        tree = svc.get_subtree(_u("core://ghost"))
        assert tree is None

    def test_subtree_depth_limit(self, svc):
        svc.write("core://a", "root")
        svc.write("core://a/b", "child")
        svc.write("core://a/b/c", "grandchild")
        tree = svc.get_subtree(_u("core://a"), max_depth=1)
        assert len(tree["children"]) == 1
        assert tree["children"][0]["children"] == []


class TestGetChildren:
    def test_direct_children_only(self, svc):
        svc.write("core://a", "root")
        svc.write("core://a/b", "child")
        svc.write("core://a/b/c", "grandchild")
        svc.write("core://a/d", "child2")
        children = svc.get_children(_u("core://a"))
        uris = [c["uri"] for c in children]
        assert "core://a/b" in uris
        assert "core://a/d" in uris
        assert "core://a/b/c" not in uris

    def test_no_children(self, svc):
        svc.write("core://a", "leaf")
        assert svc.get_children(_u("core://a")) == []


# -- Path materialization ----------------------------------------------------


class TestPathMaterialization:
    def test_write_materializes_paths(self, svc):
        svc.write("core://a/b/c", "deep")
        # Should have materialized paths for a→b/c, a/b→b/c, and a→b
        paths = svc.get_ancestors(_u("core://a/b/c"))
        ancestor_uris = [p["ancestor_uri"] for p in paths]
        assert "core://a" in ancestor_uris
        assert "core://a/b" in ancestor_uris

    def test_root_has_no_ancestors(self, svc):
        svc.write("core://a", "root")
        assert svc.get_ancestors(_u("core://a")) == []

    def test_ancestors_at_correct_depth(self, svc):
        svc.write("core://a/b/c", "deep")
        paths = svc.get_ancestors(_u("core://a/b/c"))
        depth_map = {p["ancestor_uri"]: p["depth"] for p in paths}
        assert depth_map["core://a/b"] == 1
        assert depth_map["core://a"] == 2


class TestGetDescendants:
    def test_descendants_via_paths(self, svc):
        svc.write("core://a", "root")
        svc.write("core://a/b", "child")
        svc.write("core://a/b/c", "grandchild")
        descs = svc.get_descendants(_u("core://a"))
        uris = [d["descendant_uri"] for d in descs]
        assert "core://a/b" in uris
        assert "core://a/b/c" in uris

    def test_leaf_has_no_descendants(self, svc):
        svc.write("core://a/b", "leaf")
        assert svc.get_descendants(_u("core://a/b")) == []


# -- Bulk create -------------------------------------------------------------


class TestBulkCreate:
    def test_create_multiple_nodes(self, svc):
        uris = ["core://a", "core://b", "core://c"]
        results = svc.bulk_create(uris)
        assert len(results) == 3

    def test_bulk_with_memories(self, svc):
        items = [
            ("core://x", "content x"),
            ("core://y", "content y"),
        ]
        results = svc.bulk_write(items)
        assert len(results) == 2
        assert svc.read("core://x")["content"] == "content x"

    def test_bulk_idempotent(self, svc):
        svc.bulk_create(["core://a"])
        svc.bulk_create(["core://a", "core://b"])
        nodes = svc.list_nodes("core")
        uris = [n["uri"] for n in nodes]
        # No duplicates — core:// root + a + b
        assert len(uris) == len(set(uris))
        assert "core://a" in uris
        assert "core://b" in uris


# -- Traversal ---------------------------------------------------------------


class TestTraverse:
    def test_breadth_first(self, svc):
        svc.write("core://a", "root")
        svc.write("core://a/b", "child")
        svc.write("core://a/c", "child2")
        svc.write("core://a/b/d", "grandchild")
        nodes = svc.traverse(_u("core://a"), strategy="bfs")
        uris = [n["uri"] for n in nodes]
        assert uris[0] == "core://a"
        # b and c come before d
        assert uris.index("core://a/b") < uris.index("core://a/b/d")
        assert uris.index("core://a/c") < uris.index("core://a/b/d")

    def test_depth_first(self, svc):
        svc.write("core://a", "root")
        svc.write("core://a/b", "child")
        svc.write("core://a/b/c", "grandchild")
        svc.write("core://a/d", "child2")
        nodes = svc.traverse(_u("core://a"), strategy="dfs")
        uris = [n["uri"] for n in nodes]
        assert uris[0] == "core://a"
        # dfs: a → b → c → d (or a → d → b → c depending on order)
        # Just verify all are visited
        assert len(uris) == 4

    def test_traverse_with_max_depth(self, svc):
        svc.write("core://a", "root")
        svc.write("core://a/b", "child")
        svc.write("core://a/b/c", "grandchild")
        nodes = svc.traverse(_u("core://a"), max_depth=1)
        uris = [n["uri"] for n in nodes]
        assert "core://a/b/c" not in uris
