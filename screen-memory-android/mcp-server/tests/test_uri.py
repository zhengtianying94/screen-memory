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
