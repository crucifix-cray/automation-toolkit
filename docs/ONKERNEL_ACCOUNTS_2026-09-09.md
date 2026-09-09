# OnKernel Accounts — Full Flow (2026-09-09)

End-to-end OnKernel (`onkernel.com` / `kernel.sh`) account creation + org reset,
headed local Chromium, raw IP (`LD_PRELOAD=""`, tor bypass), `dispose.lol` Gmail.
No ZenRows, no Bright Data — those are both dead (`402 AUTH004`, `403 suspended`).

## Key finding

`app.onkernel.com` does **not exist** (`NXDOMAIN` on local DNS, `1.1.1.1`, DoH).
Real surface:
- marketing/docs: `https://onkernel.com` → `https://www.kernel.sh`
- signup: `https://dashboard.onkernel.com/sign-up`
- signin: `https://dashboard.onkernel.com/sign-in`
- auth/API: `auth.onkernel.com`, `api.onkernel.com` (both resolve)

## Verified flow (Clerk)

```
1. dispose.lol -> Gmail (TreeWalker finds @gmail.com; "Change" button for a NEW inbox)
2. dashboard.onkernel.com/sign-up
   input[name=firstName] + input[name=lastName] + input[name=emailAddress]
   + input[name=password] + check input[name=legalAccepted] -> continue
3. /sign-up/verify-email-address — single input[autocomplete="one-time-code"]
   (Clerk often AUTO-SUBMITS on fill; click continue only if still on page)
4. Code mail: notifications@onkernel.com, subject "View 351817 is your verification code"
   -> code is in button[aria-label] directly (no open needed); instant (~1min)
5. /onboarding/survey — click "other" -> "Please specify..." -> "friend" -> submit arrow
6. /select-org — name + slug -> create organization -> skip invites
7. /onboarding — "generate api key" (one-time) + api-keys page -> create api key
   "auto-main" -> full sk_... shown ONCE -> save immediately
8. Verify: KERNEL_API_KEY=<sk> kernel auth  +  kernel browsers list  (expect [])
```

## Scripts

| Script | Does |
|---|---|
| `finals/core/onk-api.py` | Full signup above. `--attempts N` (default 3): no Kernel mail in ~5min → clicks dispose.lol **Change** for a fresh inbox and redoes the run. Saves `finals/sessions/onk_<ts>.json` + `.cookies.json` + `.storage.json` + `latest_onk.json` (mail + pwd + cookies + api). `--end` to skip prompt, `--headless` to override headed default. |
| `finals/core/onk-org-reset.py` | Loads session cookies (`--session`, default `latest_onk.json`), opens org switcher (`.cl-organizationSwitcherTrigger`) → manage → **delete organization** → create org → skip → fresh api key. Updates session JSON in place (mail + pwd + cookies + api). |

```
DISPLAY=:0 python3 finals/core/onk-api.py --end
DISPLAY=:0 python3 finals/core/onk-api.py --end --attempts 2 --password 'GmailK01!'
DISPLAY=:0 python3 finals/core/onk-org-reset.py --end
DISPLAY=:0 python3 finals/core/onk-org-reset.py --end --session finals/sessions/onk_123.json --org-name "Genev X"
```

## Gotchas (all hit live, all handled)

1. **Browser-use MCP reads broken** (`browser-harness 0.1.13`): `navigate` works raw,
   but `get_state`/`screenshot`/`get_html` fail (`DOMWatchdog None`, `Root CDP client
   not initialized`) even on `example.com`. Agent path needs `OPENAI_API_KEY` (unset).
   Scripts drive Chromium directly via CDP instead.
2. **Plain `browser-use` MCP is tor-wrapped** (`HTTP_PROXY=127.0.0.1:9251` inherited →
   `CDP: no valid HTTP response from proxy`). Use `browser-use-raw` (clears proxies)
   or direct Chromium with raw env.
3. **Chrome profile lock**: two MCP servers share `~/.config/browseruse/profiles/default`
   — kill the stale holder before a raw run.
4. **Headed needs silence flags**: `--mute-audio --no-first-run
   --no-default-browser-check --disable-sync` (no music, no Chrome sign-in prompt).
5. **Delete-org confirm is case-sensitive to the DISPLAY name**: prompt says
   `type "genev aochea"` but the button stays `disabled` until you type
   `Genev Aochea`. Script tries prompt text, Title Case, then switcher text.
6. **React ignores programmatic fill on the delete confirm** (button stays disabled).
   Real keystrokes required: click → `Control+a` → `keyboard.type(delay=60)` → `Tab`.
7. **Reloading dispose.lol never rotates the inbox** — must click **Change**.
8. **Never commit `finals/sessions/`** — git-ignored (API keys + cookies). Only
   `onk-api.py` / `onk-org-reset.py` / docs are tracked.

## Provenance

- Test accounts (throwaway Gmail, passwords `GmailK01!`): sessions in
  `finals/sessions/onk_*.json` (LOCAL ONLY, git-ignored).
- Raw IP `2c0e:...`, headed `Chrome/151`, `navigator.webdriver: False`.
- `kernel 0.33.0` CLI verified every key (`kernel auth` + `browsers list`).
