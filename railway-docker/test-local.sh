#!/bin/bash
# Test script locally before deploying

set -e

echo "🧪 Testing Railway automation script locally..."
echo ""

# Check dependencies
echo "1️⃣  Checking dependencies..."
command -v python3 >/dev/null 2>&1 || { echo "❌ python3 not found"; exit 1; }
command -v rclone >/dev/null 2>&1 || { echo "❌ rclone not found"; exit 1; }
command -v wgcf >/dev/null 2>&1 || { echo "⚠️  wgcf not found (WARP will be disabled)"; }

echo "✅ Dependencies OK"
echo ""

# Test rclone Mega connection
echo "2️⃣  Testing Mega connection..."
if rclone ls mega:railway_sessions >/dev/null 2>&1; then
  echo "✅ Mega connection OK"
else
  echo "❌ Mega connection failed - check rclone.conf"
  exit 1
fi
echo ""

# Test single account creation
echo "3️⃣  Testing single account creation..."
echo "   (This will create 1 Railway account)"
read -p "   Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "❌ Aborted"
  exit 1
fi

python3 railway-mailtm-full.py --warp

echo ""
echo "✅ Test completed!"
echo ""
echo "Next steps:"
echo "  1. Check ~/Documents/railways/ for new session"
echo "  2. Verify session synced to mega:railway_sessions"
echo "  3. If successful, deploy to Railway with: railway up"
