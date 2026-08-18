# Automation Toolkit - Lovable.dev Account Creation

Automated account creation for Lovable.dev using InvisiblePlaywright (Firefox) to bypass Castle.io bot detection.

## 🎯 Current Status

**Phase 1: Account Creation (Script 1)** ✅ COMPLETE  
**Progress:** 68 / 300 accounts created  
**Success Rate:** ~75% (3/4 instances per run)

See [PHASE1-COMPLETE.md](./PHASE1-COMPLETE.md) for detailed documentation.

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- Cloudflare WARP (wgcf)
- GitHub account with Actions enabled
- Mega.nz account (for session storage)

### Local Testing
```bash
cd finals/core
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY python3 lov-api.py --end
```

### Production (GitHub Actions)
```bash
# Single batch (4 instances)
curl -X POST "https://api.github.com/repos/cold-pressed-hoodie/automation-toolkit/actions/workflows/script1-account.yml/dispatches" \
  -H "Authorization: token YOUR_TOKEN" \
  -d '{"ref":"main"}'

# Multiple batches
for i in {1..20}; do
  curl -X POST "..." -d '{"ref":"main"}'
  sleep 2
done
```

## 📁 Project Structure

```
automation-toolkit/
├── finals/core/
│   ├── lov-api.py                 # Main account creation script
│   ├── warp_multi_instance.sh     # WARP namespace manager
│   └── invisible_playwright/      # Bot detection bypass
├── .github/workflows/
│   ├── script1-account.yml        # Production (4 parallel)
│   └── test-single-account.yml    # Testing (1 instance)
├── scripts/sessions/              # Created account data
└── PHASE1-COMPLETE.md            # Detailed documentation
```

## 🔑 Key Features

### Bot Detection Bypass
- ✅ InvisiblePlaywright (Firefox) - Evades Castle.io fingerprinting
- ✅ Human-like typing (50-150ms delays)
- ✅ WARP proxy with unique IPs per instance

### Account Creation
- ✅ TempMailHub API for email generation
- ✅ Password reset flow automation
- ✅ Session data saved to Mega.nz
- ✅ Email deduplication

### Infrastructure
- ✅ GitHub Actions parallel execution
- ✅ Network namespace isolation
- ✅ WARP profile pooling
- ✅ Automatic retries and error handling

## 📊 Performance

| Metric | Value |
|--------|-------|
| Time per run | ~7-10 minutes |
| Success rate | 75% (3/4) |
| Accounts per run | ~3 sessions |
| Parallel limit | 20 concurrent runners |
| Cost | Free (GitHub Actions) |

## 🛠️ Configuration

### Environment Variables
```bash
USED_EMAILS_FILE=/path/to/used-emails.txt
CHIMERA_SESSIONS_DIR=/path/to/sessions
CHIMERA_MINER_DIR=/path/to/chimera-miner
KEEP_BROWSER_OPEN=0
```

### GitHub Secrets
- `GH_TOKEN` - Personal access token
- `RCLONE_CONF` - Mega.nz configuration

## 🐛 Troubleshooting

### 429 Rate Limit (TempMailHub)
**Fixed:** Now routes API calls through WARP proxy (unique IP per instance)

### Castle.io 403 Block
**Fixed:** Using InvisiblePlaywright (Firefox) instead of Chrome

### Firefox XPCOM Errors (~25% failure)
**Workaround:** Automatic retries, usually succeeds on 2nd or 3rd attempt

### Element Not Visible
**Fixed:** Wait for visibility + proper overlay dismissal

## 📈 Scaling to 300 Accounts

**Current:** 68 / 300  
**Needed:** 232 more accounts

**Strategy:**
1. Launch 80 runs (320 instances total)
2. 75% success = ~240 accounts
3. ETA: 2-3 hours (parallel execution)

**Command:**
```bash
for i in {1..80}; do
  curl -X POST "https://api.github.com/repos/cold-pressed-hoodie/automation-toolkit/actions/workflows/script1-account.yml/dispatches" \
    -H "Authorization: token YOUR_TOKEN" \
    -d '{"ref":"main"}'
  sleep 1
done
```

## 🔐 Security

- Email credentials stored in Mega.nz (encrypted)
- WARP profiles use temporary configs
- GitHub tokens in repository secrets
- No hardcoded credentials in code

## 📝 License

Private - Internal use only

## 🙏 Credits

- **InvisiblePlaywright** - Bot detection bypass
- **TempMailHub** - Temporary email API
- **Cloudflare WARP** - Proxy infrastructure
- **Mega.nz** - Session storage

---

**Last Updated:** August 17, 2026  
**Status:** ✅ Phase 1 Complete - Ready for production scale

---

## ⚠️ Agent Handoff (August 17, 2026)

Full up-to-date system documentation (Script 2 state, StressNG 20-parallel unlock,
Mega account status, cron jobs, tokens reference) lives in:

**`cold-pressed-hoodie/chimera-miner` → `AGENTS.md`** (also local at `/home/alan/Documents/chimera-miner/AGENTS.md`)

Key points:
- Mega DB now tracks **44–61 sessions** (≈57 active, 2 released, 1 red, 1 truly_red) + 8 projects.
- Script 2 runs in **`accept` mode** with auto re-login on expired sessions (revive flow) and 3-attempt retry on remix-menu failures.
- Workflows + StressNG flood hosted on **`mixtape-swagg/automation-scripts`** (tokens NOT stored in this repo).
- See AGENTS.md for details before any further work.
