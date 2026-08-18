# Architecture

This toolkit automates two web flows and runs a small forwarding service:

```
                        +---------------------------+
                        |   WARP SOCKS (127.0.0.1:40000)   |
                        +-------------+-------------+
                                      | proxy
        +-----------------------------v------------------------------+
        |              Self-launched hardened Chrome                |
        |  (ad-block routes + webdriver masking + WARP proxy)       |
        +--+----------------------+----------------------+----------+
           |                      |                      |
           v                      v                      v
   +---------------+      +---------------+      +-----------------+
   |  TempMailHub  |      |  Lovable.dev  |      |  Railway       |
   |  mailbox API  |      |  (signup/     |      |  (OAuth device |
   |  (direct,     |      |   reset)      |      |   flow)        |
   |   bypassed)   |      +---------------+      +-----------------+
   +---------------+
```

## Components

### 1. Proxy layering

- The **WARP client** exposes a SOCKS5 proxy on `127.0.0.1:40000`. The
  browser context uses it so the automation egresses from a WARP IP.
- Some site API backends **fail over WARP** (SSL/egress issues): known
  offenders are `api.tempmailhub.org` and `api.lovable.dev`. They are in the
  Chrome proxy-bypass list, so those requests go direct while everything else
  keeps the WARP IP.
- If WARP is not running, `proxy_settings()` returns `None` and the browser
  falls back to a direct connection (a hard failure would otherwise make the
  whole run die on `ERR_SOCKS_CONNECTION_FAILED`).

### 2. Browser hardening

- `--disable-blink-features=AutomationControlled` + an init script that
  masks `navigator.webdriver` to evade bot checks.
- A `page.route("**/*")` handler aborts ad/tracker requests
  (`doubleclick.net`, `googletagytics` etc.) and continues everything else,
  keeping the pages fast and quiet.
- The browser is kept **open after the run** by default (press Enter in the
  terminal to close it). Set `KEEP_BROWSER_OPEN=0` to restore close-on-exit.

### 3. Lovable flow (two modes)

- `request_login()` submits an email; Lovable either shows the password form
  (account exists -> "reset" mode) or the signup form (-> "signup" mode).
- **Reset mode**: fill placeholder password -> click "Forgot password?" ->
  "Send reset link" -> wait for the reset email in the TempMailHub mailbox ->
  follow the link -> set the new password -> dashboard.
- **Signup mode**: fill password -> "Create your account" -> Lovable
  redirects to `/login` -> the script now detects that and logs in with the
  created password (or handles the "verify your email" branch).

### 4. TempMailHub mailbox

- Account creation via `POST https://api.tempmailhub.org/emails` (direct
  connection, bypassed from WARP).
- Broken mailboxes (inbox not readable) are skipped; the script retries until
  it finds one with a working inbox.
- Reset links are extracted with a regex over the mailbox messages JSON.

### 5. Railway flows

- `railway-script*.py`: automates the Railway "device authorization" login
  (email/SSO), including Cloudflare challenge waiting and click-through of
  "Continue to Railway" buttons.
- `railway-login.py`: runs Railway's CLI authorization-code (PKCE) OAuth
  flow in the browser, receives the redirect on a local callback server,
  exchanges the code for tokens, and writes the CLI session file.

### 6. Chimera bridge

A Railway-deployable TCP proxy that forwards connections to XMR pool
endpoints, gated by `auth_keys`. Ships with a `Procfile`, `railway.json`,
systemd unit and deploy script. See `docs/CHIMERA_BRIDGE.md`.

## Data flow through the run (Lovable script)

```
create_working_email() -> request_login() -> (reset | signup)
                                              |
        reset: do_password_reset -> read_reset_link -> set_password_and_verify
        signup: do_signup -> "login"|"dashboard"|"verify" -> dashboard
                              |
        fallback: any failure -> reset path with the same email
```

Every attempt may fail (Cloudflare, timeouts, API hiccups); the outer loop
tries up to 3 fresh emails before giving up.
