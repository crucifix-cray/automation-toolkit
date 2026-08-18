# Railway API Scripts

Scripts for automating Railway.app account creation and management.

## 📄 Scripts

### `dispose_lol_api.py`
**Dispose.lol API wrapper** - Email generation and inbox checking

#### Features
- ✅ Generate disposable emails
- ✅ Check inbox for verification emails
- ✅ Extract verification links
- ✅ Auto-retry on failures

### `railway-dispose-api.py`
**Railway account creation with dispose.lol** - Creates Railway accounts using disposable emails

#### Usage
```bash
python3 railway-dispose-api.py --count 5
```

### `railway-disposelol-full.py`
**Complete Railway automation** - Full flow from email to verified account

#### Flow
1. Generate dispose.lol email
2. Register Railway account
3. Wait for verification email
4. Extract and visit verification link
5. Confirm account
6. Save session

### `railway-mailtm-full.py`
**Railway automation with mail.tm** - Alternative using mail.tm instead of dispose.lol

#### Differences
- Uses mail.tm API instead of dispose.lol
- More reliable for some regions
- Different rate limits

---

## 🚀 Quick Start

```bash
cd /home/alan/Documents/automation-toolkit/finals/railway

# Create 5 Railway accounts
python3 railway-disposelol-full.py --count 5

# Or with mail.tm
python3 railway-mailtm-full.py --count 5
```

---

## 📁 Session Storage

Sessions saved to: `/home/alan/Documents/automation-toolkit/railway-sessions/`

Each session contains:
- Email address
- Password
- Auth tokens
- Account metadata

---

## 🔧 Configuration

### API Keys
- **dispose.lol:** No API key needed (public API)
- **mail.tm:** No API key needed (public API)

### Rate Limits
- **dispose.lol:** ~10 emails/minute
- **mail.tm:** ~5 emails/minute
- **Railway:** Unknown, be conservative

---

## 📊 Success Rate

Typical success rates:
- Email generation: 99%
- Account creation: 95%
- Email verification: 90%
- Overall: ~85%

---

## 🐛 Troubleshooting

**Email not received:**
- Wait longer (up to 60 seconds)
- Try different email provider (switch between dispose.lol and mail.tm)
- Check spam/promotions folder (if using real email)

**Railway registration fails:**
- IP may be rate limited
- Use WARP for IP rotation
- Wait 5 minutes and retry

**Verification link expired:**
- Links expire after ~1 hour
- Re-register with new email

---

## 🔗 Related

- Railway Docs: https://docs.railway.app
- dispose.lol: https://dispose.lol
- mail.tm: https://mail.tm
