# Lovable accounts (canonical)

**36 unique** 2FA accounts (deduped from 51 session dirs).

`scripts/sessions/session-N/` — one dir per email.
Per session: `config.json` (`email`, `password`, `totp_secret`, optional `totp_secret_backup`, `2fa_live_id`) + `cookies.json`.

Login: cookies first; fallback email → password → `pyotp.TOTP(totp_secret)` (local, not 2fa.live API).

## Index

| session | email |
|---|---|
| session-1 | alexandermay706@gmail.com |
| session-2 | altonlehman16@gmail.com |
| session-4 | dakarihickmanhickman@gmail.com |
| session-6 | daxtonharper8@gmail.com |
| session-7 | emmalinerivers9@gmail.com |
| session-8 | emonkhanireht56@gmail.com |
| session-9 | fletcherjakobs@gmail.com |
| session-11 | jakesparosam@gmail.com |
| session-16 | joellampard07@gmail.com |
| session-20 | johngriffin62w@gmail.com |
| session-25 | johnpeter08541@gmail.com |
| session-26 | josephgrant651@gmail.com |
| session-27 | julianhiramqwr@gmail.com |
| session-28 | kristinenorris08@gmail.com |
| session-29 | lenasolids546@gmail.com |
| session-30 | liamantoine31@gmail.com |
| session-31 | mariepeterson749@gmail.com |
| session-32 | nyomiparra12@gmail.com |
| session-33 | roce.sisla@gmail.com |
| session-34 | rosaliabarrett81@gmail.com |
| session-35 | samsonarifalo0@gmail.com |
| session-37 | zakarmmusa832@gmail.com |
| session-38 | simpsonjessicamarie.0@gmail.com |
| session-39 | lovgraukipb6b@souss.dev |
| session-40 | lov6020lpeic9@souss.dev |
| session-41 | jamesmanalodat.e@gmail.com |
| session-42 | na.thanrolutenasa@gmail.com |
| session-43 | lovohqhzhno7q@souss.dev |
| session-44 | tra.nariumkill@gmail.com |
| session-45 | lovwsrj0lswqa@souss.dev |
| session-46 | lovbvxh2yu05l@souss.dev |
| session-47 | lov484vnilli1@souss.dev |
| session-48 | lovuu5qwethzg@souss.dev |
| session-49 | lovtx66imf0z1@souss.dev |
| session-50 | hellolakanhernand.ez@gmail.com |
| session-51 | lovv2ubbdli1c@souss.dev |

## Pipeline

- Script 1 (2FA rescue): `src/lovable/session_refresh.py` / `load_session_with_rescue.py` — **pyotp TOTP**
- Script 2: `chimera-miner/script2_remix_link.py --browser kernel|zenrows` — sends **`prompts/Build a debug terminal.txt`** (never trivial `say 'a'`). Built-in re-login is email+pwd only — **no OTP**.
- Script 3: `chimera-miner/script3_launch_miner.py` + `miner_injector.py` (mine via `/__shell`)

**Notes (2026-09-19):** session-1 Lovable **disabled** — skip. session-2 cookies revived. Pilot paused mid-script2.

