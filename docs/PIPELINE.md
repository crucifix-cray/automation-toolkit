# Pipeline quickstart (2026-09-24)

| What | Where |
|---|---|
| OnKernel unlocked jars | `finals/sessions/onk_*.json` + [ONKERNEL.md](ONKERNEL.md) |
| **Lovable 1k farm** | [LOVABLE_FARM_1K.md](LOVABLE_FARM_1K.md) — Ubuntu services on `farmed-*` |
| Railway MADE jars | `finals/sessions/farmed-*` (**1236**; use **`[236:]` = 1000**) |
| Bridge | `wss://chimera-bridge-production-0703.up.railway.app` |
| Org credit reset | `src/onkernel/org_reset.py` |

**OnK pool:** ~101 healthy unlocked × 10 mobile browsers ≈ 1010 slots. Prefer **last**
keys (early ones burned on preflight). Probe: `/tmp/onk-credit-probe.json`.

**1k Lovable (current plan):** each of `farmed-*[236:]` gets a persistent **Ubuntu
service**; run `farm_lovable_ultimate.py --once` on it (multi-country mobile, soft
2FA, shuffled zenvex). See [LOVABLE_FARM_1K.md](LOVABLE_FARM_1K.md).

**Older Railway MADE path** (Holy account farm via sandboxes on Documents/railways)
is separate; do not confuse with the Lovable 1k Ubuntu-service fleet.

**Must scrub `RAILWAY_*`** inside workers or service-verify steals the host identity.

**DB:** GitHub tracks OnK jars + `farmed-*` MADE jars + `farm/lov-*` Lovable pushes.
