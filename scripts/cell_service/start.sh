#!/bin/bash
# Baked-image cell: stack lives in image layers (trial disk too small for
# runtime installs into 500MB volume). /data volume holds work files only.
export PATH="/opt/venv/bin:$PATH"
export PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright
echo "=== cell boot $(date -u) ==="
swapon -s 2>&1 || echo "SWAP: unavailable in container (expected)"
cat /proc/meminfo | head -2
/opt/venv/bin/python -c 'import patchright, playwright, camoufox; print("STACK OK")'
mkdir -p /data && touch /data/.alive && echo "alive $(date -u)" >> /data/boot.log
echo "cell ready, sleeping"
sleep infinity
