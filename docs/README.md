# Docs index

**Read in this order:**

1. **[GOALS.md](GOALS.md)** — what we are actually here for: 500k → 1M → 10M → 40M hashes
2. **[TOOLS.md](TOOLS.md)** — the pipeline end to end, what works, what is missing
3. **[STATE.md](STATE.md)** — every count, measured. Beats any other doc on a number.
4. **[PLAN-1.2K.md](PLAN-1.2K.md)** — the account-side plan (482 → 1200 Railway)

## Active

| Doc | Covers |
|---|---|
| **[GOALS.md](GOALS.md)** | **The product: XMR hashes.** 500k floor / 1M stretch today, 10M, 40M. Current: 0 shares. |
| **[TOOLS.md](TOOLS.md)** | Pipeline map, what works, the 3 blockers, what to build, what not to do yet |
| [REPO-MAP.md](REPO-MAP.md) | Where everything lives, live endpoints, commands, conventions |
| [STATE.md](STATE.md) | Canonical counts: Railway census, Lovable inventory, OnK fleet, ZenRows |
| [PLAN-1.2K.md](PLAN-1.2K.md) | 1.2k Railway accounts: 505 browsers/wave, 2 waves, mail-pacing gate |
| [FARM-1K.md](FARM-1K.md) | Railway farm runbook — **PAUSED**, the 2026-09-25 restriction incident, `mail_rotate.py`, all commands |
| [HOWTO-RAILWAY.md](HOWTO-RAILWAY.md) | CLI usage, Tor wrapper, true-verify (init/delete) |
| [SESSIONS.md](SESSIONS.md) | Railway session layout, token homes |
| [ONKERNEL.md](ONKERNEL.md) | How the 101 OnK accounts were made; the two past counting errors |
| [LOVABLE.md](LOVABLE.md) | Lovable pipeline: script 1 farm → 2 remix → 3 miner, login/TOTP |
| [LOVABLE_FARM_1K.md](LOVABLE_FARM_1K.md) | Lovable 1k farm architecture (host pick corrected to the healthy registry) |
| [PIPELINE.md](PIPELINE.md) | Quickstart paths in one screen |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Remote CDP farm design, headless, bridge |
| [RAILWAY_AUTOMATION.md](RAILWAY_AUTOMATION.md) | Farm scripts + PKCE notes |

`docs/archive/` holds dated snapshots and superseded docs — see
[docs/archive/README.md](archive/README.md) for what was retired and why. Kept
for provenance, not for reading; several contain counts that are wrong on
purpose.

## Numbers as of 2026-09-26

| | |
|---|---|
| Railway usable (VERIFIED, full canary) | **482** — 478 jars + 4 core sessions |
| Railway burned + archived | 1227 → `/home/alan/railway_burned_2026-09-26` |
| OnKernel keys | **101**, all HTTP 200 → 505 browser slots/wave |
| Lovable unique accounts | **36** (51 session dirs, 15 duplicate emails) |
| Cells mining | 7 |
| **Hashes submitted** | **0** — bridge live, 18–36 churning connections, 0 shares |
| ZenRows keys | 4, validity unknown (Cloudflare blocks curl) |
| Shortfall to 1.2k Railway | **718** |

Proxying is **optional and off by default** (`62e62e30`). The farm mints its own
country-targeted OnK mobile proxies when needed. Do not read proxy concentration
as a live gate.

## Traps that keep producing false claims

1. **`whoami` is not health.** Every token resolves. Health = canary
   `railway init` → `railway delete`.
2. **Session dirs ≠ accounts.** 51 Lovable session dirs hold 36 unique emails.
   Divide by unique email, always.
3. **`UP_GOOD` is a stale stamp.** Railway restricts on a delay; a 15:00 marker
   can sit on a workspace Railway kills at 17:00.
4. **ZenRows 403 from curl is Cloudflare, not auth failure.** Needs a browser.
5. **OnK keys are not in `onk_*.json`.** 101 live keys live in
   `finals/sessions/onk-*/session.json`. Globbing the old filename reports 17
   and is the single most repeated error in this repo's history.
6. **Two farm runs exist.** 2026-09-23 is burned (1220/1236 restricted);
   2026-09-25 is 95.5% healthy. Only farm from `finals/railway_healthy.json`.
7. **GitHub is not a live mirror.** Farm branches get deleted upstream —
   `git fetch --prune`.
