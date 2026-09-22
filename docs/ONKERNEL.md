# OnKernel Accounts DB (GitHub as DB — owner decision 2026-09-21)

Farmed via `src/onkernel/account_creation_cdp.py --end --22do` (CDP browser cloud,
22.do one-dot Gmail, Clerk OTP). After signup each account runs
`unlock_trial.py`: proxies → start a trial → just exploring → start trial.
Full records (email + password + api_key + cookies + storage trios) live under
`finals/sessions/onk_<ts>_<pid>.*` — explicit `git add -f` exception to the
`onk_*.json` ignore rule.

Password (all): `GmailK01!`. Pointer: `finals/sessions/latest_onk.json`.

**Pool policy (2026-09-22):** only `tag=unlocked` Batch B. Batch A / locked accounts
removed from disk and git. No new OnK farming for now — reuse these 10.

## Batch B — 2026-09-22 (10, `tag=unlocked`)

Trial unlocked; Clerk `__refresh_*` + `__session` + `.storage.json` present on each trio.
API-verified: `GET/POST https://api.onkernel.com/proxies` → mobile US available.

| session file | email | key prefix | tag |
|---|---|---|---|
| `onk_1790079465_170355.json` | smoottel.la206@gmail.com | `sk_dcbe0c32-c925-9` | unlocked |
| `onk_1790079494_170590.json` | lilli.anaparshsmm18@gmail.com | `sk_1bd77c6d-e57e-2` | unlocked |
| `onk_1790079514_171090.json` | lis.awscott94@gmail.com | `sk_749b04ce-3a4a-c` | unlocked |
| `onk_1790079548_170866.json` | mag.giezairetncm@gmail.com | `sk_a6784262-d3da-e` | unlocked |
| `onk_1790079557_171591.json` | jave.nskinstle77@gmail.com | `sk_d00b152f-75a8-e` | unlocked |
| `onk_1790079560_171388.json` | kenethsurrey.clm36@gmail.com | `sk_21eaf06c-6de8-5` | unlocked |
| `onk_1790079589_171821.json` | antoninan.rodriquezn38@gmail.com | `sk_69930520-f60b-8` | unlocked |
| `onk_1790079871_171277.json` | brigittemm.arloweo82@gmail.com | `sk_1bfe2de7-6d26-4` | unlocked |
| `onk_1790080303_183512.json` | pion.tkowskiheffley84@gmail.com | `sk_dbb4caaf-ddbc-1` | unlocked |
| `onk_1790080310_184023.json` | grosjeanpretz.548@gmail.com | `sk_ee2acef6-c7d9-0` | unlocked |

## Railway spreader plan (100-wide → 1k)

**Do 100 browsers — not on this laptop.** Spread workers across the verified Railway
fleet (`Documents/railways/session-1..44`). Local host only orchestrates / ships jobs;
Playwright+CDP clients run **on Railway sandboxes**, using Batch B OnK keys + unique
mobile-US proxies.

| Knob | Value |
|---|---|
| OnK accounts | **10** Batch B (`tag=unlocked`) |
| Concurrent browsers | **100** (spread on Railway fleet, not local) |
| Fleet workers | **44** Railway sessions (grow as new MADE land) |
| Binding sketch | ~2–3 OnK browser slots per Railway worker → ~100 total |
| Waves to ~1k | reuse same 10 OnK keys across waves |
| Proxy | unique `mobile-us-<hex>` per browser, `type=mobile`, `country=us` |
| Orchestrator (local thin) | `src/railway/farm_onk_1k.py` — **must dispatch to Railway**, not spawn 100 local Playwright |
| OnK pool files | `finals/sessions/onk_*.json` (+ cookies/storage) |

```bash
# WRONG on 15Gi laptop — OOM (see run notes)
# LD_PRELOAD="" python3 src/railway/farm_onk_1k.py --target 1000 --par 100

# RIGHT: spread --par 100 across Railway session-* workers (impl TBD / in progress)
# each Railway sandbox runs a thin farm worker with 1–3 OnK browsers
```

Logs (when local probe only): `/home/alae/onk-rail-1k/`. Verified Railways stay at
`/home/alae/Documents/railways/session-*` (**44** goods as of stop).

### Run notes — 2026-09-22 (stopped)

- Local `--par 100` / `--par 40` **OOM’d** the 15 GiB host — proved why spread must be
  on Railway, not localhost.
- `mail.tm` **HTTP 429** under blast; prefer 22.do primary.
- Kill leftover local clients: `pkill -9 -f farm_onk_1k; pkill -9 -f 'railway/account_creation.py'`.
- Next: ship farm workers onto `session-1..44`, target **100** concurrent OnK browsers
  fleet-wide, then wave toward 1k.

## Optional: farm more OnK (paused)

```bash
KERNEL_API_KEY=<batch-b-key> LD_PRELOAD="" python3 src/onkernel/account_creation_cdp.py --end --22do
```

New accounts must unlock trial + save cookies/`__refresh_*` before `tag=unlocked`.

## Unlock trial

```bash
from unlock_trial import unlock_full_potential
await unlock_full_potential(page)
# flow: /proxies → "start a trial" → "just exploring" → "start trial"
```

## Rotation (credit exhausted → fresh key, same account)

`src/onkernel/org_reset.py` loads `<session>.storage.json`, deletes org, creates new
org+slug, mints fresh `auto-main` key, unlocks trial, updates same JSON.
