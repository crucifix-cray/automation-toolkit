#!/bin/bash
set -e

echo "════════════════════════════════════════════════════════════"
echo "🚀 RAILWAY UBUNTU AUTOMATION TERMINAL"
echo "════════════════════════════════════════════════════════════"
echo ""

# Setup WARP if config exists
if [ -f /data/wgcf-account.toml ]; then
    echo "📡 Starting WARP..."
    wg-quick up /data/wgcf-profile.conf 2>/dev/null || echo "⚠️  WARP already running or failed"
fi

# Keep container running and show logs
echo "✅ Container ready!"
echo "📂 Persistent data: /data"
echo "🔧 Tools: python3, playwright, wgcf, rclone, railway"
echo ""
echo "🎯 Ready to run automation scripts!"
echo ""

# Keep container alive
tail -f /dev/null
