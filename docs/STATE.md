# STATE — canonical inventory (single source of truth)

**Generated 2026-09-25 by direct measurement, not from prior docs.** Every number
below was produced by a live test on this box. Supersedes the jar/session/OnK
counts in `LOVABLE_FARM_1K.md`, `ONKERNEL.md`, `SESSIONS.md`, and `README.md`,
which are stale and contradict each other.

Raw evidence: `finals/railway_census.json`, `finals/onk_key_status.json`,
`finals/railway_census.json`, `finals/lovable_inventory.json`.
Regenerate with `python3 scripts/audit_state.py`.

---

## 1. Railway

Two populations. `whoami` is **not** health — it only proves a token resolves.
Health = canary `railway init` → `railway delete`. The census below is that test.

| Population | Count | Auth (whoami) |
|---|---|---|
| Core sessions `sessions/session-1..51` | 51 | 51/51 |
| Farmed jars `finals/sessions/farmed-*` | 1724 | 1724/1724 |
| **Total** | **1775** | **1775** |

Canary census — **every jar tested individually**, not sampled
(`init` → `delete`, real writes, `finals/railway_census.json`):

| Run | Date | Jars | verified | restricted | trial-wall | link-fail |
|---|---|---|---|---|---|---|
| First run | 2026-09-23 | **1236** | **12** | **1220** | 3 | 1 |
| **New run** (enhanced script) | 2026-09-25 | **488** | **466** | 5 | 16 | 1 |
| **Total** | | **1724** | **478** | 1225 | 19 | 2 |

**The first run is burned — 98.7% restricted.** Those 1220 workspaces were
restricted by Railway and never recovered.

**The new run is 95.5% verified (466/488).** The enhanced farm script did fix
the restriction problem. This is the number that matters for capacity.

### Current fleet after cleanup (2026-09-26)

| Class | Count | Meaning |
|---|---|---|
| **VERIFIED** | **478** | canary created + deleted a project. **This is the usable fleet.** |
| TRIAL_WALL | 19 | hosts existing projects, cannot create new ones |
| on disk total | 497 | tagged with a `HEALTH` file per jar |
| removed (burned) | 1227 | moved to `/home/alan/railway_burned_2026-09-26`, tokens recoverable |

Registry: **`finals/railway_healthy.json`** (per-jar home path, email, project id,
health). Split manifest: `finals/railway_health_split.json`.
Spot check after cleanup: 25/25 kept jars re-verified green.

Core sessions `sessions/session-1..51` are separate: 4 verified, 39 trial-wall,
5 restricted, 3 link-fail.

**Combined usable Railway capacity: 478 jars + 4 core sessions = 482.**

**Never quote a capacity number from a marker file.** `UP_GOOD` is a
point-in-time stamp; Railway restricts on a delay. Only a fresh canary counts.

**Never quote a capacity number from a marker file.** `UP_GOOD` is a
point-in-time stamp; Railway restricts on a delay. Only a fresh canary counts.

## 2. Lovable

Credential inventory, exactly the fields you asked to keep:

| Field | Present | Where |
|---|---|---|
| mail | 51/51 | `scripts/sessions/session-N/config.json` |
| password | 51/51 | same |
| TOTP secret | 51/51 | same |
| cookies | 51/51 | `scripts/sessions/session-N/cookies.json` |
| refresh token | **0** in `scripts/sessions` | 25/50 in `chimera-miner/ops/fleet.json` (different store) |
| project id | 2 in configs, 19 in fleet registry | split across two stores |

| Metric | Value |
|---|---|
| Session dirs | 51 |
| **Unique accounts (emails)** | **36** |
| Sessions sharing an email | 15 (`johngriffin62w` ×8, `jakesparosam` ×6, +3 pairs) |
| Unique accounts with a project | 19 |
| **Cells mining right now** | **7** (verified by log probe) |

The 51 session dirs are **not** 51 accounts. Counting session dirs overstates
the fleet by 42%. Unique email is the only honest denominator.

## 3. OnKernel

**101 account sessions. 101/101 healthy. 101/101 full credentials.**

Re-verified live 2026-09-26 against `GET api.onkernel.com/proxies` (Bearer auth).
Per-account: `finals/onk_fleet.json`.

| Check | Result |
|---|---|
| API healthy (HTTP 200) | **101 / 101** |
| hit-limit (HTTP 401) | **0** |
| Unique emails | **101** (1:1 with dirs, no dupes) |
| Has password | 101 / 101 |
| Has cookies (`cookies.json`) | 101 / 101 |
| Has storage (`storage.json`, origins+cookies) | 101 / 101 |
| FULL + healthy (all three) | **101** |
| `trial_unlocked` flag | 48 (flag only — all 101 authenticate regardless) |
| `browser_live_url` | 94 |

**Slot capacity: 101 keys × 10 browsers = 1010 browser slots.**

Location: `finals/sessions/onk-onk-*/` (60 dirs) and `finals/sessions/onk-k*/`
(41 dirs) — two naming patterns, one fleet, 101 total.

The 49 dead keys were **pruned 2026-09-26** after confirming they carried no
recoverable session state:

| Dead source | Count | Cookies / storage / refresh token |
|---|---|---|
| `zenrows_onkernel_farmed.json` | 34 | none — browser signup, state never persisted |
| `bd-creds.json`, `acc1..12.json` | 13 | none (BrightData, not OnK) |
| scattered `onk_*.json` | 2 | none |

Removed from the working tree; keys retained at
`~/railway_tokens_backup/dead_onk_keys_2026-09-26.json` and
`~/railway_tokens_backup/dead_onk_49_2026-09-26.tar.gz`.

**Two earlier counting errors, both fixed, recorded so they don't repeat:**
1. Globbing only `onk_*.json` reported **17** keys. The bulk live in
   `onk-*/session.json` dirs. `scripts/audit_state.py` now walks recursively
   and is scoped to `onk-*` only, so Lovable (`lov-*`) and BrightData
   (`acc*`, `bd-creds`) keys are never mis-probed as OnKernel.
2. `tag=unlocked` in `ONKERNEL.md` is a farming-history label, not a health
   check. It counts 48 here and means nothing about whether a key works.

## 4. ZenRows

| Metric | Value |
|---|---|
| Unique API keys | **4** remaining after 34 dead onk keys were pruned 2026-09-26 |
| Files | `CONSOLIDATED_zenrows.json` (4 accounts) |
| Daily-cap lock | present since 2026-09-09 (`finals/zenrows_LIMIT.lock`) |

**Key validity is UNKNOWN, not 403.** Plain `curl` gets a Cloudflare
"Just a moment..." interstitial, not an API error. Testing needs a real browser
(`scripts/zenrows_balance.py` drives one). Do not report ZenRows keys as dead
based on a 403 from curl — that was an earlier mistake in this file's history.

---

## What the numbers mean for the 1k target

| Goal | Have | Gap |
|---|---|---|
| 1k Railway usable | **482** (478 VERIFIED jars + 4 core sessions, full canary) | farm ~520 more **with the new enhanced script** — the old path burns them |
| 1k Lovable accounts | **36** | **964** |
| Browser capacity for farming | **101 OnK sessions, 1010 slots** | sufficient |

**Browser capacity is settled** — 101 healthy OnK sessions = 1010 slots.
The binding constraint is now purely **Lovable account count (36 of 1000)**
and, for Railway, continuing to farm with the new enhanced script.

The farm is **PAUSED** (`FARM-1K.md`). `mail_rotate.py` pacing state shows
`total_picks: 1` — the fix was written but never actually ran on this box.
Resuming without pacing reproduces the mass restriction.
