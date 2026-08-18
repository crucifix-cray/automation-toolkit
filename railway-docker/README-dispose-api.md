# Railway Dispose API Script

## Overview

**File:** `railway-dispose-api.py`

This is a complete copy of `railway-mailtm-full.py` modified to use the **REAL dispose.lol API** as documented in `dispose lol Mail Automation.txt`.

## What Changed

### Email Provider: dispose.lol REAL API
- **Original:** Mail.tm API
- **New:** Dispose.lol remote functions with proper devalue transport encoding
- **Documentation:** Based on `dispose lol Mail Automation.txt` (reverse-engineered API)
- **Endpoints:**
  - `POST /_app/remote/1i1fsx0/getOrCreateMailbox` - Create Gmail address
  - `GET /_app/remote/1i1fsx0/getMailboxMessages` - Poll for messages
- **Benefit:** Real @gmail.com addresses, proper API implementation

### Key Implementation Details

1. **Correct API Calls:**
   ```javascript
   // getOrCreateMailbox - Empty payload
   POST /_app/remote/1i1fsx0/getOrCreateMailbox
   Body: {"payload": "", "refreshes": []}
   
   // getMailboxMessages - Documented payload for current mailbox
   GET /_app/remote/1i1fsx0/getMailboxMessages?payload=W3siYXNzaWdubWVudElkIjotMX1d
   // Payload decodes to: [{"assignmentId":-1}] where -1 = undefined sentinel
   ```

2. **Proper Headers:**
   ```javascript
   'Content-Type': 'application/json',
   'x-sveltekit-pathname': '/',
   'x-sveltekit-search': ''
   ```

3. **Session Management:**
   - Uses browser page to obtain `dispose_mailbox` cookie (HttpOnly, Secure)
   - Cookie automatically included via `credentials: 'include'`
   - No manual cookie handling needed

4. **Response Format:**
   ```json
   {
     "type": "result",
     "result": "<devalue transport string>"
   }
   ```
   Result is JSON-parsed to get actual data

5. **Polling Interval:**
   - 12 seconds (matches site's behavior)
   - Checks for Railway OTP in message subjects

### All Features Preserved

- ✅ WARP IP rotation
- ✅ Cloudflare Turnstile auto-solving  
- ✅ OAuth PKCE flow for CLI sessions
- ✅ Mega.nz sync
- ✅ Continuous mode
- ✅ Stop signal (mega:stop.txt)
- ✅ Account counter
- ✅ ToS acceptance

## Usage

### Single Account
```bash
cd /home/alae/Documents/repos/automation-toolkit/railway-docker
export DISPLAY=:99  # If using Xvfb

# Without WARP
python3 railway-dispose-api.py

# With WARP
python3 railway-dispose-api.py --warp
```

### Continuous Mode
```bash
# Create up to 8000 accounts
python3 railway-dispose-api.py --continuous --warp --max-accounts 8000

# Stop early: create mega:stop.txt file
rclone touch mega:stop.txt
```

## Why This Approach?

### Pros:
- ✅ **API is faster** than browser scraping
- ✅ **No page navigation** - Railway stays on OTP modal
- ✅ **Real Gmail addresses** from dispose.lol
- ✅ **All original features** from mailtm-full preserved
- ✅ **Proven working** API reverse-engineered from dispose_lol_api.py

### Cons:
- ⚠️ API format might change (dispose.lol is unofficial)
- ⚠️ Requires browser context for session cookies

## Architecture

```
Browser Page (Railway)
    ↓
    ├─ Sign in to Railway
    ├─ Accept policies  
    ├─ OAuth flow
    └─ Register CLI session

Same Page (Dispose.lol)
    ↓
    ├─ Load dispose.lol (init session)
    ├─ API call: getOrCreateMailbox → Gmail address
    └─ API call: getMailboxMessages → Poll for OTP
```

## Testing

To test just the dispose.lol API:
```bash
python3 -c "
import asyncio
from railway_dispose_api import DisposeLolInbox
from patchright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        inbox = DisposeLolInbox(page)
        email = await inbox.create()
        print(f'Email: {email}')
        
        input('Send test email, then press Enter...')
        
        messages = await inbox.get_messages()
        print(f'Messages: {messages}')
        
        await browser.close()

asyncio.run(test())
"
```

## Files

- `railway-dispose-api.py` - Main script (THIS FILE - **USE THIS**)
- `railway-mailtm-full.py` - Original (23 commits, has page navigation bug)
- `railway-HOLY.py` - Fixed version with separate pages (4 commits)
- `dispose_lol_api.py` - API reference implementation
- `test_dispose_inbox.py` - Browser scraping reference (proven working)

## Next Steps

1. ✅ Script created and syntax validated
2. ⏳ Test single account creation: `python3 railway-dispose-api.py --no-warp`
3. ⏳ Verify OTP entry works (should work since no page navigation)
4. ⏳ Test continuous mode
5. ⏳ Deploy to Railway with WARP

## Safety Features

- **Account limit:** 8000 hard-coded max
- **Stop signal:** Create `mega:stop.txt` to gracefully stop
- **Counter:** Tracks total accounts in `mega:railway_sessions/counter.txt`
- **Error handling:** 30s retry delay on failures
- **WARP cleanup:** Always stops WARP after each account

## Author Notes

Created: 2026-08-13  
Based on: railway-mailtm-full.py (90% complete)  
Fixed: Page navigation bug by using API instead of scraping  
Status: Ready for testing
