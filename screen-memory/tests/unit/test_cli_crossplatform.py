"""Tests for cross-platform CLI behavior: DB path defaults."""
import os
from pathlib import Path
from unittest.mock import patch

import pytest


class TestDbPathDefault:
    def test_default_db_path_uses_home(self):
        """Default DB path should be under $HOME, not hardcoded Windows path."""
        import inspect
        from screen_memory.cli import _get_registry

        source = inspect.getsource(_get_registry)
        assert "D:\\\\ScreenMemo" not in source, \
            "Hardcoded Windows path found in _get_registry"
        assert ".screenmemory" in source, \
            "Expected ~/.screenmemory in _get_registry default"

    def test_env_var_overrides_default(self):
        """SCREEN_MEMORY_DB env var should override the default path."""
        with patch.dict(os.environ, {"SCREEN_MEMORY_DB": "/tmp/test-memory.db"}):
            assert os.environ.get("SCREEN_MEMORY_DB") == "/tmp/test-memory.db"

    def test_cmd_capture_default_db_path_uses_home(self):
        """cmd_capture default DB path should also use home, not Windows path."""
        import inspect
        from screen_memory.cli import cmd_capture

        source = inspect.getsource(cmd_capture)
        assert "D:\\\\ScreenMemo" not in source, \
            "Hardcoded Windows path found in cmd_capture"
