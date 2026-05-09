# OpenClaw Android Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy OpenClaw with screen-memory plugin on connected Android phone via lightweight glibc approach, configure GLM API, and verify end-to-end screenshot + OCR pipeline.

**Architecture:** Termux (F-Droid) → glibc-runner → Node.js → OpenClaw → screen-memory Python plugin → HTTP API → screen-memory Android app (APK). The plugin code already exists in `screen-memory/` — this plan deploys it.

**Tech Stack:** Termux, glibc-runner, Node.js 22 LTS, OpenClaw, Python 3.10+, Pillow, GLM API (Anthropic-compatible endpoint)

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `screen-memory-android/deploy.sh` | Create | One-shot deployment script that orchestrates all steps on the phone |
| `screen-memory-android/deploy-plugin.sh` | Create | Plugin deployment script (copies Python code, installs deps) |
| `screen-memory-android/verify.sh` | Create | Verification script for health checks |
| `screen-memory/openclaw.plugin.json` | Existing | Plugin manifest — no changes needed |
| `screen-memory/screen_memory/` | Existing | Plugin Python code — no changes needed |

---

### Task 1: Verify screen-memory Android app connectivity

**Files:**
- Verify: `screen-memory-android/app/src/main/java/com/screenmemory/android/HttpServer.kt`

- [ ] **Step 1: Verify phone ADB connection**

Run from computer:
```bash
adb devices
```
Expected: Device listed, not "unauthorized"

- [ ] **Step 2: Check screen-memory app is running via ADB shell**

```bash
adb shell "curl -s http://localhost:19700/status"
```
Expected: `{"running":true,"ocr_ready":true,"service_enabled":true,...}`

If connection refused:
```bash
# Check if app is running
adb shell "pm list packages | grep screenmemory"
# Force-stop and restart
adb shell "am force-stop com.screenmemory.android"
adb shell "am start -n com.screenmemory.android/.MainActivity"
# Re-check status
adb shell "curl -s http://localhost:19700/status"
```

- [ ] **Step 3: Test capture endpoint**

```bash
adb shell "curl -s -X POST http://localhost:19700/capture -H 'Content-Type: application/json' -d '{\"quality\":50}' | head -c 200"
```
Expected: JSON with `"image"` field containing base64 data, `"width"`, `"height"` fields

- [ ] **Step 4: Test OCR endpoint**

First capture, then OCR:
```bash
adb shell "curl -s -X POST http://localhost:19700/capture-and-ocr -H 'Content-Type: application/json' -d '{\"quality\":50}'" > /tmp/test_capture.json
# Check text field exists
python -c "import json; d=json.load(open('/tmp/test_capture.json')); print('OCR text:', d.get('text','')[:200])"
```
Expected: JSON with `"text"` field containing OCR result, `"blocks"` array

- [ ] **Step 5: Commit verification results**

Document which endpoints work and their exact response formats for reference.

---

### Task 2: Create deployment script

**Files:**
- Create: `screen-memory-android/deploy.sh`

- [ ] **Step 1: Write the main deployment script**

Create `screen-memory-android/deploy.sh`:

```bash
#!/bin/bash
set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ---- Configuration ----
GLM_API_KEY="759e435c24fd4c89be441e03cfeb7c14.QJn8He1GTMHC0dWw"
GLM_BASE_URL="https://open.bigmodel.cn/api/anthropic"
SCREEN_MEMORY_APK_URL="http://127.0.0.1:19700"
OPENCLAW_PORT=3000

# ---- Pre-flight checks ----
info "=== Pre-flight checks ==="

# Check Termux
if [ -z "${TERMUX_VERSION:-}" ] && [ ! -d "/data/data/com.termux" ]; then
    error "Not running in Termux. Please run this script inside Termux on your Android device."
fi
info "Termux detected"

# Check Android architecture
ARCH=$(uname -m)
if [ "$ARCH" != "aarch64" ] && [ "$ARCH" != "arm64" ]; then
    warn "Architecture is $ARCH, expected aarch64. Installation may fail."
fi
info "Architecture: $ARCH"

# Check disk space (need ~500MB)
AVAILABLE=$(df -h . | awk 'NR==2 {print $4}')
info "Available disk space: $AVAILABLE"

# ---- Step 1: Configure Termux mirror (China) ----
info "=== Step 1: Configure Termux mirror ==="
if [ ! -f "$PREFIX/etc/apt/sources.list.bak" ]; then
    cp "$PREFIX/etc/apt/sources.list" "$PREFIX/etc/apt/sources.list.bak"
    sed -i 's|https://packages.termux.dev|https://mirrors.tuna.tsinghua.edu.cn/termux|g' "$PREFIX/etc/apt/sources.list"
    info "Switched to Tsinghua mirror"
else
    info "Mirror already configured, skipping"
fi

# ---- Step 2: Update packages and install dependencies ----
info "=== Step 2: Update packages ==="
pkg update -y || warn "pkg update had warnings"
pkg install -y curl git || error "Failed to install curl/git"

# ---- Step 3: Verify screen-memory app ----
info "=== Step 3: Verify screen-memory app ==="
if curl -s --connect-timeout 3 "$SCREEN_MEMORY_APK_URL/status" > /dev/null 2>&1; then
    STATUS=$(curl -s "$SCREEN_MEMORY_APK_URL/status")
    info "Screen-memory app responding: $STATUS"
else
    warn "Screen-memory app not responding at $SCREEN_MEMORY_APK_URL"
    warn "Make sure the app is running and accessibility service is enabled."
    warn "Continuing installation anyway - you can start the app later."
fi

# ---- Step 4: Install OpenClaw (lightweight glibc) ----
info "=== Step 4: Install OpenClaw ==="
if command -v openclaw &> /dev/null; then
    info "OpenClaw already installed: $(openclaw --version 2>/dev/null || echo 'version unknown')"
else
    info "Installing OpenClaw via glibc approach..."
    info "This will take 5-15 minutes. Answer prompts as follows:"
    info "  - tmux: Y (recommended)"
    info "  - Other tools: n (can install later)"
    curl -sL myopenclawhub.com/install | bash || error "OpenClaw installation failed"

    # Source environment
    if [ -f ~/.bashrc ]; then
        source ~/.bashrc
    fi
    if [ -f ~/.profile ]; then
        source ~/.profile
    fi

    info "OpenClaw installation complete"
fi

# Verify Node.js
NODE_VER=$(node --version 2>/dev/null || echo "NOT FOUND")
info "Node.js version: $NODE_VER"

# ---- Step 5: Verify Python ----
info "=== Step 5: Verify Python ==="
if ! command -v python &> /dev/null && ! command -v python3 &> /dev/null; then
    info "Installing Python..."
    pkg install -y python || error "Failed to install Python"
fi
PY_VER=$(python --version 2>/dev/null || python3 --version 2>/dev/null)
info "Python version: $PY_VER"

# ---- Step 6: Configure GLM API for OpenClaw ----
info "=== Step 6: OpenClaw configuration ==="
info "Run 'openclaw onboard' to configure:"
info "  - Provider: Anthropic (compatible)"
info "  - API Key: $GLM_API_KEY"
info "  - Base URL: $GLM_BASE_URL"
info "  - Port: $OPENCLAW_PORT"
echo ""
warn "You need to run 'openclaw onboard' manually (it's interactive)"
echo ""

# ---- Step 7: Deploy screen-memory plugin ----
info "=== Step 7: Deploy screen-memory plugin ==="
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PLUGIN_SRC="$PROJECT_DIR/screen-memory"

# Find OpenClaw plugins directory
OC_HOME="${HOME}/.openclaw"
OC_PLUGINS="$OC_HOME/plugins"

if [ -d "$OC_HOME" ]; then
    info "OpenClaw home: $OC_HOME"
else
    warn "OpenClaw home not found at $OC_HOME"
    warn "Plugin will be deployed after openclaw onboard is complete"
fi

# ---- Summary ----
echo ""
info "=== Deployment Summary ==="
info "Termux mirror: Tsinghua"
info "Node.js: $NODE_VER"
info "Python: $PY_VER"
info "OpenClaw: $(command -v openclaw &>/dev/null && echo 'installed' || echo 'NOT FOUND')"
info "Screen-memory app: $(curl -s --connect-timeout 2 "$SCREEN_MEMORY_APK_URL/status" > /dev/null 2>&1 && echo 'running' || echo 'not responding')"
echo ""
info "=== Next Steps ==="
info "1. Run: openclaw onboard"
info "2. Configure API with provider=Anthropic, key=$GLM_API_KEY, url=$GLM_BASE_URL"
info "3. Run: bash $(dirname "$0")/deploy-plugin.sh"
info "4. Run: tmux new -s openclaw && openclaw gateway"
info "5. Run: bash $(dirname "$0")/verify.sh"
```

- [ ] **Step 2: Make script executable**

```bash
chmod +x screen-memory-android/deploy.sh
```

- [ ] **Step 3: Commit**

```bash
git add screen-memory-android/deploy.sh
git commit -m "feat: add OpenClaw deployment script for Android"
```

---

### Task 3: Create plugin deployment script

**Files:**
- Create: `screen-memory-android/deploy-plugin.sh`

- [ ] **Step 1: Write the plugin deployment script**

Create `screen-memory-android/deploy-plugin.sh`:

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

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PLUGIN_SRC="$PROJECT_DIR/screen-memory"

# ---- Pre-flight ----
info "=== Plugin Deployment ==="

# Verify plugin source exists
if [ ! -f "$PLUGIN_SRC/openclaw.plugin.json" ]; then
    error "Plugin source not found at $PLUGIN_SRC. Expected openclaw.plugin.json"
fi
info "Plugin source: $PLUGIN_SRC"

# Verify Python
PYTHON_CMD=""
if command -v python &> /dev/null; then
    PYTHON_CMD="python"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
else
    error "Python not found. Install with: pkg install python"
fi
info "Using Python: $($PYTHON_CMD --version)"

# ---- Find OpenClaw plugin directory ----
OC_HOME="${HOME}/.openclaw"

# Try multiple possible plugin locations
PLUGIN_DIR=""
for candidate in \
    "$OC_HOME/plugins" \
    "$OC_HOME/skills" \
    "${HOME}/.config/openclaw/plugins" \
    "$(npm root -g 2>/dev/null)/openclaw/plugins"; do
    if [ -d "$candidate" ] || [ -d "$(dirname "$candidate")" ]; then
        PLUGIN_DIR="$candidate"
        break
    fi
done

# If no standard location found, ask OpenClaw
if [ -z "$PLUGIN_DIR" ] && command -v openclaw &> /dev/null; then
    # Try to find via openclaw commands
    OC_PATH=$(which openclaw)
    OC_ROOT=$(dirname "$(dirname "$OC_PATH")")
    if [ -d "$OC_ROOT/lib/node_modules/openclaw" ]; then
        PLUGIN_DIR="$OC_ROOT/lib/node_modules/openclaw/plugins"
    fi
fi

# Fallback: create standard location
if [ -z "$PLUGIN_DIR" ]; then
    PLUGIN_DIR="$OC_HOME/plugins"
    warn "Could not auto-detect plugin directory, using $PLUGIN_DIR"
fi

info "Plugin directory: $PLUGIN_DIR"
mkdir -p "$PLUGIN_DIR"

# ---- Copy plugin files ----
info "=== Copying plugin files ==="
DEST="$PLUGIN_DIR/screen-memory"

# Remove old deployment if exists
if [ -d "$DEST" ]; then
    info "Removing previous plugin deployment"
    rm -rf "$DEST"
fi

# Copy plugin (exclude tests, dev files)
cp -r "$PLUGIN_SRC" "$DEST"
# Remove unnecessary files to save space on phone
rm -rf "$DEST/tests" "$DEST/.git" "$DEST/__pycache__" "$DEST/**/*.pyc" 2>/dev/null || true

info "Plugin copied to $DEST"

# ---- Install Python dependencies ----
info "=== Installing Python dependencies ==="
cd "$DEST"

# Install minimal deps (only Pillow is required)
if [ -f "pyproject.toml" ]; then
    info "Installing from pyproject.toml..."
    $PYTHON_CMD -m pip install --user Pillow>=10.0 2>/dev/null || {
        warn "pip install failed, trying pkg install..."
        pkg install -y python-pip 2>/dev/null || true
        $PYTHON_CMD -m pip install --user Pillow 2>/dev/null || warn "Pillow install failed - OCR image processing may not work"
    }
else
    warn "No pyproject.toml found, installing Pillow directly"
    $PYTHON_CMD -m pip install --user Pillow 2>/dev/null || warn "Pillow install failed"
fi

# ---- Verify plugin structure ----
info "=== Verifying plugin structure ==="

check_file() {
    if [ -f "$DEST/$1" ]; then
        info "  OK: $1"
    else
        warn "  MISSING: $1"
    fi
}

check_file "openclaw.plugin.json"
check_file "screen_memory/__init__.py"
check_file "screen_memory/tools/__init__.py"
check_file "screen_memory/adapters/android_capture.py"
check_file "screen_memory/adapters/mlkit_ocr.py"
check_file "screen_memory/adapters/http_client.py"

# ---- Set environment variables ----
info "=== Configuring environment ==="

ENV_FILE="$HOME/.screenmemory.env"
cat > "$ENV_FILE" << 'ENVEOF'
# Screen Memory Plugin Configuration
export SCREEN_MEMORY_APK_URL="http://127.0.0.1:19700"
export SCREEN_MEMORY_APK_TIMEOUT="10"
export SCREEN_MEMORY_APK_OCR_TIMEOUT="15"
export SCREEN_MEMORY_SCREENSHOT_DIR="$HOME/.screenmemory/screenshots"
ENVEOF

# Add source to .bashrc if not already there
if ! grep -q ".screenmemory.env" "$HOME/.bashrc" 2>/dev/null; then
    echo "" >> "$HOME/.bashrc"
    echo "# Screen Memory Plugin" >> "$HOME/.bashrc"
    echo "[ -f \$HOME/.screenmemory.env ] && source \$HOME/.screenmemory.env" >> "$HOME/.bashrc"
fi

info "Environment configured at $ENV_FILE"

# ---- Create data directories ----
mkdir -p "$HOME/.screenmemory/screenshots"
mkdir -p "$HOME/.screenmemory/db"

# ---- Summary ----
echo ""
info "=== Plugin Deployment Complete ==="
info "Plugin location: $DEST"
info "Config: $ENV_FILE"
info "Screenshots dir: $HOME/.screenmemory/screenshots"
echo ""
info "Verify with: bash $(dirname "$0")/verify.sh"
```

- [ ] **Step 2: Make script executable**

```bash
chmod +x screen-memory-android/deploy-plugin.sh
```

- [ ] **Step 3: Commit**

```bash
git add screen-memory-android/deploy-plugin.sh
git commit -m "feat: add screen-memory plugin deployment script for Android"
```

---

### Task 4: Create verification script

**Files:**
- Create: `screen-memory-android/verify.sh`

- [ ] **Step 1: Write the verification script**

Create `screen-memory-android/verify.sh`:

```bash
#!/bin/bash
set -uo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

PASS=0
FAIL=0

check() {
    local desc="$1"
    local cmd="$2"
    local expected="$3"

    result=$(eval "$cmd" 2>&1) || result=""
    if echo "$result" | grep -q "$expected" 2>/dev/null; then
        echo -e "  ${GREEN}PASS${NC} $desc"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $desc"
        echo "    Expected: $expected"
        echo "    Got: ${result:0:100}"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== OpenClaw + Screen Memory Verification ==="
echo ""

# ---- 1. System checks ----
echo "--- System ---"
check "Termux running" "echo \$TERMUX_VERSION" ""
check "Architecture aarch64" "uname -m" "aarch64"

# ---- 2. Runtime checks ----
echo "--- Runtime ---"
check "Node.js installed" "node --version" "v22"
check "Python installed" "python --version || python3 --version" "3."
check "OpenClaw installed" "which openclaw" "openclaw"

# ---- 3. Screen-memory app ----
echo "--- Screen Memory App ---"
check "App status endpoint" "curl -s http://127.0.0.1:19700/status" "running"
check "App OCR ready" "curl -s http://127.0.0.1:19700/status" "ocr_ready"

# ---- 4. OpenClaw gateway ----
echo "--- OpenClaw Gateway ---"
if curl -s --connect-timeout 3 http://localhost:3000 > /dev/null 2>&1; then
    check "Gateway responding" "curl -s http://localhost:3000" ""
else
    echo -e "  ${YELLOW}SKIP${NC} Gateway not running (start with: tmux new -s openclaw && openclaw gateway)"
fi

# ---- 5. Plugin checks ----
echo "--- Plugin ---"
OC_HOME="${HOME}/.openclaw"
check "Plugin manifest exists" "cat $OC_HOME/plugins/screen-memory/openclaw.plugin.json" "screen-memory"
check "Plugin Python package" "ls $OC_HOME/plugins/screen-memory/screen_memory/__init__.py" "__init__.py"
check "Android capture adapter" "ls $OC_HOME/plugins/screen-memory/screen_memory/adapters/android_capture.py" "android_capture"
check "ML Kit OCR adapter" "ls $OC_HOME/plugins/screen-memory/screen_memory/adapters/mlkit_ocr.py" "mlkit_ocr"

# ---- 6. End-to-end test ----
echo "--- End-to-End ---"
CAPTURE_RESULT=$(curl -s -X POST http://127.0.0.1:19700/capture-and-ocr -H "Content-Type: application/json" -d '{"quality":50}')
if echo "$CAPTURE_RESULT" | grep -q '"text"' 2>/dev/null; then
    OCR_TEXT=$(echo "$CAPTURE_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('text','')[:80])" 2>/dev/null || echo "")
    if [ -n "$OCR_TEXT" ]; then
        echo -e "  ${GREEN}PASS${NC} Capture+OCR pipeline works"
        echo "    OCR text: $OCR_TEXT..."
        PASS=$((PASS + 1))
    else
        echo -e "  ${YELLOW}WARN${NC} Capture succeeded but OCR returned empty"
    fi
else
    echo -e "  ${RED}FAIL${NC} Capture+OCR endpoint failed"
    FAIL=$((FAIL + 1))
fi

# ---- Summary ----
echo ""
echo "=== Results: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC} ==="

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}All checks passed! System is ready.${NC}"
    exit 0
else
    echo -e "${RED}Some checks failed. Review output above.${NC}"
    exit 1
fi
```

- [ ] **Step 2: Make script executable**

```bash
chmod +x screen-memory-android/verify.sh
```

- [ ] **Step 3: Commit**

```bash
git add screen-memory-android/verify.sh
git commit -m "feat: add deployment verification script for Android"
```

---

### Task 5: Execute deployment — push scripts to phone

**Files:**
- Push: `screen-memory-android/deploy.sh`, `deploy-plugin.sh`, `verify.sh` to phone via ADB

- [ ] **Step 1: Push deployment scripts to phone**

```bash
adb push screen-memory-android/deploy.sh /data/local/tmp/deploy.sh
adb push screen-memory-android/deploy-plugin.sh /data/local/tmp/deploy-plugin.sh
adb push screen-memory-android/verify.sh /data/local/tmp/verify.sh
```
Expected: Files pushed successfully

- [ ] **Step 2: Copy scripts into Termux home via ADB shell**

The scripts need to be accessible from Termux. Since ADB shell and Termux have different user contexts, we copy through a shared location:

```bash
# Push the entire screen-memory plugin source to /sdcard/
adb push screen-memory/ /sdcard/screen-memory/
```
Expected: Plugin files copied to phone's /sdcard/

- [ ] **Step 3: Commit deployment state**

```bash
git add -A screen-memory-android/
git commit -m "chore: deployment scripts ready for Android execution"
```

---

### Task 6: Execute deployment — run on phone (Termux)

This task is executed interactively on the phone's Termux. The user runs commands manually.

- [ ] **Step 1: In Termux, copy scripts from /sdcard/ to home**

```bash
# In Termux
cp /sdcard/screen-memory/../deploy.sh ~/deploy.sh 2>/dev/null || true
# Or directly run from /sdcard/:
cd ~
```

- [ ] **Step 2: Run the main deployment script**

```bash
# In Termux
bash ~/deploy.sh
```

Follow prompts:
- During OpenClaw install: select `Y` for tmux, `n` for others initially
- Wait for installation to complete (5-15 min)

- [ ] **Step 3: Configure OpenClaw with GLM API**

```bash
# In Termux
source ~/.bashrc
openclaw onboard
```

Enter when prompted:
- Admin password: (choose one)
- AI provider: Anthropic
- API Key: `759e435c24fd4c89be441e03cfeb7c14.QJn8He1GTMHC0dWw`
- Base URL: `https://open.bigmodel.cn/api/anthropic`
- Port: `3000`

**Fallback:** If `openclaw onboard` doesn't have a Base URL field, manually edit the config:
```bash
# Find and edit OpenClaw config (path may vary)
find ~/.openclaw -name "*.yaml" -o -name "*.json" -o -name "*.toml" | head -5
# Look for the AI provider section and add/edit:
#   base_url: https://open.bigmodel.cn/api/anthropic
#   api_key: 759e435c24fd4c89be441e03cfeb7c14.QJn8He1GTMHC0dWw
```

- [ ] **Step 4: Deploy the plugin**

```bash
# In Termux — copy plugin from /sdcard/
mkdir -p ~/.openclaw/plugins/
cp -r /sdcard/screen-memory ~/.openclaw/plugins/screen-memory

# Install Python dependencies
pip install --user Pillow

# Set environment variables
source ~/.screenmemory.env 2>/dev/null || true
```

- [ ] **Step 5: Start gateway and verify**

```bash
# In Termux
tmux new -s openclaw
openclaw gateway
# Wait for "Gateway is running" message
# Detach: Ctrl+B then D

# In new Termux session, run verification
bash ~/verify.sh
```

Expected: All checks pass — screen-memory app responding, OpenClaw gateway running, plugin files in place, capture+OCR pipeline works

---

### Task 7: Post-deployment configuration

- [ ] **Step 1: Configure Android system settings**

On the phone, manually:
1. Settings → Battery → Termux → Don't optimize
2. Developer options → Pause cached apps → OFF (Android 12+)
3. Recent apps → Pull down Termux card → Lock
4. Settings → Accessibility → ScreenMemoryService → ON (if not already)

- [ ] **Step 2: Test from computer via web console**

```bash
# Get phone IP
adb shell "ip addr show wlan0 | grep inet"
# Example: 192.168.1.100

# Open browser: http://192.168.1.100:3000
# Login with admin password set during onboard
```

- [ ] **Step 3: Test screen_capture tool through OpenClaw agent**

In the OpenClaw web console:
- Create a new agent
- Ask the agent to "capture a screenshot"
- Verify the agent calls the screen_capture tool and returns results

- [ ] **Step 4: Commit final state**

```bash
git add -A
git commit -m "feat: OpenClaw Android deployment complete with screen-memory plugin"
```
