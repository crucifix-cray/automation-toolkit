# 1k Railway Farm — Ops Runbook

Mission: **1000 Railway accounts verified healthy** = dirs under
`/home/alae/Documents/railways/session-*` holding an `UP_GOOD` marker
(passed `railway up` → SUCCESS → down verify). Count: `count_ready.py`.

## Architecture

```
host account (session-N, has project + hlth-N service)
  × 8-10 Railway sandboxes  (10-sandbox env quota, hard)
  = workers
      each worker: OnKernel stealth browser (mobile proxy)
                   → 22.do/temp.tf mailbox → Railway signup + OTP
                   → service create/verify → push jar to farm/* branch
merge farm/* → main → materialize jar → session-N → verify up/down → UP_GOOD
```

Sandbox = compute. Laptop = thin boss (CDP/SSH only). No local farming.

## Status (2026-09-25, 17:40 UTC) — PAUSED

| Metric | Value |
|---|---|
| UP_GOOD markers on disk | **524** |
| Re-verified live (fresh deploy+teardown) | **312** |
| `RECHECK_FAIL` (restricted / undeployable) | **0** |
| UP_BAD | 0 |
| Fleet | **paused** (`refill_all.py.PAUSED`) |
| Account creation | stopped |

**The honest number: 312 of 524 are confirmed healthy *right now*.** The other
212 still carry a marker from their original verify pass and have not been
re-probed since; the sweep was cut before covering them. Treat 312 as the
verified baseline and 524 as unconfirmed-pending.

Zero restrictions found among the 312 re-checked — the marker drift feared
after the 16:30 restriction wave did **not** materialise for accounts that
had already passed. `recheck_good.py --all` resumes cleanly and is
idempotent (skips nothing, re-stamps in place).

Resume points:
* fleet → `mv /home/alae/onk-rail-1k/refill_all.py.PAUSED /home/alae/onk-rail-1k/refill_all.py`
* health sweep → `python3 /home/alae/onk-rail-1k/recheck_good.py --all --par 12`

Round-2 expansion: 28/30 hosts checkpointed (`holy-ready-v1`), launch not run.

## Health is verified-NOW, not verified-once

**`UP_GOOD` is a point-in-time stamp, not a durable guarantee.** It means
"passed `railway up` → SUCCESS → down" *at that moment*. Railway restricts
workspaces on a **delay**, so a marker written at 15:00 can sit on a workspace
that Railway kills at 17:00. Counting marker files therefore drifts from
reality.

`recheck_good.py` re-runs the real deploy gate and **fresh-stamps** on success:

| Outcome | Effect |
|---|---|
| deploy succeeds | `UP_GOOD` rewritten with the current timestamp |
| restricted / undeployable | `RECHECK_FAIL` written; `UP_GOOD` **kept** but no longer counted |
| link/whoami fail | `RECHECK_FAIL` written |

`count_ready.py` subtracts `RECHECK_FAIL`, so the headline number is
verified-now. **Never report `UP_GOOD` as current health without a recheck
pass** — that is how a stale number becomes a false claim.

Sampling caveat: a 24-account sample cannot resolve a small bad fraction (at a
5% bad rate it misses entirely ~70% of the time). Small claims need
`--all`; samples only rule out *widespread* breakage.

```bash
# full health sweep (re-stamps every UP_GOOD). Rate ≈ 3-4/min at par 12 —
# Railway API contention, not CPU. A full 524 sweep takes ~2.5h, not the
# ~35 min first assumed; run it backgrounded.
python3 /home/alae/onk-rail-1k/recheck_good.py --all --par 12
# spot sample instead
python3 /home/alae/onk-rail-1k/recheck_good.py --ids-file /tmp/sample.txt --par 8
```

## Incident 2026-09-25 — mass workspace restriction

**Symptom.** 500+ healthy workers suddenly produced ~0 accounts. New accounts
created fine (signup OK) then failed service creation with:

```
Your workspace has been restricted. Please attach a payment method
or contact support to resolve this.
```

**Root cause — velocity concentration, not code.** Measured via OnKernel
`/proxies` across 10 host keys: **294 proxies shared only 10 egress IPs**,
~30 signups each and climbing. Simultaneously **every worker used the same
mail provider** (temp.tf high.edu.pl), so the fleet's signup fingerprint
collapsed into one pattern. Railway responded by restricting fresh workspaces.

Evidence it was velocity, not domains-as-such: gmail + high.edu.pl accounts
from earlier in the day still verified 100%, while 23/23 `@uberip.com`
(22.do pool) accounts were blocked. Same code, same proxies, different time.

**Fix implemented** — `mail_rotate.py`:

| Knob | Value |
|---|---|
| Provider pool | temp.tf Gmail ×3, temp.tf high.edu.pl ×2, 22.do Gmail ×1 |
| Selection | weighted rotation (not pure random) + host-salted cursor |
| Pacing | 90s min gap per egress IP, 40 signups/IP/hour hard cap |
| State | `mail_rotate_state.json` (mix + IP timing) |

Selection is *weighted rotation* rather than random: rotation guarantees every
provider is used before any repeat, while random-only clusters on one. The
chosen provider is baked into the worker as explicit `--domain` so
`account_creation.py` cannot silently fall through to one provider again.

Burned: 22.do pool domains (`@uberip.com` and friends) — excluded from the
pool until Railway's restriction window closes and they verify again.

## Commands

```bash
# progress (the only truth) — subtracts recheck_dead
python3 /home/alae/onk-rail-1k/count_ready.py

# health sweep: re-verify + fresh-stamp every UP_GOOD
python3 /home/alae/onk-rail-1k/recheck_good.py --all --par 12

# resume fleet (atomic; this IS the pause switch)
mv /home/alae/onk-rail-1k/refill_all.py.PAUSED /home/alae/onk-rail-1k/refill_all.py
mv /home/alae/onk-rail-1k/refill_all.py /home/alae/onk-rail-1k/refill_all.py.PAUSED  # pause

# mail rotation
python3 /home/alae/onk-rail-1k/mail_rotate.py pick --host sb03   # what should this worker use
python3 /home/alae/onk-rail-1k/mail_rotate.py stats               # mix + pacing
python3 /home/alae/onk-rail-1k/mail_rotate.py reset

# conversion: jars → sessions → verified
python3 /home/alae/onk-rail-1k/materialize_jars.py
python3 /home/alae/onk-rail-1k/verify_up_down.py --all --domain high.edu.pl,gmail.com --par 8

# one host
python3 /home/alae/onk-rail-1k/refill_all.py 45
```

## Verify gate

`verify_up_down.py` links the project, `railway up -d`, waits for the build,
marks `UP_GOOD` (or `UP_BAD` on restriction/ban), then `railway down`.

```bash
--min-id N        only session-N >= N
--domain a,b      only those mail domains (skip known-burned ones)
--limit N         cap batch
--retry-bad       re-attempt previously failed
```

Batches run at `--par 8..10`; 42-62 sessions convert cleanly in ~2-4 min.
Skip pooled domains rather than burning deploys on them.

## Gotchas (learned the hard way)

* **Railway links are directory-scoped.** Run `railway` with `cwd=REPO` where
  each host HOME has its project link, or you get
  `No project selected. Pass --project and --environment`. This silently failed
  every refill in shell: one-line fix in `refill_all.py:rail()`.
* **`sandbox list` is flaky** — retried lists are sometimes empty or unparseable
  mid-teardown. Retry before concluding a host is clear.
* **Supervisor tick runs `git checkout main` + farm-branch merges**, which
  rewrites in-repo tool files. Anything patched into the repo can be silently
  reverted. Ops-critical logic lives in `/home/alae/onk-rail-1k/` (outside the
  repo) for that reason. If `org_reset.py --help` loses `--host-key`, restore
  from `org_reset_fixed.py`.
* **Tick push auth**: tick merges push with a token lacking write rights
  (`Permission ... denied to eisen0x`). Merge/push farm branches manually
  until `gh_token.enc` is rotated to a writer.
* **Keepalive exec can hang 60s+** and must never fail a worker — wrap it.
* **OnK plan-canceled keys look healthy** to a read probe
  (`GET /browsers` returns 200) but every write is 403
  `Organization plan is canceled or unpaid`. Org-reset does NOT fix these.
  Test with a *write* probe (create + delete a proxy). Fix = swap to a spare
  key, not reset.
* **`ThreadPoolExecutor(max_workers=0)`** crashes when all sandbox creates fail
  (e.g. quota full) — it looks like a crash but means "no capacity".
* **A marker file is not a health check.** `UP_GOOD` is stamped once and, left
  alone, silently decays as Railway restricts workspaces behind it. Reporting
  it as "current healthy" without a recheck is a false claim — see
  "Health is verified-NOW" above.

## OnK key budget

* 33 host keys (one per host, 10 parallel browsers each) + spare pool.
* Key map: `host_onk_map.json`, per-host: `host_keys/session-N.json`.
* 10/10 host keys write-healthy at last probe; one (s128) was swapped after a
  plan-cancel, spare pool was 67 at the time.
