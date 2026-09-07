# TODO — lovs ZenRows farm handoff (2026-09-07, PC1 → PC2)

## TODO
1. Rerun single test: `LD_PRELOAD="" ZENROWS_API_KEY="1a5d93cda0d10ac0bd9ab3da3fa93019f126397a" python3 finals/core/lov-api-effective.py --proxy-country gb --end` and capture FULL log to file (last run was aborted mid-Turnstile, no full log saved).
2. Fix Turnstile solver path: ClickSolver raises `Cloudflare checkbox not found or not ready`, then browser dies mid-7s-wait (`Target page, context or browser has been closed` at `lov-api-effective.py:669` keepalive). Suspects: (a) ClickSolver closes/kills page on failure, (b) ZenRows session timeout, (c) widget iframe not loaded when probed. Guard: only run ClickSolver if `iframe[src*="challenges.cloudflare.com"]` exists AND checkbox present; skip straight to `turnstile.execute()` + coordinate click.
3. Then farm loop: `lov-api-effective.py` already takes key from `ZENROWS_API_KEY` env + `--proxy-country` (no code change needed for key swap). Add `runs.log` + ASN gate per `docs/LOVABLE_FARM_NEWKEY_BLUEPRINT.md`.
4. Save verified accounts to `scripts/sessions/session-N/` + prepend `finals/lovables.json`, `git add -f`, commit, push.

## DONE (PC1, this session)
- New key `1a5d93...&proxy_country=gb` verified live: fresh GB residential IP per browser (80.3 / 81.106 / 88.97 Virgin/YouFibre).
- Root-caused password bug: `keyboard.type` landed only 2 chars (`len=2`) → form invalid → Turnstile never rendered. Fixed `lov-api-effective.py:1147-1165` → `fill()` first + length verify + one retry + hard fail (commit `5e18e12`, compiles OK).
- Second test run with fix: password passed, Turnstile reached, but ClickSolver failed (checkbox not found) and browser closed during token wait. Full log NOT saved (run aborted) — see TODO 1.
- Blueprint: `docs/LOVABLE_FARM_NEWKEY_BLUEPRINT.md` (pushed `a5d5ceb`). Key finding: `lov-api-effective.py` is the P0 seed script (not `lov-zenrows-5x.py`, which is only the mail-rotation shell).

## Key facts for PC2
- WSS: `wss://browser.zenrows.com?apikey=1a5d93cda0d10ac0bd9ab3da3fa93019f126397a&proxy_country=gb`
- Proven-good account pattern: `dispose.lol` Gmail + `<email>K01`, Turnstile token 837-858 auto on GB 2-4s.
- `api.ipify.org` blocked on ZenRows — use `wtfismyip.com/json` via fetch (not navigate, saves domain limit).
- Free keys die ~25 runs (`402 AUTH004`); this key is fresh.
- Always run with `LD_PRELOAD=""` (Tor wrapper breaks API calls).
- Sessions live in `scripts/sessions/session-1..37` (37 have 2FA secrets); new farm accounts continue numbering.
