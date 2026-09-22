# Pipeline quickstart (2026-09-22)

| What | Where |
|---|---|
| OnKernel ×10 unlocked | `finals/sessions/onk_*.json` + [ONKERNEL.md](ONKERNEL.md) |
| Railway ×44 verified | `/home/alae/Documents/railways/` + [SESSIONS.md](SESSIONS.md) |
| Railway farm (safe width) | `src/railway/farm_onk_1k.py --target 1000 --par 20` |
| Bridge | `wss://chimera-bridge-production-0703.up.railway.app` |
| Org credit reset | `src/onkernel/org_reset.py` |

**OnK pool:** Batch B only (`tag=unlocked`). Batch A deleted. No new OnK farm for now —
10 keys toward 1k Railways; **local `--par ≤20`** (par 40/100 OOM’d 15 GiB host).

**DB:** GitHub as DB for OnK session trios (`git add -f finals/sessions/onk_*`). Railway
tokens stay under `Documents/railways/` (local).
