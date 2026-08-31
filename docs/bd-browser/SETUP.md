# Setup Guide — BD Browser Stream

## Prerequisites

- Python 3.10+
- `playwright` (`pip install playwright`)
- BD Browser API account with active credits
- Zen Browser or any modern browser (client side)

## Manual Run

```bash
cd /home/alae/Documents/repos/automation-toolkit/railway-docker

# Run directly
python3 bd_stream.py

# Or with custom BD key
BRD_WSS="wss://brd-customer-hl_{KEY}-zone-scraping_browser1:{TOKEN}@brd.superproxy.io:9222" python3 bd_stream.py
```

Open `http://127.0.0.1:8888` in browser.

## systemd Service (Recommended)

### Install

```bash
# Service file is at:
# ~/.config/systemd/user/bdstream.service

# Copy if not present
mkdir -p ~/.config/systemd/user
cp /home/alae/Documents/repos/automation-toolkit/railway-docker/bdstream.service \
   ~/.config/systemd/user/bdstream.service

# Reload and enable
systemctl --user daemon-reload
systemctl --user enable bdstream
```

### Run

```bash
# Start
systemctl --user start bdstream

# Stop
systemctl --user stop bdstream

# Restart (after code changes)
systemctl --user restart bdstream

# Logs (live)
journalctl --user -u bdstream -f

# Logs (last 20 lines)
journalctl --user -u bdstream --no-pager -n 20
```

### Why systemd

- Auto-restart on crash (3s delay)
- `ALL_PROXY=` bypasses system Tor proxy (required — CDP WebSocket fails through Tor)
- Clean process management
- Log history via journald

## Switching BD Accounts

Edit `BRD_WSS` in the service file or pass as env var:

```bash
# In bdstream.service
Environment=BRD_WSS=wss://brd-customer-hl_{NEW_KEY}-zone-scraping_browser1:{TOKEN}@brd.superproxy.io:9222

# Or inline
BRD_WSS="wss://..." systemctl --user restart bdstream
```

## Using With Railway Farm

```bash
# bd_stream.py on port 8888 (for interactive debugging)
# railway-HOLY-cloud.py on session-1/2/3 (for automated farming)

# Navigate Railway signup via bd_stream:
# 1. Open http://127.0.0.1:8888
# 2. Enter https://railway.com in URL bar → click Go
# 3. Click signup → GitHub OAuth flow
```

## Verification

```bash
# Check if server is running
curl -s http://127.0.0.1:8888/status

# Expected: {"ip":"x.x.x.x","url":"...","title":"...","ready":true,...}

# Check screenshot
curl -s http://127.0.0.1:8888/screenshot -o /tmp/test.jpg
file /tmp/test.jpg  # should be JPEG
```

## Troubleshooting

### Server won't start
- Check if port 8888 is in use: `lsof -i :8888`
- Check Tor proxy isn't interfering: `echo $ALL_PROXY` (should be empty)
- Check BD API key is valid

### Screenshots are blank/black
- BD session may have died → restart service
- Check logs: `journalctl --user -u bdstream -n 20`
- BD free tier may be exhausted → switch account

### Clicks don't register
- Open Zen DevTools (F12) → Console → check for errors
- Canvas may need re-initialization → hard refresh (Ctrl+Shift+R)
- Check `viewport` values in status endpoint

### Cross-domain navigation fails
- BD `navigate_domains_limit` hit → server auto-reconnects with fresh session
- May take 3-5s for new BD session to connect
- If persistent → BD account may be rate-limited
