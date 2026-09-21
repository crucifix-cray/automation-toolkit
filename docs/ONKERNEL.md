# OnKernel Accounts DB (GitHub as DB — owner decision 2026-09-21)

10 farmed accounts, minted 2026-09-21 via `src/onkernel/account_creation_cdp.py --end --22do`
(CDP browser cloud, 22.do one-dot Gmail, Clerk OTP). Full records (email + password +
api_key + cookies + storage trios) are committed under `finals/sessions/onk_<ts>_<pid>.*`
— explicit `git add -f` exception to the `onk_*.json` ignore rule.

## Accounts (10/10 live at mint)

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

Password (all): `GmailK01!`. Full keys: read the session JSON. Pointer: `finals/sessions/latest_onk.json`.

## Farming

```bash
# single
KERNEL_API_KEY=<key> LD_PRELOAD="" python3 src/onkernel/account_creation_cdp.py --end --22do
# parallel N (12-15s stagger, --attempts 3)
for i in $(seq 1 N); do (sleep $(( (i-1)*15 )); KERNEL_API_KEY=<key> LD_PRELOAD="" \
  python3 src/onkernel/account_creation_cdp.py --end --22do --attempts 3 > log_$i.txt 2>&1) & done; wait
```

Yield notes (2026-09-21): 7/10 first batch — 3 misses from 22.do filter exhaustion under
10-way contention (fixed: tries 40→80). Refill 3/3. Browsers auto-deleted on success and
on email-fail; verify with `kernel browsers list`.

## Rotation (credit exhausted → fresh key, same account)

`src/onkernel/org_reset.py` loads `<session>.storage.json`, deletes org, creates new
org+slug, mints fresh `auto-main` key, updates same JSON. Verified 2026-09-21
(`genev-91801`, `sk_2a7a3e82-...cq1g`).

## Pool usage (Railway spreader 68 → 1.2k)

Export keys from the JSONs into the spreader browser pool (OnKernel-first, 1 browser/cell,
`--par 2`). Seed key used for farming: `sk_73b4d85f-...` (owner-provided).
