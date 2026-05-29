# Android Screen Memory Adapter Design Spec

> Android platform adapters for the OpenClaw screen-memory plugin, enabling screen capture and OCR on Android devices via a lightweight auxiliary APK.

## 1. Overview

### 1.1 Goal

Extend the existing screen-memory Python plugin to support Android by:

- Adding `AndroidCapture(ScreenCapture)` adapter that captures screenshots via a local auxiliary APK's HTTP API
- Adding `MlKitOcr(OCREngine)` adapter that performs OCR via the same auxiliary APK's ML Kit integration
- Updating `platform_factory.py` to auto-detect Android and wire the new adapters
- Building a standalone Android APK that provides Accessibility Service, MediaProjection-based capture, and ML Kit Text Recognition over a localhost HTTP server

No changes to existing service layer, storage layer, or tool layer code.

### 1.2 Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Architecture | Reuse existing abstract interfaces, add Android implementations only | Minimal code change, maximum reuse |
| Capture method | MediaProjection via auxiliary APK | Works on non-rooted devices, single user authorization |
| OCR engine | ML Kit Text Recognition (offline) | Good CJK support, no network required |
| IPC mechanism | HTTP localhost (NanoHTTPD) | Simple, Python stdlib urllib sufficient, no extra dependencies |
| Deployment | Termux (Python) + auxiliary APK | Separation of concerns, APK handles Android-native APIs, Python handles logic |
| Target devices | Non-rooted consumer devices | No ADB or root requirements |
| Dev methodology | SDD + TDD | Spec-driven, test-driven |

### 1.3 Architecture (Adapter Layer Only)

```
┌─────────────────────────────────────────────────────────┐
│  OpenClaw Agent (Python, Termux)                         │
├─────────────────────────────────────────────────────────┤
│  platform_factory.py  (modified: +android branch)        │
├────────────────────┬────────────────────────────────────┤
│  AndroidCapture    │  MlKitOcr                           │
│  (new)             │  (new)                              │
├────────────────────┴────────────────────────────────────┤
│  HttpClient (new, shared)                                │
├─────────────────────────────────────────────────────────┤
│  HTTP localhost:19700                                    │
├─────────────────────────────────────────────────────────┤
│  Auxiliary APK (Android native, separate project)        │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐ │
│  │ MediaProj    │ │ ML Kit OCR   │ │ NanoHTTPD Server │ │
│  │ Capture      │ │              │ │ (port 19700)     │ │
│  └──────────────┘ └──────────────┘ └──────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

All existing layers (Tools, Services, Storage) remain unchanged.

---

## 2. AndroidCapture Adapter

### 2.1 Interface

```python
class AndroidCapture(ScreenCapture):
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:19700",
        screenshot_dir: Optional[str] = None,
        timeout: int = 10,
    ) -> None: ...

    def capture(self, quality: int = 80, region: Optional[dict] = None) -> CaptureResult: ...
    def is_available(self) -> bool: ...
```

### 2.2 Behavior

- `capture()`: POST `/capture` with `{"quality": quality}` to auxiliary APK. APK returns base64-encoded JPEG + metadata. Python decodes, saves to `screenshot_dir/YYYY/MM/DD/HHMMSS.jpg`, returns `CaptureResult`.
- `region` handling: Full-screen capture from APK, then PIL crop on Python side.
- `app_name`: Derived from `app_package` field in APK response (e.g., `com.tencent.mm` → stored as `app_package`).
- `is_available()`: GET `/status`, returns `True` if APK HTTP server responds.
- Timeout: Single attempt, 10s default. No retry on capture (high-frequency operation, fail fast).

### 2.3 HTTP API Contract (POST /capture)

Request:
```json
{"quality": 80}
```

Response:
```json
{
  "image": "<base64 JPEG>",
  "width": 1080,
  "height": 2400,
  "app_package": "com.tencent.mm",
  "capture_time_ms": 85
}
```

Error: HTTP 503 if MediaProjection not authorized, HTTP 500 on capture failure.

---

## 3. MlKitOcr Adapter

### 3.1 Interface

```python
class MlKitOcr(OCREngine):
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:19700",
        timeout: int = 15,
    ) -> None: ...

    def is_available(self) -> bool: ...
    def recognize(self, image_data: bytes) -> OCRResult: ...
```

### 3.2 Behavior

- `recognize()`: POST `/ocr` with base64-encoded image bytes. APK runs ML Kit Text Recognition, returns text + blocks.
- Block format mapping: APK returns `[{text, bbox: [x, y, w, h], confidence}]` → converted to `OCRResult.blocks` as `tuple((text, (x, y, w, h), confidence), ...)`.
- Confidence: ML Kit doesn't provide per-block confidence. Fixed value 0.85 (stable quality for CJK).
- `is_available()`: GET `/status`, checks `ocr_ready` field.
- Timeout: 15s (OCR is heavier than capture).
- On failure: Returns `OCRResult(text="", confidence=0.0, engine="mlkit", source="system")` — never raises, allows fallback chain to continue.

### 3.3 HTTP API Contract (POST /ocr)

Request:
```json
{"image": "<base64 image bytes>"}
```

Response:
```json
{
  "text": "Full recognized text",
  "blocks": [
    {"text": "Hello", "bbox": [10, 20, 100, 30], "confidence": 0.85}
  ],
  "engine": "mlkit",
  "processing_time_ms": 120
}
```

### 3.4 OCR Fallback Chain (Android)

```
1. MlKitOcr (auxiliary APK ML Kit)
   ↓ if unavailable or confidence < 0.5
2. TesseractOcr (Termux tesseract)
   ↓ if unavailable or confidence < 0.5
3. AiFallbackOcr (OpenClaw LLM multimodal)
   ↓ if unavailable
4. Store screenshot without OCR text, mark for later processing
```

---

## 4. HttpClient (Shared)

### 4.1 Interface

```python
class ScreenMemoryHttpClient:
    def __init__(self, base_url: str, timeout: int = 10, retries: int = 2) -> None: ...

    def get(self, path: str) -> dict: ...
    def post(self, path: str, data: dict) -> dict: ...
    def is_reachable(self) -> bool: ...
```

### 4.2 Behavior

- Uses Python stdlib `urllib.request` only — no third-party HTTP dependencies.
- Retry: Up to `retries` attempts with 1s delay between attempts.
- All exceptions caught and converted to `ConnectionError` with descriptive message.

---

## 5. Platform Factory Changes

### 5.1 Android Detection

```python
def _is_android() -> bool:
    return sys.platform == "android" or "ANDROID_ROOT" in os.environ
```

### 5.2 create_capture (modified)

```python
def create_capture(screenshot_dir=None):
    platform = sys.platform

    if platform == "win32":
        from screen_memory.adapters.windows_capture import WindowsCapture
        return WindowsCapture(screenshot_dir=screenshot_dir)

    if _is_android():
        from screen_memory.adapters.android_capture import AndroidCapture
        return AndroidCapture(screenshot_dir=screenshot_dir)

    # darwin / linux unchanged...
```

### 5.3 _get_platform_engines (modified)

```python
def _get_platform_engines():
    engines = []

    if sys.platform == "win32":
        engines.append(WinRtOcr())

    if _is_android():
        from screen_memory.adapters.mlkit_ocr import MlKitOcr
        engines.append(MlKitOcr())

    # Tesseract fallback (all platforms)
    engines.append(TesseractOcr())
    return engines
```

### 5.4 Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `SCREEN_MEMORY_APK_URL` | `http://127.0.0.1:19700` | Auxiliary APK HTTP address |
| `SCREEN_MEMORY_APK_TIMEOUT` | `10` | Capture timeout (seconds) |
| `SCREEN_MEMORY_APK_OCR_TIMEOUT` | `15` | OCR timeout (seconds) |

---

## 6. Auxiliary APK (Android Native Project)

### 6.1 Project Structure

```
screen-memory-android/
├── app/
│   ├── src/main/
│   │   ├── AndroidManifest.xml
│   │   ├── java/com/screenmemory/android/
│   │   │   ├── MainActivity.kt          # Launch screen, guide user to enable Accessibility + MediaProjection
│   │   │   ├── ScreenMemoryService.kt   # Accessibility Service
│   │   │   ├── HttpServer.kt            # NanoHTTPD localhost server
│   │   │   ├── CaptureHandler.kt        # MediaProjection-based screenshot
│   │   │   ├── OcrHandler.kt            # ML Kit Text Recognition
│   │   │   └── StatusHandler.kt         # /status endpoint
│   │   └── res/
│   └── build.gradle.kts
├── build.gradle.kts
└── settings.gradle.kts
```

### 6.2 Core Components

| Component | Responsibility | Key APIs |
|-----------|---------------|----------|
| `MainActivity` | Guide user to enable Accessibility Service + authorize MediaProjection (one-time system dialog) | `Settings.ACTION_ACCESSIBILITY_SETTINGS`, `MediaProjectionManager.createScreenCaptureIntent()` |
| `ScreenMemoryService` | Accessibility Service, holds MediaProjection instance for background capture | `getRootInActiveWindow()` for package name, stored `MediaProjection` instance |
| `CaptureHandler` | Screenshot via `VirtualDisplay` + `ImageReader` | `MediaProjection.createVirtualDisplay()`, `ImageReader.acquireLatestImage()` |
| `OcrHandler` | ML Kit Text Recognition v2 with Chinese support | `TextRecognition.getClient(ChineseTextRecognizerOptions)` |
| `HttpServer` | NanoHTTPD on port 19700, routes to handlers | `/capture`, `/ocr`, `/capture-and-ocr`, `/status` |
| `StatusHandler` | Health check endpoint | Returns `{running, ocr_ready, service_enabled}` |

### 6.3 API Endpoints

| Endpoint | Method | Request | Response |
|----------|--------|---------|----------|
| `/capture` | POST | `{"quality": 80}` | `{image, width, height, app_package, capture_time_ms}` |
| `/ocr` | POST | `{"image": "<base64>"}` | `{text, blocks, engine, processing_time_ms}` |
| `/capture-and-ocr` | POST | `{"quality": 80}` | Combined capture + OCR response |
| `/status` | GET | — | `{running, ocr_ready, service_enabled}` |

### 6.4 Permissions

```xml
<uses-permission android:name="android.permission.INTERNET" />
<!-- Accessibility Service declared in manifest, user enables manually -->
<!-- MediaProjection authorization via system dialog at first launch -->
```

### 6.5 Screenshot Method

`MediaProjection` + `VirtualDisplay` + `ImageReader`:

1. First launch: `MainActivity` calls `MediaProjectionManager.createScreenCaptureIntent()`, system shows authorization dialog
2. User approves once → `ScreenMemoryService` stores the `MediaProjection` instance
3. On `/capture` request: `CaptureHandler` creates `VirtualDisplay` → `ImageReader` gets frame → compress to JPEG → return base64
4. `app_package` obtained from `AccessibilityService.getRootInActiveWindow().packageName`

---

## 7. Error Handling

### 7.1 Error Categories

| Category | Examples | Strategy |
|----------|----------|----------|
| APK not running | Connection refused on port 19700 | Return error with message "Start screen-memory APK first" |
| MediaProjection revoked | User revoked permission, APK restart | APK returns HTTP 503, Python adapter returns error |
| OCR unavailable | ML Kit not initialized | Fallback chain continues to Tesseract |
| APK crash during timed capture | Socket closed mid-stream | Python thread detects error, stops cleanly |
| All OCR engines fail | ML Kit + Tesseract + AI all unavailable | Store screenshot with `ocr_text=None`, mark for later |

### 7.2 Degradation Behavior

```
APK running + OCR ready       → Full capture + OCR pipeline
APK running + OCR unavailable  → Capture only, OCR deferred
APK not running                 → Error with installation/start instructions
APK crashes mid-operation       → Graceful stop, no thread hang
```

---

## 8. File Changes Summary

### 8.1 Python Plugin (in screen-memory/)

| File | Action | Description |
|------|--------|-------------|
| `adapters/android_capture.py` | NEW | AndroidCapture adapter |
| `adapters/mlkit_ocr.py` | NEW | MlKitOcr adapter |
| `adapters/http_client.py` | NEW | Shared HTTP client for APK communication |
| `adapters/platform_factory.py` | MODIFY | Add `_is_android()` detection + Android branches |
| `adapters/__init__.py` | MODIFY | Export new adapters |

### 8.2 Android APK (new project)

| Path | Description |
|------|-------------|
| `screen-memory-android/` | Complete Android Studio project |

### 8.3 Test Files

| File | Layer | Cases |
|------|-------|-------|
| `tests/unit/test_android_capture.py` | Unit | 7 |
| `tests/unit/test_mlkit_ocr.py` | Unit | 7 |
| `tests/unit/test_http_client.py` | Unit | 5 |
| `tests/unit/test_platform_factory_android.py` | Unit | 4 |
| `tests/integration/test_android_pipeline.py` | Integration | 10 |
| `tests/tools/test_android_tools.py` | Tool | 5 |
| `screen-memory-android/app/src/androidTest/...` | Instrumented | 4 |

---

## 9. Test Case Specification

### 9.1 test_android_capture.py

| # | Test Case | Mock | Expected |
|---|-----------|------|----------|
| 1 | capture success | HTTP 200, valid JPEG + metadata | `CaptureResult` returned, file written |
| 2 | capture APK unavailable | HTTP connection refused | Raises `ConnectionError` |
| 3 | capture timeout | HTTP timeout | Raises timeout exception |
| 4 | is_available running | GET /status 200 | Returns `True` |
| 5 | is_available not running | GET /status connection fail | Returns `False` |
| 6 | capture with region | Full capture + PIL crop | Cropped `CaptureResult`, dimensions match region |
| 7 | capture app_package | Response includes `app_package` | `CaptureResult.app_package` non-null |

### 9.2 test_mlkit_ocr.py

| # | Test Case | Mock | Expected |
|---|-----------|------|----------|
| 1 | recognize success | HTTP 200, text + blocks | `OCRResult.text` correct, `blocks` format compatible |
| 2 | recognize empty image | HTTP 200, empty text | `OCRResult.text=""`, `confidence=0.0` |
| 3 | recognize APK unavailable | HTTP connection refused | `OCRResult(text="", confidence=0.0, engine="mlkit")` |
| 4 | recognize timeout | HTTP timeout | Empty result, no exception |
| 5 | is_available OCR ready | GET /status `ocr_ready=true` | Returns `True` |
| 6 | is_available OCR not ready | GET /status `ocr_ready=false` | Returns `False` |
| 7 | blocks format conversion | ML Kit nested blocks | Converted to `(text, (x,y,w,h), confidence)` tuples |

### 9.3 test_http_client.py

| # | Test Case | Mock | Expected |
|---|-----------|------|----------|
| 1 | GET success | 200 JSON | Returns parsed dict |
| 2 | POST success | 200 JSON | Returns parsed dict |
| 3 | Retry on failure | Fail once, succeed second | Returns success result |
| 4 | Retry exhausted | 3 consecutive failures | Raises `ConnectionError` |
| 5 | Timeout config | Set 5s timeout | Request uses correct timeout |

### 9.4 test_platform_factory_android.py

| # | Test Case | Setup | Expected |
|---|-----------|-------|----------|
| 1 | sys.platform android | Mock `sys.platform="android"` | `create_capture()` returns `AndroidCapture` |
| 2 | ANDROID_ROOT env var | Set `ANDROID_ROOT` in environ | `create_capture()` returns `AndroidCapture` |
| 3 | OCR chain first engine | Android platform | `engines[0]` is `MlKitOcr` |
| 4 | OCR chain order | Android platform | Chain: MlKitOcr → TesseractOcr |

### 9.5 test_android_pipeline.py (Integration)

| # | Test Case | Flow | Expected |
|---|-----------|------|----------|
| 1 | Capture → OCR → insert → search | Mock APK → full pipeline | Search finds OCR text |
| 2 | 5 captures, search 1 keyword | 5 different screenshots | Only 1 result returned |
| 3 | Capture with no OCR text | Empty screen OCR | Record exists, search returns 0 |
| 4 | CJK OCR text search | Chinese OCR text | FTS5 search hits |
| 5 | OCR fallback MlKit timeout → Tesseract | MlKitOcr returns low confidence | TesseractOcr result used |
| 6 | All OCR unavailable | All engines fail | Screenshot stored with `ocr_text=None` |
| 7 | Timed capture lifecycle | start → 3 captures → stop | count=3, all indexed |
| 8 | Timed capture APK disconnect | Start → APK dies mid-stream | Stops cleanly, no hang |
| 9 | Signal from screenshot | Capture with person name → ingest → activate | Graph searchable |
| 10 | app_package stored | Capture from WeChat | `app_package="com.tencent.mm"` in DB |

### 9.6 test_android_tools.py (Tool Layer)

| # | Test Case | Mock | Expected |
|---|-----------|------|----------|
| 1 | CLI capture --db :memory: | Android capture mock | Output has screenshot_id + ocr_text_preview |
| 2 | CLI capture --no-ocr | Android capture mock | `ocr_engine="none"` |
| 3 | screenshot-search Android content | Android OCR text in DB | Correct search results |
| 4 | Custom APK URL env var | `SCREEN_MEMORY_APK_URL` set | Adapter uses custom URL |
| 5 | Custom timeout env var | `SCREEN_MEMORY_APK_TIMEOUT=5` | Adapter uses 5s timeout |

### 9.7 Android Instrumented Tests

| # | Test Case | Type | Expected |
|---|-----------|------|----------|
| 1 | HttpServer starts | Instrumented | Port 19700 listening |
| 2 | /status endpoint | Instrumented | Returns `{running: true}` |
| 3 | MediaProjection capture | Instrumented | Valid JPEG bytes, dimensions match screen |
| 4 | ML Kit OCR | Instrumented | Correct text from test image |

---

## 10. Dependency Impact

### Python Side

No new Python dependencies. `urllib.request` is stdlib, PIL already required.

### Android Side

| Dependency | Purpose | Size |
|------------|---------|------|
| NanoHTTPD | Embedded HTTP server | ~100KB |
| ML Kit Text Recognition v2 | Offline OCR with CJK | ~15MB (downloaded on first use) |
| AndroidX Accessibility | Accessibility Service | Part of Android SDK |

---

## 11. Out of Scope

- macOS / Linux platform adapters (no change)
- Changes to URI Graph service, signal accumulator, or tool registry
- Android UI for browsing screenshots or managing memories (APK is headless service)
- Cloud sync or remote access to screenshot data
- On-device AI model for OCR (ML Kit is the primary, not local LLM)
