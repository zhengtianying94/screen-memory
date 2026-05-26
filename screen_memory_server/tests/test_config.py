import tempfile
import os


def test_load_config_from_yaml():
    """Config loads all fields from a YAML file."""
    from screen_memory_server.config import SyncConfig

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("""
server:
  host: "127.0.0.1"
  port: 9999
  auth_token: "test-token"
database:
  path: "/tmp/test.db"
sync:
  max_batch_size: 50
""")
        f.flush()
        cfg = SyncConfig.from_yaml(f.name)

    assert cfg.host == "127.0.0.1"
    assert cfg.port == 9999
    assert cfg.auth_token == "test-token"
    assert cfg.db_path == "/tmp/test.db"
    assert cfg.max_batch_size == 50
    os.unlink(f.name)


def test_config_defaults():
    """Config uses sensible defaults when fields are missing."""
    from screen_memory_server.config import SyncConfig

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("server:\n  auth_token: 't'\n")
        f.flush()
        cfg = SyncConfig.from_yaml(f.name)

    assert cfg.host == "0.0.0.0"
    assert cfg.port == 8200
    assert cfg.db_path == "./data/screen-memory-sync.db"
    assert cfg.max_batch_size == 100
    os.unlink(f.name)
