"""End-to-end sync tests: push from client, query via server."""

import sys
import os
import pytest

# Add server package to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "screen_memory_server"))

from fastapi.testclient import TestClient
from screen_memory_server.main import create_app

from screen_memory.storage.database import Database
from screen_memory.sync.client import SyncClient


@pytest.fixture
def server():
    """Create a test server with in-memory DB."""
    app = create_app(auth_token="e2e-test-token", db_path=":memory:")
    return TestClient(app)


@pytest.fixture
def device_db():
    db = Database(":memory:")
    db.initialize()
    return db


class TestE2EPushQuery:
    def test_push_screenshots_then_query(self, server, device_db):
        """Device pushes screenshots, another device queries them."""
        # Insert data on device
        device_db.execute("INSERT INTO screenshots (file_path, ocr_text) VALUES ('/phone.png', 'mobile screen text')")

        # Create sync client and detect changes
        client = SyncClient(device_db, "http://test", "e2e-test-token")
        changes = client.detect_changes()
        assert "screenshots" in changes

        # Push to server
        resp = server.post(
            "/api/v1/sync/push",
            json={"device_id": client.get_device_id(), "tables": changes},
            headers={"Authorization": "Bearer e2e-test-token"},
        )
        assert resp.status_code == 200
        assert resp.json()["received"]["screenshots"] >= 1

        # Query from another device
        resp = server.post(
            "/api/v1/sync/query",
            json={"device_id": "other-device", "table": "screenshots", "query": {}, "exclude_self": True},
            headers={"Authorization": "Bearer e2e-test-token"},
        )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) >= 1
        assert any("mobile screen text" in (r.get("ocr_text") or "") for r in results)

    def test_push_nodes_then_query(self, server, device_db):
        """Device pushes nodes, another device queries them."""
        device_db.execute("INSERT INTO nodes (uri, domain, path) VALUES ('core://meeting/standup', 'core', 'meeting/standup')")

        client = SyncClient(device_db, "http://test", "e2e-test-token")
        changes = client.detect_changes()

        resp = server.post(
            "/api/v1/sync/push",
            json={"device_id": client.get_device_id(), "tables": changes},
            headers={"Authorization": "Bearer e2e-test-token"},
        )
        assert resp.status_code == 200

        resp = server.post(
            "/api/v1/sync/query",
            json={"device_id": "other-device", "table": "nodes", "query": {}, "exclude_self": True},
            headers={"Authorization": "Bearer e2e-test-token"},
        )
        results = resp.json()["results"]
        assert any(r.get("uri") == "core://meeting/standup" for r in results)

    def test_status_shows_both_devices(self, server, device_db):
        """Status endpoint shows devices that have pushed data."""
        server.post(
            "/api/v1/sync/push",
            json={"device_id": "device-1", "tables": {"screenshots": [
                {"id": 1, "file_path": "/a.png", "ocr_text": "hello", "captured_at": "2026-05-26 10:00:00"}
            ]}},
            headers={"Authorization": "Bearer e2e-test-token"},
        )
        server.post(
            "/api/v1/sync/push",
            json={"device_id": "device-2", "tables": {"nodes": [
                {"uri": "core://x", "domain": "core", "path": "x", "created_at": "2026-05-26 10:00:00", "updated_at": "2026-05-26 10:00:00"}
            ]}},
            headers={"Authorization": "Bearer e2e-test-token"},
        )

        resp = server.get(
            "/api/v1/sync/status?device_id=device-1",
            headers={"Authorization": "Bearer e2e-test-token"},
        )
        devices = resp.json()["devices"]
        device_ids = [d["device_id"] for d in devices]
        assert "device-1" in device_ids
        assert "device-2" in device_ids
