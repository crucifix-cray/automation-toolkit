# AI HANDOFF PROMPT — Railway/Lovable automation project

You are taking over an ongoing automation project. Read this entire document
first. It contains the exact current state, evidence from probes, known
failure modes, environment quirks, and the priorities for the next session.
Do not redesign from scratch — work from this state.

---

## 1. MISSION

Two automation goals, one repo:

1. **Railway**: programmatically create Railway accounts (email + OTP code)
   and register working Railway CLI sessions (tokens + cookies), then sync
   each per-account session folder to Mega.nz cloud. This is the PRIORITY.
2. **Lovable**: automate Lovable.dev account reset/signup using disposable
   TempMailHub mailboxes. Working; minor cleanup issues remain.

Main script being worked on:
`/home/alan/Documents/railways/scripts/railway-login-with-mega-FIXED.py`

## 2. REPOSITORY & PATHS

- GitHub repo (PUBLIC): `github.com/accbroly1/automation-toolkit`
  (aka `accbroly1/automation-toolkit`). Remote: `origin` (token is already
  in the remote URL; DO NOT print/commit any tokens).
- Local repo root: `/home/alan/Documents/railways`
- Scripts: `~/Documents/railways/scripts/`
  - `railway-login-with-mega-FIXED.py` — active railway script (priority)
  - `railway-login.py`, `railway-script.py`, `railway-script2.py` — older
    railway approaches (device-code / PKCE OAuth)
  - `lovable-script.py` + `lovable-script2.py` — WORKING Lovable automation
    (identicial; script2 is canonical). Uses `playwright`, not patchright.
  - `lov-parallel.py` — newer 2-account parallel Lovable with patchright;
    BROKEN at the TempMailHub UI step (button selector drifted) — candidate
    for API integration (see section 6).
  - `test-warp-browser.py` — outdated test (wg-quick rotation; stale).
  - `railway-with-mega-WORKING.sh`, `railway-login-with-mega-FIXED.py
    user's mega variant history`.
- Docs: `~/Documents/railways/docs/` (ARCHITECTURE, SESSIONS, HANDOFF,
  WARP_PROXY, SECURITY, etc.)
- Session dirs: `session-1`..`session-6` (1-3 local originals, 4-6 pulled
  from Mega). Each contains `browser_cookies.json`, `railway_cli_config.json`,
  `railway_cli_sessions/*.session`, `.railway/`.

## 3. ENVIRONMENT QUIRKS (critical)

- **Tor wrapper in user env**: shell exports
  `HTTP_PROXY/HTTPS_PROXY/ALL_PROXY=http://127.0.0.1:9251` (tor). This makes
  ALL host network tools (rclone, pip, apt, curl) go through tor → timeouts,
  stalls, mega CDN EOFs. ALWAYS run commands with:
  `env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy
  -u all_proxy <cmd>`
  - The TempMail API calls in the railway script already force direct via
    `urllib.request.ProxyHandler({})`.
  - rclone Mega syncs MUST use the cleared env (or the config test earlier
    proved EOF errors → clearing env fixed instant downloads).
- **WARP**: `warp-cli` in proxy mode → SOCKS5 on `127.0.0.1:40000`
  (browser-only egress). `warp-cli mode` = WarpProxy port 40000. Verify with
  `curl --noproxy '*' -x socks5h://127.0.0.1:40000
  https://www.cloudflare.com/cdn-cgi/trace`.
  - `wg-quick`/`wgcf` NOT installed — any rotation code using them fails
    gracefully ("wgcf update failed") — that is OK, do NOT install them.
  - warp-cli rotation: `warp-cli disconnect` → sleep 2 → `warp-cli connect`
    → POLL until port 40000 accepts TCP again (up to ~60s) before using the
    browser. The poll exists in `lov-parallel.py`'s `rotate_warp_ip`.
  - Do NOT rotate WARP with sudo/system tools, and never touch the tor
    wrapper (9251) — user's external stuff depends on it.
- **patchright vs playwright**: `railway-login-with-mega-FIXED.py` and
  `lov-parallel.py` import `patchright.async_api`. Run them with:
  `uv run --with "patchright" python -u <script>`. Headless patchright
  requires channel="chrome"/--browser-path `/opt/google/chrome/chrome`;
  headed works with channel="chrome" on DISPLAY=:0.
- **Chrome**: `/opt/google/chrome/chrome` (channel "chrome").
- **Mega rclone config (account #4)**: resolved at
  `/home/alan/Documents/rabbyos-dash/rclone-mega4/rclone.conf`
  (also default `~/.config/rclone/rclone.conf` has remote `mega:`).
  Remote name `mega`, folder `railway_sessions`. `next_session_dir` in the
  railway script ALREADY counts remote Mega sessions (fixed) → next session
  is `session-7`.

## 4. RAILWAY SCRIPT — CURRENT STATE

`railway-login-with-mega-FIXED.py` flow (recently modified):

1. `rotate_warp_ip` (wgcf-based → fails gracefully, no-op)
2. `create_working_email()` — TempMailHub API (NEW, see section 6)
3. `sign_in_to_railway(page, email, email_id, email_timeout)`:
   - goto `https://railway.com/login` (CHANGED — was marketing `railway.com/`
     + "Sign in" click, which now bounces home; probe-verified)
   - click `Log in using email` → email placeholder `hello@email.com` →
     fill → turnstile detection → click `Continue with Email`
     (selector already correct in code)
   - `collect_otp_fields()` — NEW fallback chain for OTP inputs:
     magic.link iframe → direct `input[inputmode="numeric"]` →
     `[autocomplete="one-time-code"]` → `[maxlength="1"]` →
     `[name*="otp" i]` → `[placeholder*="code" i]`; on total failure it
     dumps url+body+frames to stderr.
   - `wait_for_railway_code_api(email_id, timeout_ms)` — polls TempMail API
     for `\b(\d{6})\s+is your Railway login code\b`
4. fill OTP → dashboard URL → `accept_railway_policies` →
   `register_cli_session` (tokens/cookies/CLI files) → `sync_to_mega` →
   `test_railway_cli`.

**LAST RUN FAILED** (log: `/tmp/opencode/rail-test4.log`): the script died
BEFORE creating an email — `TempMailHub API request failed: The read
operation timed out` (see section 6). Earlier run (rail-test3.log) got
further: email created via API, turnstile solved (manually), `Continue with
Email` clicked → page bounced to `https://railway.com/` home, NO OTP screen.
Then `collect_otp_fields` dumped evidence confirming it was on the marketing
home. Probe evidence of the CURRENT UI:
- `railway.com/` marketing home: "Sign in" button does nothing useful.
- `railway.com/login` WORKS: "Welcome to Railway", "Continue with GitHub",
  "Log in using email".
- After clicking "Log in using email": panel with "Continue with Google",
  "Email", "Continue with Email", "Log in using GitHub", "Log in using SSO".
- After submit, a Cloudflare Turnstile challenge frame may appear
  (`challenges.cloudflare.com/cdn-cg...`).

**NEXT STEPS FOR YOU (priority order):**

1. **Diagnose the post-submit bounce.** Hypothesis: the email submit with a
   brand-new TempMail address may silently fail (account-creation gate) or
   Railway changed the OTP presentation (direct inputs inside a modal on
   /login, instead of magic.link iframe). REPRODUCE interactively with a
   probe: goto /login → Log in using email → fill temp email (API-created)
   → click "Continue with Email" → hand-solve turnstile if it appears (or
   install `playwright-captcha`) → dump url/body/frames and every input,
   THEN fix `sign_in_to_railway` accordingly. Do NOT guess selectors.
2. **Fix TempMailHub API hang** (section 6) or the whole flow keeps dying
   before login. Options: shorter timeout+more retries, connection reuse
   (http.client/urllib keep-alive), a fallback second provider if time.
3. **Turnstile**: `playwright-captcha` is NOT installed; without it the
   script waits for a manual click ("waiting for manual click"). Decide
   with user whether to install it (needs pip; may need its own browser
   binaries).
4. Re-run the full flow VISIBLE (`headless=False` is the default; keep it —
   user explicitly wants to SEE the browser) until a session-7 is
   registered AND synced to Mega, and verify `railway whoami` works from
   the session dir.

## 5. TempMailHub API — INTEGRATION SPEC & GOTCHAS

Base: `https://api.tempmailhub.org` (POST JSON, headers
`Content-Type: application/json`, `Origin: https://tempmailhub.org`,
UA `Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36`).

- `POST /emails` (body `{}`) → `201` with `{"email": "...@gmail.com",
  "email_id": N}`.
- `POST /emails/messages?email_id=N` (body `{}`) → `200` list of messages,
  OR `500` with JSON like `{"error": "Failed to fetch messages: IMAP fetch
  failed: ... AUTHENTICATIONFAILED Invalid credentials..."}` for broken
  pooled accounts.

**GOTCHAS (observed, trust them):**
- Accounts are POOLED; the API REUSES the same account across calls
  (e.g., `antonypatton90@gmail.com` id 6 returned repeatedly from one IP;
  `nemilli…` etc. were seen returned again). A mailbox that worked minutes
  ago can become `IMAP AUTHENTICATIONFAILED` shortly after — always test
  `/emails/messages` right before trusting an address and re-poll on each
  code wait.
- The API intermittently HANGS: TCP connects but the server never responds
  (urllib "The read operation timed out" even after 3–4 retries at 25s).
  Keep-alive connection reuse may help; also cap per-attempt timeout at
  ~15–20s and give more attempts; if one call hangs, the next attempt
  usually succeeds.
- Initial email validation rule (from earlier work):
  `username@gmail.com` preferred, NO dots or `+` in local part. (Railway
  does not care, but the rule is already in `create_working_email`.)
- Current implementation in the railway script (surgical, working only for
  the create part): `api_post` (direct, ProxyHandler({}), 4 tries × 25s),
  `create_working_email` (240s deadline, skips broken mailboxes, pauses 3s
  on a repeated id and 10s if it repeats again), `read_messages`,
  `wait_for_railway_code_api`.

## 6. LOVABLE SCRIPTS — STATE

- `lovable-script2.py` (playwright): WORKING end-to-end. Reset path and
  signup path both verified. White-screen bug was `api.lovable.dev` failing
  through WARP → fixed via proxy bypass list
  (`api.tempmailhub.org,api.lovable.dev,127.0.0.1,localhost`). Keeps
  browser open after success (`KEEP_BROWSER_OPEN`), prints egress probe
  (`warp=on`).
- `lov-parallel.py` (patchright): currently uses the TempMailHub **UI**
  (button `button[title="Generate new email"]`) which BROKE (site changed).
  An upgrade plan exists but was NOT applied: switch to the SAME API layer
  as section 5 (create via API, drop the 22-do-style UI polling), add the
  proxy bypass list (it currently has NONE → api.lovable.dev will fail over
  WARP → white screen), add WARP-down graceful fallback (like
  lovable-script2's `proxy_settings`), remove dead code (unreachable block
  after `return results` referencing undefined `flow_id`), fix hardcoded
  cookie path `/home/alae/Downloads/tu-cookies.txt` (wrong user).
- Do NOT touch Lovable unless user asks — priority is Railway.

## 7. SESSIONS & MEGA SYNC

- 6 sessions exist: `session-1..3` (local originals), `session-4..6`
  (created via the mega flow earlier today, pulled from Mega). None are in
  git (gitignored — they contain live tokens/cookies).
- `next_session_dir()` was fixed to consider remote Mega sessions
  (`rclone lsf mega:railway_sessions`) → next is `session-7`. Never reuse /
  overwrite an existing session number.
- Sync: `sync_to_mega()` pulls remote with `--ignore-existing` then pushes
  the new session. Runs with rclone config
  `/home/alan/Documents/rabbyos-dash/rclone-mega4/rclone.conf` —
  `_mega_rclone_conf()` resolves across machines (env override,
  `~/Documents/rabbyos-dash/...`, legacy alae path, default config).
- Run rclone operations with proxy envs cleared (see section 3).

## 8. SECURITY (repo is PUBLIC)

- Never commit: any token (`ghp_…`), `browser_cookies.json`,
  `railway_cli_config.json`, `railway_cli_sessions/*`, `.railway/*`,
  `chimera-bridge/config.json` (bridge auth keys), session dirs.
- `.gitignore` covers these. Check `git status` before every commit.
- Never print the GitHub token or rail tokens in logs handed to the user.
- GitHub login for the repo: `accbroly1` (PAT already in `origin` URL).
- Mega account #4 used exclusively for these backups.

## 9. STANDARD TEST COMMANDS

```bash
# railway (priority) — VISIBLE browser, watch it on DISPLAY=:0
cd /home/alan/Documents/railways/scripts
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  uv run --with "patchright" python -u railway-login-with-mega-FIXED.py --email-timeout 240000

# lovable (working baseline)
cd /home/alan/Documents/railways/scripts
uv run --with "playwright==1.57" python -u lovable-script2.py

# check warp socks
curl -s --noproxy '*' -x socks5h://127.0.0.1:40000 https://www.cloudflare.com/cdn-cgi/trace
```

## 10. RULES FOR YOU (user's explicit constraints)

1. Run railway automation VISIBLE (never headless without asking).
2. Never touch user's tor wrapper (127.0.0.1:9251) or system network.
3. WARP rotation only via `warp-cli` in proxy mode; never wg-quick/sudo.
4. Use API for temp email (never the broken UI).
5. Small, surgical edits to `railway-login-with-mega-FIXED.py`; keep Mega
   sync and CLI registration intact. Commit + push after verified fixes.
6. When stuck, dump url/body/frames/inputs in the log INSTEAD of guessing
   selectors (the `collect_otp_fields` debug dump pattern).
7. Report next step clearly before long-running actions.