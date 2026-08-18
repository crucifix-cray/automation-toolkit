#!/bin/bash
# Working Railway account creator with Mega sync
# Requires manual Cloudflare Turnstile click (takes 2 seconds)

cd "$(dirname "$0")"

echo "🚀 Railway Account Creator + Mega Sync"
echo ""
echo "⚠️  IMPORTANT: When the browser opens:"
echo "   1. Script will fill the email automatically"
echo "   2. Click the Cloudflare 'Verify you are human' checkbox"
echo "   3. Script will continue automatically after you click"
echo ""
echo "Press Enter to start..."
read

uv run --with "playwright==1.57" python -u railway-login-with-mega-FIXED.py
