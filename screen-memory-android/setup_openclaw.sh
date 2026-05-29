#!/bin/bash
set -e

echo "=== Step 1: Updating Termux packages ==="
pkg update -y
pkg install -y curl git

echo "=== Step 2: Installing OpenClaw ==="
curl -sL myopenclawhub.com/install | bash

echo "=== Step 3: Loading environment ==="
if [ -f ~/.bashrc ]; then
    source ~/.bashrc
fi
if [ -f ~/.profile ]; then
    source ~/.profile
fi

echo ""
echo "=== Installation complete! ==="
echo "Next: run 'openclaw onboard' to configure"
