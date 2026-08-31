# Dispose Mode: Direct /signup Flow (2026-08-31)

## Flow Overview

**Dispose mode** (`--dispose` flag) now goes DIRECT to `/signup` page instead of login popup:

```
1. Create email (temp.tf or 22.do)
2. Navigate to lovable.dev/signup (DIRECT)
3. Fill email (input#auth-dialog-email)
4. Fill password 1 (input[type="password"]:nth(0))
5. Fill password 2 (input[type="password"]:nth(1))
6. Wait for Turnstile iframe
7. Click checkbox (3 strategies)
8. Wait 7s for token generation
9. Click "Create your account" button
10. Handle verification email or dashboard
```

## Selectors Used (from git history)

```python
# Email input
'input#auth-dialog-email, input[type="email"]'

# Password inputs (2 required)
'input[type="password"]'  # .nth(0) and .nth(1)

# Create button
'button[role="button"]:has-text("Create your account")'
# or via get_by_role
page.get_by_role("button", name="Create your account", exact=True)

# Turnstile iframe
'iframe[src*="challenges.cloudflare.com"]'

# Turnstile checkbox (inside iframe)
frame_locator('iframe[src*="challenges.cloudflare.com"]')
  .locator('input[type="checkbox"]')  # or [role="checkbox"], label, span, div
```

## Key Changes

### 1. **Separate Functions**
- `do_signup()` - Tempmailhub mode (fills email + passwords + Turnstile)
- `do_signup_turnstile_only()` - Dispose mode (only Turnstile, email/pwd already filled)

### 2. **Direct /signup Navigation**
```python
await navigate(lovable_page, f"{LOVABLE_URL}signup")
await lovable_page.wait_for_timeout(3000)

# Check for skeleton/white screen
text = await body_text(lovable_page)
if len(text.strip()) < 50 or "Create your account" not in text:
    # Redirect to / first, then back to /signup
    await navigate(lovable_page, LOVABLE_URL)
    await wait_for_lovable_ready(lovable_page)
    await navigate(lovable_page, f"{LOVABLE_URL}signup")
```

### 3. **Form Fill Before Turnstile**
```python
# Email
email_input = lovable_page.locator('input#auth-dialog-email, input[type="email"]').first
await email_input.wait_for(state="visible", timeout=10000)
await email_input.click()
await email_input.fill(email)

# Passwords (2 fields)
passwords = lovable_page.locator('input[type="password"]')
await human_type(passwords.nth(0), password)
await human_type(passwords.nth(1), password)
```

### 4. **Turnstile Then Submit**
```python
signup_result = await do_signup_turnstile_only(lovable_page, email, password)
# ^ Handles Turnstile + clicks "Create your account"
```

## Tempmailhub Mode (Non-Dispose)

Uses original login popup flow:
```
1. Navigate to lovable.dev/
2. Click "Log in" button
3. Fill email in popup
4. Click "Continue"
5. Check if signup or reset needed
6. do_signup() fills email + passwords + Turnstile
```

## Error Handling

### Email Input Not Found
```python
try:
    email_input = lovable_page.locator('input#auth-dialog-email, input[type="email"]').first
    await email_input.wait_for(state="visible", timeout=10000)
except Exception as e:
    await lovable_page.screenshot(path="/tmp/signup-email-fail.png")
    raise FlowError(f"Could not fill email on /signup: {e}")
```

### Password Fields Missing
```python
pwd_count = await passwords.count()
if pwd_count < 2:
    await lovable_page.screenshot(path="/tmp/signup-pwd-missing.png")
    raise FlowError(f"Expected 2 password fields, found {pwd_count}")
```

### Skeleton/White Screen
```python
# After navigate to /signup
text = await body_text(lovable_page)
if len(text.strip()) < 50 or "Create your account" not in text:
    # Redirect to / first (forces hydration), then back
    await navigate(lovable_page, LOVABLE_URL)
    await wait_for_lovable_ready(lovable_page)
    await navigate(lovable_page, f"{LOVABLE_URL}signup")
```

## Test Commands

### Dispose mode (temp.tf or 22.do)
```bash
DISPLAY=:0 python3 -u /home/alae/Documents/repos/automation-toolkit/finals/core/lov-api.py --dispose
```

### Tempmailhub mode (API only)
```bash
DISPLAY=:0 python3 -u /home/alae/Documents/repos/automation-toolkit/finals/core/lov-api.py
```

## Expected Output (Dispose Mode)

```
📝 Dispose mode: Direct /signup flow...
  🌐 Navigating to lovable.dev/signup...
  ✅ On signup page
  📧 Filling email: xyz@gmail.com
    ✅ Email filled
  🔐 Filling passwords...
    Found 2 password fields
    ✅ Password 1 filled
    ✅ Password 2 filled
  🤖 Handling Turnstile + submit...
🤖 Waiting for Turnstile challenge...
🤖 Turnstile detected (attempt 1/15)
🎯 Strategy 1: Direct frame click...
  ✅ Clicked via frame_locator(input[type="checkbox"])
⏳ Waiting 7s for token generation...
📊 Token: 342 chars | Button enabled: True | Clicked: True
✅ Turnstile SOLVED — token valid + button enabled
  📧 Email verification required, waiting for link...
📥 Waiting for Lovable link on temp.tf...
  🎯 Link: https://lovable.dev/reset-password?token=...
✅ Lovable: Email verification required...
```

## Debug Screenshots

- `/tmp/signup-email-fail.png` - Email input not found
- `/tmp/signup-pwd-missing.png` - Password fields missing
- `/tmp/turnstile-failed-*.png` - Turnstile verification failed
- `/tmp/lovable_signup_debug.png` - General signup failure

## Selector Reference (Complete)

From `docs/SELECTORS_COMPLETE.json` + git history:

| Element | Selector | Notes |
|---------|----------|-------|
| Email input | `input#auth-dialog-email` | Primary |
| Email fallback | `input[type="email"]` | If ID not present |
| Password 1 | `input[type="password"]:nth(0)` | First field |
| Password 2 | `input[type="password"]:nth(1)` | Confirm field |
| Create button | `button[role="button"]:has-text("Create your account")` | Submit |
| Turnstile iframe | `iframe[src*="challenges.cloudflare.com"]` | Wait 10s |
| Checkbox (in iframe) | `input[type="checkbox"]` | Strategy 1 |
| Checkbox role | `[role="checkbox"]` | Strategy 1 fallback |
| Checkbox label | `label` | Strategy 1 fallback |

## Why Direct /signup?

**Before** (login popup):
- Navigate to /
- Click "Log in" (15min retry loop)
- Fill email in popup
- Popup flaky (disappears, disabled buttons)

**After** (direct /signup):
- Navigate directly to /signup
- Form already visible
- No popup flakiness
- Faster (no Log in button wait)

## Verification

After successful signup:
```python
# Check dashboard
dashboard_text = await body_text(lovable_page)
account_menu = lovable_page.locator('button[aria-label="Account menu"]')
await account_menu.wait_for(state="visible", timeout=20_000)

if "/dashboard" not in lovable_page.url or "Dashboard" not in dashboard_text:
    raise FlowError("Dashboard loaded but account not verified")
```

## Summary

Dispose mode now:
1. ✅ Goes direct to /signup (no login popup)
2. ✅ Fills email + passwords BEFORE Turnstile
3. ✅ Handles Turnstile with 3 strategies + stealth
4. ✅ Clicks "Create your account" after token valid
5. ✅ Proper error screenshots at each step
