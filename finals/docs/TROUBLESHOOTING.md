# Troubleshooting Guide - lov-api.py

## Common Issues

### 1. "No working mailbox after 30 attempts"

**Symptoms:**
```
🔄 Attempt 30/30: Creating email via API...
  📧 Created: test456@gmail.com (ID: 99)
  ✅ Valid Gmail format
  🔍 Testing mailbox via API...
  ❌ IMAP auth error - trying next...

❌ Automation failed: Could not find working Gmail mailbox after 30 attempts
```

**Cause:** TempMailHub API rate limiting or mailbox initialization issues

**Solutions:**

1. **Wait and retry:**
   ```bash
   # Wait 5-10 minutes
   sleep 300
   python3 lov-api.py
   ```

2. **Check API status:**
   ```bash
   # Test API manually
   curl -X POST https://api.tempmailhub.org/emails \
     -H "Content-Type: application/json" \
     -d '{}'
   ```

3. **Verify network:**
   ```bash
   # Check connectivity
   ping api.tempmailhub.org
   curl -I https://api.tempmailhub.org
   ```

---

### 2. "WARP proxy not running"

**Symptoms:**
```
WARP proxy (127.0.0.1:40000) is not running; using direct connection.
```

**Cause:** WARP SOCKS proxy not started

**Solutions:**

**Option A: Ignore (recommended)**
- Script works fine without WARP
- This is just informational, not an error

**Option B: Start WARP proxy**
```bash
# Check if WARP interface exists
sudo wg show wgcf-profile

# If not, create it
bash /home/alan/Documents/rotate-warp-ip.sh

# Start SOCKS proxy (if gost installed)
gost -L socks5://:40000 &
```

**Option C: Verify WARP is working**
```bash
# Test SOCKS proxy
curl --proxy socks5h://127.0.0.1:40000 https://cloudflare.com/cdn-cgi/trace
```

---

### 3. "Browser didn't open" / "No DISPLAY"

**Symptoms:**
```
playwright._impl._errors.Error: Browser closed
```
OR
```
Error: No such file or directory: '/tmp/.X11-unix/X0'
```

**Cause:** Missing DISPLAY variable or X11 not available

**Solutions:**

1. **Set DISPLAY:**
   ```bash
   export DISPLAY=:0
   python3 lov-api.py
   ```

2. **Check X11:**
   ```bash
   # Verify X is running
   ps aux | grep X
   
   # Check DISPLAY
   echo $DISPLAY
   ```

3. **Use headless mode (if needed):**
   ```python
   # Edit lov-api.py connect_browser():
   return await playwright_support.chromium.launch(
       channel="chrome",
       headless=True,  # Change to True
       ...
   )
   ```

---

### 4. "Dashboard did not load"

**Symptoms:**
```
❌ Automation failed: Dashboard did not load
```

**Cause:** Network timeout or Lovable site issue

**Solutions:**

1. **Check network:**
   ```bash
   # Test Lovable connectivity
   curl -I https://lovable.dev
   ```

2. **Increase timeout:**
   ```python
   # Edit lov-api.py:
   await wait_for_dashboard(lovable_page, timeout=120)  # Increase from 60
   ```

3. **Manual verification:**
   ```bash
   # Check if session was actually created
   ls -la sessions/session-*/
   
   # Load session manually
   python3 load_session.py $(ls sessions/ | tail -1 | cut -d- -f2)
   ```

4. **Try without WARP:**
   ```bash
   # Stop WARP
   pkill -f gost
   sudo wg-quick down wgcf 2>/dev/null
   
   # Retry
   python3 lov-api.py
   ```

---

### 5. "Invalid Gmail format" (repeated)

**Symptoms:**
```
🔄 Attempt 15/30: Creating email via API...
  📧 Created: t.e.s.t.123@gmail.com (ID: 55)
  ❌ Invalid Gmail format (has dots/+ or not @gmail.com)
```

**Cause:** TempMailHub is generating emails with dots/plus signs

**Solutions:**

**This is normal behavior:**
- Script automatically skips invalid emails
- Will find valid email within 30 attempts
- No action needed

**If persistently failing:**
```bash
# Check how many valid emails exist in recent attempts
# Run with debug output:
python3 lov-api.py 2>&1 | grep "Valid Gmail format"
```

---

### 6. "Target page has been closed"

**Symptoms:**
```
playwright._impl._errors.TargetClosedError: Target page, context or browser has been closed
```

**Cause:** Browser or page closed unexpectedly (ad redirect or crash)

**Solution:**

**This is why we use API-ONLY!**
- lov-api.py does NOT open TempMail page
- Should not see this error
- If you do, verify you're using correct script:
  ```bash
  head -5 lov-api.py
  # Should show: "TRUE API-ONLY mode (no TempMail page)"
  ```

---

### 7. "Session already exists" / "Email already used"

**Symptoms:**
```
🔄 Attempt 5/30: Creating email via API...
  📧 Created: test123@gmail.com (ID: 42)
  ⚠️  Already used - skipping
```

**Cause:** Email was used in previous run

**Solutions:**

**This is normal behavior:**
- Script automatically skips used emails
- Will find unused email
- No action needed

**To reuse email:**
```bash
# Clear used emails list (CAUTION: may cause conflicts)
> /home/alan/Documents/used-tempmailhub-emails.txt

# Or remove specific email
sed -i '/test123@gmail.com/d' /home/alan/Documents/used-tempmailhub-emails.txt
```

---

### 8. "Signup timeout" / "Create button not found"

**Symptoms:**
```
⚠️  Signup failed (Locator.click: Timeout 30000ms exceeded.
Call log:
  - waiting for get_by_role("button", name="Create your account", exact=True)
), using reset path...
```

**Cause:** Lovable UI changed or page load issue

**Solution:**

**This is handled automatically:**
- Script detects signup failure
- Falls back to reset path
- Continues normally
- No action needed

**If persistently failing:**
1. Check Lovable site manually
2. Verify page loads correctly
3. Update selectors if UI changed

---

### 9. "TempMailHub API timeout"

**Symptoms:**
```
FlowError: TempMailHub API request failed: <urlopen error timed out>
```

**Cause:** API endpoint unreachable or slow

**Solutions:**

1. **Check API status:**
   ```bash
   # Test API manually
   time curl -X POST https://api.tempmailhub.org/emails
   ```

2. **Increase timeout:**
   ```python
   # Edit lov-api.py api_request():
   def api_request(endpoint: str, method: str = "POST", timeout: int = 60):
       # Increase from 30 to 60
   ```

3. **Check network/DNS:**
   ```bash
   # Resolve API hostname
   nslookup api.tempmailhub.org
   
   # Test connectivity
   traceroute api.tempmailhub.org
   ```

---

### 10. "Password rejected" / "Password requirements"

**Symptoms:**
```
❌ Automation failed: Lovable rejected password requirements
```

**Cause:** Lovable password policy changed or email has no digits

**Solutions:**

1. **Check password generation:**
   ```python
   # Script generates:
   password = email if re.search(r"\d", email) else f"{email}1"
   
   # If email = "test@gmail.com" → password = "test@gmail.com1"
   # If email = "test123@gmail.com" → password = "test123@gmail.com"
   ```

2. **Manually verify requirements:**
   - Visit https://lovable.dev/login
   - Check password policy
   - Update script if changed

3. **Force stronger password:**
   ```python
   # Edit lov-api.py:
   password = f"{email}!1Aa"  # Ensure special char, digit, upper/lower
   ```

---

## Debugging Steps

### Step 1: Verify Environment

```bash
# Check Python version
python3 --version  # Should be 3.7+

# Check Playwright
python3 -c "import playwright; print(playwright.__version__)"

# Check Chrome
google-chrome --version
```

### Step 2: Test Components

**Test email creation:**
```bash
python3 -c "
import sys
sys.path.insert(0, '/home/alan/Documents/automation-toolkit/finals')
from lov_api import create_working_email

try:
    email, email_id = create_working_email()
    print(f'✅ Email: {email}, ID: {email_id}')
except Exception as e:
    print(f'❌ Error: {e}')
"
```

**Test API connection:**
```bash
python3 -c "
import sys
sys.path.insert(0, '/home/alan/Documents/automation-toolkit/finals')
from lov_api import api_request

try:
    status, response = api_request('/emails')
    print(f'✅ Status: {status}')
    print(f'Response: {response[:200]}')
except Exception as e:
    print(f'❌ Error: {e}')
"
```

**Test browser launch:**
```bash
python3 -c "
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome', headless=False)
        print('✅ Browser launched')
        await browser.close()

asyncio.run(test())
"
```

### Step 3: Run with Verbose Logging

```python
# Create debug_lov_api.py:
#!/usr/bin/env python3
import logging
import sys

# Enable debug logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Run main script
sys.path.insert(0, '/home/alan/Documents/automation-toolkit/finals')
from lov_api import main

if __name__ == "__main__":
    main()
```

```bash
python3 debug_lov_api.py 2>&1 | tee debug.log
```

### Step 4: Inspect State

**Check sessions:**
```bash
# List all sessions
ls -la sessions/

# Inspect latest session
cat sessions/session-$(ls sessions/ | grep -oP '\d+' | sort -n | tail -1)/config.json | jq
```

**Check used emails:**
```bash
# Count used emails
wc -l /home/alan/Documents/used-tempmailhub-emails.txt

# View recent emails
tail -10 /home/alan/Documents/used-tempmailhub-emails.txt
```

**Check browser processes:**
```bash
# List Chrome processes
ps aux | grep chrome

# Kill if stuck
pkill -9 chrome
```

### Step 5: Network Debugging

```bash
# Monitor network calls
tcpdump -i any -A 'host api.tempmailhub.org' &
python3 lov-api.py
pkill tcpdump

# Or use mitmproxy
mitmproxy --mode reverse:https://api.tempmailhub.org &
# Configure script to use proxy
```

---

## Error Messages Reference

| Error | Severity | Auto-Recovers | Action |
|-------|----------|---------------|--------|
| "WARP proxy not running" | Info | N/A | Ignore or start WARP |
| "Already used - skipping" | Info | Yes | None (automatic) |
| "Invalid Gmail format" | Info | Yes | None (automatic) |
| "IMAP auth error" | Warning | Yes | None (automatic) |
| "Signup failed" | Warning | Yes | None (automatic) |
| "No working mailbox" | Error | No | Wait 5min, retry |
| "Dashboard did not load" | Error | No | Check network, retry |
| "API request failed" | Error | No | Check API status |
| "Browser closed" | Error | No | Check DISPLAY, retry |
| "Target page closed" | Error | No | Verify using lov-api.py |

---

## Performance Issues

### Slow Email Creation

**Symptoms:** Email creation loop takes >60 seconds

**Causes:**
- API rate limiting
- Network latency
- Many invalid emails

**Solutions:**
```bash
# Check network latency
time curl -X POST https://api.tempmailhub.org/emails

# If >2s, network issue
# If <2s but still slow, API rate limiting - wait and retry
```

### Slow Message Polling

**Symptoms:** Waiting >120s for reset email

**Causes:**
- Lovable slow to send email
- Email caught in spam filter
- API polling too slow

**Solutions:**
```python
# Reduce polling interval (lov-api.py):
await asyncio.sleep(5)  # Instead of 8

# Or increase timeout:
reset_url = await read_reset_link(email_id, timeout=300)  # 5 minutes
```

### Browser Launch Slow

**Symptoms:** 10+ seconds to launch browser

**Solutions:**
```bash
# Use existing browser (saves 3-5s)
google-chrome --remote-debugging-port=9222 &
cdp=$(curl -s localhost:9222/json | jq -r '.[0].webSocketDebuggerUrl')
python3 lov-api.py --cdp-url "$cdp"

# Or use lighter browser profile
```

---

## FAQ

### Q: Can I run multiple instances in parallel?

**A:** Possible but not recommended
- TempMailHub API will rate limit
- Better to run sequentially with delays

```bash
# Sequential (recommended)
for i in {1..5}; do
    python3 lov-api.py
    sleep 30
done

# Parallel (risky)
for i in {1..5}; do
    python3 lov-api.py &
done
wait
```

### Q: Can I use a different email provider?

**A:** Yes, but requires code changes
- Replace TempMailHub API calls
- Implement new provider's API
- Ensure Gmail validation logic matches

### Q: What if Lovable changes their UI?

**A:** Update selectors in script
- Check `request_login()` for email submission
- Check `do_signup()` for account creation
- Check `do_password_reset()` for reset flow
- Update button names / selectors as needed

### Q: Can I export sessions to other tools?

**A:** Yes
```python
# Load cookies in requests
import json
import requests

with open('sessions/session-8/cookies.json') as f:
    cookies = json.load(f)

session = requests.Session()
for cookie in cookies:
    session.cookies.set(cookie['name'], cookie['value'])

# Use session for API calls
response = session.get('https://lovable.dev/api/...')
```

### Q: How do I delete an account?

**A:** Via Lovable website
1. Load session in browser
2. Navigate to Settings
3. Delete account
4. Remove local session: `rm -rf sessions/session-N`

### Q: Can this be detected/blocked?

**A:** Possible but unlikely
- Uses real browser (Playwright)
- Real email verification
- No suspicious patterns
- Ad-blocker hides automation
- WARP rotates IP (optional)

---

## Getting Help

### Before asking for help:

1. ✅ Read this troubleshooting guide
2. ✅ Check error message in Error Messages Reference table
3. ✅ Run debugging steps (Step 1-5 above)
4. ✅ Check recent changes (git log)
5. ✅ Test components individually

### Information to provide:

- Error message (full output)
- Command used
- Environment (OS, Python version, Playwright version)
- Debug log (if available)
- Steps to reproduce

### Useful logs to collect:

```bash
# Full run log
python3 lov-api.py 2>&1 | tee run.log

# Debug log
python3 debug_lov_api.py 2>&1 | tee debug.log

# System info
python3 --version
google-chrome --version
uname -a
```

---

## Known Limitations

1. **TempMailHub API rate limits**
   - Max ~30 email creations per minute
   - Max ~20 message polls per minute

2. **Gmail-only emails**
   - Script only accepts @gmail.com
   - Other domains won't pass Lovable verification

3. **Session expiration**
   - Cookies expire after ~7 days
   - Sessions must be refreshed periodically

4. **No email verification in browser**
   - Can't see emails in browser (API-only)
   - Must trust API responses

5. **WARP routing issues**
   - Some API endpoints don't work via WARP
   - Must use bypass list

---

## Changelog

### Recent Fixes

**2026-08-14:**
- ✅ Fixed ad redirect issues (moved to API-only)
- ✅ Added email deduplication
- ✅ Added session saving
- ✅ Improved error messages
- ✅ Added WARP proxy support

**Known Issues:**
- WARP IP test fails (handshake works, but curl test doesn't)
- Workaround: Script uses direct connection, works fine

---

For more help, see:
- `README.md` - Overview and quick start
- `TECHNICAL.md` - Architecture details
- `USAGE.md` - Usage examples and workflows
