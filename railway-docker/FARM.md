# Railway Account Farm — Full Setup Guide

## Current Status
- **Sessions on Mega**: 114 / 500 target
- **Checkpoint**: `holy-farm-v4` (pre-built sandbox snapshot with all deps)
- **Repo**: https://github.com/crucifix-cray/automation-toolkit

---

## Bright Data Browser API Credentials (10 active)

| # | Account | WSS | Status |
|---|---------|-----|--------|
| acc1 | hl_709648b2 | — | SUSPENDED (credit drained) |
| acc2 | hl_834743cb | `wss://brd-customer-hl_834743cb-zone-scraping_browser1:q7k1y7ug1v69@brd.superproxy.io:9222` | SUSPENDED (rate limit) |
| acc3 | hl_3496e863 | `wss://brd-customer-hl_3496e863-zone-scraping_browser1:9glc7ho0mx9w@brd.superproxy.io:9222` | SUSPENDED (rate limit) |
| acc4 | hl_faaefe91 | `wss://brd-customer-hl_faaefe91-zone-scraping_browser1:1e6cx8umg6ax@brd.superproxy.io:9222` | SUSPENDED (rate limit) |
| acc5 | hl_caa3da41 | `wss://brd-customer-hl_caa3da41-zone-scraping_browser1:ur2v4xcy072v@brd.superproxy.io:9222` | SUSPENDED (rate limit) |
| acc6 | hl_93561405 | `wss://brd-customer-hl_93561405-zone-scraping_browser1:g3jqlqtsjtkc@brd.superproxy.io:9222` | SUSPENDED (rate limit) |
| acc7 | hl_9a778bf1 | `wss://brd-customer-hl_9a778bf1-zone-scraping_browser1:ft5y6mo4jngz@brd.superproxy.io:9222` | SUSPENDED (rate limit) |
| acc8 | hl_19c80b8e | — | SUSPENDED (credit drained) |
| acc9 | hl_6b1ebf5c | `wss://brd-customer-hl_6b1ebf5c-zone-scraping_browser1:fkfbdid0zyi4@brd.superproxy.io:9222` | SUSPENDED (rate limit) |
| acc10 | hl_e895b201 | `wss://brd-customer-hl_e895b201-zone-scraping_browser1:b65xwy1jycfq@brd.superproxy.io:9222` | **ALIVE** |
| acc11 | hl_7e8d5d40 | `wss://brd-customer-hl_7e8d5d40-zone-scraping_browser1:to0nqcophe4h@brd.superproxy.io:9222` | **ALIVE** |
| acc12 | hl_76276a19 | `wss://brd-customer-hl_76276a19-zone-scraping_browser1:yv0s6mr3xrgt@brd.superproxy.io:9222` | **ALIVE** |

### BD API Config Files
Local: `/tmp/bd/acc1-12.json`

---

## Mega Cloud Storage

```
remote: mega:railway_sessions
user: emilypeterson30@mail.findmeghana.org
pass: YHpE8zZFzThFIYjGGm44xFcyUGl1YWtCWlE4_HnRwxFodO1IlI4aFoyFUg
session_id: YHpE8zZFzThFIYjGGm44xFcyUGl1YWtCWlE4_HnRwxFodO1IlI4aFoyFUg
master_key: s6SFGB0f4UZk7VYPwK/k3A==
```

### rclone config (for sandboxes)
```ini
[mega]
type = mega
user = emilypeterson30@mail.findmeghana.org
pass = AIjpeMEdPQWNTQHR6YYDYjcEoGFSOGHASO5DjwkHcXUW7iDLFg
session_id = YHpE8zZFzThFIYjGGm44xFcyUGl1YWtCWlE4_HnRwxFodO1IlI4aFoyFUg
master_key = s6SFGB0f4UZk7VYPwK/k3A==
```

---

## Local Machine

- **Sessions dir**: `/home/alan/Documents/railways/`
- **Script**: `/home/alan/Documents/repos/automation-toolkit/railway-docker/railway-HOLY-cloud.py`
- **BD configs**: `/tmp/bd/acc*.json`
- **Pool index**: `/tmp/bd_pool_index`
- **Lock files**: `/tmp/bd_api_locks/`
- **Mega config**: `~/.config/rclone/rclone.conf`

---

## Railway Sandbox Farm

### Checkpoint
```
holy-farm-v4
```
Contains: python3, playwright+chromium, rclone v1.75, git repo, mega config.

### How to Launch
```bash
export HOME=/home/alan/Documents/railways/session-107
export LD_PRELOAD=""

# Create sandbox from checkpoint
SID=$(railway sandbox create --checkpoint holy-farm-v4 2>&1 | grep -oP '[a-f0-9-]{36}')

# Run script (raw IP, no proxy)
railway sandbox exec --detach --id "$SID" -- bash -c "\
  cd /root/automation-toolkit/railway-docker && \
  LD_PRELOAD='' HTTPS_PROXY='' HTTP_PROXY='' https_proxy='' http_proxy='' ALL_PROXY='' all_proxy='' \
  BRD_WSS='wss://brd-customer-hl_76276a19-zone-scraping_browser1:yv0s6mr3xrgt@brd.superproxy.io:9222' \
  nohup python3 -u railway-HOLY-cloud.py --cloud-no-c > /tmp/run.log 2>&1 &"
```

### How to Check Progress
```bash
# Check mega count
rclone lsd mega:railway_sessions/ 2>/dev/null | wc -l

# Check sandbox logs
railway sandbox exec --id "$SID" -- bash -c "tail -20 /tmp/run.log"
```

### Important Rules
1. **MAX 3 sandboxes per API** — 10 concurrent burned 7 APIs from rate limiting
2. **Stagger launches 30s apart** — don't hit BD simultaneously
3. **Always use raw IP** — `LD_PRELOAD=''`, clear all proxy env vars
4. **Never use `--mega-use-https`** — not valid in sandbox rclone version

---

## Email Providers (Cloud Mode)

1. **temp.tf** — Instant Gmail dots, no browser needed. Shared inbox (~880k messages).
2. **dispose.lol** — Browser-based, needs WARP. Unique inbox.
3. **22.do** — API pool of 10 handlers. Unique inbox.
4. **mail.tm** — API-based, unique inbox. Fallback.

---

## Script Flags

```bash
python3 railway-HOLY-cloud.py --cloud-no-c    # Cloud mode, no cancer cells
python3 railway-HOLY-cloud.py --cloud --cells 3  # Cloud mode with 3 persistent cells
```

---

## Account Creation Flow
1. Create temp.tf email (pre-check inbox for 500 errors)
2. Navigate to railway.com/login
3. Fill email → solve Cloudflare Turnstile → click Continue
4. Wait for OTP (check last 5 messages, 7min timeout, 30s intervals)
5. Fill OTP in Magic Link iframe → press Enter inside iframe
6. Wait for redirect to dashboard
7. Accept Railway policies (Terms + Fair Use)
8. PKCE via local headless chrome (playwright)
9. Save session to `/home/alan/Documents/railways/session-N/`
10. Sync to mega via rclone
11. Verify with `railway whoami`
12. Test sandbox creation
13. Loop

---

## Troubleshooting

### BD API suspended
Wait ~2-4 hours. Or use a different API from the pool.

### OTP not detected
Shared inbox has too many messages. The script checks last 5 only. If wrong OTP, it will fail login and breaker rotates to new API + new email.

### Mega sync timeout
Session dirs get bloated with browser cache. Script now cleans `Cache/`, `Code Cache/`, `SingletonLock`, `*.log` before sync. Timeout bumped to 300s.

### Sandbox rclone "mega backend not found"
Sandbox apt rclone is v1.60 (no mega). Install v1.75 via `curl -s https://rclone.org/install.sh | bash`. Checkpoint `holy-farm-v4` already has this.
