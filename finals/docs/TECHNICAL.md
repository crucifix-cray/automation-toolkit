# Technical Documentation - lov-api.py

## Architecture Deep Dive

### Core Principles

1. **API-ONLY Mode**: No browser page for TempMail - only Lovable
2. **Fail-Fast**: Validate emails immediately via API before using
3. **Retry Logic**: Loop until working mailbox found (up to 30 attempts)
4. **Deduplication**: Track used emails to avoid conflicts

## Code Structure

### Main Components

```python
# Email Creation & Validation
create_working_email()  # API-ONLY: Creates and tests mailbox
is_valid_gmail()        # Validates Gmail format
load_used_emails()      # Deduplication check

# API Communication
api_request()           # Generic API wrapper
read_messages()         # Fetch mailbox messages
read_reset_link()       # Poll for Lovable email

# Lovable Automation
request_login()         # Submit email, detect path
do_signup()            # New account creation
do_password_reset()    # Existing account reset
set_password_and_verify()  # Complete reset flow

# Browser Management
install_ad_blocker()   # Block ads on Lovable page
connect_browser()      # Launch or connect to browser
```

### Email Creation Flow

```python
def create_working_email() -> tuple[str, str]:
    """
    TRUE API-ONLY email creation with validation.
    
    Returns:
        (email, email_id) - Verified working Gmail
    
    Process:
        1. Load used emails (deduplication)
        2. Loop up to 30 attempts:
           a. POST /emails → Create email
           b. Check if already used → Skip
           c. Validate Gmail format → Skip if invalid
           d. POST /emails/messages → Test mailbox
           e. Check for IMAP errors → Skip if broken
           f. Check for working response → FOUND!
        3. Return working email + email_id
    """
```

**API Calls:**

```python
# 1. Create Email
POST https://api.tempmailhub.org/emails
Headers: {
    "Content-Type": "application/json",
    "Origin": "https://tempmailhub.org"
}
Body: {}

Response: {
    "email": "test123@gmail.com",
    "email_id": 42
}

# 2. Test Mailbox
POST https://api.tempmailhub.org/emails/messages?email_id=42
Headers: (same)
Body: {}

Response (working): {
    "emails": []
}
OR: {
    "message": "NoRecentEmails"
}

Response (broken): {
    "error": "IMAP authentication failed"
}
```

### Gmail Validation

```python
def is_valid_gmail(email: str) -> bool:
    """
    Validate Gmail format.
    
    Rules:
        - Must end with @gmail.com
        - NO dots (.) in local part
        - NO plus signs (+) in local part
    
    Why these rules?
        - Lovable uses Gmail API for verification
        - Gmail ignores dots (test@gmail == t.e.s.t@gmail)
        - Plus addressing causes routing issues
        - Only clean Gmail addresses work reliably
    
    Examples:
        ✅ test123@gmail.com
        ✅ johnsmith@gmail.com
        ❌ test.123@gmail.com (dot)
        ❌ test+alias@gmail.com (plus)
        ❌ test@yahoo.com (not Gmail)
    """
    if not email or '@gmail.com' not in email.lower():
        return False
    
    local_part = email.split('@')[0]
    
    if '.' in local_part or '+' in local_part:
        return False
    
    return True
```

### Message Polling

```python
async def read_reset_link(email_id: str, timeout: float = 180) -> str:
    """
    Poll API for Lovable reset email.
    
    Algorithm:
        1. Start deadline timer (180s default)
        2. Loop until deadline:
           a. POST /emails/messages?email_id=X
           b. Parse JSON response
           c. Iterate through messages
           d. Check subject contains "lovable"
           e. Extract reset link via regex
           f. Return link if found
           g. Sleep 8 seconds
        3. Timeout error if not found
    
    Link Extraction:
        Pattern: https?://[^"'\s<>]*lovable\.dev[^"'\s<>]*
        Method: Regex search in JSON-stringified message
        Unescape: HTML entities decoded
    """
```

### Ad-Blocking Implementation

```python
async def install_ad_blocker(page: Page) -> None:
    """
    In-process ad/tracker blocking.
    
    Method:
        - Playwright route interception
        - Pattern matching on URL
        - Abort matching requests
        - Continue non-matching requests
    
    Blocked Patterns:
        - doubleclick.net
        - googlesyndication.com
        - googleadservices.com
        - google-analytics.com
        - (18 more patterns...)
    
    Also injects:
        - navigator.webdriver = undefined
        - Hides automation detection
    """
    def should_block(url: str) -> bool:
        lowered = url.lower()
        return any(needle in lowered for needle in AD_BLOCK_PATTERNS)
    
    async def handler(route):
        if should_block(route.request.url):
            await route.abort()
        else:
            await route.continue_()
    
    await page.route("**/*", handler)
```

## Error Handling

### API Request Retries

```python
def api_request(endpoint: str, method: str = "POST", timeout: int = 30):
    """
    Retry logic: 3 attempts with 2s delay
    
    Errors handled:
        - urllib.error.HTTPError → Return (code, body)
        - urllib.error.URLError → Retry
        - TimeoutError → Retry
        - OSError → Retry
    
    Final failure → FlowError exception
    """
```

### Email Creation Failures

```python
# IMAP auth error
if "imap" in response.lower() and "failed" in response.lower():
    continue  # Try next email

# Authentication failed
if "authentication" in response.lower() and "failed" in response.lower():
    continue  # Try next email

# Empty response
if not response or response == "":
    continue  # Try next email

# Success indicators
if "norecentemails" in response.lower() or '"emails":[' in response:
    return email, email_id  # Working mailbox!
```

### Lovable Flow Errors

```python
# Signup timeout
try:
    signup_result = await do_signup(page, email, password)
except Exception as exc:
    # Fallback to reset path
    await do_password_reset(page, email)
    # Continue with reset flow...

# Dashboard verification
if "/dashboard" not in url or "Dashboard" not in text:
    raise FlowError("Dashboard loaded but account not verified")
```

## Session Management

### Cookie Storage

```python
# Save all browser cookies
cookies = await context.cookies()

# Format: Playwright cookie dict
[
    {
        "name": "USER_COUNTRY",
        "value": "MA",
        "domain": "lovable.dev",
        "path": "/",
        "expires": 1787318440.537432,
        "httpOnly": false,
        "secure": true,
        "sameSite": "Lax"
    },
    # ... 45 more cookies
]
```

### Config Storage

```python
# Save account metadata
config = {
    "email": "test123@gmail.com",
    "password": "test123@gmail.com1",
    "created_at": "2026-08-14T14:21:47.767722",
    "dashboard_url": "https://lovable.dev/dashboard",
    "verified": True,
    "api_only": True,  # Flag for tracking
}
```

### Session Numbering

```python
# Auto-increment session number
existing_sessions = sorted(sessions_dir.glob("session-*"))
if existing_sessions:
    last_num = int(existing_sessions[-1].name.split("-")[1])
    session_num = last_num + 1
else:
    session_num = 1

# Result: session-1, session-2, session-3, ...
```

## WARP Integration

### Proxy Detection

```python
def proxy_settings() -> dict | None:
    """
    Auto-detect WARP SOCKS proxy.
    
    Test:
        socket.connect to 127.0.0.1:40000
        timeout: 2 seconds
    
    Success:
        return {
            "server": "socks5://127.0.0.1:40000",
            "bypass": "api.tempmailhub.org,api.lovable.dev,..."
        }
    
    Failure:
        return None → Direct connection
    
    Bypass list:
        - api.tempmailhub.org (API must be direct)
        - api.lovable.dev (API must be direct)
        - 127.0.0.1, localhost (local always direct)
    """
```

### Why Bypass API Endpoints?

WARP routing breaks some API endpoints:
- `api.tempmailhub.org` returns timeouts via WARP
- `api.lovable.dev` has authentication issues via WARP
- Solution: Bypass these, use WARP for everything else

## Performance

### Timing Breakdown

```
Average successful run: 45-90 seconds

Email creation:        5-15s  (retries if mailbox broken)
Lovable login:         3-5s
Reset email waiting:   10-30s (polling every 8s)
Password reset:        5-10s
Dashboard verify:      2-5s
Session save:          1-2s
-----------------------------------------
Total:                 26-67s (typical)
```

### Optimization Strategies

1. **Parallel API Calls**: Not implemented (API rate limiting risk)
2. **Cached Email Pool**: Could pre-generate working emails
3. **Faster Polling**: 8s interval is conservative (could reduce to 5s)
4. **Browser Reuse**: CDP connection saves 3-5s per run

## Security Considerations

### Credentials Storage

```python
# ⚠️ PLAINTEXT PASSWORD STORAGE
config = {
    "password": "test123@gmail.com1",  # Not encrypted!
}

# Why plaintext?
# - Temporary accounts (disposable)
# - Local filesystem only
# - Not production-grade security
```

### Email Privacy

```python
# Used emails tracked in plaintext
/home/alan/Documents/used-tempmailhub-emails.txt

# Format: lowercase emails, one per line
test123@gmail.com
test456@gmail.com
```

**Risk**: If file is compromised, all created accounts are exposed

**Mitigation**: 
- File permissions: 600 (owner read/write only)
- Not committed to git
- Deleted periodically

### Ad-Blocker Bypass Detection

```python
# Anti-detection measures
await page.add_init_script(
    "() => { "
    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined}); "
    "}"
)

# What this does:
# - Removes navigator.webdriver flag
# - Hides Playwright/Selenium detection
# - Allows automation to pass anti-bot checks
```

## Testing

### Manual Testing

```bash
# Test email creation only
python3 -c "
from lov_api import create_working_email
email, email_id = create_working_email()
print(f'Email: {email}, ID: {email_id}')
"

# Test API request
python3 -c "
from lov_api import api_request
status, response = api_request('/emails')
print(f'Status: {status}')
print(f'Response: {response[:200]}')
"

# Test Gmail validation
python3 -c "
from lov_api import is_valid_gmail
print(is_valid_gmail('test@gmail.com'))      # True
print(is_valid_gmail('test.123@gmail.com'))  # False
print(is_valid_gmail('test+a@gmail.com'))    # False
"
```

### Integration Testing

```bash
# Full run with timeout
timeout 120 python3 lov-api.py

# Check exit code
if [ $? -eq 0 ]; then
    echo "✅ Success"
else
    echo "❌ Failed"
fi

# Verify session created
ls -la sessions/session-*/
```

## Debugging

### Enable Verbose Logging

```python
# Add to main()
import logging
logging.basicConfig(level=logging.DEBUG)

# Or for specific components
print(f"DEBUG: API response: {response}", file=sys.stderr)
```

### Common Debug Points

```python
# 1. Email creation loop
print(f"  📧 Attempt {attempt}: {email} (ID: {email_id})")

# 2. API responses
print(f"DEBUG: Response length: {len(msg_response)} bytes")
print(f"DEBUG: First 200 chars: {msg_response[:200]}")

# 3. Lovable page state
print(f"DEBUG: URL: {page.url}")
print(f"DEBUG: Body text: {await body_text(page)}")

# 4. Message polling
print(f"  📥 Check #{check_count}: Polling API...")
print(f"DEBUG: Found {len(messages)} messages")
```

### Browser DevTools

```python
# Launch with DevTools open
browser = await playwright.chromium.launch(
    channel="chrome",
    headless=False,
    devtools=True,  # Opens DevTools automatically
)
```

## Future Improvements

### Possible Enhancements

1. **Email Pool Pre-Generation**
   ```python
   async def create_email_pool(size: int = 10):
       """Pre-generate working emails for faster runs"""
       pool = []
       for _ in range(size):
           email, email_id = create_working_email()
           pool.append((email, email_id))
       return pool
   ```

2. **Parallel Account Creation**
   ```python
   async def create_multiple_accounts(count: int):
       """Create multiple accounts in parallel"""
       tasks = [run(None) for _ in range(count)]
       results = await asyncio.gather(*tasks)
       return results
   ```

3. **API Response Caching**
   ```python
   _cache = {}
   def cached_api_request(endpoint):
       if endpoint in _cache:
           return _cache[endpoint]
       result = api_request(endpoint)
       _cache[endpoint] = result
       return result
   ```

4. **Retry Strategy Improvements**
   ```python
   # Exponential backoff
   for attempt in range(max_attempts):
       try:
           return create_working_email()
       except FlowError:
           delay = 2 ** attempt  # 1s, 2s, 4s, 8s...
           await asyncio.sleep(delay)
   ```

## API Rate Limiting

### TempMailHub Limits

**Observed behavior:**
- Email creation: ~30 requests/minute max
- Message polling: ~20 requests/minute max
- Beyond limit: Empty responses or timeouts

**Mitigation:**
```python
import time

last_request = 0
min_interval = 2  # seconds

def api_request(endpoint):
    global last_request
    elapsed = time.time() - last_request
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)
    
    result = _make_request(endpoint)
    last_request = time.time()
    return result
```

## Troubleshooting Matrix

| Symptom | Cause | Solution |
|---------|-------|----------|
| "No working mailbox after 30 attempts" | API rate limiting | Wait 5 minutes, retry |
| "WARP proxy not running" | WARP not started | Optional - script works without |
| "Dashboard did not load" | Network timeout | Check connection, retry |
| "Invalid Gmail format" | Dots/+ in email | Skip to next email (automatic) |
| "IMAP auth error" | Broken mailbox | Skip to next email (automatic) |
| "Browser didn't open" | No DISPLAY | `export DISPLAY=:0` |
| "Target closed" | Ad redirect | Using API-only prevents this |

## Comparison: API vs Page Scraping

### API-ONLY (lov-api.py)

**Pros:**
- ✅ No ad redirects
- ✅ Faster (no page load)
- ✅ More reliable
- ✅ No DOM parsing
- ✅ Simpler code

**Cons:**
- ❌ Depends on API stability
- ❌ No visual debugging
- ❌ Can't verify email in browser

### Page Scraping (lovable-script2.py)

**Pros:**
- ✅ Visual verification
- ✅ Can handle UI changes
- ✅ Fallback if API fails

**Cons:**
- ❌ Ad redirects break flow
- ❌ Slower (page loads)
- ❌ DOM parsing fragile
- ❌ More complex code
- ❌ White screen issues

**Winner:** API-ONLY for production use
