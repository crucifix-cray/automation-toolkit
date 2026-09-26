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

## Lovable 1k (2026-09-24) — primary use of OnK slots

See **[LOVABLE_FARM_1K.md](LOVABLE_FARM_1K.md)** and **[STATE.md](STATE.md)**.

> **Corrected twice — read this.** The "~101 healthy × 10 browsers" figure in the
> table below was aspirational. Measured state:
>
> * 2026-09-25 audit of 51 keys: 17 working / 34 hit-limit.
> * 2026-09-26 the missing keys were acquired and 49 dead ones pruned
>   (commit `f08a6931`): **101 keys, 101/101 HTTP 200, all with full creds.**
>   Re-verified on this box: 60/60 green, 0 dead.
> * Fleet registry: `finals/onk_fleet.json`. Per-key: `finals/onk_key_status.json`.
>
> `tag=unlocked` is a farming-history label, not a health check — do not read
> capacity off it.

## Railway spreader plan (51 workers → ~1k MADE jars) — legacy / paused

**Laptop = thin boss only.** Playwright+CDP on Railway via `scripts/cell_ssh.sh`.
Each job: fresh OnK **mobile** proxy → stealth browser → Holy
`account_creation.py --kernel --kernel-proxy <name> --once --no-warp`.

| Knob | Value |
|---|---|
| OnK providers | Unlocked jars (`finals/sessions/onk_*.json`) |
| Fleet workers | Documents/railways + `farmed-*` CLI homes |
| Wave math | historical `51 × ~20 ≈ 1k` MADE Railway accounts |
| Concurrent | Cap by OnK org; do **not** local `--par 50+` |
| Holy script | `src/railway/account_creation.py` |
| Status | **PAUSED** after green pilots (2026-09-23). Lovable 1k is the active track. |

```bash
# WRONG on 15Gi laptop — OOM
# LD_PRELOAD="" python3 src/railway/farm_onk_1k.py --target 1000 --par 100

# RIGHT: one worker example (see pilot notes). Fleet dispatcher still thin / TBD.
```

### Hard rule — scrub host `RAILWAY_*` inside sandboxes

Every Railway cell injects `RAILWAY_API_TOKEN` (+ project/service ids) for the **host**
account. If Holy’s service-verify `railway whoami`/`init` sees those, it operates as
the host (wrong email, “Free plan resource provision limit exceeded”) and deletes the
new jar. `create_and_verify_service` now strips **all** `RAILWAY_*` env vars and sets
`HOME=<new session dir>` before CLI calls. Runner shells must scrub too.

### GitHub push (encrypted PAT)

MADE jars push to `finals/sessions/farmed-<session>/` on this repo after service verify.

```bash
# one-time on laptop — ciphertext only is committed
HOLY_SECRET_KEY='choose-a-strong-passphrase' GITHUB_TOKEN='ghp_…' \
  python3 -m src.utils.secret_box encrypt --out finals/secrets/gh_token.enc
git add -f finals/secrets/gh_token.enc && git commit && git push

# on Railway worker / sandbox — inject passphrase only (never the raw PAT)
export HOLY_SECRET_KEY='choose-a-strong-passphrase'
# optional override instead of file: export GH_TOKEN_ENC='…ciphertext…'
# clone is automatic via src/railway/gh_push.py (TOOLKIT_ROOT=/app/toolkit if pre-cloned)
```

Disable: `GH_PUSH=0`. See `finals/secrets/README.md`.

### Pilot — 2026-09-23 (green, then stop)

- Worker: `session-40` (`cell-113`)
- OnK: provider key + fresh mobile proxy (`mobi-one3-*`)
- Result: **SERVICE OK — account MADE** `tbofekfloksc@uberip.com`
- Jar: `finals/sessions/farmed-pilot-session-1/` (`verified.json` present)
- Earlier fails: missing `railway` binary on box; host `RAILWAY_API_TOKEN` leak (fixed)

### Pilot — 2026-09-23b (Railway sandbox on session-1, full loop)

- Host account: `janic.ebunagna@gmail.com` / project `talented-celebration`
- Worker: Railway **sandbox** (fleet `cell-13` mapping was stale/offline)
- OnK: Batch B `smoottel…` + mobile proxy `mobi-holy-*`
- Bootstrap: Python 3.12 + playwright chromium(+deps) + `@onkernel/cli` + railway CLI + toolkit clone
- Result: **SERVICE OK — MADE** `uqmvvmugjqw7@uberip.com` → `cell-1-28bce9` / `hlth-1`
- Jar: `finals/sessions/farmed-sandbox-session-1/`
- GitHub push: first attempt failed (`eisen0x` token no write); re-sealed `gh_token.enc` for writable user; sandbox `sync_to_github` **OK**
- Local box footprint during run: ~0.4–0.7 GiB of 2.2 GiB (browser remote on OnK)

### Run notes — 2026-09-22 (local OOM)

- Local `--par 100` / `--par 40` **OOM’d** the 15 GiB host.
- Prefer 22.do; `mail.tm` works as fallback (pilot used mail.tm).
- Kill leftover local clients: `pkill -9 -f farm_onk_1k; pkill -9 -f 'railway/account_creation.py'`.

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
