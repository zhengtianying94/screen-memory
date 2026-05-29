#!/data/data/com.termux/files/usr/bin/bash
set -e

# OpenClaw + Screen Memory Plugin One-Click Deployment for Android
# Usage: bash /sdcard/Download/setup-all.sh

R='\033[0;31m' G='\033[0;32m' Y='\033[1;33m' N='\033[0m'
info()  { echo -e "${G}[INFO]${N} $*"; }
warn()  { echo -e "${Y}[WARN]${N} $*"; }
err()   { echo -e "${R}[ERROR]${N} $*"; }

GLM_KEY="759e435c24fd4c89be441e03cfeb7c14.QJn8He1GTMHC0dWw"
GLM_URL="https://open.bigmodel.cn/api/anthropic"
APK_URL="http://127.0.0.1:19700"

echo "========================================="
echo " OpenClaw + Screen Memory Auto Deploy"
echo "========================================="
echo ""

# Step 1: Mirror
info "Step 1/6: Configure China mirror..."
if ! grep -q "tsinghua" "$PREFIX/etc/apt/sources.list" 2>/dev/null; then
    sed -i 's|https://packages.termux.dev|https://mirrors.tuna.tsinghua.edu.cn/termux|g' "$PREFIX/etc/apt/sources.list"
    info "Switched to Tsinghua mirror"
else
    info "Already configured"
fi

# Step 2: Packages
info "Step 2/6: Install dependencies..."
pkg update -y
pkg install -y curl git python

# Step 3: OpenClaw
info "Step 3/6: Install OpenClaw..."
if command -v openclaw &>/dev/null; then
    info "OpenClaw already installed: $(openclaw --version 2>/dev/null)"
else
    info "Installing OpenClaw (select tmux=Y, others=n)..."
    curl -sL myopenclawhub.com/install | bash
    source ~/.bashrc 2>/dev/null || true
    source ~/.profile 2>/dev/null || true
fi
info "Node: $(node --version)"
info "Python: $(python --version 2>/dev/null || python3 --version)"

# Step 4: Plugin
info "Step 4/6: Deploy screen-memory plugin..."
mkdir -p ~/.openclaw/plugins
cd /sdcard/Download
if [ -f screen-memory-plugin.tar.gz ]; then
    tar xzf screen-memory-plugin.tar.gz -C ~/.openclaw/plugins/
    info "Plugin extracted to ~/.openclaw/plugins/screen-memory/"
else
    err "screen-memory-plugin.tar.gz not found in /sdcard/Download/"
    exit 1
fi

pip install --user Pillow 2>/dev/null || pip3 install --user Pillow 2>/dev/null || warn "Pillow install may have failed"

# Environment
cat > ~/.screenmemory.env << EOF
export SCREEN_MEMORY_APK_URL="$APK_URL"
export SCREEN_MEMORY_SCREENSHOT_DIR="\$HOME/.screenmemory/screenshots"
EOF
grep -q ".screenmemory.env" ~/.bashrc 2>/dev/null || echo '[ -f $HOME/.screenmemory.env ] && source $HOME/.screenmemory.env' >> ~/.bashrc
mkdir -p ~/.screenmemory/screenshots ~/.screenmemory/db

# Step 5: Verify app
info "Step 5/6: Verify screen-memory app..."
if curl -s --connect-timeout 5 "$APK_URL/status" 2>/dev/null | grep -q "running"; then
    info "Screen-memory app is running"
    CAP=$(curl -s --connect-timeout 10 -X POST "$APK_URL/capture" -H 'Content-Type: application/json' -d '{"quality":50}' 2>/dev/null || echo "")
    if echo "$CAP" | grep -q '"image"'; then
        info "Screen capture works!"
    else
        warn "Screen capture failed - authorize MediaProjection in the app"
    fi
else
    warn "Screen-memory app not responding. Start it and enable accessibility service."
fi

# Step 6: Onboard
echo ""
info "Step 6/6: OpenClaw configuration"
echo ""
info "Run this command to configure:"
echo "  openclaw onboard"
echo ""
info "When prompted:"
echo "  Provider: Anthropic (or custom)"
echo "  API Key:  $GLM_KEY"
echo "  Base URL: $GLM_URL"
echo ""
info "After onboard, start gateway:"
echo "  tmux new -s openclaw"
echo "  openclaw gateway"
echo ""
info "========================================="
info " Setup complete! Follow steps above."
info "========================================="
