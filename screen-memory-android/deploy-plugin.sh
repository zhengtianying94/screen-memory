#!/bin/bash
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

info "=== Plugin Deployment ==="

PLUGIN_SRC="/sdcard/screen-memory"
OC_HOME="${HOME}/.openclaw"
PLUGIN_DIR="$OC_HOME/plugins"

if [ ! -f "$PLUGIN_SRC/openclaw.plugin.json" ]; then
    error "Plugin source not found at $PLUGIN_SRC"
fi
info "Plugin source: $PLUGIN_SRC"

PYTHON_CMD=""
if command -v python &> /dev/null; then
    PYTHON_CMD="python"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
else
    error "Python not found. Run: pkg install python"
fi
info "Python: $($PYTHON_CMD --version)"

info "Deploying to $PLUGIN_DIR"
mkdir -p "$PLUGIN_DIR"
DEST="$PLUGIN_DIR/screen-memory"
rm -rf "$DEST" 2>/dev/null || true
cp -r "$PLUGIN_SRC" "$DEST"
rm -rf "$DEST/tests" "$DEST/.git" "$DEST/__pycache__" 2>/dev/null || true
info "Plugin copied to $DEST"

info "Installing Python dependencies..."
$PYTHON_CMD -m pip install --user Pillow 2>/dev/null || warn "Pillow install failed"

info "Configuring environment..."
cat > "$HOME/.screenmemory.env" << 'ENVEOF'
export SCREEN_MEMORY_APK_URL="http://127.0.0.1:19700"
export SCREEN_MEMORY_APK_TIMEOUT="10"
export SCREEN_MEMORY_APK_OCR_TIMEOUT="15"
export SCREEN_MEMORY_SCREENSHOT_DIR="$HOME/.screenmemory/screenshots"
ENVEOF

if ! grep -q ".screenmemory.env" "$HOME/.bashrc" 2>/dev/null; then
    echo '[ -f $HOME/.screenmemory.env ] && source $HOME/.screenmemory.env' >> "$HOME/.bashrc"
fi
mkdir -p "$HOME/.screenmemory/screenshots" "$HOME/.screenmemory/db"

info "Verifying plugin structure..."
for f in openclaw.plugin.json screen_memory/__init__.py screen_memory/tools/__init__.py screen_memory/adapters/android_capture.py screen_memory/adapters/mlkit_ocr.py; do
    if [ -f "$DEST/$f" ]; then
        info "  OK: $f"
    else
        warn "  MISSING: $f"
    fi
done

echo ""
info "=== Plugin Deployment Complete ==="
info "Run: bash $(dirname "$0")/verify.sh"
