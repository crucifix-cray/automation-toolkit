#!/bin/bash
# Railway Ubuntu Terminal Setup Script
# Run this inside the Railway Ubuntu terminal to install all tools

set -e

echo "════════════════════════════════════════════════════════════"
echo "🚀 RAILWAY UBUNTU TERMINAL SETUP"
echo "════════════════════════════════════════════════════════════"
echo ""

# Update system
echo "📦 Updating system packages..."
apt-get update -y
apt-get upgrade -y

# Install Python and dependencies
echo "🐍 Installing Python 3.11 and pip..."
apt-get install -y \
    python3.11 \
    python3-pip \
    python3.11-venv

# Install system dependencies for Playwright
echo "🌐 Installing Playwright system dependencies..."
apt-get install -y \
    wget \
    curl \
    git \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils

# Install WireGuard for WARP
echo "🔒 Installing WireGuard..."
apt-get install -y \
    wireguard-tools \
    iproute2 \
    sudo \
    jq \
    unzip

# Install wgcf for Cloudflare WARP
echo "☁️  Installing wgcf (Cloudflare WARP)..."
cd /tmp
wget -q https://github.com/ViRb3/wgcf/releases/download/v2.2.22/wgcf_2.2.22_linux_amd64 -O /usr/local/bin/wgcf
chmod +x /usr/local/bin/wgcf

# Install rclone for Mega sync
echo "📂 Installing rclone..."
curl https://rclone.org/install.sh | bash

# Install Railway CLI
echo "🚂 Installing Railway CLI..."
curl -fsSL https://railway.com/install.sh | sh
export PATH="/root/.railway/bin:$PATH"

# Install Python packages
echo "🐍 Installing Python packages..."
pip3 install --no-cache-dir \
    patchright \
    requests \
    playwright-captcha

# Install Playwright browsers (Chromium only)
echo "🎭 Installing Playwright Chromium..."
python3 -m patchright install chromium
python3 -m patchright install-deps

# Create persistent directories
echo "📁 Creating persistent directories in /data..."
mkdir -p /data/railways
mkdir -p /data/scripts
mkdir -p /data/.config

# Setup WARP
echo "⚙️  Setting up Cloudflare WARP..."
cd /data
if [ ! -f wgcf-account.toml ]; then
    wgcf register --accept-tos
    wgcf generate
fi

# Setup rclone config
echo "⚙️  Setting up rclone for Mega..."
mkdir -p /root/.config/rclone
if [ ! -f /root/.config/rclone/rclone.conf ]; then
    echo "⚠️  Rclone config needed. Run: rclone config"
fi

echo ""
echo "════════════════════════════════════════════════════════════"
echo "✅ SETUP COMPLETE!"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "📝 Next steps:"
echo "1. Configure rclone: rclone config"
echo "2. Copy railway script to /data/scripts/"
echo "3. Copy session-1 credentials to /data/railways/"
echo "4. Test browser: python3 -c 'from patchright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium.launch(headless=True); print(\"✅ Browser works!\"); b.close()'"
echo ""
echo "🎯 Ready to run Railway automation!"
