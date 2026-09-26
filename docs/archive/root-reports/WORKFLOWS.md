# Automation Toolkit - Working Workflows

Complete documentation of all working automation workflows.

---

## 📋 Table of Contents

1. [Lovable Account Creation](#1-lovable-account-creation)
2. [Lovable Session Revival](#2-lovable-session-revival)
3. [Lovable Remix + Inject](#3-lovable-remix--inject)
4. [Lovable Full Automation](#4-lovable-full-automation)
5. [Railway Account Creation](#5-railway-account-creation)
6. [Railway Health Verification](#6-railway-health-verification)
7. [ZenRows Farming](#7-zenrows-farming)
8. [Session Management](#8-session-management)

---

## 1. Lovable Account Creation

**Script**: `src/lovable/account_creation.py`  
**Original**: `finals/core/lov-api-effective.py`

### Purpose
Create new Lovable.dev accounts using ZenRows GB proxy + dispose.lol Gmail.

### Prerequisites
- `ZENROWS_API_KEY` environment variable set
- Internet connection
- ZenRows credits available

### Flow
```
1. Connect to ZenRows Browser (GB proxy - BT Telford IP)
2. Navigate to lovable.dev/signup
3. Create dispose.lol Gmail account
4. Fill email in signup form → "Continuer"
5. Fill password (GmailK01 pattern) → Submit
6. Wait for Turnstile auto-solve (837-858 char token)
7. Click "Créez votre compte"
8. Poll dispose.lol for verification email
9. Extract oobCode from email
10. Complete email verification
11. Navigate to /getting-started
12. Save session to files
```

### Usage
```bash
cd src/lovable/

# Create 1 account
python3 account_creation.py

# Create 5 accounts
python3 account_creation.py --count 5

# Use specific proxy country
python3 account_creation.py --proxy-country gb
```

### Output
- Account data saved to `finals/lovables.json`
- Session info: email, password, verification status
- Success rate: ~90-95% with ZenRows GB

### Common Issues
- **Turnstile 403**: Use GB proxy (not GF/FR)
- **Email timeout**: dispose.lol slow, wait up to 5min
- **ZenRows 402**: API key exhausted, rotate keys

---

## 2. Lovable Session Revival

**Script**: `src/lovable/session_revival.py`  
**Original**: `scripts/revive_sessions_login.py`

### Purpose
Revive dead Lovable sessions by logging in with email+password and saving fresh cookies.

### Prerequisites
- Session directories with `config.json` containing email/password
- OR lovables.json with credentials

### Flow
```
1. Load session config (email + password)
2. Navigate to lovable.dev/login
3. Fill email → Submit
4. Wait for password field
5. Fill password → Submit
6. Monitor for success (dashboard) or errors
7. Extract fresh cookies on success
8. Save cookies.json to session directory
9. Update config.json status
```

### Usage
```bash
cd src/lovable/

# Revive single session
python3 session_revival.py --pth session-7

# Revive all sessions (3 parallel workers)
python3 session_revival.py --pth all --par 3

# Revive with ZenRows remote browser
python3 session_revival.py --pth all --cdp-url "wss://browser.zenrows.com?apikey=..."

# High parallelism (5 workers)
python3 session_revival.py --pth all --par 5
```

### Output
- Fresh `cookies.json` saved to each session
- `revive_results.log` with detailed report
- Summary: REVIVED count, FAILED count, error categories

### Success Indicators
```
✅ Dashboard reached: /projects or /dashboard URL
✅ Dashboard UI elements: avatar, "New project" button
✅ Fresh cookies: 20-50 cookies saved
```

### Failure Reasons
- **Suspicious activity**: IP flagged by Lovable (need different proxy)
- **Invalid credentials**: Wrong password or deleted account
- **Turnstile challenge**: Manual challenge triggered

### Results Log Format
```
Session         Status      Cookies  Email                            Failure Reason
session-7       ✅ REVIVED  42       g.son0876@gmail.com              Dashboard reached
session-8       ❌ FAILED   0        nij.irosimon@gmail.com           Suspicious activity IP block
```

---

## 3. Lovable Remix + Inject

**Script**: `src/lovable/remix_inject.py`  
**Original**: `finals/core/lov-remix-inject.py`

### Purpose
Remix Lovable templates, inject window.doc bridge, and generate invite links.

### Prerequisites
- Active Lovable session with cookies
- OnKernel API key (for remote browser)
- Template to remix

### Flow
```
1. Login to Lovable with session cookies
2. Browse templates page
3. Select random template
4. Click "Remix" → new project created
5. Wait for editor to load
6. Open preview tab
7. Inject window.doc bridge script
8. Test bridge: doc.connect(), doc('pwd'), doc('ls')
9. Generate invite link
10. Save project + invite to database
```

### Usage
```bash
cd src/lovable/

# Remix for single session
python3 remix_inject.py --session 35

# Remix for all sessions (5 parallel)
python3 remix_inject.py --all --parallel 5

# Use local Camoufox (max stealth)
python3 remix_inject_local.py --session 35
```

### Output
- Project created in Lovable account
- Invite link generated: `lovable.dev/projects/{id}?magic_link=...`
- Saved to `finals/lovable_invites.json`

### window.doc Bridge Commands
```javascript
// Test connection
await doc.connect()

// Run commands
await doc('pwd')           // Current directory
await doc('ls')            // List files
await doc('cat file.txt')  // Read file
await doc('env')           // Environment variables
```

---

## 4. Lovable Full Automation

**Script**: `src/lovable/full_automation.py`  
**Original**: `finals/core/lovable-full-automation.py`

### Purpose
Complete automation: check credits → template or invite → build → test → save to Mega.

### Prerequisites
- Session with Lovable cookies
- Lovable account with credits
- Mega rclone configured (optional)

### Flow - High Credit (≥2 credits)
```
1. Login with session cookies
2. Check credit balance
3. Navigate to templates
4. Pick random template (first 10 visible)
5. Click "Remix"
6. Send subprocess prompt to AI
7. Wait for AI to build (30-60s)
8. Open preview tab
9. Test subprocess in preview (window.doc)
10. Generate invite link
11. Save to Mega: lovable-invites:/invites.json
```

### Flow - Low Credit (<2 credits)
```
1. Login with session cookies
2. Check credit balance
3. Download invite from Mega
4. Accept invite link
5. Test existing project subprocess
6. Report success/failure
```

### Usage
```bash
cd src/lovable/

# Run full automation for session 9
python3 full_automation.py --session 9

# Specify credit threshold
python3 full_automation.py --session 9 --min-credits 3

# Skip Mega sync
SKIP_MEGA=1 python3 full_automation.py --session 9
```

### Credit Routing Logic
```python
if credits >= 2:
    flow = HIGH_CREDIT_FLOW  # Create new project
else:
    flow = LOW_CREDIT_FLOW   # Use existing invite
```

### Keep-Alive Feature
Built into full_automation.py (lines 1120-1190):
- Opens preview tab
- Randomly interacts with editor/preview
- Tests window.doc commands
- Keeps project active during mining
- Prevents idle timeout

---

## 5. Railway Account Creation

**Script**: `src/railway/account_creation.py`  
**Original**: `railway-docker/railway-HOLY-zenrows.py`

### Purpose
Complete Railway.com automation: account creation + PKCE OAuth + viral deployment.

### Prerequisites
- ZenRows API key (GF proxy for French Orange IPs)
- dispose.lol or mail.tm for email
- Railway CLI installed

### Flow
```
1. Connect to ZenRows Browser (GF proxy - French Orange)
2. Create disposable email (dispose.lol/mail.tm)
3. Navigate to railway.com/login
4. Fill email → Request OTP
5. Poll email for OTP code (150 checks, 80s timeout)
6. Submit OTP → Dashboard access
7. Perform device + PKCE OAuth flow
8. Extract access_token + refresh_token
9. Save to ~/.railway/config.json
10. Sync session to Mega
11. Optional: Viral deployment (create more sandboxes)
```

### Usage
```bash
cd src/railway/

# Create single account
python3 account_creation.py

# No viral deployment
python3 account_creation.py --cloud-no-c

# Use specific ZenRows key
ZENROWS_API_KEY=key123 python3 account_creation.py

# Parallel viral deployment
# (Each sandbox creates 2 more → exponential growth)
python3 account_creation.py --viral-mode
```

### Viral Deployment
```
Generation 0: 1 sandbox
Generation 1: 3 sandboxes (1→3)
Generation 2: 7 sandboxes (3→7)
Generation 3: 15 sandboxes
...
Generation 13: 8191 sandboxes

Time: ~26 minutes to reach 8191
Max: 3 sandboxes per API key
```

### Output
- Railway CLI authenticated
- `~/.railway/config.json` with tokens
- Session saved to `sessions/session-N/`
- Synced to `mega:railway_sessions/`

---

## 6. Railway Health Verification

**Script**: `src/railway/verify_health.py`  
**Original**: `scripts/railway_verify.py`

### Purpose
Verify Railway session health: whoami → list projects → create → delete.

### Prerequisites
- Railway CLI installed
- Session directories with railway_cli_config.json

### Flow
```
1. Set HOME to session directory
2. Run: railway whoami (check login)
3. Run: railway list (check projects)
4. Run: railway init (create test project)
5. Run: railway delete (clean up)
6. Report: ok / restricted / trial_exceeded
```

### Usage
```bash
cd src/railway/

# Verify single session
python3 verify_health.py --pth session-1

# Verify all sessions
python3 verify_health.py --pth all

# Save results to JSON
python3 verify_health.py --pth all --output results.json
```

### Status Codes
- `ok`: Fully functional, can create projects
- `trial`: Trial plan, resource limits exceeded
- `restricted`: Account restricted, contact support
- `error`: CLI failure, authentication issue

### Output Format
```json
{
  "session": "session-1",
  "email": "user@gmail.com",
  "whoami": "Logged in as user@gmail.com 👋",
  "projects_before": 2,
  "status": "ok",
  "init_out": "Project created successfully"
}
```

---

## 7. ZenRows Farming

**Script**: `src/farming/zenrows_kernel.py`  
**Original**: `finals/core/zenrows-kernel-final.py`

### Purpose
Farm ZenRows accounts via OnKernel stealth browsers.

### Prerequisites
- OnKernel API key
- mail.tm or dispose.lol for emails

### Flow
```
1. Create OnKernel stealth browser session
2. Create disposable email (mail.tm)
3. Navigate to zenrows.com/register
4. Fill registration form
5. Verify email (poll mail.tm API)
6. Login to ZenRows dashboard
7. Extract API key from dashboard
8. Save account data to JSON
9. Close browser, repeat
```

### Usage
```bash
cd src/farming/

# Farm single account
python3 farm_single.py

# Farm 10 accounts
python3 farm_zenrows_batch.py

# Continuous farming loop (5-7min gaps)
python3 farm_zenrows_loop.py

# Parallel farming (5 browsers)
python3 zenrows_kernel_parallel.py
```

### Output
```json
{
  "email": "anhtha.nhbamot13@gmail.com",
  "password": "Test1234!AbcZ2026",
  "api_key": "11d7d0ee3adf967ba7361c9139e7a7aa66251fac",
  "url": "https://app.zenrows.com/overview",
  "farmed_at": "2026-09-07T21:15:49Z",
  "via": "onkernel"
}
```

Saved to: `finals/zenrows_onkernel_farmed.json`

### Success Rate
- OnKernel: ~90% (GB/DE IPs work best)
- Parallel 5x: ~80% (some IP conflicts)

---

## 8. Session Management

### Load Session in Browser

**Script**: `src/utils/session_loader.py`

```bash
cd src/utils/

# List all sessions
python3 session_loader.py --list

# Load session-1 in browser
python3 session_loader.py 1

# Load with specific URL
python3 session_loader.py 1 --url https://lovable.dev/projects
```

### Check Dashboard Status

**Script**: `src/utils/check_dashboard.py`

```bash
cd src/utils/

# Check single session
python3 check_dashboard.py --session 1

# Check all sessions
python3 check_dashboard.py --all

# Save results
python3 check_dashboard.py --all --output dashboard_status.json
```

### Build Configuration Files

**Script**: `src/utils/build_cells.py`, `src/utils/build_services.py`

```bash
cd src/utils/

# Rebuild cells.json from sessions
python3 build_cells.py

# Rebuild services.json
python3 build_services.py

# Verify outputs
cat ../../cells.json
cat ../../services.json
```

### Check ZenRows Balance

**Script**: `src/utils/zenrows_balance.py`

```bash
cd src/utils/

# Check balance for default API key
python3 zenrows_balance.py

# Check specific key
ZENROWS_API_KEY=key123 python3 zenrows_balance.py

# Check all farmed keys
python3 zenrows_balance.py --check-all
```

---

## 🔄 Complete Workflow Examples

### Example 1: Setup New Lovable Session

```bash
# 1. Create Lovable account
cd src/lovable/
python3 account_creation.py
# → Saves to finals/lovables.json

# 2. Assign to session-35
# Edit session_mapping.json:
# "lovable_email": "new_account@souss.dev"

# 3. Revive session (get cookies)
python3 session_revival.py --pth session-35
# → Saves cookies.json

# 4. Test with full automation
python3 full_automation.py --session 35
```

### Example 2: Revive All Dead Sessions

```bash
cd src/lovable/

# 1. Revive all sessions in parallel
python3 session_revival.py --pth all --par 5 --log-file revive_2026-09-14.log

# 2. Check results
cat revive_2026-09-14.log | grep "✅ REVIVED"
cat revive_2026-09-14.log | grep "❌ FAILED"

# 3. Re-run failed sessions with different proxy
python3 session_revival.py --pth "7,8,12" --cdp-url "wss://kernel..."
```

### Example 3: Mass Remix Across All Sessions

```bash
cd src/lovable/

# 1. Ensure all sessions have cookies
python3 session_revival.py --pth all --par 3

# 2. Run remix + inject for all
python3 remix_inject.py --all --parallel 5

# 3. Check invites generated
cat ../../finals/lovable_invites.json | jq '.[] | .invite_link'
```

### Example 4: Railway + Lovable Full Stack

```bash
# 1. Create Railway account
cd src/railway/
python3 account_creation.py
# → Session saved to sessions/session-52/

# 2. Create Lovable account
cd ../lovable/
python3 account_creation.py
# → Account in finals/lovables.json

# 3. Link them in session_mapping.json
# Edit: session-52 → railway_email + lovable_email

# 4. Verify Railway health
cd ../railway/
python3 verify_health.py --pth session-52

# 5. Run full Lovable automation
cd ../lovable/
python3 full_automation.py --session 52
```

---

## 📊 Workflow Success Rates

| Workflow | Success Rate | Time per Run | Notes |
|----------|--------------|--------------|-------|
| Lovable Account Creation | 90-95% | 5-8 min | ZenRows GB best |
| Lovable Session Revival | 70-80% | 2-3 min | IP blocks common |
| Lovable Remix + Inject | 85-90% | 10-15 min | Template availability varies |
| Lovable Full Automation | 75-85% | 15-20 min | Depends on credits |
| Railway Account Creation | 85-90% | 10-15 min | OTP delivery critical |
| Railway Health Check | 95-100% | 1-2 min | Fast, reliable |
| ZenRows Farming | 80-90% | 5-10 min | OnKernel stealth helps |

---

## ⚠️ Common Pitfalls

### 1. Path Issues
Scripts use absolute paths. Update them:
```python
# Bad
SESSIONS_DIR = Path("/home/alan/Documents/...")

# Good
SESSIONS_DIR = Path(__file__).parent.parent.parent / "sessions"
```

### 2. Browser Conflicts
Don't run multiple browser scripts in same session simultaneously. Use locks:
```python
import fcntl
with open('/tmp/session-1.lock', 'w') as f:
    fcntl.flock(f, fcntl.LOCK_EX)
    # Your automation here
```

### 3. Cookie Expiration
Lovable cookies expire after ~7 days. Revive regularly:
```bash
# Weekly revival cron job
0 0 * * 0 cd /path/to/repo/src/lovable && python3 session_revival.py --pth all
```

### 4. Credit Management
Track Lovable credits to route correctly:
```bash
# Check credits before running
python3 -c "from full_automation import check_credits; print(check_credits(session=9))"
```

### 5. Rate Limiting
Add delays between mass operations:
```python
for session in range(1, 52):
    run_automation(session)
    time.sleep(30)  # 30s between sessions
```

---

## 📝 Logging & Debugging

### Enable Verbose Logging
```bash
# Set log level
export LOG_LEVEL=DEBUG

# Or in script
python3 script.py --verbose
```

### Save Browser Screenshots
Most scripts support screenshots on error:
```python
await page.screenshot(path=f"/tmp/error_{session}.png", full_page=True)
```

### Check Logs
```bash
# Script logs
tail -f /tmp/automation.log

# Railway CLI logs
tail -f ~/.railway/logs/

# Browser console logs
# (captured by scripts automatically)
```

---

## 🎯 Best Practices

1. **Test with Single Session First** - Don't scale until verified
2. **Use Parallel Execution Wisely** - Max 5 workers for browser scripts
3. **Rotate Proxies** - Use different ZenRows keys for batches
4. **Monitor Resources** - Each browser uses ~500MB RAM
5. **Regular Health Checks** - Verify sessions weekly
6. **Backup Data** - Sync to Mega or Git regularly
7. **Document Changes** - Update session_mapping.json
8. **Use Virtual Environments** - Avoid package conflicts
9. **Set Timeouts** - All network ops should have timeouts
10. **Handle Failures Gracefully** - Retry logic with backoff

