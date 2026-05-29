# OpenClaw ScreenMemory Plugin - Test Case Design

> Total: 48 unit tests + 13 integration tests + 13 tool tests = **74 test cases**

---

## 1. Unit Tests (48 cases)

### 1.1 `test_uri.py` — URI Parsing & Validation (8 cases)

| # | Test Case | Input | Expected | Priority |
|---|-----------|-------|----------|----------|
| 1 | Parse valid URI | `"core://my_user/identity"` | domain="core", path="my_user/identity" | 🔴 |
| 2 | Parse root URI | `"core://"` | domain="core", path="" | 🔴 |
| 3 | Reject invalid URI | `"not_a_uri"` | raises `ValueError` | 🔴 |
| 4 | Reject empty domain | `"://path"` | raises `ValueError` | 🔴 |
| 5 | Normalize trailing slash | `"core://my_user/"` | trailing slash stripped → `"core://my_user"` | 🟡 |
| 6 | URI equality | `"core://a"` vs `"core://a"` | equal | 🟡 |
| 7 | URI parent detection | `"core://a/b"` is child of `"core://a"` | true | 🔴 |
| 8 | Parse system URI | `"system://boot"` | domain="system", path="boot" | 🔴 |

**TDD order**: 3→4→1→2→8→7→5→6 (validate errors first, then happy paths)

---

### 1.2 `test_uri_graph_service.py` — URI Graph CRUD (12 cases)

| # | Test Case | Setup | Action | Expected | Priority |
|---|-----------|-------|--------|----------|----------|
| 1 | Create root node | empty DB | `create("core://", "test")` | node created, readable | 🔴 |
| 2 | Create child node | root exists | `create("core://agent", "content")` | edge + path created | 🔴 |
| 3 | Create deep path | "core://a" exists | `create("core://a/b/c", "deep")` | all intermediates auto-created | 🟡 |
| 4 | Read non-existent | empty DB | `read("core://missing")` | returns None | 🔴 |
| 5 | Update via patch | content "hello world" | `update(uri, old="hello", new="hi")` | → "hi world" | 🔴 |
| 6 | Update via append | content "line1" | `update(uri, append="\nline2")` | → "line1\nline2" | 🔴 |
| 7 | Patch ambiguous match | content "abc abc" | `update(uri, old="abc", new="x")` | raises error (2 matches) | 🔴 |
| 8 | Delete with children | node has 2 children | `delete(uri)` | all descendant paths removed | 🔴 |
| 9 | Add alias | node at "core://a" | `add_alias("core://b", "core://a")` | read("core://b") = read("core://a") | 🔴 |
| 10 | Search by keyword | 3 nodes, 1 with "python" | `search("python")` | returns 1 result | 🔴 |
| 11 | Content versioning | node with "v1" | update to "v2", then "v3" | 3 versions stored, latest active | 🟡 |
| 12 | Priority ordering | 3 children (p=2,0,1) | read parent | children in order [0,1,2] | 🟡 |

**TDD order**: 4→3→1→2→5→7→6→8→9→10→11→12

---

### 1.3 `test_signal_accumulator.py` — Signal Scoring (10 cases)

| # | Test Case | Setup | Action | Expected | Priority |
|---|-----------|-------|--------|----------|----------|
| 1 | Single episode | new entity | record 1 episode | raw=1, decayed≈1 | 🔴 |
| 2 | Same-day duplicates | entity exists | 2 episodes same day | distinct_days=1, raw=2 | 🔴 |
| 3 | Multi-day evidence | entity exists | episodes across 2 days | distinct_days=2 | 🔴 |
| 4 | Decay calculation | episode 30d ago, τ=30 | refresh | decayed ≈ 1.0 × e^(-1) ≈ 0.368 | 🔴 |
| 5 | Activation met | people, score=2.1, days=2 | refresh | ready=True, status→active | 🔴 |
| 6 | Below activation | people, score=1.5, days=2 | refresh | ready=False, stays candidate | 🔴 |
| 7 | Single strong allowed | identity, 1 strong, days=1 | refresh | evidence_satisfied=True | 🔴 |
| 8 | Single strong blocked | habits, 1 strong, days=1 | refresh | evidence_satisfied=False | 🔴 |
| 9 | Archival | active, not seen 200d | refresh | status→archived | 🟡 |
| 10 | Missing score tracking | score=1.0, threshold=2.0 | refresh | missing_score=1.0 | 🟡 |

**TDD order**: 1→2→3→4→7→8→5→6→10→9

---

### 1.4 `test_entity_lifecycle.py` — Entity State Machine (6 cases)

| # | Test Case | Setup | Action | Expected | Priority |
|---|-----------|-------|--------|----------|----------|
| 1 | Candidate→Active | entity at threshold | refresh | status="active", activated_at set | 🔴 |
| 2 | Active→Archived | not seen archive_after_days | refresh | status="archived", archived_at set | 🔴 |
| 3 | Review queue created | borderline entity | refresh | needs_review=True, review entry created | 🟡 |
| 4 | Approve review | review queue item | approve | entity materialized, review resolved | 🔴 |
| 5 | Dismiss review | review queue item | dismiss | entity dropped, review resolved | 🔴 |
| 6 | Root materialization block | root entity, policy disallows | refresh | root_materialization_blocked=True | 🟡 |

**TDD order**: 1→2→4→5→3→6

---

### 1.5 `test_index_service.py` — FTS5 Search (7 cases)

| # | Test Case | Setup | Action | Expected | Priority |
|---|-----------|-------|--------|----------|----------|
| 1 | Index & find | screenshot with OCR | index → search | FTS finds it | 🔴 |
| 2 | CJK search | "你好世界" | search("你好") | returns match | 🔴 |
| 3 | App name filter | 2 apps | search(app_name="WeChat") | only WeChat results | 🔴 |
| 4 | Time range filter | 3 days of data | search(start, end) | only results in range | 🔴 |
| 5 | Pagination | 30 screenshots | search(limit=10) | 10 results, has_more=True | 🟡 |
| 6 | Update OCR | indexed screenshot | update OCR text | old FTS removed, new added | 🟡 |
| 7 | Delete screenshot | indexed screenshot | delete | FTS entry removed | 🟡 |

**TDD order**: 1→2→3→4→7→6→5

---

### 1.6 `test_ocr_service.py` — OCR Fallback Chain (4 cases)

| # | Test Case | Setup | Action | Expected | Priority |
|---|-----------|-------|--------|----------|----------|
| 1 | System OCR works | mock returns text | recognize | source="system" | 🔴 |
| 2 | System fails, AI works | mock system raises | recognize | falls back to AI, source="ai" | 🔴 |
| 3 | All unavailable | all mocks fail | recognize | raises OcrError | 🔴 |
| 4 | Low confidence | system conf=0.3 | recognize | falls through to next engine | 🟡 |

**TDD order**: 1→3→2→4

---

## 2. Integration Tests (13 cases)

### 2.1 `test_capture_pipeline.py` — Capture→OCR→Index (3 cases)

| # | Test Case | Flow | Asserts | Priority |
|---|-----------|------|---------|----------|
| 1 | Full pipeline | capture → OCR → index → search("keyword") | search returns captured content | 🔴 |
| 2 | Duplicate detection | capture same screen twice | 2nd capture deduplicated or skipped | 🔴 |
| 3 | Timed capture lifecycle | start_timed → mock wait → stop | captures recorded, status correct | 🟡 |

### 2.2 `test_memory_crud.py` — End-to-End Memory Operations (3 cases)

| # | Test Case | Flow | Asserts | Priority |
|---|-----------|------|---------|----------|
| 1 | Full CRUD cycle | create → read → update → read → delete → read | each step correct state | 🔴 |
| 2 | Aliased read | create → add_alias → read(alias) | same content as original | 🔴 |
| 3 | Deep hierarchy | create root → 3 children → read root | all 3 children listed, ordered | 🟡 |

### 2.3 `test_signal_to_materialization.py` — Signal→Entity→URI Graph (3 cases)

| # | Test Case | Flow | Asserts | Priority |
|---|-----------|------|---------|----------|
| 1 | Full lifecycle | seed episodes → refresh → auto-activate → read URI Graph | URI Graph node has entity content | 🔴 |
| 2 | Review intervention | seed borderline → review queue → approve | entity materialized after approval | 🔴 |
| 3 | Archival cleanup | archive old entity → read URI Graph | archived content in URI Graph | 🟡 |

### 2.4 `test_search_pipeline.py` — Cross-Source Search (4 cases)

| # | Test Case | Flow | Asserts | Priority |
|---|-----------|------|---------|----------|
| 1 | Screenshot search | capture 5 → search keyword | correct subset returned | 🔴 |
| 2 | Memory + screenshot | create memory + capture screenshot → search | both sources returned | 🟡 |
| 3 | Time-bounded | capture over 3 days → search 1 day | only that day's results | 🔴 |
| 4 | Empty result | search non-existent keyword | empty list, no error | 🟡 |

---

## 3. Tool Tests (13 cases)

### 3.1 `test_capture_tools.py` — Capture Tool Responses (4 cases)

| # | Test Case | Mock Setup | Call | Assert Response | Priority |
|---|-----------|------------|------|-----------------|----------|
| 1 | Success | adapter returns CaptureResult | screen_capture() | JSON with success=true, screenshot fields | 🔴 |
| 2 | Platform unavailable | adapter raises | screen_capture() | JSON with error code CAPTURE_PLATFORM_UNAVAILABLE | 🔴 |
| 3 | Timed start | adapter mock | screen_capture_timed("start") | JSON with status="running" | 🟡 |
| 4 | Timed stop | running capture | screen_capture_timed("stop") | JSON with status="stopped" | 🟡 |

### 3.2 `test_memory_tools.py` — Memory Tool Responses (9 cases)

| # | Test Case | Mock Setup | Call | Assert Response | Priority |
|---|-----------|------------|------|-----------------|----------|
| 1 | read valid URI | graph with data | read_memory("core://a") | content + children in response | 🔴 |
| 2 | read system://boot | boot data set | read_memory("system://boot") | boot context returned | 🔴 |
| 3 | create missing parent | graph empty | create_memory("core://x/y", "...") | error PARENT_NOT_FOUND | 🔴 |
| 4 | create success | parent exists | create_memory("core://a/child", "...") | success with URI | 🔴 |
| 5 | update patch | content has old_string | update_memory(uri, old, new) | success with updated content | 🔴 |
| 6 | update ambiguous | 2 matches | update_memory(uri, old, new) | error with ambiguous match info | 🔴 |
| 7 | delete with children | node has children | delete_memory(uri) | success, children gone | 🔴 |
| 8 | alias then read | aliased node | add_alias → read(alias) | same content via alias | 🔴 |
| 9 | search | 5 nodes, 2 matching | search_memory("keyword") | exactly 2 results | 🔴 |

### 3.3 `test_search_tools.py` — Search Tool Responses (additional cases)

These are covered in integration tests but could also have isolated tool-level tests for response format validation.

### 3.4 `test_entity_tools.py` — Entity Tool Responses (4 cases)

| # | Test Case | Mock Setup | Call | Assert Response | Priority |
|---|-----------|------------|------|-----------------|----------|
| 1 | query all statuses | 10 entities mixed | query_signals() | all returned with correct counts | 🔴 |
| 2 | query by type | multiple types | query_signals(entity_type="people") | only people entities | 🟡 |
| 3 | review approve | candidate in queue | review_entity(id, "approve") | entity becomes active | 🔴 |
| 4 | review dismiss | candidate in queue | review_entity(id, "dismiss") | entity removed | 🔴 |

---

## 4. Test Execution Strategy (TDD Order)

### Phase 1: Foundation (🔴 tests first)
```
1. test_uri.py           — all 8 cases
2. test_uri_graph_service.py — cases 1-5, 7-8, 10
3. test_index_service.py — cases 1-4
4. test_signal_accumulator.py — cases 1-8
5. test_entity_lifecycle.py — cases 1-2, 4-5
6. test_ocr_service.py — cases 1-3
```

### Phase 2: Integration (🔴 tests)
```
7. test_memory_crud.py — case 1-2
8. test_capture_pipeline.py — case 1-2
9. test_signal_to_materialization.py — case 1-2
10. test_search_pipeline.py — case 1, 3
```

### Phase 3: Tool Layer (🔴 tests)
```
11. test_capture_tools.py — cases 1-2
12. test_memory_tools.py — cases 1-7, 9
13. test_entity_tools.py — cases 1, 3-4
```

### Phase 4: Polish (🟡 tests)
```
14. All remaining 🟡 test cases
```

---

## 5. Test Fixtures (`conftest.py`)

```python
import pytest
import sqlite3
import tempfile
import os
from pathlib import Path

@pytest.fixture
def in_memory_db():
    """In-memory SQLite for unit tests."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    yield conn
    conn.close()

@pytest.fixture
def db_with_schema(in_memory_db):
    """In-memory DB with all tables created."""
    schema_path = Path(__file__).parent.parent / "screen_memory" / "storage" / "schema.sql"
    # Fallback: execute CREATE TABLE statements inline
    from screen_memory.storage.database import Database
    db = Database(connection=in_memory_db)
    db.create_tables()
    return db

@pytest.fixture
def temp_screenshot_dir():
    """Temporary directory for screenshot files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir

@pytest.fixture
def mock_capture_adapter():
    """Mock screen capture adapter."""
    from unittest.mock import MagicMock
    from screen_memory.adapters.base import ScreenCaptureAdapter
    adapter = MagicMock(spec=ScreenCaptureAdapter)
    return adapter

@pytest.fixture
def mock_ocr_adapter():
    """Mock OCR adapter."""
    from unittest.mock import MagicMock
    from screen_memory.adapters.base import OcrAdapter
    adapter = MagicMock(spec=OcrAdapter)
    return adapter

@pytest.fixture
def sample_screenshot(temp_screenshot_dir):
    """Create a minimal test screenshot file."""
    from PIL import Image
    img = Image.new("RGB", (100, 100), color="white")
    path = os.path.join(temp_screenshot_dir, "test_screenshot.png")
    img.save(path)
    return path
```
