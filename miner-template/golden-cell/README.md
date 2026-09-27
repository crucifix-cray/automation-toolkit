# Golden cell — copied from cell-28 (session-6), the best miner so far

**Why this one:** 2414 `Worker alive` lines (fleet best), alive within the last hour
before the overnight OOM wave, mem 895MB / chrome 8 procs.

## Exact runtime
```
daemon:  cb9305f50b6f1cee90fbbe74c0a2f009  (= daemon.golden.py in this dir)
injector:e9e158a76419522f635ebcdcd3b82590  (same as chimera-miner master)
python:  3.14.7 (/opt/venv)
cmd:     /opt/venv/bin/python3 -u daemon.py --session <SESS> --project <PROJ> --browser chromium --mode full --headed
```

## lean_sup env (copy verbatim, swap SESS/PROJ only)
```
LOG=/app/work/daemon_r<CELL>.log
SESS=<lov-session>            # e.g. session-41
PROJ=<lovable-project-uuid>
WORKER_STALE_S=600
DISPLAY=:99
CHIMERA_NO_PROXY=1 CHIMERA_SKIP_IDB=1 CHIMERA_FORCE_HEADED=1
CHIMERA_VIEW_W=1600 CHIMERA_VIEW_H=900
CHIMERA_SESSIONS_DIR=/app/work/scripts/sessions
CHIMERA_SHOT_DIR=/app/work/shots
PYTHONUNBUFFERED=1
```
No `MINER_CMD`, no `CHIMERA_THREADS` (default 16), no `CHIMERA_BRIDGE`
(default `wss://bridge-production-2e86.up.railway.app/ws`).

## Notes
- `daemon.golden.py` == chimera-miner `bfad2dd^` (parent of the auth-revive
  second-pass patch). The patch (`bfad2dd`) is the ONLY delta vs golden and
  only fires on auth-wall; steady-state mining is byte-identical.
- To clone onto a dead cell: ship these bytes + trio (cookies/LS/IDB with
  refresh_token) + set SESS/PROJ + `setsid nohup lean_sup` + verify
  `Worker alive` + `Preview healthy`.
- Per-cell swap = SESS + PROJ + LOG name. Nothing else changes. Ever.
