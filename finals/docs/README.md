# Lovable Automation - API-ONLY Mode

**TRUE API-ONLY** Lovable account creator using TempMailHub API with no page scraping.

## Overview

`lov-api.py` creates verified Lovable accounts completely via API - no TempMail page is ever opened. This eliminates ad redirect issues and page scraping failures.

## Features

✅ **TRUE API-ONLY** - No TempMail page opened  
✅ **Ad-blocking** - Blocks ads on Lovable page  
✅ **WARP Support** - Optional Cloudflare WARP proxy  
✅ **Email Validation** - Gmail only (no dots/+ before @)  
✅ **Mailbox Testing** - Tests via API before use  
✅ **Email Deduplication** - Tracks used emails  
✅ **Password Reset** - Full reset flow support  
✅ **Session Saving** - Saves cookies + credentials  

## Quick Start

```bash
cd /home/alan/Documents/automation-toolkit/finals
python3 lov-api.py
```

## Requirements

- Python 3.7+
- Playwright
- Chrome/Chromium

```bash
pip install playwright
playwright install chrome
```

## How It Works

### 1. Email Creation (API-ONLY)
```
API: POST /emails
  → Get email + email_id
  → Validate Gmail format (no dots/+)
  
API: POST /emails/messages?email_id=X
  → Test mailbox
  → Check for IMAP errors
  → Verify working mailbox
```

### 2. Lovable Account Flow
```
Navigate to lovable.dev
  → Submit email
  → Check if account exists
  
IF NEW:
  → Create account
  → Wait for verification email (via API)
  
IF EXISTS:
  → Request password reset
  → Poll API for reset email
  → Extract reset link
  → Set new password
```

### 3. Email Polling (API-ONLY)
```
Loop every 8 seconds:
  API: POST /emails/messages?email_id=X
  → Parse JSON response
  → Look for "lovable" in subject
  → Extract reset link from body
  → Return link
```

### 4. Session Saving
```
sessions/session-N/
  ├── cookies.json    (browser cookies)
  └── config.json     (email, password, timestamp)
```

## Configuration

### Environment Variables

```bash
# Keep browser open after completion (default: 1)
export KEEP_BROWSER_OPEN=1

# Connect to existing browser via CDP
export BU_CDP_WS="ws://localhost:9222/..."
```

### WARP Proxy (Optional)

If WARP proxy is running at `127.0.0.1:40000`, it will be used automatically:

```bash
# Script will detect and use:
proxy={"server": "socks5://127.0.0.1:40000"}
```

If WARP is not available, script falls back to direct connection.

## Output

### Success
```json
{
  "verified": true,
  "email": "example123@gmail.com",
  "password": "example123@gmail.com1",
  "dashboard_url": "https://lovable.dev/dashboard",
  "session_dir": "/path/to/sessions/session-8",
  "session_number": 8
}
```

### Session Structure
```
sessions/session-8/
├── cookies.json     # 46 browser cookies
└── config.json      # Account details
```

## Email Validation

**Gmail Requirements:**
- Must be `@gmail.com`
- NO dots (`.`) before `@`
- NO plus signs (`+`) before `@`

**Valid:**
- ✅ `test123@gmail.com`
- ✅ `johnsmith@gmail.com`

**Invalid:**
- ❌ `test.123@gmail.com` (has dot)
- ❌ `test+alias@gmail.com` (has plus)
- ❌ `test@yahoo.com` (not Gmail)

## Deduplication

Used emails are tracked in:
```
/home/alan/Documents/used-tempmailhub-emails.txt
```

Format: One email per line (lowercase)

## Troubleshooting

### No Working Mailbox Found

**Problem:** Script tries 30 emails but none have working mailbox

**Solution:** 
- Wait a few minutes (TempMail API may be rate-limiting)
- Run again - different email pool will be tried

### WARP Proxy Not Working

**Problem:** `WARP proxy (127.0.0.1:40000) is not running`

**Solution:**
- Script automatically falls back to direct connection
- WARP is optional, not required

### Browser Doesn't Open

**Problem:** No browser window appears

**Solution:**
```bash
# Check DISPLAY variable
echo $DISPLAY

# Set if empty
export DISPLAY=:0
```

### Dashboard Not Loading

**Problem:** Script completes but dashboard doesn't verify

**Solution:**
- Check network connectivity
- Try without WARP proxy
- Manual verification:
  ```bash
  python3 -c "
  import json
  with open('sessions/session-X/config.json') as f:
      print(json.load(f))
  "
  ```

## Advanced Usage

### Connect to Existing Browser

```bash
# Start Chrome with debugging
google-chrome --remote-debugging-port=9222 &

# Get WebSocket URL
curl localhost:9222/json | jq -r '.[0].webSocketDebuggerUrl'

# Use with script
python3 lov-api.py --cdp-url "ws://localhost:9222/..."
```

### Custom Timeout

Edit script to adjust timeouts:

```python
# Email polling timeout (default: 180s)
reset_url = await read_reset_link(email_id, timeout=300)

# Dashboard wait timeout (default: 60s)
await wait_for_dashboard(lovable_page, timeout=90)
```

## API Reference

### TempMailHub API

**Create Email:**
```bash
curl -X POST https://api.tempmailhub.org/emails \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Get Messages:**
```bash
curl -X POST "https://api.tempmailhub.org/emails/messages?email_id=123" \
  -H "Content-Type: application/json" \
  -d '{}'
```

## Comparison with Other Scripts

| Feature | lov-api.py | lovable-script2.py | lov3F.py |
|---------|------------|-------------------|----------|
| TempMail Page | ❌ No | ✅ Yes | ✅ Yes |
| API-ONLY | ✅ Yes | ❌ No | ❌ No |
| Ad Redirects | ✅ Avoided | ❌ Possible | ❌ Possible |
| Page Scraping | ❌ No | ✅ Yes | ✅ Yes |
| Session Saving | ✅ Yes | ❌ No | ✅ Yes |
| Ad-Blocking | ✅ Yes | ✅ Yes | ✅ Yes |

## Architecture

```
┌─────────────────┐
│   lov-api.py    │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌───────┐  ┌──────────┐
│ API   │  │ Lovable  │
│ Only  │  │ Browser  │
└───┬───┘  └────┬─────┘
    │           │
    ▼           ▼
┌───────────┐ ┌──────────┐
│ TempMail  │ │ Lovable  │
│ Hub API   │ │ Website  │
└───────────┘ └──────────┘
```

**Flow:**
1. Create email via API
2. Test mailbox via API
3. Open Lovable page (only page!)
4. Submit email to Lovable
5. Poll API for reset email
6. Extract link from API response
7. Complete reset on Lovable page
8. Save session

## License

MIT

## Support

For issues or questions, check:
- `/home/alan/Documents/automation-toolkit/scripts/monitor_inbox.sh` - Working API example
- Session logs in `sessions/session-X/config.json`
- Used emails list in `/home/alan/Documents/used-tempmailhub-emails.txt`
