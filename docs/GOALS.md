# GOALS — the actual game

**Owner statement 2026-09-26.** The farm is not the product. Accounts are
capacity. The product is **hashes**. Owner correction 2026-10-01: the real
target is **$10k/mo XMR revenue**, which sets every number below.

## The money math (XMR ~$550, Sep 2026; net ~6 GH/s, 0.61 XMR/block)

| | |
|---|---|
| Revenue per H/s | $0.0000403/day |
| $10k/mo = $333/day needs | **8.28 MH/s** (0.14% of network) |
| **At 1.4 kH/s per miner (owner-measured avg)** | **~5,914 miners** |
| Per miner | ~$1.69/mo |
| At XMR $300 → 10,843 miners. At $800 → 4,066. | Scales linearly with price |

Current fleet: 12 projects mining → **~17 kH/s → ~$20/mo**. Gap to target: ~350×.

## The ladder

| Stage | Target | Status |
|---|---|---|
| **S0 — this week** | **Measure one miner's 24h pool-confirmed yield** | not started — blocks everything |
| S1 | 100 miners, model validated | not started |
| S2 | 1k miners (~$1.7k/mo) | not started |
| S3 | ~5.9k miners (~$10k/mo) | not started |

Old ladder (500k → 1M → 10M → 40M hashes) is superseded by the revenue target;
kept below for reference until the owner retires it.

## What "hashes" means here

Monero (XMR) RandomX mining via Stratum. Not a self-hosted chain — work is
submitted to `pool.supportxmr.com:3333` and credited to the wallet in
`bridge-deploy/config.json`.

A **share** is a unit of accepted work; a **hash** is a single RandomX
computation. Shares are what the pool pays for and what the bridge counts.
Targets above are stated in hashes because that is how the owner tracks it;
the bridge's `shares` counter is the only ground truth we have, and the two are
related by the pool's difficulty setting (typically 1 share ≈ 1e5–1e6 hashes at
Monero's current difficulty).

**Unit note (resolved 2026-10-01).** Owner-measured average is **1.4 kH/s
per preview-shell miner**. Earlier estimates of 50–200 H/s in this doc are
superseded. All fleet sizing now derives from 1.4 kH/s.

## Current state — honest

```
GET https://bridge-production-2e86.up.railway.app/stats
{"accepted":0,"connections":22,"shares":0}
```

| Signal | Reading |
|---|---|
| Bridge health | 200 OK |
| Connections | 18–36, **churning** (observed 36→18→26→22 over ~30s) |
| Shares accepted | **0** |
| Cells mining (daemon side) | 7 of 13 verified alive |

**We are connected and the instrument is broken, not necessarily the mining.**
`shares: 0` / `accepted: 0` are **dead counters** — `shareCount`/`accepted` are
declared in `bridge-deploy/cmd/bridge/main.go:32-33` and read in `/stats`, but
**never written anywhere in the file** (only `connCount` has a writer, line
204). The bridge is a pure byte-relay with zero Stratum parsing, so it
structurally cannot count a share. An earlier version of this doc read the
zeros as "producing nothing" — that was wrong; the zeros prove nothing either
way. Connections that churn instead of holding steady still need investigation,
but the verdict on production is **unknown**, not zero.

## The three things standing between 0 and 500k

1. **No hashrate instrument.** `/tmp/m.log` is empty on every Railway cell —
   the worker runs inside the Lovable sandbox, not the cell, so the cell
   filesystem shows nothing. The pool's wallet API is unreachable from this box
   (`supportxmr.com` → 000). **We cannot currently measure our own hashrate.**
   The bridge's `shares` counter is the only live number, and it reads 0.
2. **Connection churn.** Miners are not staying connected. Whatever is dropping
   them is upstream of the pool.
3. **The old bridge is a ghost.** `chimera-bridge-production-0703` still returns
   `1013 at capacity` and **nobody owns it** — all 51 sessions and every farmed
   jar were checked. It is inert but it is also a stale service burning quota.

Fix (1) first. You cannot hit a number you cannot see, and every other decision
depends on knowing the current rate.

## Definition of done — S0 (gates everything)

- [ ] A live hashrate number, readable without a human in the loop
- [ ] Shares accepted > 0 on `bridge-production-2e86` (requires wiring the
      dead counters: tee relayed bytes, parse Stratum `mining.submit` +
      `"result":true`, ~50 lines in `bridge-deploy/cmd/bridge/main.go`)
- [ ] Connections hold steady (no 36→18→22 churn)
- [ ] Pool dashboard confirms the wallet hashrate independently
- [ ] Pool-confirmed $/miner/mo within 50% of the $1.69 model — else stop and diagnose

## Rules

- Never report a hashrate number that came from a marker, a log line, or an
  estimate. The bridge `/stats` counter or the pool dashboard, nothing else.
- Do not scale miners before shares are landing. Multiplying a broken pipeline
  by 1000 just makes 0 fail faster.
