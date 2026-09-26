# Automation Toolkit - Script Inventory

> Generated: 2026-09-14
> Purpose: Map all scripts by function for cleanup project

---

## 📋 CATEGORY 1: Lovable Account Creation

### ✅ ACTIVE / WORKING

| Script | Location | Purpose | Status | Notes |
|--------|----------|---------|--------|-------|
| `lov-api-effective.py` | finals/core/ | **PRIMARY** - ZenRows GB + dispose.lol Gmail signup | ✅ WORKING | End-to-end verified flow |
| `lov-onkernel-effective.py` | finals/core/ | OnKernel stealth browser signup | ✅ WORKING | Alternative to ZenRows |
| `lov-zenrows-final.py` | finals/core/ | ZenRows Browser Cloud + dispose.lol | ✅ WORKING | Similar to effective |
| `onk-api.py` | finals/core/ | OnKernel account creator, local chromium | ✅ WORKING | Headed browser |

### ⚠️ DEPRECATED / OLD VERSIONS

| Script | Location | Status | Notes |
|--------|----------|--------|-------|
| `lov-api.py` | finals/core/ | 🔴 OLD | Superseded by lov-api-effective.py |
| `lov-api-zenrows.py` | finals/core/ | 🔴 OLD | Superseded by effective version |
| `lov-back.py` | finals/core/ | 🔴 OLD | Legacy backup |
| `lov-f1.py` | scripts/ | 🔴 OLD | TempMailHub approach, superseded |
| `lov-test.py` | scripts/ | 🔴 TEST | Testing script |
| `lov-parallel.py` | scripts/ | 🔴 OLD | Parallel version, unclear if used |
| `lov3F.py` | scripts/ | 🔴 OLD | Legacy version |
| `lov3F_api_only.py` | scripts/ | 🔴 OLD | Legacy API-only version |

### 🧪 EXPERIMENTAL / SPECIFIC USE

| Script | Location | Purpose | Notes |
|--------|----------|---------|-------|
| `lov-brightdata-final.py` | finals/core/ | BrightData proxy attempt | Unclear if working |
| `lov-brightdata.py` | finals/core/ | BrightData proxy attempt | Likely old version |
| `lov-seleniumbase-uc.py` | finals/core/ | SeleniumBase undetected | Different library |
| `lov-final-working.py` | finals/core/ | Generic "working" version | Unclear purpose |
| `lovable-sb-uc-working.py` | finals/core/ | SeleniumBase UC working | Duplicate? |
| `lov-zenrows-project.py` | finals/core/ | ZenRows project-specific | Unclear difference |
| `lov-zenrows-5x.py` | finals/core/ | ZenRows 5x parallel | Batch creation |

---

## 📋 CATEGORY 2: Remix from Template + Inject Prompt

### ✅ ACTIVE / WORKING

| Script | Location | Purpose | Status | Notes |
|--------|----------|---------|--------|-------|
| `lov-remix-inject.py` | finals/core/ | **PRIMARY** - Remix + inject window.doc bridge + invite | ✅ WORKING | OnKernel, 5 parallel |
| `lov-remix-inject-local.py` | finals/core/ | Same as above, LOCAL Camoufox | ✅ WORKING | Max stealth version |
| `lovable-full-automation.py` | finals/core/ | **COMPLETE FLOW** - Credits check → Template/Invite → Build → Test → MEGA | ✅ WORKING | High/Low credit routing |

### 📝 RELATED

| Script | Location | Purpose | Notes |
|--------|----------|---------|-------|
| `lovable-invite-automation.py` | finals/core/ | Invite-focused automation | Part of full-automation flow |
| `blast_lovable.py` | scripts/ | Blast script2 remixes across Railway cells | Uses chimera-miner script2 |

---

## 📋 CATEGORY 3: Cookie Management (Get/Load/Revive)

### ✅ ACTIVE / WORKING

| Script | Location | Purpose | Status | Notes |
|--------|----------|---------|--------|-------|
| `revive_sessions_login.py` | scripts/ | **PRIMARY REVIVAL** - Login with email+pwd, save fresh cookies | ✅ WORKING | Parallel workers, detailed errors |
| `load_session.py` | scripts/ | Load saved session and open browser | ✅ WORKING | Simple session loader |
| `lov-session-refresh-totp.py` | finals/core/ | Refresh 2FA session: email+pwd+TOTP → cookies | ✅ WORKING | For 2FA-enabled accounts |
| `lov-2fa-enable.py` | finals/core/ | Enable Lovable 2FA on session | ✅ WORKING | Setup authenticator |

### ⚠️ UNCLEAR / EXPERIMENTAL

| Script | Location | Purpose | Notes |
|--------|----------|---------|-------|
| `revive_with_kernel.py` | scripts/ | Revive via Kernel browser | Unclear if used vs revive_sessions_login |
| `load_and_inspect.py` | scripts/ | Load session 8 and inspect templates | Testing/debugging script |

---

## 📋 CATEGORY 4: Keep-Alive / Continuous Prompting

### ✅ FUNCTIONALITY INTEGRATED

**Note:** Keep-alive and preview page prompting is **built into** `lovable-full-automation.py`

- **Lines 1120-1190**: `keep_alive_loop()` function
- Opens preview page in new tab
- Randomly interacts with editor/preview tabs
- Tests window.doc commands
- Keeps project active

**No standalone script needed** - feature is part of main automation flow.

---

## 📋 CATEGORY 5: Railway Automation

### ✅ ACTIVE / WORKING

| Script | Location | Purpose | Status | Notes |
|--------|----------|---------|--------|-------|
| `railway-HOLY-zenrows.py` | railway-docker/ | **THE HOLY SCRIPT** - Complete Railway automation | ✅ WORKING | 1700 lines, handles PKCE OAuth, viral deployment |
| `railway_verify.py` | scripts/ | Health check: whoami → list → init → delete | ✅ WORKING | True health sweep per session |
| `railway-API-WORKING.py` | scripts/ | Railway API working version | ✅ WORKING | API-focused |

### ⚠️ DEPRECATED / OLD VERSIONS

| Script | Location | Status | Notes |
|--------|----------|--------|-------|
| `railway-login.py` | scripts/ | 🔴 OLD | Basic login, superseded |
| `railway-login-with-mega.py` | scripts/ | 🔴 OLD | Login + Mega integration |
| `railway-login-with-mega-API.py` | scripts/ | 🔴 OLD | API version |
| `railway-login-with-mega-FIXED.py` | scripts/ | 🔴 OLD | "Fixed" version |
| `railway-script.py` | scripts/ | 🔴 OLD | Generic script |
| `railway-script2.py` | scripts/ | 🔴 OLD | CleanTempMail version |
| `railway-mailtm.py` | scripts/ | 🔴 OLD | MailTM integration |
| `railway-mailtm-full.py` | scripts/ | 🔴 OLD | Full MailTM flow |
| `railway-turnstile-fast-poll.py` | scripts/ | 🔴 OLD | Turnstile handling experiment |

### 🧪 TESTING

| Script | Location | Purpose | Notes |
|--------|----------|---------|-------|
| `test-railway-flow.py` | scripts/ | Step-by-step debugging | Testing script |
| `railway_audit.py` | scripts/ | Railway audit tool | Unclear if active |

---

## 📋 CATEGORY 6: Farming & Parallel Operations

### ✅ ACTIVE

| Script | Location | Purpose | Notes |
|--------|----------|---------|-------|
| `farm_one.py` | finals/core/ | Single farmed account → JSON append | For parallel runs |
| `farm_zenrows_10.py` | finals/core/ | Farm 10 ZenRows accounts | Batch operation |
| `farm_zenrows_loop.py` | finals/core/ | Loop-farm until limit, 5-7min gaps | Continuous farming |
| `zenrows-kernel-final.py` | finals/core/ | ZenRows via Kernel Browser Cloud | Deterministic creation |
| `zenrows-kernel-parallel.py` | finals/core/ | ZenRows 5 parallel tabs | Batch parallel |

---

## 📋 CATEGORY 7: Utilities & Support

### ✅ ACTIVE

| Script | Location | Purpose | Notes |
|--------|----------|---------|-------|
| `mail_providers.py` | finals/core/ | Multi mail providers (22.do, temp.tf, etc) | Support library |
| `check_sessions_dashboard.py` | scripts/ | Dashboard checking utility | Session validation |
| `build_cells.py` | scripts/ | Build cells.json config | Infrastructure |
| `build_services.py` | scripts/ | Build services.json config | Infrastructure |
| `zenrows_balance.py` | scripts/ | Check ZenRows balance | API monitoring |

### 🧪 EXPERIMENTAL / TESTING

| Script | Location | Purpose | Notes |
|--------|----------|---------|-------|
| `warp_gateway.py` | finals/core/ | WARP gateway utility | Unclear usage |
| `warp_instance_manager.py` | finals/core/ | WARP instance manager | Unclear usage |
| `open-browser-new-ip.py` | finals/core/ | Open browser with new IP | Testing/utility |
| `test_turnstile_click.py` | finals/core/ | Minimal Turnstile test | Testing |
| `gh_warp_xvfb_check.py` | finals/core/ | GitHub WARP xvfb check | Testing |

### 🧪 BROWSER TESTING

| Script | Location | Purpose | Notes |
|--------|----------|---------|-------|
| `browser-adblock-working.py` | scripts/ | Chrome + uBlock Origin | Testing |
| `browser-with-extension.py` | scripts/ | Chrome + extension | Testing |
| `adguard-browser.py` | scripts/ | AdGuard browser | Testing |
| `chrome-stable-adblock.py` | scripts/ | Chrome stable + adblock | Testing |
| `simple-browser-adblock.py` | scripts/ | Simple adblock | Testing |
| `ultimate-adblock.py` | scripts/ | Ultimate adblock | Testing |
| `open-warp-browser.py` | scripts/ | WARP browser | Testing |
| `test-warp-browser.py` | scripts/ | Test WARP | Testing |

---

## 📋 CATEGORY 8: OnKernel Management

| Script | Location | Purpose | Status |
|--------|----------|---------|--------|
| `onk-org-reset.py` | finals/core/ | OnKernel org reset, new API key | ✅ WORKING |
| `onk-api.py` | finals/core/ | OnKernel account creator | ✅ WORKING |

---

## 📋 CATEGORY 9: Duplicates in Nested Directories

### ⚠️ OLD RAILWAY SESSION COPIES

Found in `scripts/railways/session-1/*/`:
- Multiple copies of `lov-api.py`
- Multiple `warp-test.py`
- Multiple `test-warp-browser.py`

**Action:** These are old Railway deployment copies, should be archived or deleted.

---

## 🎯 CLEANUP RECOMMENDATIONS

### DELETE (Old/Superseded)
- [ ] `lov-api.py`, `lov-api-zenrows.py`, `lov-back.py` in finals/core/
- [ ] `lov-f1.py`, `lov-test.py`, `lov3F*.py` in scripts/
- [ ] All `railway-login*.py` variants in scripts/ (keep only railway-API-WORKING.py)
- [ ] All `railway-mailtm*.py` in scripts/
- [ ] All browser testing scripts in scripts/ (adguard, chrome-stable, etc)
- [ ] Entire `scripts/railways/session-1/` nested directories

### KEEP (Active & Working)
- [x] `lov-api-effective.py` - Primary account creator
- [x] `lov-remix-inject.py` - Remix + inject flow
- [x] `lovable-full-automation.py` - Complete automation
- [x] `revive_sessions_login.py` - Session revival
- [x] `railway-HOLY-zenrows.py` - Railway automation
- [x] `railway_verify.py` - Health checks
- [x] Farm scripts (farm_one, farm_zenrows_*)

### ORGANIZE (Move to Proper Locations)
- [ ] Create `src/lovable/` for Lovable scripts
- [ ] Create `src/railway/` for Railway scripts
- [ ] Create `src/cookies/` for session management
- [ ] Create `src/utils/` for utilities
- [ ] Create `archive/` for old but potentially useful scripts

---

## 📊 STATISTICS

- **Total Python files**: ~97
- **Active/Working scripts**: ~25
- **Deprecated/Old**: ~35
- **Testing/Experimental**: ~20
- **Duplicates**: ~17
- **Should keep**: ~30
- **Should archive**: ~40
- **Should delete**: ~27

