# Lovable account automation

Covers `scripts/lovable-script.py` and `scripts/lovable-script2.py`.

## What it does

1. Asks TempMailHub for a working disposable mailbox (`email` + `email_id`).
2. Opens Lovable, dismisses the cookie banner, signs out if a previous
   session is still active, and submits the email via the "Log in" modal.
3. Detects which mode Lovable chose:
   - **reset** – account exists (password form on `/login`)
   - **signup** – "No account found" / "Create your account" screen
4. Follows the mode-specific flow (below), then verifies the dashboard
   (URL contains `/dashboard` **and** the text "Dashboard", and the account
   menu button is visible).

## Reset path (existing accounts)

```
do_password_reset(page, email):
  wait for input[type=password]           # login form
  fill placeholder password               # Lovable validates the form first
  click "Forgot password?"
  if email differs: click "Use a different email", fill the real one
  click "Send reset link"
```

Then `read_reset_link()` polls the mailbox for the Lovable email and extracts
the password-reset URL, and `set_password_and_verify()`:

```
navigate to reset URL
fill input[name=newPassword] and input[name=confirmPassword]
click "Reset Password"
wait for "Your password has been updated" (or dashboard)
```

> The generated password is the email address itself (fallback: `email + "1"`).

## Signup path (new accounts)

```
do_signup(page, email, password):
  wait for input[type=password] (20s)     # "Create your account" form
  fill password twice
  click "Create your account"
  loop up to 60s watching for:
    /dashboard + "Dashboard"        -> "dashboard"
    "verif"/"code"/"Check your email" -> "verify"
    /login + password input present -> "login"
```

Important history (why the branch is the way it is):

- Lovable does **not** land on the dashboard after account creation. It
  redirects to `/login` with a password form. The script originally only
  watched for the dashboard and treated that as failure, falling back to a
  password reset (which worked, but wasted a minute).
- The fallback **did** work because the created account now existed.
- Fix: detect the `/login` state and sign in with the just-created password.

## White-screen bug (fixed)

The signup flow crashed into a blank page in some runs. Diagnosis:

- Console logs showed `Failed to fetch consent policy (api.lovable.dev)` and
  `net::ERR_SOCKS_CONNECTION_FAILED` for Lovable's own API requests.
- Root cause: `api.lovable.dev` fails through the WARP SOCKS proxy (same
  failure class as `api.tempmailhub.org`).
- Fix: add `api.lovable.dev` to the proxy-bypass list
  (`bypass = "api.tempmailhub.org,api.lovable.dev,127.0.0.1,localhost"`).
- Verified: after the fix, the signup page renders and account creation
  completes.

## Debugging helpers

- On signup failure the script saves a debug screenshot to
  `/tmp/opencode/lovable_signup_debug.png` and prints the page URL + body
  text snippet.
- The browser's egress is verified at startup:
  `Browser egress IP: ip=... warp=on colo=...` (from
  `cloudflare.com/cdn-cgi/trace`).

## Gotchas

- **Cookie banner** ("Manage preferences" / "OK") is dismissed before any
  interaction.
- **Cloudflare challenge**: `wait_for_lovable_ready()` watches for
  "Performing security verification" and "We hit a snag" and reloads as
  needed.
- **Sign out**: a leftover signed-in session would break the flow, so the
  script signs out when the dashboard account menu is present.
- Mailbox emails: TempMailHub occasionally hands out a mailbox whose inbox
  API is broken; those are skipped with a retry.
