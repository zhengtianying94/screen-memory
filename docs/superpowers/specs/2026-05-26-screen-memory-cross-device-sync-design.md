# Screen Memory Cross-Device Sync Design

Date: 2026-05-26

## Background

The OpenClaw screen memory plugin has completed Windows and Android versions. All memories are stored locally on each device with no cross-device communication. Users need the ability to access screen memories across devices — e.g., checking what the computer captured from the phone.

## Requirements

- **Server**: Self-built VPS, can deploy any service
- **Usage mode**: Background sync (push local changes to server) + real-time cross-device query
- **Data scope**: All tables (screenshots, Nocturne graph nodes/memories/edges/paths, entities)
- **Scale**: Personal use, 2-3 devices
- **Privacy**: Plaintext for now, design must accommodate future encryption
- **Development approach**: SDD + TDD

## Architecture Overview

```
[Windows] ──push──→ [Server API] ←──push── [Android]
    │                     │                     │
  Local DB            Server DB              Local DB
  (own data)       (all devices)            (own data)
    │                     ↑                     │
    └──── OpenClaw tools ─┘── real-time query ──┘
```

**Core principles:**
- **Unidirectional push**: Devices only push changes to server, never pull other devices' data locally
- **Local-first**: Local data reads/writes stay on local SQLite, preserving performance and offline capability
- **Remote query**: Cross-device data queried via server API, results not persisted locally

**Three components:**

| Component | Responsibility | Location |
|-----------|---------------|----------|
| Sync Client | Detect local changes, push to server | Device-side |
| Sync Server | Receive pushes, store all data, serve query API | Self-built server |
| Query Bridge | Remote query extension for OpenClaw tools | Device-side |

## Data Flow

1. Device captures screen memory → writes local DB (existing pipeline, unchanged)
2. Sync Client periodically checks for new data → pushes to Server
3. Server receives → stores in server DB (with device_id) → returns acknowledgment
4. User triggers cross-device query → OpenClaw tool calls Server API via Query Bridge
5. Server queries → returns results → tool returns to user (not written to local DB)

## Sync Push Timing

Three triggers, combined:

| Trigger | When | Purpose |
|---------|------|---------|
| **Periodic polling** | Every 30s (configurable) | Continuous sync during normal operation |
| **On-demand flush** | Before cross-device query | Ensure server has latest data before querying |
| **Shutdown flush** | Sync Client exit | Final push to avoid data loss (10s timeout) |

### Sync State Storage

A single metadata table on the device:

```sql
CREATE TABLE IF NOT EXISTS sync_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- Stores: last_sync_time, device_id
```

### Polling Logic

```
Sync Client background loop (every 30s):
  1. Read last_sync_time from sync_state
  2. For each table, query using its designated timestamp column:
     SELECT * FROM screenshots WHERE captured_at > {last_sync_time}
     SELECT * FROM nodes WHERE updated_at > {last_sync_time}
     SELECT * FROM memories WHERE created_at > {last_sync_time}
     SELECT * FROM edges WHERE created_at > {last_sync_time}
     SELECT * FROM paths WHERE id > {last_sync_max_rowid}  -- no timestamp column
     SELECT * FROM entities WHERE updated_at > {last_sync_time}
  3. If all tables have no new data → skip, wait next round
  4. If new data exists → batch push to Server
  5. Server returns success → update last_sync_time to now
  6. Failure → don't update last_sync_time, retry in 30s
```

### SYNC_TABLES and Change Detection Columns

Each table uses a different timestamp column for change detection. The `paths` table has no timestamp column and uses rowid comparison instead.

```python
SYNC_TABLE_CONFIG = {
    "screenshots": {"column": "captured_at"},
    "nodes":       {"column": "updated_at"},
    "memories":    {"column": "created_at"},
    "edges":       {"column": "created_at"},
    "paths":       {"column": None},          # use rowid comparison
    "entities":    {"column": "updated_at"},
}
```

## Server Design

### Tech Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Web framework | FastAPI | Python, consistent with device-side, high dev efficiency |
| Database | SQLite | Sufficient for 2-3 personal devices, simple ops |
| Deployment | Docker | One-command deploy on self-built server |

### Server Database Schema

Same structure as device-side tables, with two additional columns per table:

```sql
-- Added to every synced table
device_id TEXT NOT NULL,       -- Source device identifier
synced_at REAL NOT NULL        -- Server receipt timestamp
```

Example for screenshots:

```sql
CREATE TABLE screenshots (
    -- Original fields (same as device-side)
    id TEXT PRIMARY KEY,
    capture_time REAL,
    window_title TEXT,
    ocr_text TEXT,
    file_path TEXT,
    -- Sync extension fields
    device_id TEXT NOT NULL,
    synced_at REAL NOT NULL
);
```

### API Design

```
POST /api/v1/sync/push          -- Device pushes changes
  Request:  { device_id, tables: { screenshots: [...], nodes: [...], ... } }
  Response: { ok: true, received: { screenshots: 5, nodes: 2 } }

POST /api/v1/sync/query         -- Cross-device query
  Request:  { device_id, table: "screenshots", query: {...}, exclude_self: true }
  Response: { results: [...] }

GET  /api/v1/sync/status        -- Sync status
  Request:  ?device_id=xxx
  Response: { devices: [{ device_id, last_sync, record_counts }] }

GET  /api/v1/health             -- Health check
```

### Device ID Management

Each device generates a unique ID on first startup: `{platform}-{name}-{random}`, e.g. `windows-my-pc-a3f1`. Stored in device-side `sync_state` table.

### Server Configuration

```yaml
server:
  host: 0.0.0.0
  port: 8200
  auth_token: "a-random-secret-token"
database:
  path: ./data/screen-memory-sync.db
sync:
  max_batch_size: 100
  cleanup_days: 30
```

### Authentication

Bearer token (shared across all devices). API requests include `Authorization: Bearer {token}`. Pre-designed for future upgrade to per-device tokens or encrypted channels.

## Device-Side Sync Client Design

### File Structure

```
screen_memory/
  sync/
    __init__.py
    client.py          # SyncClient: polling + push + shutdown flush
    query_bridge.py    # QueryBridge: remote query wrapper
    config.py          # Sync config (server URL, token, interval)
```

### SyncClient Interface

```python
class SyncClient:
    def __init__(self, db_path: str, server_url: str, token: str, interval: float = 30.0)

    def start(self)          # Start background push thread
    def stop(self)           # Graceful stop (final push, 10s timeout)
    def flush(self)          # Manual push trigger (before cross-device query)
    def get_device_id(self)  # Get/generate device_id
```

### Change Detection

```python
def detect_changes(self) -> dict[str, list]:
    last_time = self._get_last_sync_time()
    changes = {}
    for table, config in SYNC_TABLE_CONFIG.items():
        if config["column"]:
            rows = self.db.execute(
                f"SELECT * FROM {table} WHERE {config['column']} > ?", (last_time,)
            ).fetchall()
        else:
            # paths table: use rowid comparison
            last_rowid = self._get_last_sync_rowid(table)
            rows = self.db.execute(
                f"SELECT * FROM {table} WHERE id > ?", (last_rowid,)
            ).fetchall()
        if rows:
            changes[table] = rows
    return changes
```

### Push Execution

```python
def push(self, changes: dict) -> bool:
    resp = http_post(
        f"{self.server_url}/api/v1/sync/push",
        json={"device_id": self.device_id, "tables": changes},
        headers={"Authorization": f"Bearer {self.token}"}
    )
    if resp.ok:
        self._update_last_sync_time(time.time())
    return resp.ok
```

### QueryBridge Interface

```python
class QueryBridge:
    def __init__(self, server_url: str, token: str, device_id: str)

    def query(self, table: str, filters: dict, exclude_self: bool = True) -> list
    # Flush first, then query

    def list_devices(self) -> list
    # List devices on server
```

### Configuration

```bash
# Environment variables
SCREEN_MEMORY_SYNC_URL=http://47.118.19.85:8200
SCREEN_MEMORY_SYNC_TOKEN=your-secret-token
SCREEN_MEMORY_SYNC_INTERVAL=30
```

## OpenClaw Tools Extension

### Changed Tools

| Tool | Change | Description |
|------|--------|-------------|
| `memory_read` | Add `scope` param | Optional remote query |
| `memory_search` | Add `scope` param | Optional remote search |
| `graph_query_subtree` | Add `scope` param | Optional remote query |
| `screenshot_search` | Add `scope` param | Optional remote search |

### Unchanged Tools

`memory_write`, `memory_delete`, `signal_ingest`, `signal_activate` — local-only, no changes needed.

### Scope Parameter

```python
# scope values:
"local"     # Default, query local only (backward compatible)
"remote"    # Query other devices' data via server
"all"       # Local + remote, merge and deduplicate
```

Example — `memory_search`:

```python
# Before
memory_search(query: str, limit: int = 10)

# After
memory_search(query: str, limit: int = 10, scope: str = "local")
```

### Execution Logic

```
scope = "local"  → existing local query (unchanged)
scope = "remote" → call QueryBridge to query server
scope = "all"    → local query + remote query, merge and deduplicate
```

### New Tool: sync_status

```python
sync_status()
# Returns:
{
    "device_id": "windows-my-pc-a3f1",
    "last_sync_time": "2026-05-26T10:30:00",
    "pending_changes": 0,
    "server_reachable": true,
    "devices": [
        {"device_id": "android-phone-1", "last_sync": "2026-05-26T10:29:00", "records": 1523},
        {"device_id": "windows-my-pc-a3f1", "last_sync": "2026-05-26T10:30:00", "records": 892}
    ]
}
```

### Backward Compatibility

`scope` defaults to `"local"`. Existing callers pass no parameter and get unchanged behavior.

## Testing Strategy (TDD)

### Test Layers

```
┌─────────────────────────────────────┐
│          E2E Tests (few)             │  Full: real Server + Client,
│          pytest + real HTTP          │  verify push-query flow
├─────────────────────────────────────┤
│     Integration Tests (moderate)     │  Server API: FastAPI TestClient
│     pytest + TestClient              │  Client integration: in-memory SQLite + mock HTTP
├─────────────────────────────────────┤
│          Unit Tests (many)           │  Change detection, push logic,
│     pytest                           │  query merge, scope routing, config parsing
└─────────────────────────────────────┘
```

### Test Files

```
screen-memory/tests/sync/
  test_sync_client.py            # Platform-agnostic: change detection, push, retry
  test_query_bridge.py           # Platform-agnostic: remote query
  test_server_api.py             # Platform-agnostic: Server API
  test_tools_remote.py           # Platform-agnostic: tool scope extension
  test_sync_windows.py           # Windows-specific: sleep resume, signal handling
  test_sync_android.py           # Android-specific: Termux restart, network switch
  test_e2e_sync.py               # Cross-device E2E: push from one, query from other
```

### TDD Development Order

| Round | Write test first | Then implement | Verify |
|-------|-----------------|----------------|--------|
| 1 | Server API tests | Server push/query/status endpoints | Tests pass |
| 2 | Change detection tests | SyncClient detect_changes | Tests pass |
| 3 | Push execution tests (mock HTTP) | SyncClient push + retry | Tests pass |
| 4 | QueryBridge tests (mock HTTP) | QueryBridge remote query | Tests pass |
| 5 | Tool scope routing tests | memory_search/screenshot_search extension | Tests pass |
| 6 | E2E tests | Full flow integration | Tests pass |

### Key Test Cases

```python
# 1. No changes detected
def test_detect_changes_no_new_data(sync_client, db_with_existing_data):
    changes = sync_client.detect_changes()
    assert changes == {}

# 2. New record detected
def test_detect_changes_with_new_screenshot(sync_client, db):
    db.insert_screenshot(...)
    changes = sync_client.detect_changes()
    assert "screenshots" in changes
    assert len(changes["screenshots"]) == 1

# 3. Push success updates last_sync_time
def test_push_updates_sync_time(sync_client, mock_server):
    mock_server.expect_push(success=True)
    sync_client.push({"screenshots": [...]})
    assert sync_client.last_sync_time > previous_time

# 4. Push failure keeps last_sync_time
def test_push_failure_keeps_sync_time(sync_client, mock_server):
    mock_server.expect_push(success=False)
    sync_client.push({"screenshots": [...]})
    assert sync_client.last_sync_time == previous_time

# 5. scope="local" uses local query
def test_search_scope_local(query_tool, local_db):
    results = query_tool.search("test", scope="local")
    # Only local, no remote call

# 6. scope="remote" queries server
def test_search_scope_remote(query_tool, mock_bridge):
    mock_bridge.expect_query(results=[...])
    results = query_tool.search("test", scope="remote")
    assert mock_bridge.query_called

# 7. scope="all" merges and deduplicates
def test_search_scope_all_merges(query_tool, local_db, mock_bridge):
    # Local has A, B; remote has B, C → merged result: A, B, C

# 8. E2E: push then query
def test_push_then_query(real_server, sync_client):
    sync_client.push({"screenshots": [screenshot_data]})
    results = real_server.query("screenshots", exclude_device=sync_client.device_id)
    assert len(results) == 1

# 9. Shutdown flush
def test_stop_flushes_pending(sync_client, db):
    db.insert_screenshot(...)
    sync_client.stop()
    assert sync_client.get_pending_count() == 0

# 10. Android: resume after Termux restart
def test_sync_resumes_after_termux_restart(sync_client):
    # Leftover unpushed data gets pushed after restart

# 11. Android: network switch
def test_sync_handles_network_switch(sync_client, mock_server):
    # WiFi→mobile data, push fails then retries

# 12. Windows: resume after sleep
def test_sync_resumes_after_sleep(sync_client):
    # Polling resumes after system wake

# 13. Cross-device E2E
def test_android_push_windows_query(real_server, android_client, windows_client):
    # Android pushes screenshot → Windows queries via scope="remote"

def test_windows_push_android_query(real_server, windows_client, android_client):
    # Windows pushes memory → Android queries via scope="remote"
```

### Test Execution

```
Local development (Windows):
  pytest tests/sync/                    # Platform-agnostic + Windows-specific

Android verification (SSH to Termux):
  pytest tests/sync/test_sync_android.py
  pytest tests/sync/test_e2e_sync.py
```

## Implementation Phases

### Phase 1: Server

| Step | TDD order | Files |
|------|-----------|-------|
| 1.1 | Write API tests → implement push/query/status/health | `server/main.py`, `server/db.py`, `server/schema.sql` |
| 1.2 | Write config tests → implement config loading | `server/config.py` |
| 1.3 | Write startup tests → implement Dockerfile + docker-compose | `Dockerfile`, `docker-compose.yml` |
| 1.4 | Deploy to VPS, verify health endpoint | — |

### Phase 2: Device-Side Sync Client

| Step | TDD order | Files |
|------|-----------|-------|
| 2.1 | Write change detection tests → implement detect_changes | `screen_memory/sync/client.py` |
| 2.2 | Write push tests (mock HTTP) → implement push + retry | `screen_memory/sync/client.py` |
| 2.3 | Write QueryBridge tests → implement remote query | `screen_memory/sync/query_bridge.py` |
| 2.4 | Write config tests → implement config parsing | `screen_memory/sync/config.py` |
| 2.5 | Write start/stop tests → implement start/stop/flush | `screen_memory/sync/client.py` |
| 2.6 | Windows platform tests → sleep resume, signal handling | `tests/sync/test_sync_windows.py` |
| 2.7 | Android platform tests → Termux restart, network switch | `tests/sync/test_sync_android.py` |

### Phase 3: OpenClaw Tools + E2E

| Step | TDD order | Files |
|------|-----------|-------|
| 3.1 | Write scope routing tests → implement tool extensions | `screen_memory/tools/` |
| 3.2 | Write sync_status tool tests → implement new tool | `screen_memory/tools/` |
| 3.3 | Write E2E tests → deploy and verify on both devices | `tests/sync/test_e2e_sync.py` |

### Dependencies

```
Phase 1 (Server) → Phase 2 (Client) → Phase 3 (Tools + E2E)
```

Each phase is independently verifiable upon completion.

## Verification Environment

- **Windows**: OpenClaw installed and ready for use
- **Android**: OpenClaw installed in Termux, accessible via SSH for deployment and testing
- **Server**: VPS at 47.118.19.85, Python environment set up via uv at `/home/zty/screen_memory_server`
