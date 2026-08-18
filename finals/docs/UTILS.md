# Utility Scripts

Helper scripts for checking credits and session management.

## 📄 Scripts

### `check_credits.py`

**Check account credit balance** - Quick credit checker with browser automation

#### Usage
```bash
python3 check_credits.py --session <N>
```

#### Arguments
- `--session <N>` - Session number to check (required)

#### What It Does
1. Loads session
2. Navigates to dashboard
3. Extracts credit count from UI
4. Prints result

#### Output
```
Session 9: 3.4 credits
```

#### Features
- ✅ Fast (< 10 seconds)
- ✅ Uses real browser cookies
- ✅ Headless mode

---

### `get_credits.py`

**Alternative credit checker** - Older version with different selector strategy

#### Usage
```bash
python3 get_credits.py --session <N>
```

Similar to `check_credits.py` but uses different DOM selectors.

---

### `get_credits_final.py`

**Final credit checker** - Most reliable version

#### Usage
```bash
python3 get_credits_final.py --session <N>
```

#### Differences from `check_credits.py`
- More robust error handling
- Additional wait logic
- Better selector fallbacks

---

## 🔄 Typical Usage

**Check single session:**
```bash
python3 check_credits.py --session 9
```

**Check multiple sessions:**
```bash
for i in {1..10}; do
  echo "Session $i:"
  python3 check_credits.py --session $i
done
```

**Check and route automation:**
```bash
credits=$(python3 check_credits.py --session 9 | grep -oP '\d+\.\d+')
if (( $(echo "$credits >= 2" | bc -l) )); then
  echo "High credit flow"
  cd ../core
  python3 lovable-full-automation.py --session 9
else
  echo "Low credit flow - skipping"
fi
```

---

## 📊 Credit Thresholds

- **≥2 credits** → High credit flow (can remix template)
- **<2 credits** → Low credit flow (use existing invite)

---

## 🐛 Troubleshooting

**"Element not found"**
- Session may not be logged in
- Solution: Check session config, re-run `lov-api.py`

**"Timeout waiting for dashboard"**
- Slow network or page load
- Solution: Increase timeout, check internet connection

**"0 credits" shown but account has credits**
- Selector mismatch
- Solution: Try different credit checker (`get_credits_final.py`)

---

## 🔧 Selector Details

### `check_credits.py`
```python
# Multiple strategies attempted in order:
1. 'div[data-testid="credits-display"]'
2. 'span:has-text("credits")'
3. DOM traversal from known elements
```

### Best Practices
- Always use `check_credits.py` first (most up-to-date)
- If it fails, try `get_credits_final.py`
- Last resort: Manual inspection via test-browser.py

---

## 📝 Output Format

All credit checkers output in format:
```
Session <N>: <X.X> credits
```

This allows easy parsing in shell scripts:
```bash
credits=$(python3 check_credits.py --session 9 | grep -oP '\d+\.\d+')
```

---

## ⚡ Performance

| Script | Speed | Reliability |
|--------|-------|-------------|
| check_credits.py | ~8s | High |
| get_credits.py | ~10s | Medium |
| get_credits_final.py | ~12s | Highest |

---

## 🎯 Integration

These utilities integrate with:
- **lovable-full-automation.py** - Credits checked at start to route flow
- **Session management** - Monitor when accounts need refill
- **Batch processing** - Filter sessions by credit balance

Example integration:
```python
# In lovable-full-automation.py
credits = await get_credits(page)
if credits >= 2:
    await high_credit_flow(page, email, session_num)
else:
    await low_credit_flow(page, invite_link, session_num)
```
