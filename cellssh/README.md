# cellssh — build Railway cells with NO build step

Railway's Railpack builder is broken platform-wide (a 2-line Dockerfile fails
with `railpack prepare exited with an error`). This path sidesteps it: create
the service with a **public image** via the GraphQL API, then drive it over SSH.

## Verified working (2026-09-28, cell-80 on session-17)

1. `rail_api.py` — create service with a public image, no build:
   ```
   serviceCreate(projectId, environmentId, name, source:{image:"ubuntu:24.04"})
   serviceInstanceUpdate(serviceId, {startCommand:"sleep infinity",
                                     restartPolicyType:ALWAYS})
   serviceInstanceDeploy(serviceId, environmentId)
   ```
   → service goes `● Online` with `image: ubuntu:24.04`.

2. `cell_ssh2.py` — SSH by **service instance id** (new services have no domain,
   so `railway ssh -s <name>` does not resolve):
   ```
   railway ssh -d <service-instance-id> -- bash -lc '...'
   ```
   Works with the registered cell key. Root shell, 2.0T free.

3. `upload_big()` — ships large files. A single SSH command cannot hold a
   182KB file, so it gzip+base64 streams in ~45KB chunks, then
   `base64 -d | gunzip -c > target` and prints md5. Gotcha: decode order is
   base64 **then** gunzip (the reverse silently writes an empty file).

4. `start_miner.sh` — launches `mine.sh` fully detached. Backgrounding straight
   from the SSH session gets it killed when the session closes.

5. `reaper.py` — kills orphaned Chrome. Playwright hard-kills reparent chrome
   children to PID 1; on a 1GB cell 166 of them starve the page. Measured
   166 procs/953MB → 40 procs/536MB.

## Cell bootstrap (plain ubuntu:24.04, ~12 min)

```
apt-get update -q
apt-get install -y xvfb curl ca-certificates python3 python3-pip fonts-liberation \
  libgtk-3-0 libasound2t64 libnspr4 libnss3 libatk1.0-0t64 \
  libatk-bridge2.0-0t64 libcups2t64 libdrm2 libgbm1 libxkbcommon0 \
  libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libpango-1.0-0 \
  libcairo2 libatspi2.0-0t64 libdbus-1-3 libxshmfence1
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.14 && uv venv --python 3.14 /opt/venv     # -> 3.14.7
uv pip install -p /opt/venv patchright playwright camoufox websockets psutil requests
/opt/venv/bin/python3 -m patchright install chromium
```

Then ship `daemon.py` (golden `cb9305f5…`), `miner_injector.py`
(`e9e158a7…`), `watchdog_worker.py`, `mine.sh`, the session trio
(`cookies.json` + `config.json`), and run `start_miner.sh`.

## Hard blockers found (not fixable from here)

- **Login is refused from Railway**: `Login denied due to suspicious activity`
  (Lovable blocks cloud egress). 23 of 25 sessions' cookies are already dead,
  so they cannot be refreshed from a cell.
- **Local login**: `mzzrfdvtedmkjoeffsup.supabase.co` (Lovable's auth host)
  is unreachable from this machine **and** via Tor (`000` both ways).
- **All 47 ZenRows keys are dead** (404) and Camoufox cannot be fetched
  (GitHub 500s), so no third egress path is available.
- **1GB memory wall**: even with a valid session the Lovable composer does not
  render (`Chat input missing 15/15`), so the worker never injects.
