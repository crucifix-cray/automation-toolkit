# Parallel Farm Strategy — BD Browser API

## Overview

Run multiple `railway-HOLY-cloud.py` instances in parallel, each using a different BD Browser API account for IP rotation. 3 alive accounts = 3 parallel farm instances.

## BD Accounts — Alive

| Account | API Key | Zone | Status |
|---------|---------|------|--------|
| acc10 | `hl_e895b201` | `scraping_browser1` | ALIVE |
| acc11 | `hl_7e8d5d40` | `scraping_browser1` | ALIVE |
| acc12 | `hl_76276a19` | `scraping_browser1` | ALIVE |

## WSS Endpoints

```
# acc10
wss://brd-customer-hl_e895b201-zone-scraping_browser1:{TOKEN}@brd.superproxy.io:9222

# acc11
wss://brd-customer-hl_7e8d5d40-zone-scraping_browser1:{TOKEN}@brd.superproxy.io:9222

# acc12
wss://brd-customer-hl_76276a19-zone-scraping_browser1:{TOKEN}@brd.superproxy.io:9222
```

## Setup

```bash
cd /home/alae/Documents/repos/automation-toolkit/railway-docker

# Create session directories
mkdir -p session-1 session-2 session-3

# Copy farm script to each
cp railway-HOLY-cloud.py session-1/
cp railway-HOLY-cloud.py session-2/
cp railway-HOLY-cloud.py session-3/

# Run each with different BD account
BRD_WSS="wss://brd-customer-hl_e895b201..." python3 session-1/railway-HOLY-cloud.py &
BRD_WSS="wss://brd-customer-hl_7e8d5d40..." python3 session-2/railway-HOLY-cloud.py &
BRD_WSS="wss://brd-customer-hl_76276a19..." python3 session-3/railway-HOLY-cloud.py &
```

## Or Use systemd

Create separate service files for each session:

```ini
# ~/.config/systemd/user/railway-farm-1.service
[Unit]
Description=Railway Farm Instance 1 (acc10)
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/alae/Documents/repos/automation-toolkit/railway-docker/session-1
ExecStart=/usr/bin/python3 railway-HOLY-cloud.py
Environment=BRD_WSS=wss://brd-customer-hl_e895b201-zone-scraping_browser1:{TOKEN}@brd.superproxy.io:9222
Environment=ALL_PROXY=
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user start railway-farm-1 railway-farm-2 railway-farm-3
```

## IP Rotation

- Each BD `?sessionId` gets a fresh residential IP
- `railway-HOLY-cloud.py` already handles session rotation
- With 3 accounts = 3 independent IP pools = 3× throughput
- Accounts have independent credit pools → 3× monthly capacity

## Monitoring

```bash
# Check all 3 instances
systemctl --user status railway-farm-{1,2,3}

# Logs
journalctl --user -u railway-farm-1 -f
journalctl --user -u railway-farm-2 -f
journalctl --user -u railway-farm-3 -f

# Check active sessions on mega
LD_PRELOAD="" LD_LIBRARY_PATH="" rclone ls mega:railway_sessions/ --mega-use-https | head -20
```

## Scaling

- 3 alive accounts = 3 parallel instances
- Target: 8000+ Railway accounts (see `VIRAL_DEPLOYMENT_READY.md`)
- Each instance handles ~2666 accounts at 8K target
- Reuse accounts when credits exhaust (BD free tier = 5K credits/month each)
