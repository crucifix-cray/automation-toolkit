#!/bin/bash
# Usage: ./sandbox_runner.sh <sandbox_number> <bd_wss>
# e.g. ./sandbox_runner.sh 1 "wss://brd-customer-hl_834743cb-zone-scraping_browser1:q7k1y7ug1v69@brd.superproxy.io:9222"
set -e

SANDBOX_NUM=$1
BD_WSS=$2
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SESSIONS_DIR="/root/railway_sessions"
MEGA_REMOTE="mega:railway_sessions"

echo "============================================================"
echo "🏭 SANDBOX #${SANDBOX_NUM} — Account Farm Worker"
echo "============================================================"
echo "🌐 BD WSS: ${BD_WSS:0:50}..."
echo "📁 Sessions: ${SESSIONS_DIR}"
echo "☁️  Mega: ${MEGA_REMOTE}"
echo "============================================================"

export LD_PRELOAD=""
export HTTPS_PROXY=""
export HTTP_PROXY=""
export https_proxy=""
export http_proxy=""
export ALL_PROXY=""
export all_proxy=""

# Ensure rclone config exists
mkdir -p /root/.config/rclone
if [ ! -f /root/.config/rclone/rclone.conf ]; then
    echo "❌ No rclone config found!"
    exit 1
fi

# Pull latest code
cd /root/automation-toolkit
git pull origin main 2>&1 | tail -3 || true

mkdir -p "$SESSIONS_DIR"

# Loop: create accounts until stopped or mega has 500+
while true; do
    # Check current count on mega
    CURRENT_COUNT=$(rclone lsd "${MEGA_REMOTE}/" --mega-use-https 2>/dev/null | wc -l)
    echo ""
    echo "📊 Mega sessions: ${CURRENT_COUNT}/500"

    if [ "$CURRENT_COUNT" -ge 500 ]; then
        echo "🎯 TARGET REACHED! ${CURRENT_COUNT} sessions. Stopping."
        break
    fi

    echo "🔄 Starting account creation cycle..."
    cd /root/automation-toolkit/railway-docker

    BRD_WSS="$BD_WSS" python3 -u railway-HOLY-cloud.py --cloud-no-c 2>&1 | tee -a "/tmp/sandbox_${SANDBOX_NUM}.log" | tail -20

    EXIT_CODE=$?
    if [ $EXIT_CODE -ne 0 ]; then
        echo "⚠️  Cycle exited with code $EXIT_CODE, retrying in 5s..."
        sleep 5
    fi
done

echo "✅ Sandbox #${SANDBOX_NUM} finished. Total on mega: $(rclone lsd ${MEGA_REMOTE}/ --mega-use-https 2>/dev/null | wc -l)"
