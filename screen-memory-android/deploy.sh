#!/bin/bash
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

GLM_API_KEY="759e435c24fd4c89be441e03cfeb7c14.QJn8He1GTMHC0dWw"
GLM_BASE_URL="https://open.bigmodel.cn/api/anthropic"
SCREEN_MEMORY_APK_URL="http://127.0.0.1:19700"

info "=== Pre-flight checks ==="
if [ -z "${TERMUX_VERSION:-}" ] && [ ! -d "/data/data/com.termux" ]; then
    error "Not running in Termux."
fi
info "Termux detected, arch=$(uname -m)"

info "=== Step 1: Configure Termux mirror (China) ==="
if ! grep -q "tsinghua" "$PREFIX/etc/apt/sources.list" 2>/dev/null; then
    cp "$PREFIX/etc/apt/sources.list" "$PREFIX/etc/apt/sources.list.bak" 2>/dev/null || true
    sed -i 's|https://packages.termux.dev|https://mirrors.tuna.tsinghua.edu.cn/termux|g' "$PREFIX/etc/apt/sources.list"
    info "Switched to Tsinghua mirror"
else
    info "Mirror already configured"
fi

info "=== Step 2: Update packages ==="
pkg update -y || warn "pkg update had warnings"
pkg install -y curl git || error "Failed to install curl/git"

info "=== Step 3: Verify screen-memory app ==="
if curl -s --connect-timeout 3 "$SCREEN_MEMORY_APK_URL/status" > /dev/null 2>&1; then
    STATUS=$(curl -s "$SCREEN_MEMORY_APK_URL/status")
    info "Screen-memory app: $STATUS"
else
    warn "Screen-memory app not responding at $SCREEN_MEMORY_APK_URL"
    warn "Enable accessibility service and authorize MediaProjection in the app."
fi

info "=== Step 4: Install OpenClaw ==="
if command -v openclaw &> /dev/null; then
    info "OpenClaw already installed: $(openclaw --version 2>/dev/null || echo 'unknown')"
else
    info "Installing OpenClaw (5-15 min, select tmux=Y when prompted)..."
    curl -sL myopenclawhub.com/install | bash || error "OpenClaw install failed"
    if [ -f ~/.bashrc ]; then source ~/.bashrc; fi
    if [ -f ~/.profile ]; then source ~/.profile; fi
    info "OpenClaw installed"
fi
info "Node: $(node --version 2>/dev/null || echo 'NOT FOUND')"

info "=== Step 5: Verify Python ==="
if ! command -v python &> /dev/null && ! command -v python3 &> /dev/null; then
    pkg install -y python || error "Python install failed"
fi
PY=$(command -v python 2>/dev/null || command -v python3 2>/dev/null)
info "Python: $($PY --version 2>/dev/null || echo 'NOT FOUND')"

echo ""
info "=== Deployment Summary ==="
info "OpenClaw: $(command -v openclaw &>/dev/null && echo 'installed' || echo 'NOT FOUND')"
info "Node: $(node --version 2>/dev/null || echo 'N/A')"
info "Python: $($PY --version 2>/dev/null || echo 'N/A')"
info "Screen-memory app: $(curl -s --connect-timeout 2 $SCREEN_MEMORY_APK_URL/status > /dev/null 2>&1 && echo 'running' || echo 'not responding')"
echo ""
info "=== Next Steps ==="
info "1. Run: openclaw onboard"
info "   Provider: Anthropic, Key: $GLM_API_KEY"
info "   URL: $GLM_BASE_URL"
info "2. Run: bash $(dirname "$0")/deploy-plugin.sh"
info "3. Run: tmux new -s openclaw && openclaw gateway"
info "4. Run: bash $(dirname "$0")/verify.sh"
