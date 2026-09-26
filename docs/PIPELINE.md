# Pipeline quickstart (2026-09-24)

| What | Where |
|---|---|
| OnKernel unlocked jars | `finals/sessions/onk_*.json` + [ONKERNEL.md](ONKERNEL.md) |
| **Lovable 1k farm** | [LOVABLE_FARM_1K.md](LOVABLE_FARM_1K.md) — Ubuntu services on VERIFIED jars |
| Railway VERIFIED jars | `finals/railway_healthy.json` (**478 verified**, use these) |
| Bridge | `wss://chimera-bridge-production-0703.up.railway.app` |
| Org credit reset | `src/onkernel/org_reset.py` |

**OnK pool:** **101 keys, 101/101 verified HTTP 200** with full creds
(`finals/onk_fleet.json`). At 5 browsers/key = **505 slots per wave**.
Registry: `finals/onk_fleet.json` — read capacity there, not from tag labels.

**Counts live in [STATE.md](STATE.md).** Two farm runs exist: the 2026-09-23 run
is **burned** (1220/1236 restricted), the 2026-09-25 enhanced run is **95.5%
healthy** (466/488). Only farm from the healthy registry.

**1.2k target plan:** [PLAN-1.2K.md](PLAN-1.2K.md) — 505 browsers/wave, 2 waves,
with the mail-pacing gate that must run first.

**Must scrub `RAILWAY_*`** inside workers or service-verify steals the host identity.

**DB:** GitHub tracks OnK jars + `farmed-*` MADE jars + `farm/lov-*` Lovable pushes.
