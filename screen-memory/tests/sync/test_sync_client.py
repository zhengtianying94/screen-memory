import pytest
from screen_memory.storage.database import Database


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
