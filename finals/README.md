# Lovable.dev Automation Toolkit

Complete automation suite for Lovable.dev account management and project creation.

## 📁 Structure

```
finals/
├── core/           # Main automation scripts
├── utils/          # Utility scripts
├── debug/          # Debug and testing tools
└── docs/           # Documentation
```

## 🚀 Quick Start

### 1. Generate Sessions (Accounts)
```bash
cd core/
python3 lov-api.py --count 5
```

### 2. Run Full Automation
```bash
cd core/
python3 lovable-full-automation.py --session 9
```

### 3. Check Credits
```bash
cd utils/
python3 check_credits.py --session 9
```

## 📚 Documentation

- [Core Scripts](docs/CORE.md) - Main automation workflows
- [Utils](docs/UTILS.md) - Helper and utility scripts
- [Debug Tools](docs/DEBUG.md) - Testing and debugging
- [Configuration](docs/CONFIG.md) - Setup and configuration

## ⚙️ Requirements

- Python 3.14+
- invisible-playwright
- WARP proxy (optional, for IP rotation)
- rclone with MEGA config (for invite storage)

## 🔑 Key Features

- ✅ Account generation via API
- ✅ Credit-based flow routing (High ≥2, Low <2)
- ✅ Template remixing with anti-detection
- ✅ Subprocess injection and testing
- ✅ Automated invite generation
- ✅ MEGA integration for invite storage
- ✅ WARP IP rotation support

## 📝 Flows

### High Credit Flow (≥2 credits)
1. Pick random template
2. Remix template
3. Send subprocess prompt
4. Wait for AI to build
5. Test subprocess in preview
6. Generate invite link
7. Save to MEGA

### Low Credit Flow (<2 credits)
1. Download invite from MEGA
2. Accept invite
3. Test existing project

## 🛠️ Sessions

Sessions are stored in: `/home/alan/Documents/automation-toolkit/scripts/sessions/session-{N}/`

Each session contains:
- `config.json` - Account credentials and metadata
- Browser profile data (cookies, storage)

## 📊 Logs

Logs are written to stdout. Redirect to file if needed:
```bash
python3 lovable-full-automation.py --session 9 2>&1 | tee run.log
```

## ⚠️ Important Notes

- NO scrolling during template selection (uses first 10 visible templates)
- NO human behavior mimicking on critical actions (direct clicks)
- Invisible-playwright for anti-bot detection
- Button state checking (wait for enabled before clicking)
- Viewport positioning for dialog interactions

## 🔗 Related

- Session directory: `/home/alan/Documents/automation-toolkit/scripts/sessions/`
- Real cookies: `/home/alan/Downloads/cookies.txt`
- MEGA remote: `lovable-invites:/invites.json`
