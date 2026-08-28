# Railway Holy Cloud — Bright Data Browser API (ASN Rotation)

**Cloud version:** `railway-docker/railway-HOLY-cloud.py` — fresh ASN per run.

## Why Cloud
- **953MB RAM + 2 CPU + no tun** caps make WARP flaky (EPIPE).
- BD Browser API off-host, Chennai `223.178.84.38` (Airtel AS 9498) now rotates via pool + `?sessionId`.

## Stack
- **Pool:** `hl_4ee0cb14` (Chennai Airtel `AS 9498` `223.178.x.x`), `hl_709648b2` (acc1), Zenrows `3a6a9ee9...` `170.199.x.x` → fresh `?sessionId` per run for new IP/ASN
- **Browser:** `wss://...@brd.superproxy.io:9222?sessionId=<uuid>` per run, `pkill` old
- **Mailbox:** `dispose.lol` Gmail (separate BD, keep open, `Loading inbox` gone wait `3s`) → `22.do` (`@gmail`→`@outlook`→`@hotmail`→temp) → `mail.tm` (`emalupe.com`), `150 checks` / `750s` for dispose OTP
- **WARP:** disabled, `Turnstile` `100s` screenshot to `mega:railway_sessions` via `LD_PRELOAD="" --mega-use-https`

## Usage
```bash
BRD_PASS=hv9meysibkzv python3 railway-HOLY-cloud.py --cloud  # Gmail dispose first
BRD_PASS=... python3 railway-HOLY-cloud.py --cloud --domain @gmail.com
HOME=session-*/.railway LD_PRELOAD="" railway whoami  # raw IP, not RAILWAY_CONFIG_DIR
LD_PRELOAD="" LD_LIBRARY_PATH="" rclone copy session-*/ mega:railway_sessions/ --mega-use-https
```

## Fixes
- Fresh `sessionId` + `pkill` per run for new IP/ASN
- `mail.tm` vs `dispose` 1-domain safe
- Local headless Chrome PKCE via `HOME=`, `LD_PRELOAD=""`

## Update 2026-08-28 — Dispose OTP wait 150 checks
- Increased `DisposeLolInbox.wait_for_railway_code` to 750s / 150 checks (was 300s / ~41) to handle Railway email delay via dispose Gmail.
