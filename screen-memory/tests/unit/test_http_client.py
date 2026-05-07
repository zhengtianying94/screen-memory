# tests/unit/test_http_client.py
"""Tests for ScreenMemoryHttpClient: urllib-based HTTP with retry."""

import json
from unittest.mock import patch, MagicMock

import pytest

from screen_memory.adapters.http_client import ScreenMemoryHttpClient


class TestHttpGet:
    def test_get_success(self):
        """GET request returns parsed JSON dict."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({"running": True}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("screen_memory.adapters.http_client.urllib.request.urlopen", return_value=mock_response):
            client = ScreenMemoryHttpClient("http://localhost:19700")
            result = client.get("/status")
            assert result == {"running": True}

    def test_get_constructs_correct_url(self):
        """GET uses base_url + path as the full URL."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b"{}"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("screen_memory.adapters.http_client.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = mock_response
            client = ScreenMemoryHttpClient("http://localhost:19700")
            client.get("/status")
            call_args = mock_urlopen.call_args[0][0]
            assert call_args.full_url == "http://localhost:19700/status"


class TestHttpPost:
    def test_post_success(self):
        """POST request sends JSON body and returns parsed response."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({"text": "hello"}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("screen_memory.adapters.http_client.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = mock_response
            client = ScreenMemoryHttpClient("http://localhost:19700")
            result = client.post("/ocr", {"image": "base64data"})
            assert result == {"text": "hello"}
            # Verify POST method was used
            request_obj = mock_urlopen.call_args[0][0]
            assert request_obj.method == "POST"


class TestRetry:
    def test_retry_succeeds_on_second_attempt(self):
        """Retry recovers from first failure."""
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("refused")
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.read.return_value = json.dumps({"ok": True}).encode()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            return mock_response

        with patch("screen_memory.adapters.http_client.urllib.request.urlopen", side_effect=side_effect):
            with patch("screen_memory.adapters.http_client.time.sleep"):
                client = ScreenMemoryHttpClient("http://localhost:19700", retries=2)
                result = client.get("/status")
                assert result == {"ok": True}
                assert call_count == 2

    def test_retry_exhausted_raises_connection_error(self):
        """After all retries fail, raises ConnectionError."""
        with patch(
            "screen_memory.adapters.http_client.urllib.request.urlopen",
            side_effect=ConnectionError("refused"),
        ):
            with patch("screen_memory.adapters.http_client.time.sleep"):
                client = ScreenMemoryHttpClient("http://localhost:19700", retries=2)
                with pytest.raises(ConnectionError, match="refused"):
                    client.get("/status")


class TestIsReachable:
    def test_reachable(self):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b"{}"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("screen_memory.adapters.http_client.urllib.request.urlopen", return_value=mock_response):
            client = ScreenMemoryHttpClient("http://localhost:19700", timeout=5)
            assert client.is_reachable() is True

    def test_not_reachable(self):
        with patch(
            "screen_memory.adapters.http_client.urllib.request.urlopen",
            side_effect=Exception("connection failed"),
        ):
            client = ScreenMemoryHttpClient("http://localhost:19700")
            assert client.is_reachable() is False
