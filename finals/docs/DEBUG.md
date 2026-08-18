# Debug & Testing Tools

Scripts for debugging, selector discovery, and manual testing.

## 📄 Scripts

### `test-browser.py`

**Manual browser testing** - Loads session with cookies and keeps browser open

#### Usage
```bash
python3 test-browser.py <session_number>
```

#### What It Does
1. Loads session config
2. Applies real browser cookies
3. Opens browser to Lovable dashboard
4. **Keeps browser open** for manual testing
5. Waits for user to press Enter before closing

#### Use Cases
- Manually test if session can remix templates
- Debug selector issues by inspecting live DOM
- Verify cookies are working correctly
- Test actions that automation struggles with

#### Example
```bash
python3 test-browser.py 9
# Browser opens, you can click around manually
# Press Enter in terminal when done
```

---

### `browser_use_selector_discovery.py`

**Automated selector discovery** - Uses browser-use AI to find correct selectors

#### Usage
```bash
python3 browser_use_selector_discovery.py
```

#### What It Does
1. Opens Lovable.dev templates page
2. Uses AI vision model to identify UI elements
3. Discovers correct CSS selectors
4. Outputs selector recommendations

#### Features
- ✅ AI-powered element identification
- ✅ Handles dynamic class names
- ✅ Finds stable selectors (data-testid, aria-label, etc.)
- ✅ No manual DOM inspection needed

#### Output Format
```json
{
  "template_card": "article[aria-label]",
  "menu_button": "button[data-button][aria-label*='More options']",
  "remix_item": "div[role='menuitem']:has-text('Remix')"
}
```

---

### `inspect_dashboard.py`

**Dashboard DOM inspector** - Analyzes dashboard structure

#### Usage
```bash
python3 inspect_dashboard.py --session <N>
```

#### What It Does
1. Loads dashboard
2. Extracts full DOM tree
3. Saves to file for analysis
4. Identifies credits display elements

#### Output
- `dashboard-dom.html` - Full page HTML
- `dashboard-structure.json` - Parsed DOM tree
- Console output with credit element candidates

---

### `inspect_credits_deep.py`

**Deep credit inspection** - Advanced credit display analysis

#### Usage
```bash
python3 inspect_credits_deep.py --session <N>
```

#### What It Does
1. Loads dashboard
2. Takes screenshot
3. Analyzes all text nodes containing "credit"
4. Tests multiple selector strategies
5. Outputs most reliable selector

#### Features
- ✅ Multiple detection strategies
- ✅ Visual verification (screenshot)
- ✅ Selector validation
- ✅ Fallback testing

#### Output
```
Testing strategy 1: data-testid
  ✅ Found: 3.4 credits

Testing strategy 2: text search
  ✅ Found: 3.4 credits

Testing strategy 3: DOM traversal
  ⚠️  Not found

Recommended selector: div[data-testid="credits-display"]
```

---

## 🔄 Typical Debug Workflow

### Problem: Automation fails at specific step

1. **Run test-browser.py:**
   ```bash
   python3 test-browser.py 9
   ```
   - Manually perform the failing action
   - Observe what happens
   - Note any error messages or unexpected behavior

2. **Inspect DOM:**
   ```bash
   python3 inspect_dashboard.py --session 9
   ```
   - Check `dashboard-dom.html` for actual structure
   - Compare with selectors in main script

3. **Use selector discovery:**
   ```bash
   python3 browser_use_selector_discovery.py
   ```
   - Let AI find updated selectors
   - Update main script with new selectors

4. **Verify fix:**
   - Run main automation again
   - Monitor for success

---

## 🐛 Common Debugging Scenarios

### Scenario 1: Template cards not found
```bash
# Open browser manually
python3 test-browser.py 9

# In browser: Go to /templates
# In DevTools: Find actual card selector
# Update SELECTORS in lovable-full-automation.py
```

### Scenario 2: Credit display changed
```bash
# Deep analysis
python3 inspect_credits_deep.py --session 9

# Review output for new selector
# Update get_credits() function
```

### Scenario 3: Remix dialog different
```bash
# Use AI discovery
python3 browser_use_selector_discovery.py

# Compare suggested selectors with current ones
# Update dialog handling code
```

---

## 📸 Screenshots

Debug scripts save screenshots to `/tmp/`:
- `/tmp/lovable-before-remix-click.png`
- `/tmp/lovable-after-remix-click.png`
- `/tmp/lovable-no-dialog.png`
- `/tmp/lovable-no-menu.png`
- `/tmp/lovable-no-button-in-dialog.png`

Check these when automation fails to see exact state at failure point.

---

## 🔧 Selector Testing

**Test a selector manually:**
```javascript
// In test-browser.py console (F12)
document.querySelector('article[aria-label]')
// Should return first template card

document.querySelectorAll('article[aria-label]').length
// Should return total template count
```

**Test selector in Python:**
```python
# In test-browser.py, add at end:
cards = page.locator('article[aria-label]')
count = await cards.count()
print(f"Found {count} cards")
```

---

## 📊 Performance Testing

**Measure action timing:**
```python
import time

start = time.time()
await page.goto("https://lovable.dev/templates")
print(f"Page load: {time.time() - start:.2f}s")

start = time.time()
await menu_btn.click()
print(f"Menu open: {time.time() - start:.2f}s")
```

---

## 🎯 Best Practices

1. **Always screenshot on error** - Helps diagnose without re-running
2. **Use test-browser.py first** - Fastest way to verify selectors
3. **Keep old selectors commented** - Easy rollback if new ones fail
4. **Version control DOM snapshots** - Track Lovable UI changes over time
5. **Test with multiple sessions** - Ensure selectors work universally

---

## ⚠️ Limitations

- **browser_use_selector_discovery.py** requires API key and internet
- **Manual testing** (test-browser.py) is not headless - requires display
- **DOM inspection** captures only moment in time - dynamic content may differ
- **Screenshots** are static - can't show timing issues

---

## 🔗 Related Tools

- **Chrome DevTools** - Press F12 in test-browser.py session
- **Playwright Inspector** - `PWDEBUG=1 python3 script.py`
- **Browser Console** - Run JS selectors directly
- **rclone** - Check MEGA for uploaded invites

---

## 💡 Tips

**Quick selector test:**
```bash
# Open test browser
python3 test-browser.py 9

# In Python console (if interactive):
>>> cards = page.locator('article[aria-label]')
>>> await cards.count()
194
```

**Find elements by text:**
```bash
# In DevTools console:
$x("//*[contains(text(), 'Remix')]")
```

**Verify WARP is working:**
```bash
# In test browser console:
fetch('https://cloudflare.com/cdn-cgi/trace')
  .then(r => r.text())
  .then(console.log)
```

**Check cookies loaded:**
```bash
# In test browser console:
document.cookie
```
