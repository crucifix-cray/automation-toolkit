# Repo map

Start at [`README.md`](README.md) → [`docs/GOALS.md`](docs/GOALS.md).

## Layout

| Path | What |
|---|---|
| `docs/` | All documentation. `STATE.md` is authoritative for counts. |
| `bridge-deploy/` | **The live WSS→Stratum bridge** (Go + Tor). Source of truth for bridge code. |
| `ops/` | Farm ops. `ops/host/` = this-box host scripts, `ops/onk-rail-1k/` = farm runbook scripts. |
| `ops/fleet.json` | *(chimera-miner repo)* cell registry: 51 cells, miner state, projects. |
| `src/` | Farm logic: `railway/`, `lovable/`, `onkernel/`, `farming/`, `utils/`. |
| `scripts/` | Tooling. `audit_state.py` regenerates every count in STATE.md. `legacy/` = parked. |
| `finals/` | Account inventory: 497 Railway jars, 101 OnK accounts, health manifests. |
| `sessions/` | 51 core Railway sessions (tokens + cellkeys, tracked by owner decision). |
| `scripts/sessions/` | 51 Lovable sessions (config + cookies). |
| `railway-docker/` | The Railway farm script (`railway-HOLY-zenrows.py`). |
| `ubuntu-service/`, `ubuntu-terminal/` | Cell image + terminal setup. |
| `mega_db/` | Old Mega mirror. Largely superseded by `finals/`. |
| `tests/` | Test suites. |
| `bin/` | Helper wrappers (`rclone-pr`). |
| `archive/` | Old top-level material. |

## Two repos

| Repo | Holds |
|---|---|
| **automation-toolkit** (this one) | accounts, farm scripts, bridge, docs |
| **chimera-miner** | `daemon.py`, `miner_injector.py`, `watchdog_worker.py`, `ops/fleet.json`, `sysoptd-v2/` |

## Live endpoints

| What | Where |
|---|---|
| Stratum bridge | `wss://bridge-production-2e86.up.railway.app/ws` |
| Bridge stats | `https://bridge-production-2e86.up.railway.app/stats` → `{"accepted":0,"connections":22,"shares":0}` |
| Bridge health | `https://bridge-production-2e86.up.railway.app/health` |
| Pool | `pool.supportxmr.com:3333` (via Tor — Railway's own IP is blocklisted) |
| Wallet | `bridge-deploy/config.json` |
| Dead bridge | `chimera-bridge-production-0703` — 1013 at capacity, **owner unknown**, inert |

## Commands

```bash
# regenerate every count in docs/STATE.md
python3 scripts/audit_state.py            # fast, no Railway writes
python3 scripts/audit_state.py --census   # + real init/delete canary (slow)

# cell ops (chimera-miner repo)
python3 ops/cell_ops.py status 13 16 28
python3 ops/cell_ops.py ssh 13 -- 'tail -20 /data/work/daemon_r13.log'

# bridge health
curl -s https://bridge-production-2e86.up.railway.app/stats
```

## Conventions

- **Never** quote a count from a marker file (`UP_GOOD`) or a log line. Only a
  fresh measurement, recorded in `finals/*.json`.
- Railway health = canary `railway init` → `railway delete`. `whoami` is not health.
- Account counts use **unique email**, never session-dir count.
- Secrets stay out of commits. Railway tokens and cellkeys are tracked by
  explicit owner decision (`eddf339`) — rotate if repo access ever changes.
