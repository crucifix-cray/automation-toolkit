# Pipeline quickstart (2026-09-23)

| What | Where |
|---|---|
| OnKernel unlocked jars | `finals/sessions/onk_*.json` + [ONKERNEL.md](ONKERNEL.md) |
| Railway fleet | **51** in `services.json` / `sessions/session-1..51` — [SESSIONS.md](SESSIONS.md) |
| Farm → 1k MADE | Spread on Railway workers (not local) — [ONKERNEL.md](ONKERNEL.md) |
| Bridge | `wss://chimera-bridge-production-0703.up.railway.app` |
| Org credit reset | `src/onkernel/org_reset.py` |

**OnK pool:** Batch B + newer unlocked jars tracked in git. Farm more OnK only when needed for browser slots.

**1k Railway MADE:** `51 × ~20 waves`. Laptop orchestrates; each Railway runs Holy with a
fresh OnK **mobile** browser. **Paused** after one green pilot on `session-40`
(`finals/sessions/farmed-pilot-session-1/`). Resume with a 50-wide wave when ready.

**Must scrub `RAILWAY_*`** inside sandboxes or service-verify steals the host cell identity.

**DB:** GitHub tracks OnK jars + pilot MADE jar. Live Railway CLI tokens for the 51
fleet stay under `sessions/` / `Documents/railways/`.
