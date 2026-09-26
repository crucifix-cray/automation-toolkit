# Automation Toolkit - Data Sources Inventory

> Generated: 2026-09-14  
> Purpose: Document all data sources, identify duplicates, filtering issues, and consolidation needs

---

## 📊 OVERVIEW

The project tracks data in **THREE main locations**:
1. **GitHub** (tracked in finals/*.json)
2. **Mega Cloud** (mega_db/ directory, synced via rclone)
3. **Local Sessions** (sessions/session-1 through session-51/)

---

## 🎯 LOVABLE ACCOUNTS DATA

### Source 1: `finals/lovables.json`
- **Size**: 6.8 KB
- **Accounts**: 25 total
- **Verified**: 23 (92%)
- **With Projects**: 0
- **Types**: `zenvex`, `dispose.lol`, `tempmailhub`
- **Duplicates**: 0
- **Status**: ✅ **Clean, filtered, verified subset**

### Source 2: `finals/all_lovables_final.json`
- **Size**: 646 KB (🔴 **HUGE**)
- **Accounts**: 69 total
- **Verified**: 67 (97%)
- **With Projects**: 0
- **Types**: `None`, `zenvex`, `dispose.lol`, `tempmailhub`
- **Duplicates**: 0
- **Status**: ⚠️ **Larger dataset, some have type=None**

### Relationship Analysis
```
lovables.json:              25 accounts (SUBSET)
all_lovables_final.json:    69 accounts (SUPERSET)
Overlap:                    25 accounts (100% of lovables.json)
Only in all_lovables_final: 44 accounts
```

**Conclusion**: `lovables.json` is a **filtered subset** of `all_lovables_final.json`. All 25 accounts in lovables.json also exist in all_lovables_final.json.

### Source 3: Mega Cloud (`mega_db/`)
- **Lovable Data**: ❌ **NOT FOUND** in mega_db
- **What's in mega_db**:
  - BrightData accounts (acc1-12.json)
  - ZenRows accounts (2 in db/browsers+proxies/zenrows/)
  - BrightData browser configs

**Conclusion**: Lovable accounts are **NOT stored in Mega**, only in GitHub (finals/*.json).

### Source 4: `finals/zenrows_onkernel_farmed.json`
- **ZenRows Accounts**: 34 farmed via OnKernel
- **Structure**: email, password, api_key, url, live_url, session_id, farmed_at
- **Status**: ✅ Clean, OnKernel-specific

### Source 5: `finals/lovable_invites.json`
- **Invites**: 2 invite links
- **Purpose**: Stores project invite links for low-credit flow
- **Status**: ✅ Clean but minimal data

---

## 🚂 RAILWAY ACCOUNTS DATA

### Source 1: `finals/railway_verify.json`
- **Size**: 43 KB
- **Sessions**: 130 entries
- **Structure**: session, email, whoami, projects_before, status, init_out
- **Statuses**:
  - `restricted` - Workspace restricted by Railway
  - `trial` - Free plan limit exceeded
  - `ok` - Working properly
  - `trial_exceeded` - Trial limits hit
- **Purpose**: Latest verification sweep results
- **Status**: ✅ **Most recent, authoritative**

### Source 2: `finals/railway_audit.json`
- **Size**: 19 KB
- **Sessions**: 100 entries
- **Structure**: session, email_txt, created_at, whoami, projects, project_names, status
- **Purpose**: Historical audit snapshot
- **Status**: ⚠️ Older data (created_at around 2026-08-22)

### Source 3: `cells.json`
- **Sessions**: 51 cells configured
- **Structure**: session, project (UUID), checkpoint, status, env (UUID)
- **All Status**: `ready`
- **Purpose**: Railway deployment cell mapping (session → project → environment)
- **Status**: ✅ **Critical infrastructure config**

### Source 4: `services.json`
- **Purpose**: Service/environment mappings
- **Status**: Not examined yet

### Relationship Analysis
```
railway_verify.json:  130 sessions (includes old/dead ones)
railway_audit.json:   100 sessions (historical snapshot)
cells.json:            51 sessions (active infrastructure)
```

**Discrepancy**: 
- ✅ `cells.json` tracks **51 active sessions** (session-1 to session-51)
- ⚠️ `railway_verify.json` has **130 entries** (includes old session-123, 124, 127, 128, etc.)
- The git history mentions: *"sessions: drop restricted 123/124/127/128, index remaining 52"*
- This suggests the numbering was **renormalized** from 130 down to 51

---

## 📁 LOCAL SESSIONS DATA

### Directory: `sessions/session-1` through `sessions/session-51`

#### Structure per session:
```
session-N/
├── email.txt                    # Railway email
├── verified_at.txt              # Timestamp
├── railway_cli_config.json      # Railway CLI config
├── railway_cli_sessions/        # Railway session data
├── .railway/                    # Railway metadata
├── .ssh/                        # SSH keys for Railway
├── config.json                  # ❌ MISSING (Lovable creds should be here)
└── cookies.json                 # ❌ MISSING (Lovable cookies should be here)
```

#### What's Actually There:
- ✅ Railway infrastructure files (railway_cli_config.json, .railway/, .ssh/)
- ❌ **Lovable config.json** - Missing in most/all sessions
- ❌ **Lovable cookies.json** - Missing in most/all sessions

#### Why Lovable Files Are Missing:
Based on git history: *"security: remove leaked Lovable creds, ignore nested session secrets"*

The Lovable credentials were **intentionally removed** from git for security.

---

## 🔍 FILTERING ISSUES ANALYSIS

### Issue 1: "Previous AI Hallucinated Filtering"

**Hypothesis**: The previous AI may have incorrectly filtered accounts when creating lovables.json from all_lovables_final.json.

**Evidence**:
- ✅ **NO duplicates** in either file (good)
- ✅ All accounts in lovables.json exist in all_lovables_final.json (correct subset)
- ⚠️ 44 accounts in all_lovables_final.json are NOT in lovables.json (filtering happened)

**The Filtering**:
```python
lovables.json (25):     Highly verified, clean subset
all_lovables_final (69): Full dataset, includes some with type=None
```

**Possible Filter Criteria**:
1. Only accounts with explicit `type` (not None)?
2. Only most recent accounts?
3. Only accounts meeting certain verification threshold?
4. **Random selection** (hallucination)?

**NEEDS INVESTIGATION**: Check what criteria was used to select 25 from 69.

### Issue 2: Railway Session Number Chaos

**Problem**: Session numbering was renormalized
- Original: session-1 through session-130 (with gaps, restricted accounts)
- Current: session-1 through session-51 (renumbered, clean)
- `railway_verify.json` still has 130 entries (old numbering)
- `cells.json` has 51 entries (new numbering)

**Impact**:
- ⚠️ Old scripts/docs may reference wrong session numbers
- ⚠️ railway_verify.json is **out of sync** with actual session directories
- ⚠️ References to "session-123" no longer exist

### Issue 3: Missing Lovable Session Data

**Problem**: Local sessions/ directories have Railway data but **no Lovable data**

**Where Lovable Data Should Be**:
```
sessions/session-N/config.json - should contain:
  - email: lovable account email
  - password: lovable password  
  - verified: true/false
  - created_at: timestamp
  - projects: []

sessions/session-N/cookies.json - should contain:
  - Array of browser cookies for lovable.dev
```

**Where It Actually Is**:
- ✅ finals/lovables.json (25 accounts)
- ✅ finals/all_lovables_final.json (69 accounts)
- ❌ NOT in sessions/ directories

**Why**: Security - removed from git, should be pulled from Mega or regenerated.

---

## 🎯 CONSOLIDATION RECOMMENDATIONS

### Lovable Accounts

**Decision Needed**: Which is the source of truth?

**Option A: Keep Both** (Recommended)
- `all_lovables_final.json` → **Master list** (69 accounts, all data)
- `lovables.json` → **Active subset** (25 accounts, currently being used)
- Document why 25 were selected from 69

**Option B: Consolidate to One**
- Review the 44 accounts only in all_lovables_final.json
- Decide which to keep/discard
- Merge into single source of truth
- Archive the rejected one

### Railway Accounts

**Required Actions**:
1. ✅ **KEEP** `cells.json` (51 sessions) - critical infrastructure
2. 🔄 **UPDATE** `railway_verify.json`:
   - Remove old session-123, 124, 127, 128, etc.
   - Keep only session-1 through session-51
   - OR mark old ones as `status: deleted`
3. 📦 **ARCHIVE** `railway_audit.json` (historical snapshot, keep for reference)

### Mega DB

**Current State**: mega_db/ contains:
- BrightData accounts (12)
- ZenRows accounts (2)
- Browser configs
- ❌ NO Lovable accounts

**Action**: Document that Lovable accounts are GitHub-only, not in Mega.

### Session Directories

**Required Actions**:
1. Generate `config.json` for each session-1 to session-51:
   - Map from lovables.json or all_lovables_final.json
   - One Lovable account per Railway session
2. Either:
   - Add to .gitignore (keep secret)
   - OR encrypt and track
   - OR sync from Mega (if they exist there)
3. Document the mapping: session-N → lovable-account

---

## 📋 DATA QUALITY SUMMARY

| Data Source | Size | Quality | Issues | Action |
|-------------|------|---------|--------|--------|
| `lovables.json` | 25 | ✅ Clean | Unclear filter criteria | Document selection |
| `all_lovables_final.json` | 69 | ✅ Mostly clean | 2 accounts type=None | Review & decide master |
| `railway_verify.json` | 130 | ⚠️ Stale | Has deleted sessions | Clean up old entries |
| `railway_audit.json` | 100 | ✅ OK | Historical only | Archive |
| `cells.json` | 51 | ✅ Critical | None | Keep as-is |
| `zenrows_onkernel_farmed.json` | 34 | ✅ Clean | None | Keep |
| `sessions/session-*/` | 51 dirs | ⚠️ Incomplete | Missing Lovable data | Generate configs |
| `mega_db/` | Various | ✅ OK | No Lovable accounts | Document scope |

---

## 🚨 CRITICAL ISSUES FOUND

### 1. ⚠️ Unclear Filtering Logic
**Problem**: Cannot determine why 25 accounts were selected from 69 in all_lovables_final.json  
**Risk**: May have excluded valid accounts  
**Action**: Review all 69 accounts, document selection criteria, or re-filter

### 2. 🔴 Session Number Mismatch
**Problem**: railway_verify.json (130) vs cells.json (51) vs actual directories (51)  
**Risk**: Scripts may reference wrong sessions, confusion about which sessions exist  
**Action**: Clean railway_verify.json to match current 51 sessions

### 3. 🔴 Missing Lovable Credentials in Sessions
**Problem**: sessions/session-N/ have Railway data but no Lovable config.json/cookies.json  
**Risk**: Cannot map which Lovable account belongs to which Railway session  
**Action**: Create mapping and generate config files (or document external storage)

### 4. ⚠️ No Single Source of Truth
**Problem**: Lovable accounts in 2 JSON files, Railway data in 3 files, sessions in 51 directories  
**Risk**: Data drift, updates not reflected everywhere  
**Action**: Designate one source as master for each data type

---

## 🎯 RECOMMENDED DATA MODEL

### Final Structure (Post-Cleanup):

```
finals/
├── lovables_master.json         # ← MASTER (69 accounts, full data)
├── lovables_active.json         # ← ACTIVE SUBSET (25 accounts, in use)
├── railway_sessions.json        # ← MASTER (51 sessions, current state)
├── railway_audit_2026-08-22.json # ← ARCHIVED (historical)
├── zenrows_accounts.json        # ← ZenRows (34 accounts)
└── session_mapping.json         # ← NEW: session-N → lovable email mapping

sessions/
└── session-N/
    ├── config.json              # ← GENERATE: Lovable creds
    ├── cookies.json             # ← REVIVE: Fresh cookies
    ├── railway_cli_config.json  # ✅ Already exists
    └── ... (Railway infrastructure)

mega_db/                         # ← Proxy/browser accounts only
```

---

## 📝 NEXT STEPS

1. ✅ **Document** filtering criteria for lovables.json selection
2. 🔄 **Clean** railway_verify.json (remove sessions 52-130)
3. 🔄 **Create** session_mapping.json (session → lovable account)
4. 🔄 **Generate** config.json for each session-1 to session-51
5. 📦 **Archive** railway_audit.json with date suffix
6. ✅ **Designate** master files for each data type
7. 📝 **Document** data sync procedures (GitHub ↔ Mega ↔ Local)

