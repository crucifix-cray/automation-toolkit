#!/bin/bash
# Setup WARP SOCKS5 proxy + Mega + all dependencies for Railway viral deployment
# This script makes Railway sandbox ready to create accounts and self-replicate

set -e

echo "=========================================="
echo "Railway Viral Farm - Complete Setup"
echo "=========================================="

# 1. Check if wgcf is installed
if ! command -v wgcf &> /dev/null; then
    echo "📦 Installing wgcf..."
    wget -O /usr/local/bin/wgcf https://github.com/ViRb3/wgcf/releases/download/v2.2.22/wgcf_2.2.22_linux_amd64
    chmod +x /usr/local/bin/wgcf
fi

# 2. Register WARP account if not exists
if [ ! -f /root/wgcf-profile.conf ]; then
    echo "🌐 Registering WARP account..."
    cd /root
    wgcf register --accept-tos
    wgcf generate
fi

# 3. Install wireproxy
if ! command -v wireproxy &> /dev/null; then
    echo "📦 Installing wireproxy..."
    wget https://github.com/octeep/wireproxy/releases/download/v1.0.9/wireproxy_linux_amd64.tar.gz
    tar xzf wireproxy_linux_amd64.tar.gz
    mv wireproxy /usr/local/bin/
    chmod +x /usr/local/bin/wireproxy
    rm wireproxy_linux_amd64.tar.gz
fi

# 4. Extract WARP config values
echo "⚙️  Creating wireproxy config..."
PRIV_KEY=$(grep PrivateKey /root/wgcf-profile.conf | awk '{print $3}')
PUB_KEY=$(grep PublicKey /root/wgcf-profile.conf | awk '{print $3}')
ADDRESS=$(grep 'Address = ' /root/wgcf-profile.conf | awk '{print $3}')
ENDPOINT=$(grep Endpoint /root/wgcf-profile.conf | awk '{print $3}')

# 5. Create wireproxy config
cat > /root/wireproxy.conf << EOF
[Interface]
PrivateKey = ${PRIV_KEY}
Address = ${ADDRESS}
DNS = 1.1.1.1

[Peer]
PublicKey = ${PUB_KEY}
Endpoint = ${ENDPOINT}
AllowedIPs = 0.0.0.0/0

[Socks5]
BindAddress = 127.0.0.1:40000
EOF

echo "✅ Config created at /root/wireproxy.conf"

# 6. Setup Mega rclone config
echo "☁️  Configuring Mega cloud storage..."
mkdir -p /root/.config/rclone

cat > /root/.config/rclone/rclone.conf << 'MEGA_EOF'
[mega]
type = mega
user = emilypeterson30@mail.findmeghana.org
pass = AIjpeMEdPQWNTQHR6YYDYjcEoGFSOGHASO5DjwkHcXUW7iDLFg
session_id = YHpE8zZFzThFIYjGGm44xFcyUGl1YWtCWlE4_HnRwxFodO1IlI4aFoyFUg
master_key = s6SFGB0f4UZk7VYPwK/k3A==
MEGA_EOF

echo "✅ Mega configured"

# 7. Kill existing wireproxy if running
pkill wireproxy 2>/dev/null || true

# 8. Start wireproxy in background
echo "🚀 Starting wireproxy..."
nohup wireproxy -c /root/wireproxy.conf > /tmp/wireproxy.log 2>&1 &

# 9. Wait for it to start
sleep 3

# 10. Test SOCKS5 proxy
echo "🧪 Testing WARP connection..."
WARP_OK=false
if curl --socks5 127.0.0.1:40000 http://icanhazip.com 2>/dev/null | grep -q "."; then
    WARP_OK=true
    echo "✅ WARP proxy is working"
else
    echo "⚠️  WARP proxy test failed, but continuing..."
fi

# 11. Test Mega connection
echo "🧪 Testing Mega connection..."
MEGA_OK=false
if rclone lsd mega: 2>/dev/null | grep -q "railway_sessions"; then
    MEGA_OK=true
    echo "✅ Mega is connected"
else
    echo "⚠️  Mega connection failed, but continuing..."
fi

# 12. Summary
echo ""
echo "=========================================="
echo "✅ SETUP COMPLETE"
echo "=========================================="
echo "WARP Proxy: ${WARP_OK}"
echo "Mega Cloud: ${MEGA_OK}"
echo ""
echo "Ready to run viral script:"
echo "  cd /root/automation-toolkit/railway-docker"
echo "  export DISPLAY=:99"
echo "  python3 railway-mailtm-full.py --warp --continuous --deploy-recursive"
echo "=========================================="
