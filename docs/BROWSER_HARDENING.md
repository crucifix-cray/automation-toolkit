# Browser hardening & debugging

Everything shared by the automation scripts that makes the browser behave
and helps you debug when it does not.

## Launch flags & anti-detection

- `channel="chrome"` – uses system Chrome (stable, most Cloudflare-
  compatible).
- `--disable-blink-features=AutomationControlled` – removes the automation
  fingerprint from Blink.
- Init script on every page:
  `Object.defineProperty(navigator, 'webdriver', {get: () => undefined})`.
- Viewport fixed to 1440x900 for consistent layouts.

## Ad blocker

`install_ad_blocker(page)` installs `page.route("**/*", ...)`:

- Aborts requests whose URL contains ad/tracker needles
  (`doubleclick.net`, `googlesyndication.com`, `googleadservices.com`,
  `google-analytics.com`, `googletagmanager.com/gtag`, `analytics.google.com`,
  `adroll.com`, `outbrain.com`, `taboola.com`, `amazon-adsystem.com`,
  `moatads.com`, `scorecardresearch.com`, `criteo.com`, `teads.tv`,
  `doubleverify.com`, `yieldmo.com`, `adnxs.com`, `adsafeprotected.com`,
  `adzerk.net`, `pubmatic.com`, `casalemedia.com`, `openx.net`,
  `rubiconproject.com`).
- Continues everything else; the handler is wrapped in try/except so a
  failing route can never kill the interception.
- Installed on **every** tab (TempMailHub and Lovable/Railway).

## Keeping the browser open

`KEEP_BROWSER_OPEN` (default `1`): after a successful run the script prints
the JSON result, then waits for Enter in the terminal so you can inspect the
session (cookies, dashboard, tabs). `KEEP_BROWSER_OPEN=0` restores the old
close-on-exit behavior. With `--cdp-url` the external browser is never
closed regardless.

## Debugging playbook

| Symptom | Check |
|---|---|
| White screen on Lovable | Console: `Failed to fetch ... (api.lovable.dev)` -> proxy bypass missing; `docs/WARP_PROXY.md` |
| Signup never completes | The script dumps `/tmp/opencode/lovable_signup_debug.png` + URL/body text; check whether the page landed on `/login` (that is now handled) |
| `ERR_SOCKS_CONNECTION_FAILED` | Site API not in the bypass list |
| Cloudflare loop | `wait_for_lovable_ready` / `wait_for_cloudflare` reload on "Just a moment" / "We hit a snag" |
| Click does nothing | Buttons are matched with `get_by_role(..., exact=True)`; new copy on the site breaks matching – screenshot + `page.locator("body").inner_text()` first |
| Slow/blank ad-heavy pages | Verify ad blocker is active on that tab |
| Playwright "Target closed" noise at exit | Benign – GC of an unawaited future after the browser closes |

## Session artifacts

Probe scripts and run logs from the working sessions live under
`/tmp/opencode/` locally (`probe_*.py`, `lovable_run*.txt`, HTML captures,
screenshots). They are not committed to the repo; see `docs/SESSIONS.md`
for what happened in each session.
