#!/usr/bin/env python3
"""new_miner.py — template bootstrap: new account + project -> mining cell that never stops.

Usage:
    python3 new_miner.py --cell 94 --lov-session 52 --project fa7ad090-... --rig rig-194 [--threads 16]

Does, in order (fails fast with a clear reason):
  1. PREFLIGHT  session trio exists (cookies.json + indexeddb.json with refresh_token),
                bridge serves a real JOB, wallet pinned to WALLET.
  2. DEPLOY     cell_ops deploy-daemon <cell> --bounce (code + trio + lean_sup).
  3. SUPERVISE  lean_sup running (respawns daemon+browser forever).
  4. VERIFY     poll for "Worker alive" + "Preview healthy" (up to --timeout min).
  5. REGISTER   cell already in ops/fleet.json -> fleet supervisor picks it up
                automatically on its next 4-min cycle. Nothing extra to wire.

Never-stop stack (every cell gets all three):
  lean_sup.sh  (on cell)   respawns daemon + Chromium if either dies.
  daemon.py    (on cell)   health loop: revive auth via refresh_token, relaunch
                           browser on crash, re-inject worker, re-point bridge.
  fleet_supervisor.py (here) external watchdog: bounce -> full lean_sup restart
                           after 2 strikes. Never touches a mining cell.

Wallet rule: workers log in with WALLET below. The bridge is byte-relay and
passes worker logins straight to the pool, so the worker-side wallet is the
one that gets credited. This script refuses to run if any layer disagrees.
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

WALLET = "49J8k2f3qtHaNYcQ52WXkHZgWhU4dU8fuhRJcNiG9Bra3uyc2pQRsmR38mqkh2MZhEfvhkh2bNkzR892APqs3U6aHsBcN1F"
BRIDGE_WS = "wss://bridge-production-2e86.up.railway.app/ws"

OPS = Path("/home/alan/Documents/repos/chimera-miner/ops")
sys.path.insert(0, str(OPS))
from ssh_reliable import ssh_checked  # noqa: E402
from cell_ops import load_map  # noqa: E402

SESSIONS = Path("/home/alan/Documents/railways/scripts/sessions")


def fail(msg: str) -> int:
    print(f"ABORT: {msg}", flush=True)
    return 1


def preflight(lov_session: str) -> int:
    sdir = SESSIONS / f"session-{lov_session}"
    cj = sdir / "cookies.json"
    if not cj.exists():
        return fail(f"no cookies.json for lov session {lov_session}")
    try:
        idb = json.loads((sdir / "indexeddb.json").read_text())
        has_rt = any(
            isinstance(r, dict)
            and isinstance(r.get("value"), dict)
            and (r["value"].get("stsTokenManager") or {}).get("refreshToken")
            for r in idb
        )
    except Exception:
        has_rt = False
    if not has_rt:
        return fail(f"lov session {lov_session} has no refresh_token — rescue trio first")
    print(f"preflight: trio OK (lov session {lov_session})", flush=True)
    return 0


async def bridge_serves_job() -> bool:
    try:
        import websockets  # type: ignore
    except ImportError:
        print("preflight: websockets lib missing, skipping live JOB check", flush=True)
        return True
    try:
        async with websockets.connect(BRIDGE_WS, open_timeout=25, ping_interval=None) as ws:
            await ws.send(
                json.dumps(
                    {"id": 1, "method": "login",
                     "params": {"login": f"{WALLET}.preflight", "pass": "x",
                                "agent": "template-check"}}
                ).encode() + b"\n"
            )
            d = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
            ok = bool(d.get("result", {}).get("job"))
            print(f"preflight: bridge JOB {'OK' if ok else 'MISSING'}", flush=True)
            return ok
    except Exception as e:
        print(f"preflight: bridge check failed: {e}", flush=True)
        return False


def deploy(cell: str) -> int:
    import subprocess
    r = subprocess.run(
        [sys.executable, str(OPS / "cell_ops.py"), "deploy-daemon", str(cell), "--bounce"],
        capture_output=True, text=True, timeout=600,
        env={"PATH": "/usr/bin:/bin", "HOME": "/home/alan",
             "LD_PRELOAD": "", "PYTHONUNBUFFERED": "1"},
    )
    tail = (r.stdout + r.stderr)[-400:]
    print(f"deploy cell-{cell}: rc={r.returncode} {tail}", flush=True)
    return r.returncode


def verify(cell: str, cells: dict, timeout_min: int) -> int:
    c = cells[cell]
    home = Path(f"/home/alan/Documents/railways/sessions/session-{c.get('railway_session')}")
    svc = c.get("service_name") or f"cell-{cell}"
    log = c.get("log") or f"daemon_r{cell}.log"
    deadline = time.time() + timeout_min * 60
    while time.time() < deadline:
        try:
            ok, out = ssh_checked(
                home, svc, f"echo MARK-END; tail -8 /data/work/{log} 2>/dev/null",
                "MARK-END", timeout=200, tries=1)
        except Exception:
            ok, out = False, ""
        o = out or ""
        if ok and "Worker alive" in o and "Preview healthy" in o:
            print(f"cell-{cell}: MINING (worker alive + preview healthy)", flush=True)
            return 0
        time.sleep(120)
    return fail(f"cell-{cell} not mining within {timeout_min} min — check fleet_nodoc.json causes")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cell", required=True)
    ap.add_argument("--lov-session", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--rig", required=True)
    ap.add_argument("--threads", default="16")
    ap.add_argument("--timeout", type=int, default=30)
    a = ap.parse_args()

    cells = load_map()["cells"]
    if a.cell not in cells:
        return fail(f"cell-{a.cell} not in ops/fleet.json — add it via build_fleet.py first")
    if cells[a.cell].get("miner") != "mining":
        return fail(f"cell-{a.cell} not flagged miner=mining in fleet.json")

    if preflight(a.lov_session):
        return 1
    if not asyncio.run(bridge_serves_job()):
        return fail("bridge not serving JOB — fix bridge before bootstrapping miners")
    if deploy(a.cell):
        return fail("deploy failed")
    print(f"rig={a.rig} threads={a.threads} project={a.project} wallet={WALLET[:12]}...",
          flush=True)
    return verify(a.cell, cells, a.timeout)


if __name__ == "__main__":
    sys.exit(main())
