# Pipeline quickstart (2026-09-22)

| What | Where |
|---|---|
| OnKernel ×10 unlocked | `finals/sessions/onk_*.json` + [ONKERNEL.md](ONKERNEL.md) |
| Railway ×44 verified | `/home/alae/Documents/railways/` + [SESSIONS.md](SESSIONS.md) |
| Farm 100-wide | **spread on Railway fleet** (not local) — see [ONKERNEL.md](ONKERNEL.md) |
| Bridge | `wss://chimera-bridge-production-0703.up.railway.app` |
| Org credit reset | `src/onkernel/org_reset.py` |

**OnK pool:** Batch B only (`tag=unlocked`). Batch A deleted. No new OnK farm for now.

**100 browsers:** run across Railway `session-*` workers. Local `--par 100` OOMs the
15 GiB laptop — do not.

**DB:** GitHub as DB for OnK session trios (`git add -f finals/sessions/onk_*`). Railway
tokens stay under `Documents/railways/` (local).
