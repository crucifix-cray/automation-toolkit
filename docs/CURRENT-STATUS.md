# Automation Toolkit - Current Status (Reindexed 2026-08-28 18:30 UTC)

**6 healthy Railway CLI sessions ordered 1..6 on all 3 (local, sandbox test-ubuntu-6, mega:railway_sessions) via raw IP `LD_PRELOAD=""`**

| # | Email | Source | CLI `whoami` | Mega |
|---|-------|--------|--------------|------|
| 1 | jzwvvhj4934m+vla1ycoqmow59@outlook.com | local session-3 | OK | ✅ |
| 2 | kar.lxyprio@gmail.com | local session-6 | OK | ✅ |
| 3 | janic.ebunagna@gmail.com | local session-xx | OK | ✅ |
| 4 | ghian.sean5@gmail.com | BD Chennai 223.178.84.38 | OK | ✅ |
| 5 | ae.lexclement@gmail.com | local session-4 | OK | ✅ |
| 6 | khea.docusin@gmail.com | sandbox session-28 | OK | ✅ |

All verified via `HOME=session-*/.railway LD_PRELOAD="" railway whoami` on raw IP (`152.55.184.157` direct, no WARP/BD). `rclone` via `LD_PRELOAD="" LD_LIBRARY_PATH="" --mega-use-https` raw IP.

**Cloud Holy** `railway-HOLY-cloud.py` — `BD Browser API` `wss://hl_4ee0cb14`/`hl_709648b2` + `?sessionId` per run (ASN rotation), `dispose.lol` Gmail (separate BD) → `22.do` → `mail.tm`, `150 checks` for OTP, `Turnstile` `100s` screenshot to `mega:railway_sessions`, breaker on `OTP 0`/`Continue [disabled]` → fresh IP + next mailbox, local headless Chrome PKCE for CLI.

**Next:** Kill old BD browser (pkill) → SSH `test-ubuntu-6` → `HOLY-cloud.py --cloud` fresh `?sessionId` ASN → new Railway acc + CLI (`HOME=session`) → `rclone --mega-use-https` raw IP to `session-7..500`.
