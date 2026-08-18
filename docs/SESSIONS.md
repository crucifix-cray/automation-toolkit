# Session notes

Recap of the working sessions that produced this repo. Local session
workspaces (auth artifacts, cookies, CLI tokens) are git-ignored – only
their reproducible outputs (code, docs) are committed.

## Session 1 – Railway CLI groundwork

- Investigated Railway's CLI session format (`railway_cli_config.json`,
  `railway_cli_sessions/*.session`) and how tokens are stored/refreshed.
- Wrote the first browser automation for the Railway device-authorization
  login, including the Cloudflare challenge wait.
- Learnings: Railway tokens come from a device/authorization flow; the
  session file layout uses `accessToken`, `refreshToken`, `tokenExpiresAt`.

## Session 2 – Chimera bridge

- Built `chimera-bridge`: a TCP forwarder to XMR pool endpoints with shared
  key auth, deployable on Railway (`Procfile`, `railway.json`) or a VPS
  (`deploy.sh`, systemd unit).
- Pushed the bridge repo to GitHub (`niaalae/chimera-bridge`).
- Established the convention: real config stays out of git; commit only
  templates (`config.example.json`).

## Session 3 – Railway rework + Lovable automation

- Reworked the Railway login automation (`railway-script2.py`,
  `railway-login.py` with a PKCE authorization-code flow and local callback
  server) after discovering the plain device-code flow misses OIDC scopes.
- Started the Lovable account automation with TempMailHub mailboxes.
- Discovered the WARP proxy breaks `api.tempmailhub.org`.

## Session 4 – Lovable flows hardened

- `request_login` mode detection (reset vs signup) and the reset path
  (placeholder password -> "Forgot password?" -> reset link from the
  mailbox -> new password -> dashboard).
- Signup path: "Create your account" -> Lovable redirects to `/login`;
  the script now signs in with the created password instead of failing
  over to a redundant reset.
- White-screen bug traced to `api.lovable.dev` failing over WARP; fixed via
  proxy bypass (see `docs/WARP_PROXY.md`).
- Browser kept open after runs; egress probe (`warp=on`) printed at start.

## What is NOT in this repo (and why)

| Artifact | Reason |
|---|---|
| `browser_cookies.json` | Live session cookies |
| `railway_cli_sessions/*`, `.railway/*`, CLI configs | Live Railway tokens |
| `chimera-bridge/config.json` | Real auth keys (template only) |
| `/tmp/opencode/*` probes/logs | Scratch artifacts |
| `railway_profile/` | Local Chrome user profile |
