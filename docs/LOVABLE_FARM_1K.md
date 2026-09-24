# Lovable farm — 1k one-shot (Ubuntu services)

**Status (2026-09-24):** inventory + farm scripts ready. Next = deploy Ubuntu
services on farmed jars and run `farm_lovable_ultimate.py` on them.

## Architecture (owner decision)

| Layer | What |
|---|---|
| **Hosts** | `finals/sessions/farmed-*` Railway CLI jars (**1236** total) |
| **Slice** | Sorted list, **skip first 236** → take **`jars[236:]` = 1000** |
| **Compute** | Persistent **Ubuntu services** on each jar (not sandboxes) |
| **Browsers** | OnKernel: ~**101** healthy unlocked keys × **10** mobile browsers ≈ **1010** slots |
| **Script** | `src/lovable/farm_lovable_ultimate.py --once` (mail chain → signup → soft-2FA → `farm/lov-*` GH push) |
| **Proxies** | OnK `type=mobile`, multi-country (not US-only): `gb,de,fr,nl,ie,es,it,be,at,se` |

Each farmed jar already has: CLI tokens (`.railway` + `railway_cli_config.json`),
`verified.json` (project + `hlth-*` service ids), email. Those are the 1k Ubuntu
service homes. The farm script runs **on** those Ubuntu services.

## Jar pick (hard rule)

```text
homes = sorted(verified farmed-*)
fleet = homes[236 : 236+1000]   # NOT from 0
```

First usable: `farmed-cxs37-r8a2185-804e278ba6` … last: `farmed-w3s9-sb09-7a4b5ee540`.

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

1. **Deploy Ubuntu** persistent service on each of `jars[236:]` (1k).
2. **Inject** secrets (`HOLY_SECRET_KEY`, decrypted GH token, one OnK key per
   ~10 workers) + run `farm_lovable_ultimate.py --once` with multi-country mobile.
3. **Watch** `farm/lov-*` branches / MADE session count; soft-2FA jars count as kept.
4. Do **not** re-blast from jar index 0; do **not** treat Documents/railways×44 as the 1k fleet.

## Preflight already done

- Soft-2FA save path, multi-country mobile, last-OnK key pick, random zenvex.
- Small Railway sandbox waves on `Documents/railways/session-1` (warmup only).
- Jar inventory confirmed: **1236** farmed, **1000** from offset 236.
