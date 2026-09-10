#!/bin/bash
# Plain Ubuntu cell: installs stack once (marker on /data volume), then sleeps.
export DEBIAN_FRONTEND=noninteractive
export PATH="/root/.local/bin:/data/venv/bin:$PATH"
echo "=== cell boot $(date -u) ==="
swapon -s 2>&1 || echo "SWAP: unavailable in container (expected)"
mkdir -p /data
if [ ! -f /data/.ready ]; then
  echo "first boot: installing stack..."
  apt-get update && apt-get install -y curl unzip xvfb python3-pip procps
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="/root/.local/bin:$PATH"
  export PLAYWRIGHT_BROWSERS_PATH=/data/browsers
  uv python install 3.14 && uv venv --python 3.14 /data/venv
  export PATH="/data/venv/bin:$PATH"
  uv pip install --python /data/venv/bin/python patchright playwright camoufox playwright-stealth playwright-captcha
  /data/venv/bin/python -m patchright install chromium --with-deps
  /data/venv/bin/python -m camoufox fetch 2>&1 | tail -1 || true
  touch /data/.ready && echo "stack installed"
else
  echo "stack cached on /data, skipping install"
fi
export PATH="/data/venv/bin:$PATH"
export PLAYWRIGHT_BROWSERS_PATH=/data/browsers
python -c 'import patchright, playwright, camoufox; print("STACK OK")' 2>&1 || /data/venv/bin/python -c 'import patchright, playwright, camoufox; print("STACK OK")'
touch /data/.alive && echo "alive $(date -u)" >> /data/boot.log
echo "cell ready, sleeping"
sleep infinity
