# OpenClaw Android Deployment Design Spec

> Deploy OpenClaw with screen-memory plugin on Android phone using lightweight glibc approach.

## 1. Overview

### 1.1 Goal

Deploy OpenClaw AI agent platform on an Android phone (connected via ADB), then install the screen-memory OpenClaw plugin that connects to the screen-memory Android app's HTTP API for screen capture and OCR.

### 1.2 Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Deployment approach | Lightweight glibc | ~200MB, near-native performance, existing setup script |
| Termux source | F-Droid | Already installed, compatible with pkg updates |
| AI model | GLM (Zhipu AI) | User's choice, Anthropic-compatible endpoint |
| Plugin language | Python 3 | Existing plugin spec is Python, user preference |
| Plugin ↔ App comm | HTTP API (localhost:19700) | Screen-memory app provides HTTP server |
| APK status | Already installed manually | app-debug.apk on phone |

### 1.3 Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Android Phone                      │
│                                                      │
│  ┌──────────────────┐    ┌────────────────────────┐ │
│  │ Screen Memory App │    │       Termux           │ │
│  │   (Android APK)   │    │                        │ │
│  │                    │    │  glibc-runner          │ │
│  │ HTTP API :19700   │◄───│  └─ Node.js            │ │
│  │ - /capture        │    │     └─ OpenClaw        │ │
│  │ - /ocr            │    │        └─ screen-memory│ │
│  │ - /capture-and-ocr│    │           plugin (Py)  │ │
│  │ - /status         │    │                        │ │
│  └──────────────────┘    └────────────────────────┘ │
│         ▲                          ▲                 │
│    Accessibility           GLM API (cloud)          │
│    MediaProjection         open.bigmodel.cn          │
└─────────────────────────────────────────────────────┘
```

---

## 2. Deployment Steps

### 2.1 Step 1: Verify screen-memory Android app

The APK is already installed manually. Verify it works:

```bash
# From ADB shell or Termux
curl http://localhost:19700/status
# Expected: {"status": "running", ...}
```

Prerequisites on phone:
- Accessibility service enabled: Settings → Accessibility → ScreenMemoryService
- MediaProjection permission granted: open app → tap authorize button

If `/status` returns connection refused, check:
1. App is running (not killed by system)
2. Accessibility service is enabled
3. MediaProjection permission is granted

### 2.2 Step 2: Install OpenClaw (lightweight glibc)

```bash
# In Termux
pkg update -y && pkg install -y curl git

# One-click install (glibc approach from myopenclawhub.com)
curl -sL myopenclawhub.com/install | bash && source ~/.bashrc

# During installation, when prompted for optional tools:
# - tmux: YES (required for persistent gateway)
# - Others: optional
```

The install script handles:
- glibc-runner installation (dynamic linker)
- Node.js v22 LTS (Linux ARM64 binary via glibc wrapper)
- Build tools (python, make, cmake, clang)
- OpenClaw core package

Verify installation:
```bash
openclaw --version
node --version
```

### 2.3 Step 3: Configure GLM API

```bash
openclaw onboard
```

Configuration:
- Admin password: user-defined
- AI model provider: Anthropic (compatible endpoint)
- API Key: `759e435c24fd4c89be441e03cfeb7c14.QJn8He1GTMHC0dWw`
- Base URL: `https://open.bigmodel.cn/api/anthropic`
- Gateway port: 3000 (default)

### 2.4 Step 4: Deploy screen-memory plugin

```bash
# Ensure Python is available (should be installed by OpenClaw build tools)
python --version
# If not: pkg install python

# Copy plugin to OpenClaw plugins directory
# (exact path depends on OpenClaw version, typically ~/.openclaw/plugins/)
cp -r screen-memory/ ~/.openclaw/plugins/screen-memory/

# Or use openclaw plugins install if supported
```

Plugin configuration for Android HTTP adapter:
```yaml
screen_memory:
  screen_memory_api_url: "http://localhost:19700"
  database_path: "~/.screenmemory/db.sqlite"
  screenshot_dir: "~/.screenmemory/screenshots"
  capture:
    default_quality: 80
  ocr:
    preferred_engine: "system"  # Use app's ML Kit OCR via HTTP
    ai_fallback: true
```

On Android, the plugin's capture adapter calls the screen-memory app HTTP API instead of native platform APIs:
- `POST /capture` → capture screenshot
- `POST /ocr` → OCR on image
- `POST /capture-and-ocr` → combined operation

### 2.5 Step 5: Start and verify

```bash
# Start gateway in tmux for persistence
tmux new -s openclaw
openclaw gateway

# In another Termux session, verify:
# 1. Screen-memory app
curl http://localhost:19700/status

# 2. OpenClaw gateway
curl http://localhost:3000

# 3. Test capture via OpenClaw agent (in web console)
#    Use the screen_capture tool through the agent
```

Access web console from computer:
```bash
# Get phone IP
ifconfig  # or ip addr show

# Browser: http://<phone-ip>:3000
```

---

## 3. Android-Specific Configuration

### 3.1 System Settings (Critical)

| Setting | Path | Why |
|---------|------|-----|
| Battery optimization off | Settings → Battery → Termux → Don't optimize | Prevent system from killing OpenClaw gateway |
| Phantom Process Killer off | Developer options → Pause cached apps | Android 12+ kills background processes aggressively |
| Lock Termux in recents | Recent apps → Pull down Termux card → Lock | Prevent accidental swipe-to-close |
| Stay awake (dev only) | Developer options → Stay awake | Keep screen on during setup |

### 3.2 Termux Source Mirror (China)

If `pkg update` is slow:
```bash
termux-change-repo
# Select: Mirrors by country → China → mirrors.tuna.tsinghua.edu.cn
```

### 3.3 npm Mirror (if needed)

```bash
npm config set registry https://registry.npmmirror.com
```

---

## 4. Error Handling

| Problem | Detection | Solution |
|---------|-----------|----------|
| Termux mirror slow | `pkg update` timeout | `termux-change-repo` → China mirror |
| glibc install fail | Script 404 error | Check network, retry |
| screen-memory app unreachable | `curl localhost:19700/status` fails | Check accessibility service, app running |
| OpenClaw gateway killed | Process disappears | tmux + battery optimization off |
| Python not found | `python --version` fails | `pkg install python` |
| GLM API connection fail | Gateway log errors | Verify API key, check network |
| Plugin load fail | OpenClaw startup error | Check plugin directory, Python path |
| tmux session lost | `tmux ls` empty | Gateway was killed, check battery settings |

---

## 5. Integration: Plugin HTTP Adapter

The screen-memory plugin's Android adapter replaces native capture/OCR with HTTP calls to the screen-memory Android app:

```python
class AndroidHttpCaptureAdapter(ScreenCaptureAdapter):
    """Calls screen-memory Android app HTTP API."""

    def __init__(self, base_url: str = "http://localhost:19700"):
        self._base_url = base_url

    def capture(self, quality: int = 80, region=None) -> CaptureResult:
        resp = requests.post(f"{self._base_url}/capture", json={"quality": quality})
        data = resp.json()
        return CaptureResult(
            file_path=data["image_path"],
            width=data["width"],
            height=data["height"],
            capture_time_ms=data["timestamp"],
            app_name=data.get("app_name"),
        )

    def recognize(self, image_path: str) -> OcrResult:
        with open(image_path, "rb") as f:
            import base64
            img_b64 = base64.b64encode(f.read()).decode()
        resp = requests.post(f"{self._base_url}/ocr", json={"image": img_b64})
        data = resp.json()
        return OcrResult(
            text=data["text"],
            confidence=data.get("confidence", 0.8),
            blocks=data.get("blocks", []),
            source="system",
        )
```

---

## 6. Rollback Plan

If the lightweight glibc approach has compatibility issues:

1. Uninstall: `oa --uninstall`
2. Switch to proot-distro approach:
   ```bash
   pkg install proot-distro
   proot-distro install ubuntu
   proot-distro login ubuntu
   # Then follow traditional Ubuntu → Node.js → OpenClaw path
   ```
3. Re-deploy plugin in Ubuntu environment
