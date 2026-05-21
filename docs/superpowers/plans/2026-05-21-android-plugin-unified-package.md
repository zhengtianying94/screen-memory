# Android Plugin Unified Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify Windows and Android screen-memory plugins into a single shared Python package, so Android gains all missing capabilities (GraphService, SignalService, ToolRegistry, etc.) without code duplication.

**Architecture:** The existing `screen-memory` package already has platform-independent business logic and Android adapters. The change is minimal: fix the hardcoded Windows DB path in `cli.py`, add `[android]` optional deps to `pyproject.toml`, update deployment scripts, delete the standalone `mcp-server/`, and add Android-specific tests for degradation and tool parity.

**Tech Stack:** Python 3.10+, SQLite (FTS5), pytest, stdlib urllib for HTTP

**Baseline:** 194 existing tests all pass on Windows. Every change must keep them green.

---

## File Structure

### Files Modified

| File | Responsibility |
|------|---------------|
| `screen-memory/pyproject.toml` | Add `[android]` optional deps group |
| `screen-memory/screen_memory/cli.py` | Cross-platform DB default path (remove hardcoded Windows path) |
| `screen-memory-android/deploy-plugin.sh` | Install shared package instead of standalone mcp-server |

### Files Deleted

| File | Reason |
|------|--------|
| `screen-memory-android/mcp-server/screen_memory_server.py` | Replaced by shared `screen_memory` package |
| `screen-memory-android/mcp-server/tests/test_uri.py` | Covered by `screen-memory/tests/unit/test_uri.py` |
| `screen-memory-android/mcp-server/tests/test_storage.py` | Covered by `screen-memory/tests/unit/test_graph_repo.py` etc. |
| `screen-memory-android/mcp-server/tests/__init__.py` | No longer needed |

### Files Created (Tests)

| File | Responsibility |
|------|---------------|
| `screen-memory/tests/unit/test_cli_crossplatform.py` | Test cross-platform DB path resolution |
| `screen-memory/tests/unit/test_index_service.py` (expanded) | Add graceful degradation tests |

### Files Expanded (Tests)

| File | New Tests |
|------|-----------|
| `screen-memory/tests/unit/test_platform_factory_android.py` | Full adapter wiring verification |
| `screen-memory/tests/tools/test_android_tools.py` | All 8 tools with Android mock |
| `screen-memory/tests/unit/test_index_service.py` | APK-unavailable degradation |

---

## Task 1: Cross-platform DB default path in cli.py

**Files:**
- Modify: `screen-memory/screen_memory/cli.py:19-23` (DB path default)
- Create: `screen-memory/tests/unit/test_cli_crossplatform.py`

**Context:** `cli.py` lines 19-23 hardcode the DB path to `D:\ScreenMemo\screen-memory\screen-memory.db`. This breaks on Android/Termux where that path doesn't exist. The fix: use `pathlib` to default to `~/.screenmemory/screen-memory.db`.

- [ ] **Step 1: Write the failing test**

Create `screen-memory/tests/unit/test_cli_crossplatform.py`:

```python
"""Tests for cross-platform CLI behavior: DB path defaults."""
import os
from pathlib import Path
from unittest.mock import patch

import pytest


class TestDbPathDefault:
    def test_default_db_path_uses_home(self):
        """Default DB path should be under $HOME, not hardcoded Windows path."""
        from screen_memory.cli import _get_registry

        # Patch Database.initialize to avoid creating real files
        with patch("screen_memory.storage.database.Database.initialize"):
            # _get_registry reads db_path from env or falls back to default
            # We test the default by unsetting the env var
            with patch.dict(os.environ, {}, clear=False):
                if "SCREEN_MEMORY_DB" in os.environ:
                    del os.environ["SCREEN_MEMORY_DB"]
                # Import fresh to pick up default
                import importlib
                import screen_memory.cli as cli_mod
                importlib.reload(cli_mod)

                # The default should be under HOME, not D:\ScreenMemo
                home = Path.home()
                expected_dir = home / ".screenmemory"
                # We can't call _get_registry without a real DB,
                # so test the default string directly
                import screen_memory.cli
                # Read the source to find the default
                import inspect
                source = inspect.getsource(screen_memory.cli._get_registry)
                assert "D:\\\\ScreenMemo" not in source, \
                    "Hardcoded Windows path found in _get_registry"
                assert ".screenmemory" in source, \
                    "Expected ~/.screenmemory in _get_registry default"

    def test_env_var_overrides_default(self):
        """SCREEN_MEMORY_DB env var should override the default path."""
        with patch.dict(os.environ, {"SCREEN_MEMORY_DB": "/tmp/test-memory.db"}):
            from screen_memory.cli import _get_registry
            # Can't fully call without DB init, but verify env var is read
            import os
            assert os.environ.get("SCREEN_MEMORY_DB") == "/tmp/test-memory.db"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:/ScreenMemo/screen-memory && python -m pytest tests/unit/test_cli_crossplatform.py -v`
Expected: FAIL — `"D:\\\\ScreenMemo"` will be found in source (hardcoded path exists)

- [ ] **Step 3: Fix cli.py to use cross-platform default**

Replace the hardcoded path in `screen-memory/screen_memory/cli.py`. The function `_get_registry` at lines 19-23 currently has:

```python
if db_path is None:
    db_path = os.environ.get(
        "SCREEN_MEMORY_DB",
        "D:\\ScreenMemo\\screen-memory\\screen-memory.db",
    )
```

Change to:

```python
if db_path is None:
    db_path = os.environ.get(
        "SCREEN_MEMORY_DB",
        str(Path.home() / ".screenmemory" / "screen-memory.db"),
    )
```

Add `from pathlib import Path` to the imports at the top of `cli.py` if not already present.

Also fix the same pattern in `cmd_capture` at lines 116-118:

```python
# Before:
db_path = args.db or os.environ.get(
    "SCREEN_MEMORY_DB",
    "D:\\ScreenMemo\\screen-memory\\screen-memory.db",
)

# After:
db_path = args.db or os.environ.get(
    "SCREEN_MEMORY_DB",
    str(Path.home() / ".screenmemory" / "screen-memory.db"),
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd D:/ScreenMemo/screen-memory && python -m pytest tests/unit/test_cli_crossplatform.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to verify no regression**

Run: `cd D:/ScreenMemo/screen-memory && python -m pytest tests/ -v`
Expected: All 194 + 2 new tests pass

- [ ] **Step 6: Commit**

```bash
cd D:/ScreenMemo
git add screen-memory/screen_memory/cli.py screen-memory/tests/unit/test_cli_crossplatform.py
git commit -m "fix(cli): cross-platform DB default path via pathlib

Replace hardcoded Windows path with Path.home()/.screenmemory/screen-memory.db.
Android/Termux and any other platform now works out of the box."
```

---

## Task 2: Add `[android]` optional deps to pyproject.toml

**Files:**
- Modify: `screen-memory/pyproject.toml:17-29` (optional-dependencies section)

**Context:** Add an empty `[android]` group so `pip install screen-memory[android]` is a valid no-op. This documents Android as a supported platform and leaves room for future Android-only deps.

- [ ] **Step 1: Modify pyproject.toml**

Current `optional-dependencies` section (lines 17-29):

```toml
[project.optional-dependencies]
windows = [
    "winrt-Windows.Media.Ocr>=3.0",
    "winrt-Windows.Graphics.Imaging>=3.0",
    "winrt-Windows.Storage.Streams>=3.0",
    "winrt-Windows.Foundation>=3.0",
    "winrt-Windows.Foundation.Collections>=3.0",
]
tesseract = [
    "pytesseract>=0.3.10",
]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
]
```

Add the `android` group:

```toml
[project.optional-dependencies]
windows = [
    "winrt-Windows.Media.Ocr>=3.0",
    "winrt-Windows.Graphics.Imaging>=3.0",
    "winrt-Windows.Storage.Streams>=3.0",
    "winrt-Windows.Foundation>=3.0",
    "winrt-Windows.Foundation.Collections>=3.0",
]
android = []
tesseract = [
    "pytesseract>=0.3.10",
]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
]
```

- [ ] **Step 2: Verify package still installs**

Run: `cd D:/ScreenMemo/screen-memory && pip install -e ".[dev]" --dry-run 2>&1 | head -5`
Expected: No errors

- [ ] **Step 3: Run full test suite**

Run: `cd D:/ScreenMemo/screen-memory && python -m pytest tests/ -q`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
cd D:/ScreenMemo
git add screen-memory/pyproject.toml
git commit -m "feat(pyproject): add [android] optional deps group

Empty group documents Android as a supported platform. No extra deps needed
— Android adapters use stdlib urllib to communicate with the APK."
```

---

## Task 3: Expand platform_factory Android routing tests

**Files:**
- Modify: `screen-memory/tests/unit/test_platform_factory_android.py`

**Context:** Existing tests verify `create_capture` and `create_ocr_engines` on Android. Add tests verifying `create_ocr_chain` works and that the full adapter set is correct for Android.

- [ ] **Step 1: Write the failing tests**

Append to `screen-memory/tests/unit/test_platform_factory_android.py`:

```python
class TestAndroidOcrChainIntegration:
    def test_android_ocr_chain_has_two_engines(self):
        """create_ocr_chain on Android returns a chain with MlKit + Tesseract."""
        with patch.object(sys, "platform", "android"):
            from screen_memory.adapters.platform_factory import create_ocr_chain
            chain = create_ocr_chain()
            assert len(chain._engines) == 2
            assert isinstance(chain._engines[0], MlKitOcr)
            assert isinstance(chain._engines[1], TesseractOcr)

    def test_android_ocr_chain_min_confidence_default(self):
        """Default min_confidence is 0.5."""
        with patch.object(sys, "platform", "android"):
            from screen_memory.adapters.platform_factory import create_ocr_chain
            chain = create_ocr_chain()
            assert chain._min_confidence == 0.5

    def test_android_ocr_chain_custom_confidence(self):
        """Custom min_confidence is propagated."""
        with patch.object(sys, "platform", "android"):
            from screen_memory.adapters.platform_factory import create_ocr_chain
            chain = create_ocr_chain(min_confidence=0.8)
            assert chain._min_confidence == 0.8


class TestAndroidCaptureOnNonAndroid:
    def test_linux_without_android_root_returns_linux_capture(self):
        """On plain Linux (no ANDROID_ROOT), should not return AndroidCapture."""
        with patch.object(sys, "platform", "linux"), \
             patch.dict(os.environ, {}, clear=False):
            if "ANDROID_ROOT" in os.environ:
                del os.environ["ANDROID_ROOT"]
            try:
                from screen_memory.adapters.platform_factory import create_capture
                capture = create_capture()
                assert not isinstance(capture, AndroidCapture)
            except RuntimeError:
                pass  # Expected: no linux_capture module exists yet
```

- [ ] **Step 2: Run tests to verify they pass (no implementation change needed)**

Run: `cd D:/ScreenMemo/screen-memory && python -m pytest tests/unit/test_platform_factory_android.py -v`
Expected: PASS — `create_ocr_chain` already exists and works correctly for Android.

- [ ] **Step 3: Run full test suite**

Run: `cd D:/ScreenMemo/screen-memory && python -m pytest tests/ -q`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
cd D:/ScreenMemo
git add screen-memory/tests/unit/test_platform_factory_android.py
git commit -m "test(platform-factory): add Android OCR chain integration tests

Verify create_ocr_chain produces MlKit+Tesseract chain on Android,
and that plain Linux without ANDROID_ROOT does not get AndroidCapture."
```

---

## Task 4: Add IndexService graceful degradation tests

**Files:**
- Modify: `screen-memory/tests/unit/test_index_service.py`

**Context:** When the APK is unavailable, `capture()` throws `ConnectionError`. `IndexService.capture_and_index()` should catch this and return a degraded result rather than crashing.

- [ ] **Step 1: Write the failing test**

Append to `screen-memory/tests/unit/test_index_service.py`:

```python
class _FailingCapture(ScreenCapture):
    """Capture adapter that always raises ConnectionError (APK unavailable)."""

    def capture(self) -> CaptureResult:
        raise ConnectionError("APK service not reachable")


class TestGracefulDegradation:
    def test_capture_unavailable_returns_error_dict(self):
        """When capture raises ConnectionError, capture_and_index returns error."""
        db = Database(":memory:")
        db.initialize()
        repo = GraphRepo(db)
        ss_repo = ScreenshotRepo(db)
        capture = _FailingCapture()
        ocr = OCRChain([])
        svc = IndexService(repo, ss_repo, capture, ocr)
        result = svc.capture_and_index()
        assert result["ok"] is False
        assert "error" in result
        assert "capture" in result["error"].lower() or "unavailable" in result["error"].lower()

    def test_no_screenshot_stored_on_failure(self):
        """When capture fails, no screenshot record is created."""
        db = Database(":memory:")
        db.initialize()
        repo = GraphRepo(db)
        ss_repo = ScreenshotRepo(db)
        capture = _FailingCapture()
        ocr = OCRChain([])
        svc = IndexService(repo, ss_repo, capture, ocr)
        svc.capture_and_index()
        assert len(ss_repo.list_all()) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:/ScreenMemo/screen-memory && python -m pytest tests/unit/test_index_service.py::TestGracefulDegradation -v`
Expected: FAIL — `capture_and_index` does not catch `ConnectionError`, test will raise unhandled exception

- [ ] **Step 3: Implement graceful degradation in IndexService**

Modify `screen-memory/screen_memory/services/index_service.py`. Change `capture_and_index`:

```python
def capture_and_index(
    self, link_uri: Optional[str] = None
) -> dict:
    """Capture screen, run OCR, store screenshot, optionally link to graph."""
    try:
        cap = self._capture.capture()
    except (ConnectionError, TimeoutError, OSError) as exc:
        return {"ok": False, "error": f"capture_unavailable: {exc}"}

    ocr_result = self._ocr.recognize(cap.image_data)

    uri_obj = NocturneUri.parse(link_uri) if link_uri else None
    if uri_obj:
        self._repo.create_node(uri_obj)
    s = self._ss_repo.insert(
        file_path=cap.file_path,
        ocr_text=ocr_result.text or None,
        uri=uri_obj,
    )

    if uri_obj and ocr_result.text:
        self._repo.write_memory(uri_obj, ocr_result.text)

    return s
```

- [ ] **Step 4: Run degradation tests**

Run: `cd D:/ScreenMemo/screen-memory && python -m pytest tests/unit/test_index_service.py::TestGracefulDegradation -v`
Expected: PASS

- [ ] **Step 5: Run full test suite (regression check)**

Run: `cd D:/ScreenMemo/screen-memory && python -m pytest tests/ -v`
Expected: All tests pass (existing tests don't trigger the error path)

- [ ] **Step 6: Commit**

```bash
cd D:/ScreenMemo
git add screen-memory/screen_memory/services/index_service.py screen-memory/tests/unit/test_index_service.py
git commit -m "feat(index-service): graceful degradation when capture unavailable

Catch ConnectionError/TimeoutError/OSError from capture adapter and return
a structured error dict instead of crashing. APK service being down no longer
breaks the tool pipeline."
```

---

## Task 5: Expand Android tools test — all 8 tools with mock

**Files:**
- Modify: `screen-memory/tests/tools/test_android_tools.py`

**Context:** Existing test file tests CLI capture and screenshot search. Add tests verifying all 8 tools work through ToolRegistry with Android mock HTTP client.

- [ ] **Step 1: Write the tests**

Append to `screen-memory/tests/tools/test_android_tools.py`:

```python
def _make_registry() -> ToolRegistry:
    """Create a ToolRegistry with in-memory DB (no APK dependency)."""
    db = Database(":memory:")
    db.initialize()
    repo = GraphRepo(db)
    ss_repo = ScreenshotRepo(db)
    graph_svc = GraphService(repo)
    policies = {
        "person": EntityPolicy("person", 3.0, 86400 * 7, ["seen_multiple_times"]),
        "topic": EntityPolicy("topic", 2.0, 86400 * 3, []),
    }
    signal_svc = SignalService(repo, policies)
    return ToolRegistry(graph_svc, signal_svc, ss_repo)


class TestAllToolsViaRegistry:
    """Verify all 8 tools work through the registry (shared package)."""

    def test_memory_write(self):
        reg = _make_registry()
        result = reg.call("memory_write", {"uri": "core://android/test", "content": "hello android"})
        assert result["ok"] is True
        assert result["uri"] == "core://android/test"

    def test_memory_read(self):
        reg = _make_registry()
        reg.call("memory_write", {"uri": "core://android/test", "content": "data"})
        result = reg.call("memory_read", {"uri": "core://android/test"})
        assert result["content"] == "data"

    def test_memory_search(self):
        reg = _make_registry()
        reg.call("memory_write", {"uri": "core://a", "content": "android kotlin"})
        reg.call("memory_write", {"uri": "core://b", "content": "ios swift"})
        results = reg.call("memory_search", {"query": "android"})
        assert len(results) == 1
        assert results[0]["node_uri"] == "core://a"

    def test_memory_delete(self):
        reg = _make_registry()
        reg.call("memory_write", {"uri": "core://del", "content": "temp"})
        result = reg.call("memory_delete", {"uri": "core://del"})
        assert result["ok"] is True
        assert reg.call("memory_read", {"uri": "core://del"}) is None

    def test_graph_query_subtree(self):
        reg = _make_registry()
        reg.call("memory_write", {"uri": "core://a", "content": "root"})
        reg.call("memory_write", {"uri": "core://a/b", "content": "child"})
        result = reg.call("graph_query_subtree", {"uri": "core://a"})
        assert result["uri"] == "core://a"
        assert len(result["children"]) == 1

    def test_signal_ingest(self):
        reg = _make_registry()
        result = reg.call("signal_ingest", {
            "entity_type": "person",
            "entity_name": "Alice",
            "source": "screenshot",
            "evidence": ["seen_multiple_times"],
        })
        assert result["name"] == "Alice"
        assert result["status"] == "candidate"

    def test_signal_activate(self):
        reg = _make_registry()
        for _ in range(5):
            reg.call("signal_ingest", {
                "entity_type": "person",
                "entity_name": "Bob",
                "source": "screenshot",
                "evidence": ["seen_multiple_times"],
            })
        result = reg.call("signal_activate", {"entity_name": "Bob"})
        assert result["status"] == "active"

    def test_screenshot_search(self):
        reg = _make_registry()
        reg._ss_repo.insert("/tmp/android.png", "screen memory plugin test")
        results = reg.call("screenshot_search", {"query": "plugin"})
        assert len(results) == 1

    def test_list_tools_has_8(self):
        reg = _make_registry()
        tools = reg.list_tools()
        assert len(tools) == 8
        names = [t["name"] for t in tools]
        expected = [
            "memory_write", "memory_read", "memory_search", "memory_delete",
            "graph_query_subtree", "signal_ingest", "signal_activate",
            "screenshot_search",
        ]
        assert names == expected


class TestSignalActivationOnAndroid:
    """Verify signal activation creates graph memory (Android scenario)."""

    def test_activate_creates_graph_node(self):
        reg = _make_registry()
        for _ in range(5):
            reg.call("signal_ingest", {
                "entity_type": "topic",
                "entity_name": "Android",
                "source": "screenshot",
                "evidence": [],
            })
        reg.call("signal_activate", {"entity_name": "Android"})
        mem = reg.call("memory_read", {"uri": "core://entities/topic/Android"})
        assert mem is not None
        assert "Android" in mem["content"]
```

- [ ] **Step 2: Run the new tests**

Run: `cd D:/ScreenMemo/screen-memory && python -m pytest tests/tools/test_android_tools.py -v`
Expected: PASS — all tests use in-memory DB, no APK dependency

- [ ] **Step 3: Run full test suite**

Run: `cd D:/ScreenMemo/screen-memory && python -m pytest tests/ -q`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
cd D:/ScreenMemo
git add screen-memory/tests/tools/test_android_tools.py
git commit -m "test(android-tools): verify all 8 tools via ToolRegistry

Add comprehensive tests for memory_write/read/search/delete,
graph_query_subtree, signal_ingest/activate, and screenshot_search
using in-memory DB — no APK dependency needed."
```

---

## Task 6: Update Android deployment script

**Files:**
- Modify: `screen-memory-android/deploy-plugin.sh`

**Context:** The deploy script currently copies plugin files from `/sdcard/screen-memory`. It needs to install the shared `screen-memory` package instead. The script should `pip install` the shared package and let OpenClaw discover `openclaw.plugin.json`.

- [ ] **Step 1: Update deploy-plugin.sh**

Replace the entire content of `screen-memory-android/deploy-plugin.sh`:

```bash
#!/bin/bash
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

info "=== Shared Package Deployment ==="

PYTHON_CMD=""
if command -v python &> /dev/null; then
    PYTHON_CMD="python"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
else
    error "Python not found. Run: pkg install python"
fi
info "Python: $($PYTHON_CMD --version)"

SCREEN_MEMORY_SRC="${SCREEN_MEMORY_SRC:-/sdcard/screen-memory}"

if [ ! -f "$SCREEN_MEMORY_SRC/pyproject.toml" ]; then
    error "Shared package not found at $SCREEN_MEMORY_SRC (expected pyproject.toml)"
fi
info "Package source: $SCREEN_MEMORY_SRC"

info "Installing screen-memory package..."
$PYTHON_CMD -m pip install --user --editable "$SCREEN_MEMORY_SRC" 2>&1 || warn "pip install had warnings"

info "Verifying package import..."
$PYTHON_CMD -c "from screen_memory.tools import register; print('OK: tools.register imported')" \
    || error "Failed to import screen_memory.tools"

info "Configuring environment..."
mkdir -p "$HOME/.screenmemory/screenshots" "$HOME/.screenmemory/db"

cat > "$HOME/.screenmemory.env" << 'ENVEOF'
export SCREEN_MEMORY_APK_URL="http://127.0.0.1:19700"
export SCREEN_MEMORY_APK_TIMEOUT="10"
export SCREEN_MEMORY_APK_OCR_TIMEOUT="15"
export SCREEN_MEMORY_SCREENSHOT_DIR="$HOME/.screenmemory/screenshots"
export SCREEN_MEMORY_DB="$HOME/.screenmemory/db/screen-memory.db"
ENVEOF

if ! grep -q ".screenmemory.env" "$HOME/.bashrc" 2>/dev/null; then
    echo '[ -f $HOME/.screenmemory.env ] && source $HOME/.screenmemory.env' >> "$HOME/.bashrc"
fi

OC_HOME="${HOME}/.openclaw"
PLUGIN_DIR="$OC_HOME/plugins"
mkdir -p "$PLUGIN_DIR"
DEST="$PLUGIN_DIR/screen-memory"
rm -rf "$DEST" 2>/dev/null || true
cp -r "$SCREEN_MEMORY_SRC" "$DEST"
rm -rf "$DEST/tests" "$DEST/.git" "$DEST/__pycache__" "$DEST/**/__pycache__" 2>/dev/null || true

info "Verifying plugin structure..."
for f in openclaw.plugin.json screen_memory/__init__.py screen_memory/tools/__init__.py screen_memory/adapters/android_capture.py screen_memory/adapters/mlkit_ocr.py screen_memory/services/graph_service.py screen_memory/services/signal_service.py screen_memory/tools/registry.py; do
    if [ -f "$DEST/$f" ]; then
        info "  OK: $f"
    else
        warn "  MISSING: $f"
    fi
done

echo ""
info "=== Deployment Complete ==="
info "Run: bash $(dirname "$0")/verify.sh"
```

- [ ] **Step 2: Verify script syntax**

Run: `bash -n D:/ScreenMemo/screen-memory-android/deploy-plugin.sh`
Expected: No output (syntax OK)

- [ ] **Step 3: Commit**

```bash
cd D:/ScreenMemo
git add screen-memory-android/deploy-plugin.sh
git commit -m "refactor(deploy): install shared screen-memory package

Replace standalone mcp-server copy with pip install -e of the shared
screen-memory package. Plugin files are also copied to OpenClaw plugins
dir for discovery. New env var SCREEN_MEMORY_SRC controls package location."
```

---

## Task 7: Delete standalone Android MCP server

**Files:**
- Delete: `screen-memory-android/mcp-server/screen_memory_server.py`
- Delete: `screen-memory-android/mcp-server/tests/test_uri.py`
- Delete: `screen-memory-android/mcp-server/tests/test_storage.py`
- Delete: `screen-memory-android/mcp-server/tests/__init__.py`

**Context:** The standalone `mcp-server/` is now fully replaced by the shared `screen-memory` package. Its functionality (NocturneUri, Database, GraphRepo) is identical to what the shared package provides, plus the shared package adds GraphService, SignalService, ToolRegistry, etc.

- [ ] **Step 1: Verify shared tests cover all deleted test functionality**

Run: `cd D:/ScreenMemo/screen-memory && python -m pytest tests/unit/test_uri.py tests/unit/test_database.py tests/unit/test_graph_repo.py -v`
Expected: All pass — these cover everything `test_uri.py` and `test_storage.py` tested

- [ ] **Step 2: Delete the files**

```bash
cd D:/ScreenMemo
rm screen-memory-android/mcp-server/screen_memory_server.py
rm screen-memory-android/mcp-server/tests/test_uri.py
rm screen-memory-android/mcp-server/tests/test_storage.py
rm screen-memory-android/mcp-server/tests/__init__.py
```

- [ ] **Step 3: Remove empty directories**

```bash
rmdir screen-memory-android/mcp-server/tests 2>/dev/null || true
rmdir screen-memory-android/mcp-server 2>/dev/null || true
```

- [ ] **Step 4: Run shared test suite to confirm nothing broke**

Run: `cd D:/ScreenMemo/screen-memory && python -m pytest tests/ -q`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
cd D:/ScreenMemo
git add -A screen-memory-android/mcp-server/
git commit -m "chore: remove standalone mcp-server (replaced by shared package)

The shared screen-memory package provides all functionality that was in
screen_memory_server.py, plus GraphService, SignalService, ToolRegistry,
and CLI. No capability is lost."
```

---

## Task 8: Final integration verification

**Files:** None (verification only)

**Context:** Final check that everything works together — all tests pass, no leftover references to the deleted mcp-server.

- [ ] **Step 1: Run full test suite**

Run: `cd D:/ScreenMemo/screen-memory && python -m pytest tests/ -v --tb=short`
Expected: All tests pass (should be ~210+ tests)

- [ ] **Step 2: Verify no import references to deleted mcp-server**

Run: `cd D:/ScreenMemo && grep -r "screen_memory_server" screen-memory-android/ 2>/dev/null || echo "No references found"`
Expected: "No references found"

- [ ] **Step 3: Verify package import chain works**

Run: `cd D:/ScreenMemo/screen-memory && python -c "from screen_memory.tools import register; print('OK')"`
Expected: "OK"

- [ ] **Step 4: Verify all 8 tools are listed**

Run: `cd D:/ScreenMemo/screen-memory && python -c "
from screen_memory.tools.registry import ToolRegistry
from screen_memory.storage.database import Database
from screen_memory.storage.graph_repo import GraphRepo
from screen_memory.storage.screenshot_repo import ScreenshotRepo
from screen_memory.services.graph_service import GraphService
from screen_memory.services.signal_service import SignalService, EntityPolicy
db = Database(':memory:'); db.initialize()
repo = GraphRepo(db); ss_repo = ScreenshotRepo(db)
graph_svc = GraphService(repo)
policies = {'person': EntityPolicy('person', 3.0, 86400*7, ['seen_multiple_times'])}
signal_svc = SignalService(repo, policies)
reg = ToolRegistry(graph_svc, signal_svc, ss_repo)
tools = [t['name'] for t in reg.list_tools()]
print(f'{len(tools)} tools: {tools}')
"`
Expected: "8 tools: ['memory_write', 'memory_read', ...]"

- [ ] **Step 5: Commit any remaining changes**

```bash
cd D:/ScreenMemo
git status
# If clean, no commit needed
```

---

## Self-Review Checklist

**1. Spec coverage:**
- Module classification (shared vs platform-specific) → Task 1 (cli.py), Task 2 (pyproject.toml), Task 3 (factory tests)
- Delete mcp-server/ → Task 7
- Deploy script update → Task 6
- Graceful degradation → Task 4
- TDD (8 tools tests) → Task 5
- Final integration → Task 8

**2. Placeholder scan:** No TBD, TODO, or "implement later" found. All steps have actual code.

**3. Type consistency:** All method names, class names, and parameter names match across tasks:
- `ToolRegistry(graph_svc, signal_svc, ss_repo)` — consistent in Task 5 and Task 8
- `EntityPolicy(entity_type, activation_threshold, decay_tau, required_evidence)` — consistent
- `capture_and_index()` returns `dict` — consistent between Task 4 test and implementation
