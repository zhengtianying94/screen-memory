#!/bin/bash
set -uo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

PASS=0
FAIL=0

check() {
    local desc="$1" cmd="$2" expected="$3"
    result=$(eval "$cmd" 2>&1) || result=""
    if echo "$result" | grep -q "$expected" 2>/dev/null; then
        echo -e "  ${GREEN}PASS${NC} $desc"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $desc (expected: $expected)"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== OpenClaw + Screen Memory Verification ==="
echo ""

echo "--- System ---"
check "Architecture" "uname -m" "aarch64"

echo "--- Runtime ---"
check "Node.js" "node --version" "v"
check "Python" "python --version || python3 --version" "3."
check "OpenClaw" "which openclaw" "openclaw"

echo "--- Screen Memory App ---"
check "App status" "curl -s http://127.0.0.1:19700/status" "running"
check "OCR ready" "curl -s http://127.0.0.1:19700/status" "ocr_ready"

echo "--- Capture Test ---"
CAP=$(curl -s --connect-timeout 15 -X POST http://127.0.0.1:19700/capture -H 'Content-Type: application/json' -d '{"quality":50}' 2>/dev/null)
if echo "$CAP" | grep -q '"image"' 2>/dev/null; then
    echo -e "  ${GREEN}PASS${NC} Screen capture works"
    PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} Screen capture: ${CAP:0:100}"
    FAIL=$((FAIL + 1))
fi

echo "--- Plugin ---"
OC_HOME="${HOME}/.openclaw"
check "Plugin manifest" "cat $OC_HOME/plugins/screen-memory/openclaw.plugin.json" "screen-memory"
check "Android adapter" "ls $OC_HOME/plugins/screen-memory/screen_memory/adapters/android_capture.py" "android_capture"

echo "--- Gateway ---"
if curl -s --connect-timeout 3 http://localhost:3000 > /dev/null 2>&1; then
    check "Gateway responding" "curl -s http://localhost:3000" ""
else
    echo -e "  ${YELLOW}SKIP${NC} Gateway not running (start: tmux new -s openclaw && openclaw gateway)"
fi

echo ""
echo "=== Results: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC} ==="
[ $FAIL -eq 0 ] && exit 0 || exit 1
