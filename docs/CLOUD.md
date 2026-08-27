# Railway Holy Cloud — Bright Data Browser API

**Cloud version:** `railway-docker/railway-HOLY-cloud.py`

## Why Cloud
- **953MB RAM + 2 CPU + no tun** sandbox caps make local WARP + Chromium flaky (EPIPE, Turnstile disabled).
- Bright Data **Browser API** runs the browser **off** the sandbox (Chennai residential `223.178.84.38` Bharti Airtel) — no RAM limit, clean IP, built-in CAPTCHA solver.

## Stack (Cloud)
- **Browser:** `wss://brd-customer-hl_4ee0cb14-zone-scraping_browser1:***@brd.superproxy.io:9222` (zone `scraping_browser1`, 5k free credits, $8/GB, 5cr/MB)
- **Mailbox:** `mail.tm` API (`emalupe.com`) for cloud (1 domain/session, avoids free-tier `navigate_domains_limit`). For `@gmail.com`, uses `dispose.lol` via **separate** BD browser (keeps main railway session at 1 domain).
- **WARP:** disabled in cloud (BD residential already)

## Usage
```bash
# emalupe.com (proven, 1-domain safe)
BRD_PASS=hv9meysibkzv python3 railway-HOLY-cloud.py --cloud

# Gmail (dispose, separate BD browser)
BRD_PASS=hv9meysibkzv python3 railway-HOLY-cloud.py --cloud --domain @gmail.com

# raw IP verify after creation
RAILWAY_CONFIG_DIR=/root/Documents/railways/session-*/.railway railway whoami
RAILWAY_CONFIG_DIR=/root/Documents/railways/session-*/.railway railway status
```

## What Works (2026-08-27)
- `b4ux5k3q0m8f@emalupe.com` OTP `710367` — Turnstile solved poll 1, OTP via iframe, `Logged in successfully!`
- `ghian.sean5@gmail.com` OTP `860204` — dispose Gmail, BD Chennai, `My Projects` dashboard
- `whatismyipaddress.com` via BD: `223.178.84.38` Chennai, `110.235.239.255`

## Limits (Free Tier)
- `brb`/`brul` for `cloudflare.com/cdn-cgi/trace` — ignore, use `railway.com/login` directly
- `brob` for `railway.com/dashboard` via `Page.goto` — avoid, do `railway.com/login` then SPA nav
- `navigate_domains_limit` — 1 domain/session free, so mailbox must be API-based or separate browser
- `add_cookies`/`storage_state` for `HttpOnly` (`rw.session`) is forbidden — use fresh login flow, not cookie reuse

## Next
- Fix Gmail dispose polling to avoid Turnstile disabled (use non-Gmail for cloud, or separate BD browser)
- Fix PKCE `backboard.railway.com` 2nd domain block — use direct API token via cookies instead of browser PKCE
- Add `rclone copy` for cloud sessions to `mega:railway_sessions`
