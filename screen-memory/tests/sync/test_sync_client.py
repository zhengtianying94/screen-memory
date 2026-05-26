import pytest
from screen_memory.storage.database import Database
from screen_memory.sync.client import SyncClient, SYNC_TABLE_CONFIG


@pytest.fixture
def db():
    database = Database(":memory:")
    database.initialize()
    return database


class TestSyncStateTable:
    def test_sync_state_table_exists(self, db):
        tables = [r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sync_state'"
        ).fetchall()]
        assert "sync_state" in tables

    def test_sync_state_read_write(self, db):
        db.execute("INSERT INTO sync_state (key, value) VALUES ('last_sync_time', '0')")
        row = db.execute("SELECT value FROM sync_state WHERE key='last_sync_time'").fetchone()
        assert row[0] == "0"


class TestDetectChanges:
    def test_no_changes_returns_empty(self, db):
        client = SyncClient(db, "http://localhost:8200", "token")
        changes = client.detect_changes()
        assert changes == {}

    def test_detects_new_screenshot(self, db):
        db.execute("INSERT INTO screenshots (file_path, ocr_text) VALUES ('/a.png', 'hello')")
        client = SyncClient(db, "http://localhost:8200", "token")
        changes = client.detect_changes()
        assert "screenshots" in changes
        assert len(changes["screenshots"]) == 1

    def test_detects_new_memory(self, db):
        db.execute("INSERT INTO nodes (uri, domain, path) VALUES ('core://a', 'core', 'a')")
        db.execute("INSERT INTO memories (node_uri, content, version) VALUES ('core://a', 'hello', 1)")
        client = SyncClient(db, "http://localhost:8200", "token")
        changes = client.detect_changes()
        assert "nodes" in changes
        assert "memories" in changes

    def test_no_duplicate_detection_after_sync(self, db):
        db.execute("INSERT INTO screenshots (file_path, ocr_text) VALUES ('/a.png', 'hello')")
        client = SyncClient(db, "http://localhost:8200", "token")
        changes1 = client.detect_changes()
        assert "screenshots" in changes1
        client._update_last_sync_time()
        changes2 = client.detect_changes()
        assert changes2 == {}

    def test_detects_new_path_rows(self, db):
        db.execute("INSERT INTO nodes (uri, domain, path) VALUES ('core://a', 'core', 'a')")
        db.execute("INSERT INTO nodes (uri, domain, path) VALUES ('core://a/b', 'core', 'a/b')")
        db.execute("INSERT INTO paths (ancestor_uri, descendant_uri, depth) VALUES ('core://a', 'core://a/b', 1)")
        client = SyncClient(db, "http://localhost:8200", "token")
        changes = client.detect_changes()
        assert "paths" in changes

    def test_detects_new_entity(self, db):
        db.execute(
            "INSERT INTO entities (entity_type, name) VALUES ('person', 'Alice')"
        )
        client = SyncClient(db, "http://localhost:8200", "token")
        changes = client.detect_changes()
        assert "entities" in changes


class TestGetDeviceId:
    def test_generates_device_id(self, db):
        client = SyncClient(db, "http://localhost:8200", "token")
        device_id = client.get_device_id()
        assert device_id
        assert "-" in device_id

    def test_device_id_persists(self, db):
        client = SyncClient(db, "http://localhost:8200", "token")
        id1 = client.get_device_id()
        id2 = client.get_device_id()
        assert id1 == id2
