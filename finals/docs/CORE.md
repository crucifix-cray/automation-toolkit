# Core Scripts

Main automation scripts for Lovable.dev workflows.

## 📄 Scripts

### `lovable-full-automation.py`

**Full end-to-end automation** - Account → Template → Remix → Subprocess → Test → Invite

#### Usage
```bash
python3 lovable-full-automation.py --session <N> [--headless] [--warp]
```

#### Arguments
- `--session <N>` - Session number to use (required)
- `--headless` - Run browser in headless mode (optional)
- `--warp` - Use WARP proxy for IP rotation (default: enabled)
- `--raw` - Disable WARP proxy

#### Flow Decision

**High Credit (≥2):**
1. Navigate to /templates
2. Select random template from first 10 visible
3. Click 3-dot menu → Remix
4. Fill remix dialog and submit
5. Wait for project creation (up to 2 minutes)
6. Send subprocess prompt in chat
7. Wait for AI to finish building (up to 5 minutes)
8. Navigate to preview URL (lovableproject.com)
9. Test subprocess via JS console (`doc.connect()`, `doc('ls')`)
10. Return to project and generate invite link
11. Upload invite to MEGA

**Low Credit (<2):**
1. Download invite from MEGA
2. Accept invite
3. Wait for project load
4. Test subprocess

#### Key Features
- ✅ Credit-based routing
- ✅ Invisible-playwright anti-detection
- ✅ WARP IP rotation
- ✅ Real browser cookies
- ✅ NO scrolling (first 10 templates only)
- ✅ Direct JS clicks (no human mimicking)
- ✅ Button state validation (wait for enabled)
- ✅ Viewport positioning for dialogs
- ✅ Subprocess testing in preview
- ✅ MEGA integration

#### Selectors Used
```python
# Templates page
cards = 'article[aria-label]'
menu_btn = 'button[data-button][aria-label*="More options"]'
menu_dropdown = 'div[role="menu"][data-open]'
remix_item = 'div[role="menuitem"]:has-text("Remix")'

# Remix dialog
dialog = 'div[role="dialog"]'
checkbox = 'input[type="checkbox"]'
submit_btn = 'button:has-text("Acknowledge and remix")'

# Chat interface
chat_input = 'div[contenteditable="true"][role="textbox"][aria-label="Ask Lovable..."]'
send_btn = 'button[data-testid="chat-input-send"]'
```

#### Exit Codes
- `0` - Success
- `1` - Error (see traceback)

#### Logs
All actions logged with timestamps. Key log markers:
- `🎯 HIGH CREDIT FLOW` / `🎯 LOW CREDIT FLOW`
- `✅` - Success
- `❌` - Error
- `⚠️` - Warning

---

### `lov-api.py`

**Session (account) generator** - Creates new Lovable.dev accounts via API

#### Usage
```bash
python3 lov-api.py --count <N> [--start <N>]
```

#### Arguments
- `--count <N>` - Number of accounts to create (required)
- `--start <N>` - Starting session number (default: 1)

#### What It Does
1. Generates random email (Gmail-like format)
2. Registers account via Lovable API
3. Verifies email (auto-confirm)
4. Saves session config to: `/home/alan/Documents/automation-toolkit/scripts/sessions/session-{N}/config.json`

#### Session Config Format
```json
{
  "email": "example@gmail.com",
  "password": "same_as_email",
  "created_at": "2026-08-14T20:17:00.774395",
  "dashboard_url": "https://lovable.dev/dashboard",
  "verified": true,
  "api_only": true
}
```

#### Features
- ✅ Random email generation
- ✅ Auto-verification
- ✅ Session persistence
- ✅ Batch creation support

#### Notes
- Password = Email (for simplicity)
- Sessions created are API-only (no browser profile yet)
- Browser profile is created on first `lovable-full-automation.py` run

---

## 🔄 Typical Workflow

1. **Generate sessions:**
   ```bash
   cd /home/alan/Documents/automation-toolkit/finals/core
   python3 lov-api.py --count 10
   ```

2. **Run automation on each session:**
   ```bash
   for i in {1..10}; do
     python3 lovable-full-automation.py --session $i
   done
   ```

3. **Check credits periodically:**
   ```bash
   cd ../utils
   python3 check_credits.py --session 5
   ```

---

## ⚠️ Important Implementation Details

### NO Scrolling
- Template selection uses **first 10 visible templates only**
- NO `human_scroll()`, NO `scroll_into_view_if_needed()`
- Random selection: `random.randint(0, min(count - 1, 9))`

### Direct Clicks
- 3-dot menu: `menu_btn.evaluate("el => el.click()")`
- Remix button: `remix_item.evaluate("el => el.click()")`
- NO mouse positioning, NO curved paths, NO human delays

### Button State Validation
```python
# Wait for button to become enabled
for i in range(20):
    is_disabled = await btn.get_attribute("disabled")
    if is_disabled is None:
        break
    await asyncio.sleep(0.5)
```

### Viewport Positioning
```python
# Bring button into viewport center
viewport_height = await page.evaluate("window.innerHeight")
scroll_y = box['y'] - (viewport_height / 2) + (box['height'] / 2)
await page.evaluate(f"window.scrollTo(0, {scroll_y})")
```

### Subprocess Testing
```javascript
// In preview page console
doc.connect()
doc('ls')
```

---

## 🐛 Common Issues

**Dialog doesn't appear after Remix click:**
- Session likely soft-blocked (bot detection)
- Solution: Use different session or wait 24h

**Button stays disabled:**
- Checkbox not checked properly
- Solution: Script now validates checkbox state

**Element detached from DOM:**
- Old issue - was caused by scrolling after dialog appeared
- Solution: NO scrolling after dialog appears

**Timeout waiting for project redirect:**
- Project creation can take 30-120 seconds
- Solution: Timeout increased to 2 minutes

**Subprocess test fails (`doc is not defined`):**
- Preview page may not have subprocess implemented yet
- Solution: Script continues anyway, user can test manually

---

## 📊 Success Metrics

Track these in your logs:
- Session creation success rate
- High vs Low credit flow distribution
- Dialog appearance rate (bot detection)
- Project creation time
- Subprocess test pass rate
- Invite generation success rate

---

## 🔐 Security Notes

- Real browser cookies loaded from: `/home/alan/Downloads/cookies.txt`
- WARP proxy hides real IP
- Invisible-playwright bypasses bot detection
- Sessions stored locally (not cloud)
- MEGA invites are public but obscured by random IDs

---

## 🎯 Next Steps

After successful run:
1. Check MEGA for new invite: `rclone cat lovable-invites:/invites.json`
2. Verify project URL is accessible
3. Test invite link manually
4. Monitor credits for next automation run
