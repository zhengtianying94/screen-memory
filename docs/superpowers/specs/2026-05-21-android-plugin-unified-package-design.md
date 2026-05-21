# Android Plugin Unified Package Design

Date: 2026-05-21
Status: Approved

## Problem

The Android screen-memory plugin (`screen-memory-android/mcp-server/screen_memory_server.py`) only implements the data layer (NocturneUri, Database, GraphRepo), missing 60% of Windows plugin capabilities: GraphService, SignalService, ScreenshotRepo, IndexService, ToolRegistry, CLI, and the actual MCP/OpenClaw protocol integration.

## Decision

**Unify into a single shared package.** The Windows `screen-memory` package already has platform-independent business logic and Android adapters (`android_capture.py`, `mlkit_ocr.py`). Android deployment installs the same package, and `platform_factory.py` auto-routes to the correct adapters.

The standalone `screen-memory-android/mcp-server/` directory will be **deleted**.

## Module Classification

### Platform-Independent (shared, zero changes)

| Module | Purpose |
|--------|---------|
| `models/uri.py` | Nocturne URI parsing |
| `storage/database.py` | SQLite schema + connection |
| `storage/graph_repo.py` | Node/memory/edge/FTS CRUD |
| `storage/screenshot_repo.py` | Screenshot metadata storage |
| `services/graph_service.py` | Subtree queries, path materialization, traversal, bulk ops |
| `services/signal_service.py` | Signal accumulation, decay scoring, entity activation |
| `services/index_service.py` | capture -> OCR -> store -> graph pipeline |
| `tools/registry.py` | 8-tool registration and dispatch |
| `adapters/capture.py` | Capture abstract interface |
| `adapters/ocr.py` | OCR abstract interface + fallback chain |
| `adapters/http_client.py` | APK HTTP communication client |
| `adapters/tesseract_ocr.py` | Tesseract OCR (optional fallback) |
| `adapters/android_capture.py` | Android capture (HTTP -> APK) |
| `adapters/mlkit_ocr.py` | ML Kit OCR (HTTP -> APK) |

### Platform-Specific (routed by platform_factory)

| Platform | Capture Adapter | OCR Adapter |
|----------|----------------|-------------|
| Windows | `windows_capture.py` (PIL ImageGrab + Win32) | `winrt_ocr.py` (WinRT) |
| Android | `android_capture.py` (HTTP -> APK) | `mlkit_ocr.py` (HTTP -> APK) |

## Changes Required

### screen-memory/ (shared package)

| File | Change |
|------|--------|
| `pyproject.toml` | Add `[android]` optional deps group (empty - no extra deps needed) |
| `adapters/platform_factory.py` | **Already correct** - `_is_android()` + `AndroidCapture`/`MlKitOcr` routing exists |
| `cli.py` | Fix hardcoded Windows DB path (`D:\ScreenMemo\...`) to cross-platform default (`$HOME/.screenmemory/screen-memory.db` via `pathlib`) |

### screen-memory-android/

| File | Change |
|------|--------|
| `mcp-server/screen_memory_server.py` | **DELETE** - replaced by shared package |
| `mcp-server/tests/` | **DELETE** - replaced by shared tests |
| `deploy-plugin.sh` | Change from `pip install ./mcp-server/` to `pip install -e /path/to/screen-memory/` |

### screen-memory/tests/

| File | Change |
|------|--------|
| `test_platform_factory_android.py` | Expand: verify Android detection -> correct adapter selection |
| `test_index_service.py` | Add: APK unavailable graceful degradation tests |
| `test_android_tools.py` | Add: verify all 8 tools work with Android mock |
| `test_cli.py` (new or expanded) | Add: Android environment CLI initialization |

## Graceful Degradation

When the APK HTTP service is unavailable:

| Scenario | Behavior |
|----------|----------|
| APK not running | Capture/OCR tools return `{"ok": false, "error": "capture_unavailable"}` |
| MediaProjection not authorized | Same as above |
| HTTP timeout | `AndroidCapture`: no retry (retries=0). `MlKitOcr`: 1 retry |
| OCR returns empty | Store screenshot with `ocr_text=None`, continue normally |
| Memory/graph tools | Never affected - pure SQLite operations |

`AndroidCapture.is_available()` and `MlKitOcr.is_available()` (already implemented) allow pre-flight checks.

## TDD Strategy

### Test Layers

1. **Shared unit tests** (already exist): uri, database, graph_repo, graph_service, signal, screenshot_repo, index_service, tools
2. **Shared integration tests** (already exist): full pipeline tests
3. **Android-specific tests** (to add/expand):
   - Platform factory Android routing
   - IndexService degradation when APK unavailable
   - All 8 tools with Android mock adapters
   - CLI initialization on Android

### TDD Flow Per Change

For each modification:
1. Write failing test first
2. Minimal implementation to pass
3. Refactor
4. Verify all existing tests still pass (Windows regression check)

## Feature Checklist (Android Gains)

| # | Feature | Status After Change |
|---|---------|-------------------|
| 1 | NocturneUri | Shared (already exists) |
| 2 | Database + Schema | Shared (already exists) |
| 3 | GraphRepo CRUD | Shared (already exists) |
| 4 | GraphService (subtree, traversal, bulk, path materialization) | **NEW for Android** |
| 5 | SignalService (accumulation, decay, activation, archive) | **NEW for Android** |
| 6 | ScreenshotRepo (metadata storage, search) | **NEW for Android** |
| 7 | IndexService (capture -> OCR -> store -> graph) | **NEW for Android** |
| 8 | ToolRegistry (8 tools: memory_write/read/search/delete, graph_query_subtree, signal_ingest/activate, screenshot_search) | **NEW for Android** |
| 9 | CLI (command-line interface) | **NEW for Android** |
| 10 | Android capture + ML Kit OCR | Shared (already exists) |
| 11 | Platform factory auto-routing | Enhanced for Android |
| 12 | Graceful degradation | **NEW** (IndexService + adapters) |

## OpenClaw Registration

Both platforms use the same `openclaw.plugin.json`:

```json
{
  "name": "screen-memory",
  "version": "0.1.0",
  "entry_point": "screen_memory.tools:register",
  "tools": [
    "memory_write", "memory_read", "memory_search", "memory_delete",
    "graph_query_subtree", "signal_ingest", "signal_activate", "screenshot_search"
  ]
}
```

On Android, `platform_factory` detects `sys.platform == "android"` or `ANDROID_ROOT` in env, and wires `AndroidCapture` + `MlKitOcr` as the capture/OCR adapters. All 8 tools work identically.

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Windows regression | Run full Windows test suite before/after each change |
| Termux pip install fails | Pillow only needed for `region` crop in `android_capture.py`; make it optional with lazy import |
| Pillow missing on Android | `android_capture.py` already handles region cropping — wrap PIL import in try/except, skip region support if unavailable |
| APK HTTP service flaky | Graceful degradation + retry strategy already designed |
| DB path conflicts | Android uses `$HOME/.screenmemory/screen-memory.db`, isolated from Windows path |
