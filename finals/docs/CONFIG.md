# Configuration Guide

Setup and configuration for Lovable.dev automation toolkit.

## 📋 Prerequisites

### System Requirements
- **OS:** Linux (tested on EndeavourOS)
- **Python:** 3.14+
- **Shell:** fish (or bash/zsh)
- **Memory:** 4GB+ recommended
- **Disk:** 2GB+ for browser profiles

### Required Software
```bash
# Python packages
pip install invisible-playwright asyncio

# WARP (optional, for IP rotation)
# Follow: https://developers.cloudflare.com/warp-client/

# rclone (for MEGA integration)
# Follow: https://rclone.org/install/
```

---

## 🔧 Setup Steps

### 1. Install Dependencies

```bash
# Install invisible-playwright
pip install invisible-playwright

# Verify installation
python3 -c "from invisible_playwright.async_api import InvisiblePlaywright; print('OK')"
```

### 2. Configure WARP (Optional)

**Install WARP:**
```bash
# Follow official guide for your distro
# https://developers.cloudflare.com/warp-client/get-started/linux/
```

**Start WARP:**
```bash
warp-cli connect
```

**Test WARP:**
```bash
curl https://cloudflare.com/cdn-cgi/trace | grep warp
# Should show: warp=on
```

**Configure WARP proxy:**
- Proxy listens on: `socks5://127.0.0.1:40000`
- This is hardcoded in `lovable-full-automation.py`

### 3. Setup MEGA with rclone

**Configure rclone:**
```bash
rclone config
```

**Settings:**
- Name: `lovable-invites`
- Type: `mega`
- User: Your MEGA email
- Pass: Your MEGA password

**Create remote directory:**
```bash
rclone mkdir lovable-invites:/
```

**Test:**
```bash
rclone ls lovable-invites:/
```

### 4. Prepare Real Browser Cookies

**Export cookies from your browser:**
1. Install "Get cookies.txt LOCALLY" extension
2. Visit lovable.dev while logged in
3. Export cookies to: `/home/alan/Downloads/cookies.txt`

**Verify format:**
```bash
head -5 /home/alan/Downloads/cookies.txt
# Should show Netscape cookie format
```

### 5. Create Session Directory

```bash
mkdir -p /home/alan/Documents/automation-toolkit/scripts/sessions
```

### 6. Generate First Session

```bash
cd /home/alan/Documents/automation-toolkit/finals/core
python3 lov-api.py --count 1 --start 1
```

**Verify:**
```bash
cat /home/alan/Documents/automation-toolkit/scripts/sessions/session-1/config.json
```

---

## 📁 Directory Structure

```
/home/alan/Documents/automation-toolkit/
├── finals/
│   ├── core/
│   │   ├── lovable-full-automation.py
│   │   └── lov-api.py
│   ├── utils/
│   │   ├── check_credits.py
│   │   ├── get_credits.py
│   │   └── get_credits_final.py
│   ├── debug/
│   │   ├── test-browser.py
│   │   ├── browser_use_selector_discovery.py
│   │   ├── inspect_dashboard.py
│   │   └── inspect_credits_deep.py
│   └── docs/
│       ├── CORE.md
│       ├── UTILS.md
│       ├── DEBUG.md
│       └── CONFIG.md
└── scripts/
    └── sessions/
        ├── session-1/
        │   └── config.json
        ├── session-2/
        │   └── config.json
        └── ...
```

---

## ⚙️ Configuration Files

### Session Config (`config.json`)

```json
{
  "email": "example@gmail.com",
  "password": "example@gmail.com",
  "created_at": "2026-08-14T20:17:00.774395",
  "dashboard_url": "https://lovable.dev/dashboard",
  "verified": true,
  "api_only": true
}
```

**Fields:**
- `email` - Account email (auto-generated)
- `password` - Same as email for simplicity
- `created_at` - ISO timestamp
- `dashboard_url` - Always https://lovable.dev/dashboard
- `verified` - Email verification status
- `api_only` - True if created via API (no browser profile yet)

### MEGA Invites (`invites.json`)

```json
{
  "invites": [
    {
      "url": "https://lovable.dev/projects/invite/xyz123",
      "project_id": "abc-def-ghi",
      "email": "user@example.com",
      "created_at": "2026-08-14T22:30:00",
      "uses": 0,
      "max_uses": 1
    }
  ]
}
```

**Fields:**
- `url` - Full invite link
- `project_id` - Lovable project ID
- `email` - Creator email
- `created_at` - Timestamp
- `uses` - Current usage count
- `max_uses` - Maximum allowed uses

---

## 🔑 Environment Variables

### Optional Variables

```bash
# Disable WARP proxy
export USE_WARP=false

# Custom cookie path
export COOKIE_FILE="/path/to/cookies.txt"

# Custom session directory
export SESSIONS_DIR="/path/to/sessions"

# MEGA remote name
export MEGA_REMOTE="lovable-invites"
```

**Set in `.bashrc` or `.config/fish/config.fish`:**
```fish
# In fish
set -gx USE_WARP true
set -gx COOKIE_FILE ~/Downloads/cookies.txt
```

---

## 🚨 Troubleshooting Setup

### Problem: invisible-playwright not found

```bash
# Reinstall
pip uninstall invisible-playwright
pip install invisible-playwright

# Verify Python version
python3 --version  # Should be 3.14+
```

### Problem: WARP not working

```bash
# Check WARP status
warp-cli status

# Reconnect
warp-cli disconnect
warp-cli connect

# Test proxy
curl -x socks5://127.0.0.1:40000 https://cloudflare.com/cdn-cgi/trace
```

### Problem: rclone MEGA auth fails

```bash
# Reconfigure
rclone config delete lovable-invites
rclone config

# Test connection
rclone lsd lovable-invites:/
```

### Problem: Cookie file not found

```bash
# Check path
ls -lh /home/alan/Downloads/cookies.txt

# If missing, export from browser
# Use "Get cookies.txt LOCALLY" extension
```

### Problem: Session creation fails

```bash
# Check API access
curl -I https://api.lovable.dev

# Verify session directory exists
mkdir -p /home/alan/Documents/automation-toolkit/scripts/sessions

# Check permissions
ls -ld /home/alan/Documents/automation-toolkit/scripts/sessions
```

---

## 🔐 Security Considerations

### Cookie Security
- Cookies contain authentication tokens
- Keep `/home/alan/Downloads/cookies.txt` private
- Don't commit to git
- Regenerate if exposed

### Session Security
- Session configs contain credentials
- Store in secure directory (not public)
- Use encryption for sensitive deployments

### MEGA Security
- MEGA account should be dedicated to this project
- Use strong password
- Enable 2FA (may need to disable for rclone)

### WARP Privacy
- WARP hides your real IP
- Lovable sees WARP exit node IP
- Reduces bot detection via IP patterns

---

## 📊 Monitoring

### Check Session Health

```bash
# Count total sessions
ls /home/alan/Documents/automation-toolkit/scripts/sessions/ | wc -l

# Check credits for all
for i in {1..10}; do
  python3 utils/check_credits.py --session $i
done
```

### Check MEGA Invites

```bash
# View all invites
rclone cat lovable-invites:/invites.json | jq

# Count invites
rclone cat lovable-invites:/invites.json | jq '.invites | length'

# Filter unused invites
rclone cat lovable-invites:/invites.json | jq '.invites[] | select(.uses == 0)'
```

### Monitor Logs

```bash
# Run with logging
cd core
python3 lovable-full-automation.py --session 9 2>&1 | tee -a ~/automation.log

# Tail live logs
tail -f ~/automation.log
```

---

## 🎯 Production Deployment

### Systemd Service (Optional)

**Create service file:**
```bash
sudo nano /etc/systemd/system/lovable-automation.service
```

**Service content:**
```ini
[Unit]
Description=Lovable Automation
After=network.target

[Service]
Type=simple
User=alan
WorkingDirectory=/home/alan/Documents/automation-toolkit/finals/core
ExecStart=/usr/bin/python3 lovable-full-automation.py --session 1
Restart=on-failure
RestartSec=300

[Install]
WantedBy=multi-user.target
```

**Enable and start:**
```bash
sudo systemctl enable lovable-automation
sudo systemctl start lovable-automation
sudo systemctl status lovable-automation
```

### Cron Job (Alternative)

```bash
crontab -e
```

**Add line:**
```cron
# Run every hour
0 * * * * cd /home/alan/Documents/automation-toolkit/finals/core && python3 lovable-full-automation.py --session 1 >> /tmp/lovable-cron.log 2>&1
```

---

## 🔄 Update Procedures

### Update Scripts

```bash
# Pull latest from git (if using version control)
cd /home/alan/Documents/automation-toolkit
git pull

# Or manually update files
```

### Update Dependencies

```bash
# Update invisible-playwright
pip install --upgrade invisible-playwright

# Update rclone
# Follow official update guide
```

### Rotate Sessions

```bash
# Generate new batch
cd core
python3 lov-api.py --count 10 --start 11

# Archive old sessions
mkdir -p ~/session-archives
mv scripts/sessions/session-{1..10} ~/session-archives/
```

---

## 📞 Support Resources

- **Lovable API Docs:** https://lovable.dev/docs
- **WARP Docs:** https://developers.cloudflare.com/warp-client/
- **rclone Docs:** https://rclone.org/docs/
- **invisible-playwright:** https://github.com/kaliiiiiiiiii/undetected-playwright

---

## ✅ Setup Verification Checklist

- [ ] Python 3.14+ installed
- [ ] invisible-playwright installed
- [ ] WARP configured and running
- [ ] rclone configured with MEGA
- [ ] Cookie file exists at `/home/alan/Downloads/cookies.txt`
- [ ] Session directory created
- [ ] At least one session generated via `lov-api.py`
- [ ] Credits check successful for session-1
- [ ] Full automation test run successful
- [ ] MEGA invites accessible via rclone

**Test command:**
```bash
cd /home/alan/Documents/automation-toolkit/finals/core
python3 lovable-full-automation.py --session 1
```

If successful, setup is complete! ✅
