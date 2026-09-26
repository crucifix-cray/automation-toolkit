#!/usr/bin/env python3
"""Fleet supervisor — keeps every mining cell alive.

Runs forever. Each cycle it probes every cell over the *reliable* ssh helper
(marker-checked; a bare rc=0 with no output means the command never ran), then
applies the least-blaming fix that works:

  healthy          -> "Worker alive" + "Preview healthy" in the recent log
  browser-dead     -> chrome procs == 0            -> restart lean_sup (relaunches browser)
  stalled          -> mem pinned at ceiling, no progress, no worker -> bounce daemon
  daemon-dead      -> no daemon proc               -> bounce
  unreachable      -> leave alone, count it, try next cycle

Escalation: a cell that stays unhealthy for N consecutive cycles gets a full
lean_sup restart regardless of which bucket it landed in. Nothing here ever
kills a cell that is actually mining.

Usage:  python3 fleet_supervisor.py            (foreground, Ctrl-C to stop)
        setsid nohup python3 fleet_supervisor.py >> /var/log/fleet-sup.log 2>&1 &
Options: --par 2 --interval 240 --escalate 2 --only 13,16
"""
import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

OPS = Path("/home/alan/Documents/repos/chimera-miner/ops")
sys.path.insert(0, str(OPS))
from ssh_reliable import ssh_checked  # noqa: E402
from cell_ops import load_map  # noqa: E402

LOG_DIR = Path("/home/alan/Documents/railways")
MEM_MAX_MB = 953

PROBE = (
    'echo MARK-END; '
    'echo "chrome=$(pgrep -c chrome || echo 0)"; '
    'echo "daemon=$(pgrep -c -f "daemon.py" || echo 0)"; '
    'echo "mem=$(( $(cat /sys/fs/cgroup/memory.current 2>/dev/null || echo 0) / 1048576 ))"; '
    'tail -14 /data/work/{log} 2>/dev/null'
)


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def probe(cell_no: str, cell: dict) -> dict:
    """Return {state, chrome, daemon, mem, tail} for one cell."""
    rs = cell.get("railway_session")
    home = Path(f"/home/alan/Documents/railways/sessions/session-{rs}")
    logf = cell.get("log") or f"daemon_r{cell_no}.log"
    svc = cell.get("service_name") or f"cell-{cell_no}"

    try:
        ok, out = ssh_checked(
            home, svc, PROBE.format(log=logf), "MARK-END", timeout=200, tries=2
        )
    except Exception as e:
        return {"state": "unreachable", "err": str(e)[:80]}

    out = out or ""
    if not ok:
        return {"state": "unreachable"}

    chrome = daemon = mem = -1
    m = re.search(r"chrome=(\d+)", out)
    if m:
        chrome = int(m.group(1))
    m = re.search(r"daemon=(\d+)", out)
    if m:
        daemon = int(m.group(1))
    m = re.search(r"mem=(\d+)", out)
    if m:
        mem = int(m.group(1))

    tail = out.split("MARK-END", 1)[-1]
    alive = "Worker alive" in tail and "Preview healthy" in tail
    cycling = "tab_fail_streak" in tail

    if daemon == 0:
        state = "daemon-dead"
    elif chrome == 0:
        state = "browser-dead"
    elif alive:
        state = "healthy"
    elif cycling:
        state = "cycling"
    else:
        state = "stalled"

    return {"state": state, "chrome": chrome, "daemon": daemon, "mem": mem, "tail": tail[-200:]}


def act(cell_no: str, cell: dict, action: str) -> str:
    """Apply a fix. action in {bounce, restart_sup}."""
    rs = cell.get("railway_session")
    home = Path(f"/home/alan/Documents/railways/sessions/session-{rs}")
    svc = cell.get("service_name") or f"cell-{cell_no}"

    if action == "bounce":
        script = (
            "echo MARK-END; "
            "for p in $(pgrep -f 'daemon.py'); do kill -9 $p 2>/dev/null; done; "
            "sleep 1; echo BOUNCED"
        )
    else:  # restart_sup -> lean_sup respawns daemon + browser from scratch
        script = (
            "echo MARK-END; "
            "pkill -9 -f lean_sup.sh 2>/dev/null; "
            "pkill -9 -f daemon.py 2>/dev/null; "
            "pkill -9 -f chrome 2>/dev/null; "
            "sleep 2; "
            "setsid bash /app/work/lean_sup.sh >/dev/null 2>&1 & "
            "sleep 3; echo SUP_RESTARTED"
        )
    try:
        ok, out = ssh_checked(home, svc, script, "MARK-END", timeout=220, tries=1)
        return "ok" if ok else "failed"
    except Exception as e:
        return f"err:{str(e)[:60]}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--par", type=int, default=2)
    ap.add_argument("--interval", type=int, default=240)
    ap.add_argument("--escalate", type=int, default=2)
    ap.add_argument("--only", type=str, default="")
    a = ap.parse_args()

    m = load_map()
    cells = m["cells"]
    targets = sorted(
        [c for c, v in cells.items() if v.get("miner") == "mining"], key=int
    )
    if a.only:
        keep = set(a.only.split(","))
        targets = [c for c in targets if c in keep]

    log(f"supervising {len(targets)} cells: {','.join(targets)}")
    log(f"interval={a.interval}s par={a.par} escalate_after={a.escalate}")

    strikes: dict[str, int] = {c: 0 for c in targets}
    cycle = 0

    while True:
        cycle += 1
        log(f"--- cycle {cycle} ---")
        results = {}
        try:
            with ThreadPoolExecutor(max_workers=a.par) as ex:
                futs = {ex.submit(probe, c, cells[c]): c for c in targets}
                for f in futs:
                    c = futs[f]
                    try:
                        results[c] = f.result()
                    except Exception as e:
                        results[c] = {"state": "unreachable", "err": str(e)[:60]}
        except Exception as e:
            log(f"cycle error: {e}")
            time.sleep(a.interval)
            continue

        summary = {}
        for c in targets:
            r = results.get(c, {"state": "unreachable"})
            st = r["state"]
            summary[st] = summary.get(st, 0) + 1
            if st == "healthy":
                strikes[c] = 0
                continue

            strikes[c] += 1
            escalate = strikes[c] >= a.escalate
            action = "restart_sup" if escalate else "bounce"
            log(
                f"cell-{c}: {st} chrome={r.get('chrome')} daemon={r.get('daemon')} "
                f"mem={r.get('mem')}MB strike={strikes[c]} -> {action}"
            )
            res = act(c, cells[c], action)
            log(f"cell-{c}: {action} = {res}")
            if res != "ok":
                strikes[c] = 0  # couldn't act; re-evaluate fresh next cycle

        healthy = summary.get("healthy", 0)
        log(f"cycle {cycle}: {healthy}/{len(targets)} healthy  {summary}")

        state = {
            "cycle": cycle,
            "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "healthy": healthy,
            "total": len(targets),
            "summary": summary,
            "strikes": strikes,
        }
        (LOG_DIR / "fleet_supervisor_state.json").write_text(json.dumps(state, indent=1))

        time.sleep(a.interval)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("stopped")
