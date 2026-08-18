#!/bin/bash
# Start Xvfb virtual display and run Railway automation script
# For use on VPS/Railway without physical display

set -e

echo "🖥️  Starting Xvfb virtual display..."

# Check if Xvfb is installed
if ! command -v Xvfb &> /dev/null; then
    echo "❌ Xvfb not installed. Installing..."
    sudo apt-get update && sudo apt-get install -y xvfb
fi

# Set display number
export DISPLAY=:99

# Start Xvfb on display :99 with 1280x720 resolution
Xvfb :99 -screen 0 1280x720x24 -ac +extension GLX +render -noreset &
XVFB_PID=$!

echo "✅ Xvfb started (PID: $XVFB_PID, DISPLAY: $DISPLAY)"

# Wait for Xvfb to be ready
sleep 2

# Verify Xvfb is running
if ! ps -p $XVFB_PID > /dev/null; then
    echo "❌ Xvfb failed to start"
    exit 1
fi

echo "🚀 Running Railway automation script..."

# Run the script with proper error handling
python3 railway-disposelol-full.py "$@"
EXIT_CODE=$?

# Cleanup
echo "🧹 Cleaning up..."
kill $XVFB_PID 2>/dev/null || true

exit $EXIT_CODE
