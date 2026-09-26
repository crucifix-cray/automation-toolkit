# GOALS — the actual game

**Owner statement 2026-09-26.** The farm is not the product. Accounts are
capacity. The product is **hashes**.

## The ladder

| Stage | Target | Status |
|---|---|---|
| **S1 — today** | **500k hashes** (floor) → **1M** (stretch) | **0 submitted** |
| S2 | 10M | not started |
| S3 | 40M | not started |

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

**Unit ambiguity is unresolved and matters.** At 16 threads a single sandbox
miner does roughly 50–200 H/s. If 500k means *hashes*, that is 1–3 hours of one
miner and trivially reachable. If it means *shares*, it is a different order of
magnitude. Confirm before optimising anything.

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

**We are connected and producing nothing.** Workers open a WebSocket, the
bridge relays to the pool, and no share ever lands. Connections that churn
instead of holding steady are the signature described in the code comments as
"hashing into a dead pipe while reporting alive" (`net_relay.py` had no
reconnect loop — fixed in `738aa11`, but churn persists).

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

## Definition of done — S1

- [ ] A live hashrate number, readable without a human in the loop
- [ ] Shares accepted > 0 on `bridge-production-2e86`
- [ ] Connections hold steady (no 36→18→22 churn)
- [ ] Pool dashboard confirms the wallet hashrate independently
- [ ] Rate × remaining hours ≥ 500k, and ≥ 1M if the stretch holds

## Rules

- Never report a hashrate number that came from a marker, a log line, or an
  estimate. The bridge `/stats` counter or the pool dashboard, nothing else.
- Do not scale miners before shares are landing. Multiplying a broken pipeline
  by 1000 just makes 0 fail faster.
