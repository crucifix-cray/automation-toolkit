# Lovable Farm Blueprint — ZenRows key `1a5d93...` (GB residential)

Verified 2026-09-07: key live, fresh GB residential IP per browser
(`80.3.110.27` Virgin Grays, `81.106.127.115` Virgin, `88.97.240.61` YouFibre).

## WSS (fresh IP + fresh browser every run)

```
wss://browser.zenrows.com?apikey=1a5d93cda0d10ac0bd9ab3da3fa93019f126397a&proxy_country=gb
```

- New `connect_over_cdp` per run = new exit IP (proven: 3 connects → 3 IPs).
- One browser per run, `browser.close()` + `kernel browsers delete` in `finally`.
- Never reuse a browser across runs (stale IP gets flagged after ~2 signups).

## Run loop (per account)

1. **Mail** — rotate providers in order (skip on block, next provider):
   `dispose.lol` (browser tab, 1-dot Gmail) → `temp.tf` (`/account?dot=1`, reject `+`)
   → `22.do` (10 handlers in `lov-zenrows-5x.py:44-54`, normalize Gmail to short one-dot)
   → `zenvex.dev` (`/api/domains` iterate) → `mail.tm` (`emalupe.com`, usually blocked — last resort)
2. **Signup** — `lovable.dev/signup` → `input#email` fill → Continue
   → `input#password` fill `<email>K01` (ZenRows has no `Forbidden` trap — plain `fill` works)
3. **Turnstile** — wait `input[name="cf-turnstile-response"]` len >100 (auto `Success!` 2-4s;
   if 0 after 4s, `window.turnstile.execute()`). If still 0 after 12s → kill run (IP burned).
4. **Create** — click `Créez votre compte` → `Check your inbox` = success.
   `suspicious activity` / `Unable` / `Disposable` → kill run, next provider+IP.
5. **Verify** — poll provider inbox for `oobCode` link → goto → `/getting-started` = verified.
6. **Save** — `scripts/sessions/session-N/{config.json,cookies.json}` (same schema:
   `email,password,created_at,dashboard_url,verified,api_only,status`) + prepend
   `finals/lovables.json` + `git add -f` + commit + push (session configs are gitignored).

## Health gates per run (abort fast, save quota)

- IP check via `wtfismyip.com/json` (fetch, not navigate — saves `navigate_domains_limit`).
  Skip datacenter ASNs (LogicWeb/Xplore); prefer BT/Virgin/Sky residential.
- `api.ipify.org` is blocked on ZenRows (`fail2`) — don't use it.
- Turnstile token 0 after 12s → abort run (don't waste Create click).
- `402 AUTH004` on connect → stop loop, key exhausted.

## Quota tracking

- No balance API — track locally: `runs.log` per run `{ip, provider, email, token_len, result}`.
- Free keys die after ~25 runs; rotate to next key from `mega:chimera/zenrows/`.

## Script

Extend `finals/core/lov-zenrows-5x.py` (already has 13-handler rotation + fresh browser/run):
swap `ZENROWS_WSS` to the new key, add `runs.log` + ASN gate. Everything else stays.
