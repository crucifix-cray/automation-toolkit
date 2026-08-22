# 22.do Email Provider — Diagnostic & Pool Tool

**File:** `test_22do.py` — headless/Xvfb diagnostic for 22.do temporary email generators.

---

## Overview

22.do offers multiple disposable email generators under different domains. This tool:
- Diagnoses each generator's flow (selectors, API, CF behavior)
- Provides a unified pool for Railway/Lovable automation to `random.choice` per run
- Supports **recovery** of existing inboxes via `https://22.do/inbox/#/<mail>`

---

## Handlers (11 total)

| # | Domain | Generator URL | Notes |
|---|---|---|---|
| 1 | `@linshiyou.com` | `https://22.do/` | Main page, dropdown select |
| 2 | `@colabeta.com` | `https://22.do/` | Main page, dropdown select |
| 3 | `@youxiang.dev` | `https://22.do/` | Main page, dropdown select |
| 4 | `@colaname.com` | `https://22.do/` | Main page, dropdown select |
| 5 | `@usdtbeta.com` | `https://22.do/` | Main page, dropdown select |
| 6 | `@tnbeta.com` | `https://22.do/` | Main page, dropdown select |
| 7 | `@fft.edu.do` | `https://22.do/` | Main page, dropdown select |
| 8 | `@gmail.com` | `https://22.do/fake-gmail-generator` | Fake Gmail generator |
| 9 | `@googlemail.com` | `https://22.do/fake-gmail-generator` | Fake Googlemail generator |
| 10 | `@hotmail.com` | `https://22.do/temporary-hotmail` | Temporary Hotmail |
| 11 | `@outlook.com` | `https://22.do/temporary-outlook` | Temporary Outlook |

**Key distinction:** #8 vs #9 are **different** addresses from the same fake-gmail page — tool enforces which one you want (retries Random until match).

---

## Usage

```bash
# Generate new (Xvfb recommended — CF blocks headless on 8-11)
xvfb-run -a --server-args="-screen 0 1280x720x24" python3 -u test_22do.py 8   # @gmail
xvfb-run -a --server-args="-screen 0 1280x720x24" python3 -u test_22do.py      # interactive menu 1-11/r/c

# Recover existing inbox (poll every 5s)
xvfb-run -a --server-args="-screen 0 1280x720x24" python3 -u test_22do.py --recov "g92w@colabeta.com"
# Opens https://22.do/inbox/#/g92w@colabeta.com → polls #email-list-wrap .tr every 5s

# Headless=new (works for 1-7 only; 8-11 CF blocked)
python3 -u test_22do.py --headless 1
```

**Commands:**
- `xvfb-run -a --server-args="-screen 0 1280x720x24" python3 -u test_22do.py [1-11]`
- `python3 -u test_22do.py --recov "g92w@colabeta.com"` (via Xvfb)
- `python3 -u test_22do.py --headless 3` (headless=new, 1-7 only)

---

## Flow (Diagnosed)

### Generation (main page 1-7)
1. `GET https://22.do/` → load `#mail-random`, `#mail-input`, `#mail-choices` (Choices.js), `#into-mailbox`
2. Click `#mail-random` → generates local part in `#mail-input`
2b. Optional: click `.choices__inner` → select domain `.choices__item--choice >> text=@youxiang.dev`
3. Click `#into-mailbox` → `POST /action/mailbox/login {email, language}` → 302 to `https://22.do/inbox/#/<full-email>`

### Generation (fake-gmail 8-9 / hotmail 10 / outlook 11)
- Same flow but generator page has no dropdown — domain fixed per page.
- **WAF blocks headless** on these pages → must use Xvfb.

### Inbox (all)
- URL: `https://22.do/inbox/#/<full-email>`
- Messages in `#email-list-wrap .tr` (each has `.item.subject`, `.item.from`, `.item.time`)
- Poll every 5s: `#email-list-wrap .tr` count + `.item.subject/.from/.time` text

### Recovery
- Direct: `https://22.do/inbox/#/<mail>` → same inbox UI, no re-generation needed.

---

## Selectors

```python
# generator
page.locator("#mail-random")              # click → new local part
page.locator("#mail-input")               # value = local part
page.locator(".choices__inner")           # click open domain dropdown
page.locator(".choices__item--choice >> text=@domain")  # select domain
page.locator("#into-mailbox")             # click → POST /action/mailbox/login

# inbox
page.locator("#email-list-wrap .tr")              # each message row
page.locator("#email-list-wrap .tr .item.subject")  # subject text
page.locator("#email-list-wrap .tr .item.from")     # from text
page.locator("#email-list-wrap .tr .item.time")     # time text
```

---

## Anti-Flag / Railway Integration

### Why it fits Railway automation
- **Per-run heterogeneity:** `random.choice(HANDLERS)` → each Railway account gets different `@domain` (diverse MX, different WAF scores).
- **Recovery without re-gen:** `--recov` reuses existing inbox → Railway OTP arrives to same mailbox without new address.
- **Gmail/Googlemail split:** 22.do fake-gmail produces both `@gmail.com` and `@googlemail.com` — tool enforces which (Railway may treat differently).
- **Diverse MX:** linshiyou/colabeta/youxiang/colaname/usdtbeta/tnbeta/fft.edu.do → different mail infra per run.

### Pool integration for Railway
```python
# In railway-HOLY.py / railway-mailtm-full.py
from test_22do import HANDLERS, run_recov
import random

handler = random.choice(HANDLERS)
# handler = (name, url, domain)
# navigate handler[1], click Random, click Open → inbox
# or recover: run_recov("existing@colabeta.com")
```

### Per-run chain diversity (as discussed)
- Chain per run: `proton ovpn → warp → browser` (already have proton pool + warp 40000)
- Handler diversity: each run picks different `@domain` from HANDLERS
- Recovery: same mailbox for OTP retries (no new address = lower flag)

---

## CF / Headless Notes

| Handler | headless=new | Xvfb (headless:false) |
|---|---|---|
| 1-7 (main dropdown) | ⚠️ partially blocked | ✅ works |
| 8-9 (fake-gmail) | ⛔ CF blocked | ✅ works |
| 10 (hotmail) | ⛔ CF blocked | ✅ works |
| 11 (outlook) | ⛔ CF blocked | ✅ works |

**Recommendation:** Always use `xvfb-run -a --server-args="-screen 0 1280x720x24"` for Railway automation — works for all 11 handlers.

---

## Files

- `test_22do.py` — main tool
- `/tmp/22do_inbox.png` / `/tmp/22do_recov.png` / `/tmp/22do_cf.png` — screenshots on key steps
- Inbox HTML: `#email-list-wrap .tr` + `.item.subject/.from/.time`

---

## Next Steps for Railway

1. **Integrate pool** into `railway-HOLY.py` — replace `DisposeLolInbox` with `random.choice(HANDLERS)` + recovery logic.
2. **Add `--recov` to Railway flow** — if account creation fails at OTP, retry same inbox without new address.
3. **Track per-handler success rate** — some domains may have higher Railway delivery / lower WAF score.
4. **Chain + handler combo per run** — proton ovpn country + `@domain` = unique fingerprint per Railway account.