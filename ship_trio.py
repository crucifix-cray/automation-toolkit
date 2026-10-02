#!/usr/bin/env python3
"""ship_trio.py — push a fresh trio to a cell and relaunch mine.sh.

Usage: python3 ship_trio.py --cell 88 --lov 42
Trio source: railways/scripts/sessions/session-<lov>/ (cookies.json +
indexeddb.json when present). Daemon + mine.sh must already be on the cell.
"""
import argparse
import base64
import sys
from pathlib import Path

sys.path.insert(0, "/home/alan/Documents/repos/chimera-miner/ops")
from ssh_reliable import ssh_checked  # noqa: E402
from cell_ops import load_map  # noqa: E402

BASE = Path("/home/alan/Documents/railways")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cell", required=True)
    ap.add_argument("--lov", type=int, required=True)
    a = ap.parse_args()
    cells = load_map()["cells"]
    cell = cells[a.cell]
    home = Path(f"/home/alan/Documents/railways/sessions/session-{cell.get('railway_session')}")
    svc = cell.get("service_name") or f"cell-{a.cell}"
    log = cell.get("log") or f"daemon_r{a.cell}.log"
    ck = base64.b64encode((BASE / f"scripts/sessions/session-{a.lov}/cookies.json").read_bytes()).decode()
    ij = BASE / f"scripts/sessions/session-{a.lov}/indexeddb.json"
    ijb = base64.b64encode(ij.read_bytes()).decode() if ij.exists() else ""
    s = ("echo MARK-END; mkdir -p /app/work/scripts/sessions/session-%s; "
         "printf '%%s' '%s' | base64 -d > /app/work/scripts/sessions/session-%s/cookies.json; "
         % (a.lov, ck, a.lov))
    if ijb:
        s += ("printf '%%s' '%s' | base64 -d > /app/work/scripts/sessions/session-%s/indexeddb.json; "
              % (ijb, a.lov))
    s += ("chmod +x /app/work/chimera-miner/mine.sh; cd /app/work/chimera-miner && "
          "setsid nohup ./mine.sh --session session-%s --project %s --log /app/work/%s "
          ">>/app/work/launch_%s.log 2>&1 < /dev/null & sleep 10; echo SHIPPED"
          % (a.lov, cell.get("lovable_project"), log, a.cell))
    try:
        ok, _ = ssh_checked(home, svc, s, "MARK-END", timeout=250, tries=2)
    except Exception as e:
        print(f"cell-{a.cell}: ERR {str(e)[:70]}", flush=True)
        return 1
    print(f"cell-{a.cell}: {'TRIO+RELAUNCH' if ok else 'FAIL'}", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
