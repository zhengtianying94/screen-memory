import pytest
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from screen_memory_server.main import create_app


@pytest.fixture
def client():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        app = create_app(auth_token="test-token", db_path=str(db_path))
        test_client = TestClient(app)
        yield test_client
        # Close the database connection to release file lock
        app.state.db.close()


class TestHealthEndpoint:
    def test_health(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestAuth:
    def test_push_without_token(self, client):
        resp = client.post("/api/v1/sync/push", json={"device_id": "x", "tables": {}})
        assert resp.status_code == 401

    def test_push_with_wrong_token(self, client):
        resp = client.post(
            "/api/v1/sync/push",
            json={"device_id": "x", "tables": {}},
            headers={"Authorization": "Bearer wrong"},
        )
        assert resp.status_code == 401

    def test_push_with_correct_token(self, client):
        resp = client.post(
            "/api/v1/sync/push",
            json={"device_id": "x", "tables": {}},
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200


class TestPushEndpoint:
    def test_push_empty(self, client):
        resp = client.post(
            "/api/v1/sync/push",
            json={"device_id": "device-1", "tables": {}},
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert resp.json()["received"] == {}

    def test_push_screenshots(self, client):
        resp = client.post(
            "/api/v1/sync/push",
            json={
                "device_id": "device-1",
                "tables": {
                    "screenshots": [
                        {"id": 1, "file_path": "/a.png", "ocr_text": "hello", "captured_at": "2026-05-26 10:00:00"},
                    ]
                },
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        assert resp.json()["received"]["screenshots"] == 1


class TestQueryEndpoint:
    def test_query_excludes_self(self, client):
        client.post(
            "/api/v1/sync/push",
            json={
                "device_id": "device-1",
                "tables": {
                    "screenshots": [
                        {"id": 1, "file_path": "/a.png", "ocr_text": "hello", "captured_at": "2026-05-26 10:00:00"},
                    ]
                },
            },
            headers={"Authorization": "Bearer test-token"},
        )
        resp = client.post(
            "/api/v1/sync/query",
            json={"device_id": "device-1", "table": "screenshots", "query": {}, "exclude_self": True},
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        assert resp.json()["results"] == []

    def test_query_returns_other_device(self, client):
        client.post(
            "/api/v1/sync/push",
            json={
                "device_id": "device-1",
                "tables": {
                    "screenshots": [
                        {"id": 1, "file_path": "/a.png", "ocr_text": "hello", "captured_at": "2026-05-26 10:00:00"},
                    ]
                },
            },
            headers={"Authorization": "Bearer test-token"},
        )
        resp = client.post(
            "/api/v1/sync/query",
            json={"device_id": "device-2", "table": "screenshots", "query": {}, "exclude_self": True},
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 1
        assert results[0]["device_id"] == "device-1"


class TestStatusEndpoint:
    def test_status(self, client):
        client.post(
            "/api/v1/sync/push",
            json={
                "device_id": "device-1",
                "tables": {
                    "screenshots": [
                        {"id": 1, "file_path": "/a.png", "ocr_text": "hello", "captured_at": "2026-05-26 10:00:00"},
                    ]
                },
            },
            headers={"Authorization": "Bearer test-token"},
        )
        resp = client.get(
            "/api/v1/sync/status?device_id=device-1",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["devices"]) == 1
        assert data["devices"][0]["device_id"] == "device-1"
