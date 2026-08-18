# Railway automation

Covers `scripts/railway-API-WORKING.py`, `scripts/railway-script.py`, 
`scripts/railway-script2.py` and `scripts/railway-login.py`.

## Device-flow login automation (`railway-script*.py`)

Automates Railway's CLI login UI in the browser:

1. Launches (or attaches to) a hardened Chrome.
2. Opens the Railway device-authorization page and waits out the
   Cloudflare challenge (`wait_for_cloudflare(page, "Railway device
   authorization")` – reloads while "Just a moment" / challenge screens
   persist).
3. Clicks through "Continue to Railway" / authorization confirmations.
4. Optionally writes the resulting session into the Railway CLI config
   format used by this project.

`railway-script2.py` is a reworked variant (same goal, cleaner
Cloudflare-wait handling) and is the preferred one.

## CLI OAuth flow (`railway-login.py`)

`railway-login.py` re-implements the Railway CLI's authorization-code (PKCE)
OAuth flow so the resulting tokens include the OIDC scopes the plain
device-code flow omits:

1. Generate PKCE verifier + state, start a local callback HTTP server.
2. Open the authorization URL in the browser (user logs in / SSO).
3. Receive the `code` redirect on `127.0.0.1`, exchange it at
   `RAILWAY_OAUTH/token` for `access_token` + `refresh_token`.
4. Write a Railway CLI session file (`*.session`) and update the CLI config.

### Cloudflare in the middle

Railway's auth pages sit behind Cloudflare. The scripts never click until
`wait_for_cloudflare` reports the real page; forced clicks on challenge
screens produce `ERR_ABORTED`-style dead ends, so patience is built in.

## Wiring into the CLI

The CLI config/session layout (per-session dirs such as
`railway_cli_sessions/` and `.railway/`) is:

```
{
  "user": { "accessToken": "...", "refreshToken": "...", "token": null,
            "tokenExpiresAt": <epoch ms>, ... }
}
```

`railway-login.py` writes this structure and refreshes tokens before expiry.
Refresh flow: re-run the OAuth dance; there is no refresh-token rotation
endpoint in the automation, the token endpoint answers with a fresh pair.

## API-based Email Automation (`railway-API-WORKING.py`)

The latest script uses TempMail Hub API for disposable Gmail accounts:

1. **Email Creation:** Creates validated Gmail via API (bypasses proxy for reliability)
   - Validates format: `@gmail.com` without dots or + signs
   - Tests mailbox 2x to ensure working IMAP
   - Retries up to 30 emails until finding working mailbox

2. **Browser Automation:** Uses WARP SOCKS4 proxy for browser
   ```python
   WARP_PROXY = "socks4://127.0.0.1:40000"  # SOCKS4 works, SOCKS5 blocked
   ```

3. **Cloudflare Turnstile:** Passive solving
   - Detects Turnstile iframe
   - Polls button every 500ms (fast polling)
   - Clicks immediately when enabled
   - 180s timeout for headless solve

4. **Code Retrieval:** Polls TempMail API for Railway 6-digit code
   - 15s initial wait for Railway to send email
   - Polls every 8s for up to 180s
   - Extracts code via regex: `\b(\d{6})\s+is your Railway`

### WARP Configuration

**Browser:** Use WARP SOCKS4 proxy for IP rotation
```python
proxy_settings = {
    "server": "socks4://127.0.0.1:40000",
    "bypass": "22.do,127.0.0.1,localhost,railway.com"
}
```

**API:** Bypass proxy for TempMail API (blocked on WARP SOCKS5)
```python
no_proxy_handler = urllib.request.ProxyHandler({})
opener = urllib.request.build_opener(no_proxy_handler)
urllib.request.install_opener(opener)
```

### Email Validation

Critical: ~50% of TempMail mailboxes have IMAP errors. Robust validation required:

```python
# Test mailbox before accepting
for test_attempt in range(1, 3):
    status, messages = api_post(f"/emails/messages?email_id={email_id}")
    
    # Check for IMAP/auth errors
    if any(err in messages.lower() for err in 
           ["imap", "authentication", "invalid credentials"]):
        break  # Try next email
        
    # Success indicators
    if "norecentemails" in messages.lower() or '"emails":[' in messages:
        return email, email_id  # Working mailbox!
```

See `docs/TEMPMAIL_API.md` for complete API documentation.

### Usage

```bash
cd /home/alan/Documents/automation-toolkit/scripts
python3 railway-API-WORKING.py
```

**Output:**
```
🚀 Railway CLI Session Creator + Mega Sync
📁 Sessions directory: /home/alan/Documents/railways
🌐 Mega remote: mega:railway_sessions

🔄 Rotating WARP IP for new session...
🌐 Current IP: 160.178.33.219

📧 Creating TempMailHub Gmail via API...
⚠ Skipping invalid Gmail: probe+alias@gmail.com
✓ Working Gmail: altonlehman16@gmail.com (email_id=57)
✓ Gmail created: altonlehman16@gmail.com
✓ Clicked 'Log in using email'
✓ Filled email: altonlehman16@gmail.com
✓ Turnstile found - waiting passively
⏳ Fast polling button (every 0.5s, max 180s)...
✅ BUTTON ENABLED! Clicking NOW...

⏳ Polling TempMailHub API for Railway code...
⏳ Waiting 15s for Railway to send email...
  Poll #1: 0 messages in inbox
  Poll #2: 1 messages in inbox
✓ Found Railway code: 123456
```

## Monitor Script (`monitor_inbox.sh`)

Standalone utility for testing TempMail API email reception.

**Features:**
- Creates validated Gmail mailbox
- Continuous monitoring (doesn't exit)
- Proxy support: Direct, WARP, TOR
- Email filtering: Railway, Lovable, or all
- Shows latest emails first
- Detects mailbox death

**Usage:**
```bash
# Direct connection, all emails
bash scripts/monitor_inbox.sh

# WARP proxy, Railway emails only  
bash scripts/monitor_inbox.sh --warp --railway

# TOR proxy, Lovable emails only
bash scripts/monitor_inbox.sh --tor --lovable
```

**Arguments:**
- `--warp` - Use WARP SOCKS4 proxy (127.0.0.1:40000)
- `--tor` - Use TOR SOCKS5 proxy (127.0.0.1:9050)
- `--railway` - Show only emails containing "railway"
- `--lovable` - Show only emails containing "lovable"

**Example Output:**
```
==========================================
TEMPMAIL INBOX MONITOR
==========================================

🌐 Connection: WARP (socks4://127.0.0.1:40000)
🔍 Filter: Show only 'railway' emails

Attempt 1: Creating email...
  Created: example123@gmail.com (ID: 45)
  ✅ Valid Gmail format
  Testing mailbox...
  ✅ Mailbox working!

================================================
📬 SEND YOUR EMAIL TO: example123@gmail.com
================================================

Check #1 at 04:30:17
📧 1 total email(s) in inbox
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📧 Email #1 (ID: imap-12345)
From: Railway <noreply@railway.com>
Subject: Your Railway verification code is 123456
Date: 2026-08-11T04:30:00+00:00
```

**Known Issue:** TempMail mailboxes die after receiving real emails. Monitor script detects and reports this.

## Gotchas

- Token expiry: session files carry `expires_at`; automation should re-login
  before expiry or requests 401.
- Do **not** commit `browser_cookies.json`, `railway_cli_sessions/*`,
  `.railway/*` or any `config.json` containing live tokens (see
  `docs/SECURITY.md`).
- **TempMail API:** Mailboxes expire/die quickly, especially after receiving real emails. 
  Scripts implement robust validation and retry logic (see `docs/TEMPMAIL_API.md`).
