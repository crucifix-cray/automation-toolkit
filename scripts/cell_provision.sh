#!/bin/bash
# Provision a Railway sandbox into a ready worker cell (Debian 13, root).
# Proven 2026-09-10 on session-110: uv -> Python 3.14 -> pip stack -> xvfb -> chromium.
# Runs INSIDE the sandbox via `railway sandbox exec` (single call, set -e).
set -e
uv python install 3.14
uv pip install --system --break-system-packages patchright playwright camoufox playwright-stealth playwright-captcha
apt-get update && apt-get install -y xvfb curl unzip
python3.14 -m patchright install chromium --with-deps
python3.14 -c 'import patchright, playwright, camoufox, playwright_stealth, playwright_captcha; print("CELL READY")'
