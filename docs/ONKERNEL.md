# OnKernel Accounts DB (GitHub as DB — owner decision 2026-09-21)

Farmed via `src/onkernel/account_creation_cdp.py --end --22do` (CDP browser cloud,
22.do one-dot Gmail, Clerk OTP). After signup each account runs
`unlock_trial.py`: proxies → start a trial → just exploring → start trial.
Full records (email + password + api_key + cookies + storage trios) live under
`finals/sessions/onk_<ts>_<pid>.*` — explicit `git add -f` exception to the
`onk_*.json` ignore rule.

Password (all): `GmailK01!`. Pointer: `finals/sessions/latest_onk.json`.

## Batch A — 2026-09-21 (10)

| session file | email | key prefix | created (UTC) |
|---|---|---|---|
| `onk_1789993285_172424.json` | tros.kykreie516@gmail.com | `sk_b5434fb9-df19-a11` | 2026-09-21 12:21 |
| `onk_1789993299_172785.json` | goicongn.hanxua925@gmail.com | `sk_c1b88f75-fb42-705` | 2026-09-21 12:21 |
| `onk_1789993310_173152.json` | lizeeh.h4@gmail.com | `sk_1cd7df14-6f1a-fa1` | 2026-09-21 12:21 |
| `onk_1789993337_173679.json` | nakitauth.urlowh88@gmail.com | `sk_0de5bb5e-3e0e-e26` | 2026-09-21 12:22 |
| `onk_1789993346_173916.json` | landec.kpoist911@gmail.com | `sk_f3a9a525-4ce6-53e` | 2026-09-21 12:22 |
| `onk_1789993360_174254.json` | beckivuongcv.u22@gmail.com | `sk_95e4d3e4-1db2-a60` | 2026-09-21 12:22 |
| `onk_1789993386_174552.json` | gle.ndaxgageo95@gmail.com | `sk_539d4e45-f819-e9a` | 2026-09-21 12:23 |
| `onk_1790010320_240895.json` | luzk.ruegelxnp17@gmail.com | `sk_c64de3da-8c79-f10` | 2026-09-21 17:05 |
| `onk_1790010334_241354.json` | kath.lynsavannahvki60@gmail.com | `sk_14cf4f06-9426-ce3` | 2026-09-21 17:05 |
| `onk_1790010356_242052.json` | dasi.nmolvs93@gmail.com | `sk_61ed6820-a461-d5b` | 2026-09-21 17:05 |

## Batch B — 2026-09-22 (10, trial unlocked)

Farmed on `dasi.nmolvs93@gmail.com` browsers; each unlocked via proxies trial flow.
API-verified: `GET/POST https://api.onkernel.com/proxies` → available.

| session file | email | key prefix | unlocked |
|---|---|---|---|
| `onk_1790079465_170355.json` | smoottel.la206@gmail.com | `sk_dcbe0c32-c925-9` | yes |
| `onk_1790079494_170590.json` | lilli.anaparshsmm18@gmail.com | `sk_1bd77c6d-e57e-2` | yes |
| `onk_1790079514_171090.json` | lis.awscott94@gmail.com | `sk_749b04ce-3a4a-c` | yes |
| `onk_1790079548_170866.json` | mag.giezairetncm@gmail.com | `sk_a6784262-d3da-e` | yes |
| `onk_1790079557_171591.json` | jave.nskinstle77@gmail.com | `sk_d00b152f-75a8-e` | yes |
| `onk_1790079560_171388.json` | kenethsurrey.clm36@gmail.com | `sk_21eaf06c-6de8-5` | yes |
| `onk_1790079589_171821.json` | antoninan.rodriquezn38@gmail.com | `sk_69930520-f60b-8` | yes |
| `onk_1790079871_171277.json` | brigittemm.arloweo82@gmail.com | `sk_1bfe2de7-6d26-4` | yes |
| `onk_1790080303_183512.json` | pion.tkowskiheffley84@gmail.com | `sk_dbb4caaf-ddbc-1` | yes |
| `onk_1790080310_184023.json` | grosjeanpretz.548@gmail.com | `sk_ee2acef6-c7d9-0` | yes |

## Farming

```bash
# single
KERNEL_API_KEY=<key> LD_PRELOAD="" python3 src/onkernel/account_creation_cdp.py --end --22do
# parallel N (12-15s stagger, --attempts 3)
for i in $(seq 1 N); do (sleep $(( (i-1)*15 )); KERNEL_API_KEY=<key> LD_PRELOAD="" \
  python3 src/onkernel/account_creation_cdp.py --end --22do --attempts 3 > log_$i.txt 2>&1) & done; wait
```

## Unlock trial

```bash
# wired into create + org_reset; standalone:
from unlock_trial import unlock_full_potential
await unlock_full_potential(page)
# flow: /proxies → "start a trial" → "just exploring" → "start trial"
```

## Rotation (credit exhausted → fresh key, same account)

`src/onkernel/org_reset.py` loads `<session>.storage.json`, deletes org, creates new
org+slug, mints fresh `auto-main` key, unlocks trial, updates same JSON.

## Pool usage (Railway spreader → 1k)

Batch B keys + `mobile` proxies (`config.country=us`), unique proxy name per browser
(`mobile-us-<hex>`). Orchestrator: `src/railway/farm_onk_1k.py` — `--par 10`, rotate
key+proxy each browser.
