# Source Scripts - Active Automation Toolkit

This directory contains all **active, working scripts** organized by function.

---

## 📁 Directory Structure

```
src/
├── lovable/         # Lovable.dev automation
├── railway/         # Railway.com automation  
├── farming/         # Account farming (ZenRows, OnKernel)
├── onkernel/        # OnKernel-specific operations
└── utils/           # Shared utilities and helpers
```

---

## 🎯 lovable/ - Lovable.dev Automation

Scripts for automating Lovable.dev account management, project creation, and session handling.

| Script | Original Name | Purpose | Status |
|--------|---------------|---------|--------|
| `account_creation.py` | lov-api-effective.py | **PRIMARY** account creator via ZenRows GB + dispose.lol | ✅ Production |
| `full_automation.py` | lovable-full-automation.py | Complete flow: credits check → template/invite → build → test → MEGA | ✅ Production |
| `remix_inject.py` | lov-remix-inject.py | Remix template + inject window.doc bridge + generate invite | ✅ Production |
| `remix_inject_local.py` | lov-remix-inject-local.py | Same as above but uses local Camoufox (max stealth) | ✅ Production |
| `session_revival.py` | revive_sessions_login.py | Revive dead sessions by logging in with email+pwd | ✅ Production |
| `session_refresh.py` | lov-session-refresh-totp.py | Refresh 2FA-enabled sessions (email+pwd+TOTP) | ✅ Production |
| `enable_2fa.py` | lov-2fa-enable.py | Enable Lovable 2FA authenticator on live session | ✅ Production |
| `invite_automation.py` | lovable-invite-automation.py | Invite-focused automation for low-credit flow | ✅ Production |

### Usage Examples

**Create new Lovable account:**
```bash
cd src/lovable/
python3 account_creation.py --count 5
```

**Revive dead sessions:**
```bash
cd src/lovable/
python3 session_revival.py --pth all --par 3
```

**Full automation (high credit flow):**
```bash
cd src/lovable/
python3 full_automation.py --session 9
```

**Remix + inject across all sessions:**
```bash
cd src/lovable/
python3 remix_inject.py --all
```

---

## 🚂 railway/ - Railway.com Automation

Scripts for Railway.com account creation, deployment, and health verification.

| Script | Original Name | Purpose | Status |
|--------|---------------|---------|--------|
| `account_creation.py` | railway-HOLY-zenrows.py | **THE HOLY SCRIPT** - Complete Railway automation (1700 lines) | ✅ Production |
| `verify_health.py` | railway_verify.py | Health check: whoami → list → init (create) → delete | ✅ Production |
| `api_client.py` | railway-API-WORKING.py | Railway API client (API-focused operations) | ✅ Production |

### Usage Examples

**Create Railway account:**
```bash
cd src/railway/
python3 account_creation.py
```

**Verify all sessions health:**
```bash
cd src/railway/
python3 verify_health.py --pth all
```

---

## 🌾 farming/ - Account Farming

Scripts for mass account creation via browser cloud services (ZenRows, OnKernel).

| Script | Original Name | Purpose | Status |
|--------|---------------|---------|--------|
| `farm_single.py` | farm_one.py | Farm single account → JSON append (for parallel runs) | ✅ Production |
| `farm_zenrows_batch.py` | farm_zenrows_10.py | Farm 10 ZenRows accounts via OnKernel | ✅ Production |
| `farm_zenrows_loop.py` | farm_zenrows_loop.py | Continuous farming with 5-7min random gaps | ✅ Production |
| `zenrows_kernel.py` | zenrows-kernel-final.py | ZenRows account creation via Kernel Browser Cloud | ✅ Production |
| `zenrows_kernel_parallel.py` | zenrows-kernel-parallel.py | ZenRows parallel (5 tabs, fresh IPs) | ✅ Production |

### Usage Examples

**Farm 10 ZenRows accounts:**
```bash
cd src/farming/
python3 farm_zenrows_batch.py
```

**Continuous farming loop:**
```bash
cd src/farming/
python3 farm_zenrows_loop.py
```

---

## ⚙️ onkernel/ - OnKernel Operations

OnKernel-specific account management and organization operations.

| Script | Original Name | Purpose | Status |
|--------|---------------|---------|--------|
| `account_creation.py` | onk-api.py | OnKernel account creator (headed local Chromium + dispose.lol) | ✅ Production |
| `org_reset.py` | onk-org-reset.py | OnKernel org reset: kill org → new org → fresh API key | ✅ Production |

### Usage Examples

**Create OnKernel account:**
```bash
cd src/onkernel/
python3 account_creation.py
```

**Reset organization:**
```bash
cd src/onkernel/
python3 org_reset.py
```

---

## 🛠️ utils/ - Utilities

Shared helper scripts and utilities used across other modules.

| Script | Original Name | Purpose | Status |
|--------|---------------|---------|--------|
| `mail_providers.py` | mail_providers.py | Multi mail providers (22.do, temp.tf, tempmailhub, dispose) | ✅ Library |
| `session_loader.py` | load_session.py | Load saved session and open browser | ✅ Utility |
| `check_dashboard.py` | check_sessions_dashboard.py | Dashboard checking utility | ✅ Utility |
| `build_cells.py` | build_cells.py | Build cells.json configuration | ✅ Utility |
| `build_services.py` | build_services.py | Build services.json configuration | ✅ Utility |
| `zenrows_balance.py` | zenrows_balance.py | Check ZenRows API balance | ✅ Utility |

### Usage Examples

**Load session in browser:**
```bash
cd src/utils/
python3 session_loader.py 1  # Load session-1
```

**Check ZenRows balance:**
```bash
cd src/utils/
python3 zenrows_balance.py
```

**Build cells config:**
```bash
cd src/utils/
python3 build_cells.py
```

---

## 🔄 Migration Notes

All scripts have been **copied** (not moved) from their original locations to maintain compatibility with existing workflows. Original files remain in:
- `finals/core/` - Original Lovable/farming scripts
- `scripts/` - Original Railway/utility scripts
- `railway-docker/` - Original Railway HOLY script

**Future Actions**:
1. Update import paths in scripts to use new locations
2. Test all scripts in new locations
3. Update documentation and runbooks
4. Eventually deprecate old locations

---

## 📊 Statistics

- **Total Active Scripts**: 24
- **Lovable Scripts**: 8
- **Railway Scripts**: 3
- **Farming Scripts**: 5
- **OnKernel Scripts**: 2
- **Utility Scripts**: 6

---

## 🚀 Quick Start

1. **Install dependencies** (see main repo requirements.txt)
2. **Set environment variables** (KERNEL_API_KEY, etc.)
3. **Navigate to appropriate directory**
4. **Run desired script with python3**

---

## 📝 Related Documentation

- `../SCRIPT_INVENTORY.md` - Complete script inventory with all versions
- `../archive/` - Deprecated and old script versions
- `../tests/` - Testing scripts
- `../CONSOLIDATION_REPORT.md` - Data consolidation report
- `../DATA_SOURCES.md` - Data sources documentation

---

## ⚠️ Important Notes

- Scripts use **absolute paths** in many places - you may need to update paths
- Some scripts expect files in `finals/`, `scripts/`, or `sessions/` directories
- ZenRows scripts require API key: `ZENROWS_API_KEY` environment variable
- OnKernel scripts require: `KERNEL_API_KEY` environment variable
- Railway scripts require Railway CLI authenticated sessions
- Lovable scripts expect sessions in `/home/alae/Documents/repos/automation-toolkit/sessions/`

