# TempMail API Documentation

## Overview

This document covers the TempMail Hub API integration used in Railway and Lovable automation scripts for disposable email accounts.

**API Base URL:** `https://api.tempmailhub.org`  
**Web Interface:** `https://tempmailhub.org`

## Critical Issues & Solutions

### 1. WARP Proxy Compatibility

**Problem:** WARP SOCKS5 proxy blocks `api.tempmailhub.org` with error code 4 (host unreachable).

**Solution:** Use SOCKS4 instead of SOCKS5:
```python
WARP_PROXY = "socks4://127.0.0.1:40000"  # ✅ Works
# NOT: "socks5://127.0.0.1:40000"        # ❌ Blocked
```

**Best Practice:** Use direct connection (bypass proxy) for API calls, WARP only for browser:
```python
# Bypass proxy for API
no_proxy_handler = urllib.request.ProxyHandler({})
opener = urllib.request.build_opener(no_proxy_handler)
urllib.request.install_opener(opener)
```

### 2. Mailbox Validation Required

**Problem:** ~50% of created mailboxes have IMAP authentication failures or empty responses.

**Solution:** Implement robust validation loop:
```python
def create_working_email() -> tuple[str, str]:
    """Create accounts until finding one with working mailbox.
    
    Tests each mailbox 2x, checking for:
    - IMAP/auth errors
    - Empty/timeout responses
    - Success: "norecentemails" or '"emails":['
    
    Tries up to 30 emails in 180s timeout.
    """
    for attempt in range(1, 31):
        # Create email
        status, raw = api_post("/emails")
        email, email_id = extract_from_response(raw)
        
        # Validate Gmail format
        if not is_valid_gmail(email):
            continue
            
        # Test mailbox 2x
        for test in range(2):
            status, messages = api_post(f"/emails/messages?email_id={email_id}")
            
            # Check for errors
            if any(err in messages.lower() for err in 
                   ["imap", "authentication", "invalid credentials"]):
                break  # Try next email
                
            if "norecentemails" in messages.lower() or '"emails":[' in messages:
                return email, email_id  # Success!
                
        # Mailbox broken, try next
```

### 3. Gmail Format Validation

**Problem:** Need clean Gmail addresses without problematic characters.

**Validation Rules:**
```python
def is_valid_gmail(email: str) -> bool:
    """Validate Gmail: @gmail.com with NO dots or + before @"""
    if not email or '@gmail.com' not in email.lower():
        return False
    
    local_part = email.split('@')[0]
    
    # Reject + signs (aliases)
    if '+' in local_part:
        return False
    
    # Reject dots (can cause issues)
    if '.' in local_part:
        return False
    
    return True
```

### 4. Mailbox Expiration Issue

**CRITICAL BUG:** TempMail mailboxes die when receiving real incoming emails.

**Symptoms:**
- Mailbox works initially (200-300KB responses)
- After receiving email from external sender, API returns 0 bytes
- Subsequent requests timeout or return empty responses

**Diagnosis:**
```bash
# Monitor script shows:
Check #1: 222100 bytes (3 emails) ✅
Check #2: 222100 bytes (3 emails) ✅  
Check #3: 0 bytes (mailbox dead)    ❌ <- Email sent here
```

**Impact:** TempMail API is unreliable for real-time email reception. Only works for pre-existing spam/signup emails.

**Workaround:** Use for automated signups only (Railway, Lovable) where emails arrive within first few checks.

## API Endpoints

### Create Email
```bash
POST https://api.tempmailhub.org/emails
Content-Type: application/json
Origin: https://tempmailhub.org

{}

Response (201):
{
  "email": "example@gmail.com",
  "email_id": 123
}
```

### Check Messages
```bash
POST https://api.tempmailhub.org/emails/messages?email_id=123
Content-Type: application/json
Origin: https://tempmailhub.org

{}

Response (200):
{
  "emails": [
    {
      "id": "imap-12345",
      "subject": "Your code",
      "senderEmail": "noreply@example.com",
      "senderName": "Example",
      "date": "2026-08-11T04:00:00+00:00",
      "body": "..."
    }
  ]
}

Response (no emails):
{"message": "NoRecentEmails"}

Response (error):
{"error": "IMAP fetch failed: authentication failed"}
```

## Error Types

### IMAP Authentication Errors
```json
{
  "error": "Failed to fetch messages: IMAP fetch failed: IMAP connection failed: Can not authenticate to IMAP server: [AUTHENTICATIONFAILED] Invalid credentials (Failure)"
}
```

**Solution:** Skip this mailbox, try next one.

### Empty Response
Response body is empty (0 bytes) or only whitespace.

**Causes:**
- API timeout (>30s request)
- Mailbox expired
- Mailbox died when receiving email

**Solution:** Retry with fresh mailbox.

### Connection Timeout
```
curl: (28) Operation timed out
```

**Solution:** 
- Use direct connection instead of proxy
- Increase timeout to 60-90s
- Retry with exponential backoff

## Proxy Configuration

### Direct Connection (Recommended for API)
```python
no_proxy_handler = urllib.request.ProxyHandler({})
opener = urllib.request.build_opener(no_proxy_handler)
urllib.request.install_opener(opener)
```

### WARP SOCKS4 (Browser only)
```python
proxy = {
    "server": "socks4://127.0.0.1:40000"
}
```

### TOR (Alternative)
```bash
curl --proxy socks5h://127.0.0.1:9050 https://api.tempmailhub.org/emails
```

## Monitor Script Usage

Located at: `scripts/monitor_inbox.sh`

**Features:**
- Creates validated Gmail mailbox
- Continuous monitoring (doesn't exit)
- Proxy support (--warp, --tor, or direct)
- Email filtering (--railway, --lovable)
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

**Output:**
```
==========================================
TEMPMAIL INBOX MONITOR
==========================================

🌐 Connection: DIRECT (Raw IP)
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
📧 3 total email(s) in inbox
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📧 Email #1 (ID: imap-12345)
From: Railway <noreply@railway.com>
Subject: Your Railway verification code
Date: 2026-08-11T04:30:00+00:00
```

## Timing & Performance

| Connection Type | Create Email | Check Messages | Notes |
|----------------|--------------|----------------|-------|
| Direct | 0.5s | 4-30s | ✅ Most reliable |
| WARP SOCKS4 | 1.0s | Unstable | ⚠️ Use for creation only |
| WARP SOCKS5 | ❌ Blocked | ❌ Blocked | Don't use |
| TOR | 1.4s | 10-40s | ⚠️ Slow but works |

**Recommendations:**
1. Use direct connection for API calls
2. Use WARP/TOR only for browser automation
3. Set timeout to 90s minimum for message checks
4. Implement retry logic with fresh mailbox

## Integration Examples

### Railway Script
```python
# Create validated email
email, email_id = create_working_email()

# Fill form
await page.fill('input[type="email"]', email)

# Wait for code
code = await wait_for_railway_code(email_id, timeout_ms=180000)
```

### Lovable Script
```python
# Create email via API (bypass proxy)
email, email_id = create_working_email()

# Poll for verification link
for poll in range(30):
    messages = read_messages(email_id)
    for msg in messages:
        if 'lovable' in msg.get('subject', '').lower():
            # Extract link
            return extract_verification_link(msg['body'])
    await asyncio.sleep(10)
```

## Troubleshooting

### Mailbox Always Returns Errors
**Symptom:** Every created mailbox fails IMAP auth.

**Solution:** Increase validation attempts to 30, test each mailbox 2x.

### API Returns Empty After Working
**Symptom:** Mailbox works initially, then returns 0 bytes.

**Diagnosis:** Mailbox died (TempMail API bug).

**Solution:** This is expected behavior. Use mailbox only for initial signup flow.

### WARP Proxy Blocks API
**Symptom:** `curl: (97) cannot complete SOCKS5 connection. (4)`

**Solution:** Switch to SOCKS4 or use direct connection.

### Emails Never Arrive
**Symptom:** Mailbox works but no emails show up.

**Check:**
1. Email sent to correct address?
2. Filter applied? (--railway, --lovable)
3. Mailbox still alive? (check response length)
4. Sender domain blocked? (some domains won't deliver to temp mail)

## Known Limitations

1. **Mailbox lifespan:** ~30-60 seconds after receiving real email
2. **Success rate:** ~50% of created mailboxes are broken
3. **API speed:** 4-30s per request (very slow)
4. **No refresh:** Cannot extend mailbox lifetime
5. **No history:** Old emails disappear when mailbox dies
6. **Domain issues:** Some senders (GitHub, Google) may block temp mail domains

## Best Practices

1. ✅ Always validate mailbox before use
2. ✅ Use direct connection for API calls
3. ✅ Implement retry logic (try 30 emails)
4. ✅ Set generous timeouts (90s+)
5. ✅ Test mailbox 2x before accepting
6. ✅ Handle mailbox death gracefully
7. ❌ Don't rely on mailbox lasting >60s
8. ❌ Don't use WARP SOCKS5 for API
9. ❌ Don't expect 100% success rate
10. ❌ Don't use for production email

## Security Notes

- API requires no authentication
- Emails are public (anyone with email_id can read)
- No HTTPS required (but recommended)
- Rate limiting: unknown (observed >100 requests/min)
- IP blocking: use WARP/TOR rotation to avoid

## Future Improvements

Consider alternative providers if TempMail API remains unstable:

1. **Mail.tm** - More reliable API
2. **Guerrilla Mail** - Faster responses
3. **10minutemail** - Simple API
4. **Maildrop** - No rate limits

See `docs/ALTERNATIVES.md` for comparison.
