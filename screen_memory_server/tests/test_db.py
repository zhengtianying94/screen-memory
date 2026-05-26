import pytest
from screen_memory_server.db import SyncDatabase


@pytest.fixture
def sdb():
    db = SyncDatabase(":memory:")
    db.initialize()
    return db


class TestSyncDatabaseInit:
    def test_tables_created(self, sdb):
        tables = sdb.list_tables()
        for t in ["nodes", "memories", "edges", "paths", "entities", "screenshots"]:
            assert t in tables

    def test_sync_state_table_exists(self, sdb):
        tables = sdb.list_tables()
        assert "sync_state" in tables


class TestPushRecords:
    def test_push_screenshots(self, sdb):
        records = [
            {"id": 1, "file_path": "/a.png", "ocr_text": "hello", "captured_at": "2026-05-26 10:00:00"},
            {"id": 2, "file_path": "/b.png", "ocr_text": "world", "captured_at": "2026-05-26 10:01:00"},
        ]
        sdb.push_records("device-1", "screenshots", records)
        results = sdb.query_records("screenshots", exclude_device=None)
        assert len(results) == 2
        assert results[0]["device_id"] == "device-1"

    def test_push_nodes(self, sdb):
        records = [
            {"uri": "core://test/a", "domain": "core", "path": "test/a", "created_at": "2026-05-26 10:00:00", "updated_at": "2026-05-26 10:00:00"},
        ]
        sdb.push_records("device-1", "nodes", records)
        results = sdb.query_records("nodes", exclude_device=None)
        assert len(results) == 1


class TestQueryRecords:
    def test_query_excludes_device(self, sdb):
        sdb.push_records("device-1", "screenshots", [
            {"id": 1, "file_path": "/a.png", "ocr_text": "hello", "captured_at": "2026-05-26 10:00:00"},
        ])
        sdb.push_records("device-2", "screenshots", [
            {"id": 2, "file_path": "/b.png", "ocr_text": "world", "captured_at": "2026-05-26 10:01:00"},
        ])
        results = sdb.query_records("screenshots", exclude_device="device-1")
        assert len(results) == 1
        assert results[0]["device_id"] == "device-2"

    def test_query_with_filter(self, sdb):
        sdb.push_records("device-1", "screenshots", [
            {"id": 1, "file_path": "/a.png", "ocr_text": "hello world", "captured_at": "2026-05-26 10:00:00"},
            {"id": 2, "file_path": "/b.png", "ocr_text": "goodbye", "captured_at": "2026-05-26 10:01:00"},
        ])
        results = sdb.query_records("screenshots", exclude_device=None, filters={"ocr_text LIKE": "%hello%"})
        assert len(results) == 1


class TestSyncStatus:
    def test_status_returns_devices(self, sdb):
        sdb.push_records("device-1", "screenshots", [
            {"id": 1, "file_path": "/a.png", "ocr_text": "hello", "captured_at": "2026-05-26 10:00:00"},
        ])
        sdb.push_records("device-2", "nodes", [
            {"uri": "core://x", "domain": "core", "path": "x", "created_at": "2026-05-26 10:00:00", "updated_at": "2026-05-26 10:00:00"},
        ])
        status = sdb.get_status()
        assert len(status) == 2
        devices = [s["device_id"] for s in status]
        assert "device-1" in devices
        assert "device-2" in devices
