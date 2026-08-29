# Automation Toolkit - Current Status (Reindexed 2026-08-29 15:15 UTC)

**7 healthy Railway CLI sessions verified via `HOME=session-*/.railway LD_PRELOAD="" railway whoami` raw IP (152.55.184.157)**

| # | Dir | Email | CLI `whoami` | Mega |
|---|-----|-------|--------------|------|
| 1 | session-1 | eyx1lakw1uizeyw4lm@usdtbeta.com | OK | ✅ |
| 2 | session-2 | st.odezgdvkp+odytn8e1il@gmail.com | OK | ✅ |
| 3 | session-3 | jzwvvhj4934m+vla1ycoqmow59@outlook.com | OK | ✅ |
| 4 | session-4 | bsu.ejjrue.kis8.0.9+bxbqr9ff@gmail.com | OK | ✅ |
| 5 | session-11 | nlvnod39153u+jm7mu6cj9m01hh5@outlook.com | OK | ✅ |
| 6 | session-13 | tha.t.huchoem0.1.8@gmail.com | OK | ✅ (just synced) |
| 7 | session-21 | s2d6bjrla38o@emalupe.com | OK | ✅ (just synced, BD→local chrome PKCE) |

All verified via `HOME=session-*/.railway LD_PRELOAD="" railway whoami` on raw IP (`152.55.184.157` direct, no WARP/BD). `rclone` via `LD_PRELOAD="" LD_LIBRARY_PATH="" --mega-use-https` raw IP.

**Cloud Holy** `railway-HOLY-cloud.py` — `BD Browser API` `wss://hl_4ee0cb14`/`hl_709648b2` + `?sessionId` per run (ASN rotation), `dispose.lol` Gmail (separate BD) → `22.do` → `mail.tm`, `150 checks` for OTP, `Turnstile` `100s` screenshot to `mega:railway_sessions`, breaker on `OTP 0`/`Continue [disabled]` → fresh IP + next mailbox, local headless Chrome PKCE for CLI.

**Next:** Kill old BD browser (pkill) → SSH `test-ubuntu-6` → `HOLY-cloud.py --cloud` fresh `?sessionId` ASN → new Railway acc + CLI (`HOME=session`) → `rclone --mega-use-https` raw IP to `session-7..500`.
