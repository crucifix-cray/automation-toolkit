# Lovable farm — 1k one-shot (Ubuntu services)

**Status (2026-09-24):** inventory + farm scripts ready. Next = deploy Ubuntu
services on farmed jars and run `farm_lovable_ultimate.py` on them.

> **Corrected 2026-09-25.** Jar count is **1724**, not 1236 — and after the
> 2026-09-26 census only **478** of those can create projects. OnKernel capacity is
> **101 keys, all verified** (not the 17 seen mid-audit). Most *old* jars answer
> `restricted`; the 2026-09-25 run does not. See **[STATE.md](STATE.md)** for
> measured numbers, **[PLAN-1.2K.md](PLAN-1.2K.md)** for the wave plan, and
> **[FARM-1K.md](FARM-1K.md)** for the PAUSED status + the restriction incident.

## Architecture (owner decision)

| Layer | What |
|---|---|
| **Hosts** | VERIFIED Railway jars — `finals/railway_healthy.json` (**478**) |
| **Slice** | Sorted list, **skip first 236** → take **`jars[236:]` = 1000** |
| **Compute** | Persistent **Ubuntu services** on each jar (not sandboxes) |
| **Browsers** | OnKernel: **101** verified keys × 5 mobile browsers = **505** slots/wave |
| **Script** | `src/lovable/farm_lovable_ultimate.py --once` (mail chain → signup → soft-2FA → `farm/lov-*` GH push) |
| **Proxies** | Optional. Farm mints its own country-targeted OnK mobile proxies on demand; platform proxying is opt-in and defaults to off (`62e62e30`). |

Each farmed jar already has: CLI tokens (`.railway` + `railway_cli_config.json`),
`verified.json` (project + `hlth-*` service ids), email. Those are the 1k Ubuntu
service homes. The farm script runs **on** those Ubuntu services.

## Jar pick (hard rule)

```text
# OLD (do not use — that run is burned):
#   homes = sorted(verified farmed-*); fleet = homes[236:1236]
# CURRENT: take every jar canary-verified green
from finals/railway_healthy.json -> [j for j in jars if j.health == "VERIFIED"]   # 478
```

Hosts must be re-censused before each run — health drifts, Railway restricts on a
delay. `python3 scripts/audit_state.py --census`.

## Soft 2FA

If TOTP enable fails after a verified signup, still save session + push
`farm/lov-*` with `2fa_pending` (do not discard). See `farm_lovable_ultimate.py`
+ `src/railway/gh_push.py`.

## Mail

Zenvex domains shuffled (not fixed first-four). Chain: zenvex → … in
`src/lovable/mail_chain.py`.

## OnK keys

Prefer **last** healthy unlocked keys (`/tmp/onk-credit-probe.json` skips burned
api_keys). Early keys were used on preflight waves.

## Scripts in repo

| File | Role |
|---|---|
| `src/lovable/farm_lovable_ultimate.py` | One-shot Lovable farm (OnK CDP) |
| `src/lovable/farm_lovable_rail.py` | Preflight / sandbox wave helper (earlier path) |
| `src/lovable/mail_chain.py` | Mailbox acquire |
| `src/lovable/session_state.py` | Full cookie/IDB persist |
| `src/railway/gh_push.py` | Push MADE jar → `farm/lov-*` on GitHub |
| `src/railway/farmed_host_farm.py` | Multi-host over `farmed-*` CLI homes |

## Next (ordered)

1. **Deploy Ubuntu** persistent service on each VERIFIED jar (see
   `finals/railway_healthy.json`, 478 of them).
2. **Inject** secrets (`HOLY_SECRET_KEY`, decrypted GH token, one OnK key per
   ~10 workers) + run `farm_lovable_ultimate.py --once`.
3. **Watch** `farm/lov-*` branches / MADE session count; soft-2FA jars count as kept.
4. Do **not** re-blast from jar index 0; do **not** treat Documents/railways×44 as the 1k fleet.

## Preflight already done

- Soft-2FA save path, last-OnK key pick, random zenvex.
- Small Railway sandbox waves on `Documents/railways/session-1` (warmup only).
- Jar inventory confirmed: **478 canary-verified** usable (see STATE.md).
