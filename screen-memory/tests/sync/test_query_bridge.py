import pytest
from unittest.mock import patch, MagicMock
from screen_memory.sync.query_bridge import QueryBridge


@pytest.fixture
def bridge():
    return QueryBridge("http://localhost:8200", "test-token", "device-1")


class TestQueryBridgeQuery:
    @patch("screen_memory.sync.query_bridge.httpx")
    def test_query_calls_server(self, mock_httpx, bridge):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": [{"id": 1, "ocr_text": "hello"}]}
        mock_httpx.post.return_value = mock_resp

        results = bridge.query("screenshots", {}, exclude_self=True)
        assert len(results) == 1
        mock_httpx.post.assert_called_once()

    @patch("screen_memory.sync.query_bridge.httpx")
    def test_query_returns_empty_on_error(self, mock_httpx, bridge):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_httpx.post.return_value = mock_resp

        results = bridge.query("screenshots", {})
        assert results == []

    @patch("screen_memory.sync.query_bridge.httpx")
    def test_query_returns_empty_on_exception(self, mock_httpx, bridge):
        mock_httpx.post.side_effect = Exception("connection failed")

        results = bridge.query("screenshots", {})
        assert results == []


class TestQueryBridgeListDevices:
    @patch("screen_memory.sync.query_bridge.httpx")
    def test_list_devices(self, mock_httpx, bridge):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"devices": [{"device_id": "device-2"}]}
        mock_httpx.get.return_value = mock_resp

        devices = bridge.list_devices()
        assert len(devices) == 1
        assert devices[0]["device_id"] == "device-2"

    @patch("screen_memory.sync.query_bridge.httpx")
    def test_list_devices_returns_empty_on_error(self, mock_httpx, bridge):
        mock_httpx.get.side_effect = Exception("fail")

        devices = bridge.list_devices()
        assert devices == []
