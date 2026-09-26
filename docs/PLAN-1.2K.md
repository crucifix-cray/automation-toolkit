# PLAN — reach 1.2k Railway

**Status: ready to run, blocked on one gate (mail pacing).** Numbers below come
from [STATE.md](STATE.md), measured 2026-09-26. Nothing here is a projection
except where marked.

## The gap

| | Count | Source |
|---|---|---|
| VERIFIED jars | 478 | `finals/railway_healthy.json` (per-jar canary) |
| Verified core sessions | 4 | canary on `sessions/session-1..51` |
| **Current usable** | **482** | |
| **Target** | **1200** | |
| **Shortfall** | **718** | |
| Must farm (95.5% yield) | **752** | new run measured 466/488 |
| With ~5% buffer | **790** | |

The 19 TRIAL_WALL jars host existing projects but cannot create new ones — they
are not capacity toward 1.2k.

## Capacity

| Resource | Have | Needed | Status |
|---|---|---|---|
| OnKernel keys | **101** (101/101 HTTP 200, full creds) | 101 | ✅ ready |
| Browser slots | **505/wave** at 5 browsers/key | 505 | ✅ ready |
| Waves | 752 ÷ 505 = **2** | 2 | |
| Farm hosts | 478 verified jars have project + `hlth-*` service → 478 × 8 = 3824 worker slots | ~101 hosts (505 ÷ 5) | ✅ ample |

Browser capacity is **not** the constraint. Two waves clear the target.

## ⚠️ Gate — do not skip

`mail_rotate.py` has never run on this box: `total_picks: 1`, empty pacing state.
The 2026-09-25 incident restricted 1220 of 1236 accounts because every signup
shared one mail provider while 294 proxies collapsed onto 10 egress IPs.

Before wave 1:

```bash
python3 ops/onk-rail-1k/mail_rotate.py stats     # confirm providers + pacing loaded
python3 ops/onk-rail-1k/mail_rotate.py pick --host sb01   # dry run one worker
```

Pacing is **90 s min gap per egress IP, 40 signups/IP/hour**. 752 signups
therefore requires **≥19 distinct active egress IPs** or the pacing constraint is
mathematically unsatisfiable and you will re-trigger the incident.

Provider pool is 6 weighted entries, 5 live (`22.do` pool is burned until Railway's
restriction window closes). At 505/wave that is ~150 signups per provider per
wave. That is the same concentration that burned run #1.

**Two ways to satisfy the gate, pick one:**
- **A — throttle.** Drop to ~200/wave so no provider exceeds ~40 signups/wave.
  4 waves instead of 2. Safe, slower.
- **B — widen the pool.** Add mail providers until no provider sees >40 signups
  per wave. 2 waves. Requires new providers.

## Second risk — retired

Proxy geography was a listed gate here. It is **no longer one**: the farm mints
its own country-targeted proxies on demand (`ensure_mobile_proxy(country="gb")`)
and the platform removed the proxy dependency — commit `62e62e30` makes proxying
opt-in via `--proxy`, default none. The US proxies visible in the OnK inventory
are pre-existing leftovers, not a constraint.

## Run order

1. Re-census the host pool — health drifts, Railway restricts on a delay.
   `python3 scripts/audit_state.py --census`
2. Satisfy the mail gate (A or B).
3. Wave 1 — 505 accounts, `--par` sized to respect the 10-sandbox/account cap
   (`refill_all.py SLOTS = 8`; Railway enforces 10 hard per account).
4. `materialize_jars.py` — **dedups by email**; run #1 produced duplicate emails,
   so check the dedup actually fired before counting.
5. `verify_up_down.py` — the UP_GOOD gate. **3–4/min at par 12, Railway-API
   bound.** 752 accounts ≈ 3–5 h of pure verification. This is the clock, not
   the signups.
6. `count_ready.py` — subtracts RECHECK_FAIL. That is the only number to quote.
7. Wave 2 for the remaining ~247.
8. Final canary re-census, then update STATE.md.

## What not to do

- Do not farm from the 2026-09-23 run — 1220/1236 are restricted and archived at
  `/home/alan/railway_burned_2026-09-26`.
- Do not fall back to the old farm script. The enhanced one is the only reason
  run #2 came out 95.5% healthy.
- Do not quote `UP_GOOD` as current health without a recheck pass.
- Do not resume the fleet before mail pacing is live.
