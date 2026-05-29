# Android Screen Memory MCP Server — Full Feature Parity Design

## Goal

Bring the Android screen-memory MCP server to full feature parity with the Windows plugin: URI Graph memory, signal tracking, continuous capture, and screenshot search — all in a single pure-stdlib Python file running on Termux.

## Architecture

```
screen-memory.py (single file, ~800 lines)
├── NocturneUri              — URI parsing, identical to Windows models/uri.py
├── Database                 — SQLite with identical schema to Windows
├── GraphRepo                — identical method signatures to Windows storage/graph_repo.py
├── ScreenshotRepo           — identical method signatures to Windows storage/screenshot_repo.py
├── GraphService             — identical method signatures to Windows services/graph_service.py
├── SignalService            — identical method signatures to Windows services/signal_service.py
├── AndroidCapture           — ScreenCapture interface via APK HTTP API
├── CaptureSession           — background thread for timed capture
├── ToolRegistry             — identical 8 tools + 3 Android-specific tools = 11 MCP tools
└── MCPServer                — JSON-RPC stdio protocol handler
```

**Key principle**: All public interfaces (method signatures, return types, database schema) are character-identical to the Windows implementation. Only the capture/OCR adapter layer differs.

## Database Schema

Identical to Windows `database.py`. All 6 tables + FTS:

```sql
CREATE TABLE IF NOT EXISTS nodes (
    uri         TEXT PRIMARY KEY,
    domain      TEXT NOT NULL,
    path        TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS memories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    node_uri    TEXT NOT NULL REFERENCES nodes(uri) ON DELETE CASCADE,
    content     TEXT NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    status      TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'deprecated', 'deleted')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (node_uri, version)
);

CREATE TABLE IF NOT EXISTS edges (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_uri  TEXT NOT NULL REFERENCES nodes(uri) ON DELETE CASCADE,
    target_uri  TEXT NOT NULL REFERENCES nodes(uri) ON DELETE CASCADE,
    relation    TEXT NOT NULL DEFAULT 'related',
    weight      REAL NOT NULL DEFAULT 1.0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (source_uri, target_uri, relation),
    CHECK (source_uri != target_uri)
);

CREATE TABLE IF NOT EXISTS paths (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ancestor_uri TEXT NOT NULL REFERENCES nodes(uri) ON DELETE CASCADE,
    descendant_uri TEXT NOT NULL REFERENCES nodes(uri) ON DELETE CASCADE,
    depth       INTEGER NOT NULL DEFAULT 1,
    UNIQUE (ancestor_uri, descendant_uri),
    CHECK (ancestor_uri != descendant_uri)
);

CREATE TABLE IF NOT EXISTS entities (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type     TEXT NOT NULL,
    name            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'candidate'
                    CHECK (status IN ('candidate', 'active', 'archived')),
    score           REAL NOT NULL DEFAULT 0.0,
    signal_count    INTEGER NOT NULL DEFAULT 0,
    evidence        TEXT NOT NULL DEFAULT '[]',
    first_seen_at   TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at    TEXT NOT NULL DEFAULT (datetime('now')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (entity_type, name)
);

CREATE TABLE IF NOT EXISTS screenshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path   TEXT NOT NULL,
    ocr_text    TEXT,
    captured_at TEXT NOT NULL DEFAULT (datetime('now')),
    uri         TEXT REFERENCES nodes(uri) ON DELETE NULL,
    UNIQUE (file_path)
);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
    USING fts5(content, content='memories', content_rowid='id');
```

Database file location: `$HOME/.screenmemory/db/screenmemory.db`

## Interface Parity with Windows

### NocturneUri (identical to `models/uri.py`)

```python
@dataclass(frozen=True)
class NocturneUri:
    domain: str
    path: str

    @classmethod
    def parse(cls, raw: str) -> NocturneUri: ...
    @classmethod
    def make(cls, domain: str, path: str) -> NocturneUri: ...
    def parent(self) -> Optional[NocturneUri]: ...
    @property
    def leaf(self) -> str: ...
    def is_child_of(self, parent: NocturneUri) -> bool: ...
    def __str__(self) -> str: ...
```

### GraphRepo (identical signatures to `storage/graph_repo.py`)

```python
class GraphRepo:
    def create_node(self, uri: NocturneUri) -> NocturneUri: ...
    def get_node(self, uri: NocturneUri) -> Optional[dict]: ...
    def list_nodes(self, domain: Optional[str] = None) -> list[dict]: ...
    def delete_node(self, uri: NocturneUri) -> None: ...
    def write_memory(self, uri: NocturneUri, content: str) -> dict: ...
    def read_memory(self, uri: NocturneUri) -> Optional[dict]: ...
    def memory_history(self, uri: NocturneUri) -> list[dict]: ...
    def deprecate_memory(self, uri: NocturneUri, version: int) -> None: ...
    def create_edge(self, source: NocturneUri, target: NocturneUri, relation: str = "related", weight: float = 1.0) -> dict: ...
    def get_neighbors(self, uri: NocturneUri, relation: Optional[str] = None) -> list[dict]: ...
    def delete_edge(self, source: NocturneUri, target: NocturneUri, relation: str) -> None: ...
    def search(self, query: str, limit: int = 20) -> list[dict]: ...
```

### ScreenshotRepo (identical signatures to `storage/screenshot_repo.py`)

```python
class ScreenshotRepo:
    def insert(self, file_path: str, ocr_text: Optional[str] = None, uri: Optional[NocturneUri] = None) -> dict: ...
    def get_by_id(self, screenshot_id: int) -> Optional[dict]: ...
    def list_all(self, after: Optional[str] = None, before: Optional[str] = None) -> list[dict]: ...
    def update_ocr(self, screenshot_id: int, ocr_text: str) -> None: ...
    def link_uri(self, screenshot_id: int, uri: NocturneUri) -> None: ...
    def search(self, query: str, limit: int = 20) -> list[dict]: ...
```

### GraphService (identical signatures to `services/graph_service.py`)

```python
class GraphService:
    def write(self, uri: str | NocturneUri, content: str) -> dict: ...
    def read(self, uri: str | NocturneUri) -> Optional[dict]: ...
    def list_nodes(self, domain: Optional[str] = None) -> list[dict]: ...
    def get_subtree(self, uri: NocturneUri, max_depth: Optional[int] = None) -> Optional[dict]: ...
    def get_children(self, uri: NocturneUri) -> list[dict]: ...
    def get_ancestors(self, uri: NocturneUri) -> list[dict]: ...
    def get_descendants(self, uri: NocturneUri) -> list[dict]: ...
```

### SignalService (identical signatures to `services/signal_service.py`)

```python
@dataclass
class EntityPolicy:
    entity_type: str
    activation_threshold: float
    decay_tau: float
    required_evidence: list[str]

class SignalService:
    def ingest_signal(self, entity_type: str, entity_name: str, source: str, evidence: Optional[list[str]] = None) -> dict: ...
    def get_entity_score(self, name: str) -> float: ...
    def can_activate(self, name: str) -> bool: ...
    def activate(self, name: str) -> dict: ...
    def get_entity(self, name: str) -> Optional[dict]: ...
    def list_entities(self, status: Optional[str] = None, entity_type: Optional[str] = None) -> list[dict]: ...
```

### AndroidCapture (platform-specific, implements Windows ScreenCapture interface)

```python
class AndroidCapture:
    """ScreenCapture interface via APK HTTP API."""

    def capture(self, quality: int = 80, region: Optional[dict] = None) -> CaptureResult: ...
    def start_timed_capture(self, interval_seconds: int = 30, quality: int = 80, callback=None) -> None: ...
    def stop_timed_capture(self) -> dict: ...
    def is_capturing(self) -> bool: ...
    def timed_status(self) -> dict: ...
```

## MCP Tools (11 total)

### Windows-parity tools (8, identical inputSchema)

| Tool | Description |
|------|-------------|
| `memory_write` | Write memory to URI Graph |
| `memory_read` | Read latest memory at URI |
| `memory_search` | FTS5 search across memories |
| `memory_delete` | Delete node and all memories |
| `graph_query_subtree` | Query subtree rooted at URI |
| `signal_ingest` | Ingest signal for entity tracking |
| `signal_activate` | Activate entity into graph |
| `screenshot_search` | Search screenshots by OCR text |

### Android-specific tools (3)

| Tool | Description |
|------|-------------|
| `screen_capture` | Single capture via APK, returns image + metadata |
| `screen_ocr` | Capture + OCR via APK, returns text + blocks (no base64 image) |
| `capture_session` | Start/stop continuous capture with interval control |

The `capture_session` tool uses a single tool with an `action` parameter:
```json
{"action": "start", "interval_seconds": 10, "quality": 80}
{"action": "stop"}
{"action": "status"}
```

## Continuous Capture Flow

```
capture_session(action="start", interval=10)
  → AndroidCapture.start_timed_capture(interval=10, callback=_on_capture)
  → Background thread loop:
      1. APK POST /capture-and-ocr → {image, text, blocks}
      2. Save image to ~/.screenmemory/screenshots/YYYY/MM/DD/HHMMSS.jpg
      3. ScreenshotRepo.insert(file_path, ocr_text)
      4. Extract app_package → signal_ingest("app", package, "screenshot")
      5. timed_stop.wait(interval_seconds)

capture_session(action="stop")
  → AndroidCapture.stop_timed_capture()
  → Return status {captures_count, started_at}
```

## File Structure

```
screen-memory-android/mcp-server/
├── screen_memory_server.py       # Single-file MCP server (~800 lines)
└── tests/
    ├── test_uri.py               # NocturneUri parsing, parent, hierarchy
    ├── test_storage.py           # GraphRepo, ScreenshotRepo CRUD + FTS
    ├── test_services.py          # GraphService, SignalService logic
    ├── test_capture.py           # AndroidCapture mock, timed capture control
    └── test_mcp.py               # JSON-RPC protocol, tool dispatch
```

## Testing Strategy (TDD)

Each module has tests that run locally on the development machine (no phone needed):

1. **test_uri.py** — Test NocturneUri.parse, parent, leaf, is_child_of (pure logic, no deps)
2. **test_storage.py** — Test with `:memory:` SQLite database: node CRUD, memory versioning, edge creation, path materialization, FTS search, screenshot insert/search
3. **test_services.py** — Test GraphService subtree queries, SignalService decay scoring and activation
4. **test_capture.py** — Mock APK HTTP responses, test AndroidCapture flow, test timed capture start/stop/status
5. **test_mcp.py** — Test JSON-RPC request parsing, tool dispatch, response formatting

Run: `cd screen-memory-android/mcp-server && python3 -m pytest tests/ -v`

## Deployment

After implementation, update the single file on the phone:
```bash
scp -P 8022 -i ~/.ssh/id_rsa screen_memory_server.py u0_aXXX@127.0.0.1:~/.openclaw/mcp-servers/screen-memory.py
# Restart gateway to pick up changes
```

## Constraints

- Pure Python stdlib — no pip install needed (no Pillow, no requests, no numpy)
- Single file — easy to deploy, just scp one file
- SQLite only — no external database
- All data stored under `$HOME/.screenmemory/`
- Must work on Termux Python 3.13
