# BD Browser Stream — Remote Browser Viewer

Local interactive web viewer powered by Bright Data Browser API (CDP). Control a remote browser session via HTTP, view live screenshots, click, type, scroll — all from your machine.

## What It Is

A self-contained 2-file system:
- `bd_stream.py` — Python server, connects to BD Browser API via CDP, serves screenshots + accepts commands
- `bd_stream.html` — Web UI, canvas-based live viewer with URL bar, click, keyboard, scroll

Exposed on `http://127.0.0.1:8888`.

## Quick Start

```bash
cd railway-docker
python3 bd_stream.py
# Open http://127.0.0.1:8888 in browser
```

Or via systemd (auto-restart on crash):
```bash
systemctl --user restart bdstream
```

## Features

- **Live screenshot streaming** — JPEG polling at ~10fps, canvas-based rendering
- **Remote click** — click anywhere on canvas → mapped to remote browser coordinates
- **Keyboard forwarding** — type into remote page, special keys (Enter, Backspace, arrows, Tab, Esc)
- **Scroll forwarding** — wheel events forwarded to remote
- **URL bar** — navigate to any URL (cross-domain triggers fresh BD session)
- **Auto-reconnect** — screenshot death → new BD session automatically
- **Crash guard** — infinite restart loop on unhandled exceptions
- **IP rotation** — each new `?sessionId` gets a fresh residential IP

## Architecture

```
┌─────────────┐      HTTP       ┌──────────────┐     CDP/WSS     ┌─────────────────┐
│  Zen Browser │  ─────────────  │  bd_stream   │ ────────────── │  BD Browser API  │
│  (localhost) │  screenshots    │  :8888       │  Playwright     │  (residential)   │
│  canvas UI   │  ←──────────── │  Python      │  connect_over   │  headless Chrome │
│              │  commands →     │              │  _cdp           │                  │
└─────────────┘                  └──────────────┘                  └─────────────────┘
```

## Key Files

| File | Purpose |
|------|---------|
| `railway-docker/bd_stream.py` | Main server — CDP connection, command queue, HTTP endpoints |
| `railway-docker/bd_stream.html` | Web UI — canvas rendering, input handling, URL bar |
| `railway-docker/bd_keep_alive.py` | Keep-alive script — prevents BD session timeout |
| `railway-docker/bd_cdp_proxy.py` | CDP proxy stub (unused) |
| `railway-docker/bd_stealth_proxy.py` | Local Chromium via BD ISP proxy (abandoned — CF blocked) |
| `~/.config/systemd/user/bdstream.service` | systemd user service |

## History

Built to bypass Cloudflare Turnstile for Railway.com signup. ISP proxy IPs (ASN 213541 WS Telecom) are flagged as datacenter → Turnstile blocks them. BD Browser API uses real residential Chrome sessions → Turnstile passes, but BD free tier limits apply.

### Iterations

1. **ISP proxy** (`bd_stealth_proxy.py`) — local headless Chromium via BD proxy → CF blocks datacenter ASN
2. **BD Browser API CDP** (`bd_stream.py` v1) — remote Chrome via CDP, `<img>` tag viewer → worked but img src replacement killed event listeners
3. **Canvas rewrite** (`bd_stream.html` v2) — `<canvas>` with `createImageBitmap` → faster rendering, clean event model
4. **systemd service** — auto-restart on crash, `ALL_PROXY=` to bypass Tor proxy
