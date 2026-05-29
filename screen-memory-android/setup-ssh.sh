#!/data/data/com.termux/files/usr/bin/bash
# Minimal SSH setup - run this once in Termux
set -e

# Change mirror first for speed
sed -i 's|https://packages.termux.dev|https://mirrors.tuna.tsinghua.edu.cn/termux|g' $PREFIX/etc/apt/sources.list 2>/dev/null || true

pkg update -y
pkg install -y openssh

# Set password for SSH
echo "Setting SSH password to: termux123"
echo "termux123" | passwd --stdin 2>/dev/null || echo "termux123\ntermux123" | passwd 2>/dev/null || true

# Start SSH daemon
sshd

# Show connection info
USER=$(whoami)
IP=$(ifconfig 2>/dev/null | grep "inet " | grep -v 127.0.0.1 | head -1 | awk '{print $2}')
echo ""
echo "=== SSH Ready ==="
echo "From computer: ssh -p 8022 $USER@$IP"
echo ""
