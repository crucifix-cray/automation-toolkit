#!/bin/bash
# Railway account creation with Mega.nz sync
# Uses Mega account #4 from CREDENTIALS.md

# TODO: Set these from your credentials file
export MEGA_EMAIL="your-mega-email@example.com"
export MEGA_PASSWORD="your-mega-password"

# Optional: Set WARP proxy if available
# export WARP_PROXY="socks5://127.0.0.1:40000"

cd "$(dirname "$0")"
uv run --with "playwright==1.57" python -u railway-login-with-mega.py
