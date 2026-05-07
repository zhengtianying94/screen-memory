"""Tests for Nocturne URI parsing and validation.

TDD order: validate errors first → happy paths → edge cases
"""

import pytest

from screen_memory.models.uri import NocturneUri


class TestNocturneUriParsing:
    """Test 3,4: Reject invalid inputs."""

    def test_reject_plain_string(self):
        with pytest.raises(ValueError, match="invalid"):
            NocturneUri.parse("not_a_uri")

    def test_reject_empty_domain(self):
        with pytest.raises(ValueError):
            NocturneUri.parse("://path")

    def test_reject_empty_string(self):
        with pytest.raises(ValueError):
            NocturneUri.parse("")

    def test_reject_whitespace_only(self):
        with pytest.raises(ValueError):
            NocturneUri.parse("   ")

    def test_reject_missing_separator(self):
        with pytest.raises(ValueError):
            NocturneUri.parse("corepath")

    def test_reject_double_slash_only(self):
        with pytest.raises(ValueError):
            NocturneUri.parse("://")


class TestNocturneUriValid:
    """Test 1,2,8: Valid URI parsing."""

    def test_parse_standard_uri(self):
        uri = NocturneUri.parse("core://my_user/identity")
        assert uri.domain == "core"
        assert uri.path == "my_user/identity"

    def test_parse_root_uri(self):
        uri = NocturneUri.parse("core://")
        assert uri.domain == "core"
        assert uri.path == ""

    def test_parse_system_uri(self):
        uri = NocturneUri.parse("system://boot")
        assert uri.domain == "system"
        assert uri.path == "boot"

    def test_parse_deep_path(self):
        uri = NocturneUri.parse("core://my_user/people/zhang_san")
        assert uri.domain == "core"
        assert uri.path == "my_user/people/zhang_san"

    def test_parse_dynamic_date(self):
        uri = NocturneUri.parse("dynamic://2026/04/28")
        assert uri.domain == "dynamic"
        assert uri.path == "2026/04/28"


class TestNocturneUriNormalize:
    """Test 5: Trailing slash normalization."""

    def test_trailing_slash_stripped(self):
        uri = NocturneUri.parse("core://my_user/")
        assert uri.path == "my_user"

    def test_no_trailing_slash_unchanged(self):
        uri = NocturneUri.parse("core://my_user")
        assert uri.path == "my_user"

    def test_root_trailing_slash(self):
        uri = NocturneUri.parse("core://")
        assert uri.path == ""


class TestNocturneUriEquality:
    """Test 6: URI equality."""

    def test_equal_uris(self):
        a = NocturneUri.parse("core://a")
        b = NocturneUri.parse("core://a")
        assert a == b

    def test_different_domain(self):
        a = NocturneUri.parse("core://a")
        b = NocturneUri.parse("dynamic://a")
        assert a != b

    def test_different_path(self):
        a = NocturneUri.parse("core://a")
        b = NocturneUri.parse("core://b")
        assert a != b

    def test_hash_equal(self):
        a = NocturneUri.parse("core://a")
        b = NocturneUri.parse("core://a")
        assert hash(a) == hash(b)


class TestNocturneUriParent:
    """Test 7: Parent-child detection."""

    def test_child_of_parent(self):
        child = NocturneUri.parse("core://a/b")
        parent = NocturneUri.parse("core://a")
        assert child.is_child_of(parent)

    def test_not_child_of_unrelated(self):
        a = NocturneUri.parse("core://a")
        b = NocturneUri.parse("core://b")
        assert not a.is_child_of(b)

    def test_not_child_of_self(self):
        uri = NocturneUri.parse("core://a/b")
        assert not uri.is_child_of(uri)

    def test_deep_child(self):
        deep = NocturneUri.parse("core://a/b/c/d")
        root = NocturneUri.parse("core://a")
        assert deep.is_child_of(root)

    def test_different_domain_not_child(self):
        a = NocturneUri.parse("core://a/b")
        b = NocturneUri.parse("dynamic://a")
        assert not a.is_child_of(b)


class TestNocturneUriMake:
    """Test URI construction."""

    def test_make_uri(self):
        uri = NocturneUri.make("core", "my_user/identity")
        assert str(uri) == "core://my_user/identity"

    def test_make_root(self):
        uri = NocturneUri.make("core", "")
        assert str(uri) == "core://"

    def test_str_roundtrip(self):
        original = "core://my_user/people/zhang_san"
        uri = NocturneUri.parse(original)
        assert str(uri) == original

    def test_parent_uri(self):
        uri = NocturneUri.parse("core://a/b/c")
        parent = uri.parent()
        assert str(parent) == "core://a/b"

    def test_parent_of_depth1(self):
        uri = NocturneUri.parse("core://a")
        parent = uri.parent()
        assert str(parent) == "core://"

    def test_parent_of_root_is_none(self):
        uri = NocturneUri.parse("core://")
        assert uri.parent() is None

    def test_leaf_name(self):
        uri = NocturneUri.parse("core://my_user/people/zhang_san")
        assert uri.leaf == "zhang_san"

    def test_leaf_of_root(self):
        uri = NocturneUri.parse("core://")
        assert uri.leaf == ""
