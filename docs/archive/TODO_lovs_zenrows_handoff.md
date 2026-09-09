# TODO — lovs ZenRows farm handoff (2026-09-07, PC1 → PC2)

## TODO
1. **Beat the 3-min session lifetime.** ZenRows CDP sessions die ~170-180s after creation even idle (proven `/tmp/lifeprobe.log`: `connected=True` → `False` at t+180s, no traffic). Our flow (dispose tab + signup + password + Turnstile) crosses it and dies mid-Turnstile (`Target page...closed`). Options in order: (a) shrink flow under ~150s — cut static waits (`wait_for_timeout(3200)`, 12s quick-path, 4s post-Continue), skip solver entirely when token auto-appears (probes show 837 with ZERO clicks); (b) reconnect-resume supervisor: on `TargetClosedError` before Create, fresh session + fast refill (reuse email, skip dispose) + jump to token wait, one resume max.
2. **Skip ClickSolver by default.** Timeline (`/tmp/lovrun4.log` timestamps): checkbox_ready=True, ClickSolver clicks, `success element does not exist`, attempt 2 `iframes not found`, browser closed. Probes prove token 837 auto-appears with no interaction — clicking may be what flags/kills. Only click if token stays 0 after 8s AND checkbox present.
3. Then farm loop: `lov-api-effective.py` already takes key from `ZENROWS_API_KEY` env + `--proxy-country` (no code change needed for key swap). Add `runs.log` + ASN gate per `docs/LOVABLE_FARM_NEWKEY_BLUEPRINT.md`.
4. Save verified accounts to `scripts/sessions/session-N/` + prepend `finals/lovables.json`, `git add -f`, commit, push.

## PROBE EVIDENCE (all with key `1a5d93...&proxy_country=gb`, `LD_PRELOAD=""`)
- `lifeprobe.py`: idle session dies t+170-180s. Hard lifetime, not traffic.
- `tsprobe2.py`: email submit only (no password) → token **837 auto**, alive 90s+. Dispose tab open too.
- `tsprobe3/4/7`: full-page screenshot, patchright client, screenshot loop — all innocent, sessions live.
- `tsprobe5/6`: password fill (+stealth init scripts) → token 837, alive 60s.
- Conclusion: every component survives alone. Killer = wall-clock lifetime vs slow flow (88s observed for a "12s" wait = cloud CDP latency; `d32bb8d` batched quick-path to 1 evaluate/tick to fight it).
- Latest run (`/tmp/lovrun5.log`): mailbox `clie.nsantia@gmail.com`, egress `94.9.46.69 Sky`, password len 8 OK, checkbox_ready=True, ClickSolver fail, browser closed.

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
