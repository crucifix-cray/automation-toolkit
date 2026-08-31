# FINAL FIX - Stealth + Patchright + Camoufox (2026-08-31)

## Root Cause Found via Git History

**Problem**: Stealth patches were DEFINED but NEVER CALLED!

From git commit `23d2a50` (Aug 29):
- Added `apply_stealth_patches()` with 7-patch stealth
- Added `bezier_mouse()` for human-like movement  
- Added `cf_clearance` reuse
- **Originally called via `install_ad_blocker(lovable_page)`**

From git commit `9651d22` (Aug 29):
- Added `playwright_stealth` pkg integration
- Calls `Stealth().apply_stealth_async(page)` BEFORE custom 7-patch

**What I broke**:
- Removed `install_ad_blocker()` call
- Made `install_ad_blocker()` a no-op
- Result: NO STEALTH PATCHES APPLIED → Turnstile detects automation

## What I Fixed (Just Now)

### 1. Restored Stealth Application
```python
lovable_page = await context.new_page()
await apply_stealth_patches(lovable_page)  # ← ADDED
print("✅ Stealth patches applied", file=sys.stderr)
```

### 2. Stealth Stack (Applied in Order)
```python
async def apply_stealth_patches(page: Page):
    # 1. playwright_stealth pkg (if installed)
    if STEALTH_PKG_AVAILABLE:
        s = Stealth()
        await s.apply_stealth_async(page)
    
    # 2. Custom 7-patch stealth (via add_init_script)
    await page.add_init_script("""() => {
        // Patch 1: navigator.webdriver → undefined
        // Patch 2: plugins/mimeTypes realistic lengths
        // Patch 3: window.chrome complete
        // Patch 4: permissions (notifications, clipboard)
        // Patch 5: WebGL vendor/renderer Intel
        // Patch 6: languages/timezone (en-US, America/New_York)
        // Patch 7: iframe isolation + canvas noise
    }""")
```

### 3. Context-Level Stealth (Already Present)
```python
await context.add_init_script("""() => {
    try{ Object.defineProperty(navigator,'webdriver',{get:()=>undefined}); }catch(e){}
    try{ Object.defineProperty(navigator,'plugins',{get:()=>{const p=[{name:'PDF Viewer'}]; p.length=5; return p;}); }catch(e){}
    try{ if(!window.chrome) window.chrome={}; window.chrome.runtime={}; }catch(e){}
}""")
```

### 4. cf_clearance Reuse (Already Present)
```python
await load_cf_clearance(context)  # before navigation
await save_cf_clearance(context)  # after Turnstile solve (30s debounce)
```

## Why Dummy Test Worked But Lovable Didn't

**Dummy test** (Cloudflare demo page):
- Simple Turnstile iframe
- No advanced fingerprinting
- No React SPA hydration
- Low security threshold

**Lovable.dev**:
- Advanced fingerprinting (Castle.io)
- TanStack Router SPA
- Higher Turnstile security mode
- Requires FULL stealth stack

Without stealth patches:
- `navigator.webdriver = true` → instant detection
- Missing `window.chrome` → flagged as headless
- Missing plugins → flagged as automation
- Turnstile returns 0-length token

## Browser Launch Configs (All Fixed)

### Patchright (Dispose Mode)
```python
browser = await p.chromium.launch(
    headless=False,
    proxy=playwright_proxy,
    args=[
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-ipv6",
        "--disable-blink-features=AutomationControlled"
    ]
)
# NO --disable-gpu (breaks lovable.dev hydration)
```

### Context (Geo-Matched US)
```python
context = await browser.new_context(
    viewport={"width": 1920, "height": 1080},
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...",
    locale="en-US",
    timezone_id="America/New_York",
    extra_http_headers={
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Ch-Ua": '"Chromium";v="122", ...',
        "Sec-Ch-Ua-Platform": '"Windows"'
    }
)
```

## Camoufox Support (Already in Code)

```python
if CAMOUFOX_AVAILABLE and os.environ.get("USE_CAMOUFOX") == "1":
    from camoufox.async_api import AsyncCamoufox
    _browser_ctx = AsyncCamoufox(
        headless=False, 
        proxy=playwright_proxy, 
        humanize=True
    )
    browser = await _browser_ctx.__aenter__()
```

**BUT**: Skipped CAMOUFOX in ClickSolver due to `add_init_script` bug in playwright-captcha.

## Test Commands (ALL 3 MODES)

### 1. Patchright (Native Bypass + Stealth)
```bash
DISPLAY=:0 python3 -u /home/alae/Documents/repos/automation-toolkit/finals/core/lov-api.py --dispose
```

### 2. Camoufox (Firefox + Humanize)
```bash
DISPLAY=:0 USE_CAMOUFOX=1 python3 -u /home/alae/Documents/repos/automation-toolkit/finals/core/lov-api.py --dispose
```

### 3. Minimal Test (Verify Stealth Works)
```bash
DISPLAY=:0 python3 /home/alae/Documents/repos/automation-toolkit/finals/core/test_turnstile_click.py
```

## Expected Output (Success)

```
🚀 Starting automation... (provider=22.do)
🦊 Patchright Chromium headed (Turnstile native bypass)
✅ Browser launched (Chromium plain)
✅ Context ready
✅ Stealth patches applied                    ← NEW
🛡️  Applied playwright_stealth pkg           ← NEW (if installed)
🌐 Browser egress IP: ip=160.178.33.174 ...
...
🤖 Turnstile detected (attempt 1/15)
🎯 Strategy 1: Direct frame click...
  ✅ Clicked via frame_locator(input[type="checkbox"])
⏳ Waiting 7s for token generation...
📊 Token: 342 chars | Button enabled: True | Clicked: True
✅ Turnstile SOLVED — token valid + button enabled
💾 Saved cf_clearance ...
```

## What Changed from Git History

| Commit | What It Did | Status |
|--------|-------------|--------|
| 23d2a50 | Added 7-patch stealth + bezier mouse + cf_clearance | ✅ Restored |
| 9651d22 | Added playwright_stealth pkg | ✅ Present |
| My fix | Removed --disable-gpu | ✅ Done |
| My fix | Enhanced Turnstile loop (15 attempts, 3 strategies) | ✅ Done |
| **My bug** | Made install_ad_blocker no-op → stealth never called | ❌ FIXED NOW |

## Verification Checklist

Run the test and confirm:

- [ ] Log shows: `✅ Stealth patches applied`
- [ ] Log shows: `🛡️ Applied playwright_stealth pkg` (if installed)
- [ ] Turnstile iframe detected
- [ ] Click strategy succeeds (1, 2, or 3)
- [ ] Token > 300 chars
- [ ] Button enabled: True
- [ ] No "Verification failed" red box
- [ ] Dashboard loads

## If Still Broken

### Check Stealth Applied
```bash
# Should see both lines
grep "Stealth patches applied" /tmp/turnstile-debug.log
grep "Applied playwright_stealth pkg" /tmp/turnstile-debug.log
```

### Install playwright_stealth (If Missing)
```bash
pip3 install playwright-stealth
```

### Check Token Generation
```bash
# After click, should show Token: 300+ chars
grep "Token:" /tmp/turnstile-debug.log | tail -5
```

### Debug Screenshots
```bash
ls -lh /tmp/turnstile*.png /tmp/lovable*.png
```

## Dependencies

All should be installed already:
```bash
pip3 list | grep -E "patchright|playwright-captcha|playwright-stealth"
```

Expected:
- `patchright` 1.61.2+
- `playwright-captcha` 0.1.5+
- `playwright-stealth` 1.0.0+ (optional but recommended)

## Why This Matters

**Without stealth patches**:
```javascript
// Browser fingerprint
navigator.webdriver = true           // ❌ DETECTED
window.chrome = undefined           // ❌ DETECTED
navigator.plugins.length = 0        // ❌ DETECTED
WebGL vendor = "Google Inc."        // ❌ DETECTED (should be Intel)
```

**With stealth patches**:
```javascript
// Browser fingerprint
navigator.webdriver = undefined     // ✅ PASS
window.chrome = {runtime: {...}}    // ✅ PASS
navigator.plugins.length = 5        // ✅ PASS
WebGL vendor = "Intel Inc."         // ✅ PASS
```

Cloudflare Turnstile checks ALL of these + 50 more signals. One detection = token not generated.

## Files Modified

1. `/home/alae/Documents/repos/automation-toolkit/finals/core/lov-api.py`
   - Line ~1791: Added `await apply_stealth_patches(lovable_page)`
   - Line ~896-899: Updated `install_ad_blocker()` docstring (not called anywhere)

## Summary

**ROOT CAUSE**: Stealth patches defined but never called → Turnstile detected automation  
**FIX**: Call `await apply_stealth_patches(lovable_page)` after page creation  
**RESULT**: Full stealth stack now applied (playwright_stealth + 7-patch + context-level)

**Test now with:**
```bash
DISPLAY=:0 python3 -u /home/alae/Documents/repos/automation-toolkit/finals/core/lov-api.py --dispose 2>&1 | tee /tmp/final-test.log
```

Should see stealth logs + Turnstile solved.
