# Cloudflare Turnstile Fix - lovable.dev Automation (2026-08-31)

## Issues Fixed

### 1. **White Screen / Skeleton Page (lovable.dev/signup)**
**Root Cause**: `--disable-gpu` flag prevents WebGL/Canvas rendering needed for React hydration  
**Fix**: Removed `--disable-gpu` from all browser launch configurations

**Changes**:
- Line ~1156: Removed `--disable-gpu` from Patchright Chromium args (dispose mode)
- Line ~1167: Removed `--disable-gpu` from Patchright Chromium args (tempmailhub mode)  
- Line ~1695: Removed `--disable-gpu` from fallback `connect_browser()` function

**Detection**: Enhanced white-screen detection in `wait_for_lovable_ready()`:
- Check for `/signup` skeleton: `<67KB html + animate-pulse + no "Create your account"`
- Redirect to `/` (never direct to `/signup`) for proper hydration
- 3 retry limit with detailed logging

---

### 2. **Turnstile "Verification failed" Loop**
**Root Cause**: Token expires after 5 minutes, page shows red "Verification failed" box but script counted as failed attempt  
**Fix**: Detect "Verification failed" → reload + re-fill form WITHOUT counting as failed attempt

**Changes** (do_signup function, ~line 1320-1450):
```python
# Check for "Verification failed" (expired token) — reload without counting attempt
if "Verification failed" in txt or "Troubleshooting" in txt:
    print("  ⚠️ Token expired/rejected — reload + retry (not counting as failed attempt)")
    await page.reload(wait_until="domcontentloaded", timeout=30000)
    # Re-fill email + passwords
    attempt -= 1  # Don't count expired token as failed attempt
    continue
```

---

### 3. **Turnstile Token Validation**
**Root Cause**: Script clicked checkbox but didn't validate token length or button state  
**Fix**: Check `cf-turnstile-response` token >20 chars AND "Create your account" button enabled

**Changes**:
```python
# Validate token length (must be >20 characters)
token_len = await page.evaluate(
    '''() => document.querySelector('input[name="cf-turnstile-response"]')?.value?.length || 0'''
)

# Check if "Create your account" button is enabled
is_enabled = not await create_btn.is_disabled()

print(f"  📊 Token: {token_len} chars, Button enabled: {is_enabled}")

# Success criteria: token >20 chars AND button enabled
if token_len > 20 and is_enabled:
    print("✅ Turnstile solved — token valid, button enabled")
    button_enabled = True
    break
```

---

### 4. **Turnstile Attempt Limit Too Low**
**Root Cause**: 5 attempts not enough for low-score IPs (raw Morocco, Tor exits)  
**Fix**: Increased to 10 attempts + smart retry (don't count expired tokens)

**Changes**:
```python
max_turnstile_attempts = 10  # was 5
attempt = 0
button_enabled = False

while not button_enabled and attempt < max_turnstile_attempts:
    # ... solve logic ...
    if "Verification failed":
        attempt -= 1  # smart retry
        continue
    attempt += 1
```

---

### 5. **Enhanced Turnstile Click Strategy**
**Root Cause**: Coordinate click at 22px needed human-like mouse movement  
**Fix**: Added bezier mouse movement before coordinate click

**Changes**:
```python
# Coordinate click fallback: 22px from left edge (exact Turnstile checkbox position)
if not clicked:
    box = await turnstile_iframe.first.bounding_box()
    if box and box["width"] > 0:
        # Human-like bezier mouse movement to checkbox
        await bezier_mouse(page, int(box["x"] + 22), int(box["y"] + box["height"] / 2))
        await page.mouse.click(box["x"] + 22, box["y"] + box["height"] / 2, delay=100)
        await page.wait_for_timeout(300)
        # Second click for robustness
        await page.mouse.click(box["x"] + 30, box["y"] + box["height"] / 2, delay=100)
        print("  🔘 Clicked checkbox via coords (22px)")
```

---

### 6. **Longer Token Generation Wait**
**Root Cause**: 5s not enough for token generation on slow IPs  
**Fix**: Increased to 6s after checkbox click

**Changes**:
```python
# Wait for token generation (5-6 seconds critical for Turnstile)
await page.wait_for_timeout(6000)  # was 5000
```

---

## Implementation Summary

### Turnstile Solve Flow (2026 Best Practices)
1. **Detect**: Wait for `iframe[src*="challenges.cloudflare.com"]` or `div.cf-turnstile` (8s timeout)
2. **Human scroll**: `mouse.wheel(0, 80)` then `mouse.wheel(0, -40)` with delays
3. **Click checkbox**: 
   - Try frame_locator selectors: `input[type="checkbox"]`, `[role="checkbox"]`, `label`, `#challenge-stage`
   - Fallback: Bezier mouse to coords (22px from left edge) + double click
4. **ClickSolver fallback**: PATCHRIGHT → PLAYWRIGHT → CAMOUFOX (3 frameworks, 3 attempts each)
5. **Wait 6s**: Critical for token generation
6. **Validate**: Check `cf-turnstile-response` >20 chars AND button enabled
7. **Handle expired**: If "Verification failed" → reload + re-fill (don't count attempt)
8. **Repeat**: Until button enabled or 10 attempts (smart retry doesn't count expired)

---

## Browser Configuration

### Patchright Chromium (Both Modes)
```python
args=[
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-ipv6",
    "--disable-blink-features=AutomationControlled"
]
# NO --disable-gpu (breaks lovable.dev hydration)
```

### Context (Realistic US Fingerprint)
```python
viewport={"width": 1920, "height": 1080}
user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ..."
locale="en-US"
timezone_id="America/New_York"
```

---

## Testing Commands

### 1. Test tempmailhub mode (no --end keeps browser open)
```bash
DISPLAY=:0 python3 -u /home/alae/Documents/repos/automation-toolkit/finals/core/lov-api.py
```

### 2. Test dispose mode (22.do/temp.tf/dispose.lol)
```bash
DISPLAY=:0 python3 -u /home/alae/Documents/repos/automation-toolkit/finals/core/lov-api.py --dispose
```

### 3. Test with WARP proxy (if wireproxy alive on 40000)
```bash
DISPLAY=:0 LOV_PROXY_PORT=40000 python3 -u /home/alae/Documents/repos/automation-toolkit/finals/core/lov-api.py --dispose
```

### 4. Test raw IP (force no proxy)
```bash
DISPLAY=:0 python3 -u /home/alae/Documents/repos/automation-toolkit/finals/core/lov-api.py --raw
```

### 5. Test with Camoufox (Firefox + humanize)
```bash
DISPLAY=:0 USE_CAMOUFOX=1 python3 -u /home/alae/Documents/repos/automation-toolkit/finals/core/lov-api.py
```

---

## Expected Output (Success)

```
🚀 Starting automation... (provider=tempmailhub)
🌐 Browser direct (warp=off, isolated)
🦊 Patchright Chromium headed (Turnstile native bypass)
✅ Browser launched (Chromium plain)
✅ Context ready
🌐 Browser egress IP: ip=160.178.33.174 ...
📋 Loaded 0 used emails
🔄 Attempt 1/30: Creating email via API...
  📧 Created: xyz@gmail.com (ID: 12345)
  ✅ Valid Gmail format
  🔍 Testing mailbox via API...
  ✅ Mailbox working (empty, ready for verification mail)
🎉 FOUND WORKING GMAIL: xyz@gmail.com (ID: 12345)
  🌐 Navigating to Lovable...
  🍪 Dismissing overlays...
  🖱️  Clicking 'Log in' button (with retry for 15 min)...
  ✅ Clicked 'Log in' button
  ✅ Login popup appeared!
📝 Lovable: No account found, creating one...
🤖 Waiting for Turnstile challenge...
🤖 Turnstile detected (attempt 1/10)
  🔘 Clicked checkbox via input[type="checkbox"]
  📊 Token: 0 chars, Button enabled: False
🤖 Turnstile detected (attempt 2/10)
  🔘 Clicked checkbox via coords (22px)
  📊 Token: 342 chars, Button enabled: True
✅ Turnstile solved — token valid, button enabled
✅ Saved 1 cookies to /path/to/session-123/cookies.json
🎉 SUCCESS!
```

---

## Verification Checklist

After running, verify:
- [ ] Browser visible in `hyprctl clients` (chromium-browser or firefox-default)
- [ ] lovable.dev/signup renders "Create your account" form (not white/skeleton)
- [ ] Turnstile checkbox clicked + token >20 chars logged
- [ ] No "Verification failed" red box (or reloaded successfully)
- [ ] Dashboard Account menu visible after success
- [ ] cookies.json + config.json saved to session dir
- [ ] Egress IP not Tor Exit Node (if --raw or warp working)

---

## Debug Screenshots

On failure, script saves:
- `/tmp/lovable_signup_debug.png` - signup page state
- `/tmp/lov-no-submit.png` - login popup without submit button
- `/tmp/disposelol-error.png` - dispose.lol email not found

---

## References (Content rephrased for compliance)

Based on research from multiple sources about Cloudflare Turnstile bypass techniques in 2026:

1. **Token validation is critical** - Turnstile tokens expire after 5 minutes and must be >20 characters
2. **Patchright provides native bypass** - `navigator.webdriver=false` built-in, better than playwright-stealth
3. **Behavioral signals matter** - Mouse movement, scroll timing, human delays increase pass rate
4. **ClickSolver framework cascade** - PATCHRIGHT → PLAYWRIGHT → CAMOUFOX provides redundancy
5. **--disable-gpu breaks React hydration** - Modern SPAs need WebGL/Canvas for rendering
6. **Smart retry logic** - Don't count expired token as failed attempt, reload + re-fill instead

Sources included official Cloudflare Turnstile documentation, GitHub playwright-captcha library, and automation engineering blogs discussing 2026 anti-bot bypass techniques.

---

## File Stats
- **Original**: 1863 lines
- **Updated**: 1988 lines (+125 lines enhanced Turnstile logic)
- **Syntax**: ✅ Verified with `python3 -m py_compile`
