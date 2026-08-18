#!/bin/bash
set -e

echo "════════════════════════════════════════════════════════════"
echo "🚀 RAILWAY AUTOMATION AUTO-START"
echo "════════════════════════════════════════════════════════════"
echo ""

cd /app

# Setup WARP
echo "📡 Setting up WARP..."
if [ ! -f wgcf-account.toml ]; then
    wgcf register --accept-tos
    wgcf generate
fi

# Start WARP in background
echo "📡 Starting WARP..."
wg-quick up ./wgcf-profile.conf 2>&1 | head -20 || echo "⚠️ WARP issue (continuing anyway)"
sleep 5

# Test WARP
echo "🧪 Testing WARP connection..."
curl --socks4 127.0.0.1:40000 https://cloudflare.com/cdn-cgi/trace 2>&1 | head -10 || echo "⚠️ WARP test issue"

# Setup rclone (using env vars if provided)
if [ -n "$MEGA_USER" ] && [ -n "$MEGA_PASS" ]; then
    echo "📂 Configuring rclone..."
    mkdir -p /root/.config/rclone
    cat > /root/.config/rclone/rclone.conf <<EOF
[mega]
type = mega
user = $MEGA_USER
pass = $(rclone obscure "$MEGA_PASS")
EOF
fi

# Verify rclone
rclone ls mega:railway_sessions 2>&1 | head -5 || echo "⚠️ Mega not configured"

echo ""
echo "✅ Setup complete!"
echo "🎯 Starting automation..."
echo ""

# Run automation in continuous mode
python3 railway-mailtm-full.py --warp --continuous --max-accounts 8000
