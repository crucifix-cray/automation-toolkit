# Index

**[STATE.md](STATE.md) is the single source of truth for counts.** Every number
in it was measured live on 2026-09-25. Other docs may describe *how*; if they
disagree with STATE.md on a *count*, STATE.md wins.

| Doc | Covers |
|---|---|
| **[STATE.md](STATE.md)** | **Canonical counts** — Railway census, Lovable inventory, OnK verdicts, ZenRows status |
| [FARM-1K.md](FARM-1K.md) | 1k Railway farm runbook — **PAUSED**, mass-restriction incident, `mail_rotate.py` fix, all commands |
| [ONKERNEL.md](ONKERNEL.md) | OnK farming history + how keys were made (live counts live in STATE.md) |
| [SESSIONS.md](SESSIONS.md) | Railway session layout + token homes + true-verify rules |
| [HANDOFF-BLAST.md](HANDOFF-BLAST.md) | Legacy 50×10 Lovable blast (superseded — never produced projects) |
| [LOVABLE_FARM_1K.md](LOVABLE_FARM_1K.md) | 1k Lovable farm architecture (counts corrected, see STATE.md) |
| [PIPELINE.md](PIPELINE.md) | Quickstart paths (OnK + Railway + bridge) |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Remote CDP farm, headless, viral bridge |
| [RAILWAY_AUTOMATION.md](RAILWAY_AUTOMATION.md) | Railway farm scripts + PKCE notes |
| [HOWTO-RAILWAY.md](HOWTO-RAILWAY.md) | CLI usage, Tor wrapper, true-verify (init/delete) |
| [ONKERNEL_ACCOUNTS_2026-09-09.md](ONKERNEL_ACCOUNTS_2026-09-09.md) | Historical OnK snapshot |

Evidence files (machine-readable, regenerable):

| File | Contents |
|---|---|
| `finals/railway_healthy.json` | **the usable fleet** — 478 VERIFIED jars, per-jar home/email/project |
| `finals/railway_census.json` | full canary verdict for all 1724 jars + 51 sessions |
| `finals/railway_health_split.json` | healthy / trial-wall / burned partition |
| `finals/lovable_inventory.json` | per-session mail/pwd/totp/cookies |
| `finals/lovable_summary.json` | session count vs unique-account count |
| `finals/onk_key_status.json` | per-key working / hit-limit |
| `finals/zenrows_key_status.json` | per-key status + why curl can't test it |

## Traps that keep causing false claims

1. **`whoami` is not health.** Every token resolves. Health = canary
   `railway init` → `railway delete`. See HOWTO-RAILWAY.md.
2. **Session dirs ≠ accounts.** 51 Lovable session dirs hold only **36 unique
   emails**. Always divide by unique email.
3. **`UP_GOOD` is a stale stamp.** Railway restricts on a delay; a marker from
   15:00 can sit on a workspace Railway kills at 17:00. Never quote it as
   current health.
4. **ZenRows 403 from curl is Cloudflare, not auth failure.** Needs a real
   browser to test.
5. **Marker counts drift, GitHub is not a live mirror.** Farm branches get
   deleted upstream; `git fetch --prune`.
