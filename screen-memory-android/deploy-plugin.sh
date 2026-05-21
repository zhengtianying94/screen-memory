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