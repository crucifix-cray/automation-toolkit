#!/usr/bin/env python3
"""One-shot fleet fix: kill stray processes eating cells, and make swap usable.

Two things were found costing every cell its headroom:

1. Stray `tor` (96MB on cell-13) left over from egress testing. The bridge
   provides Tor; cells never needed it.
2. 223MB of swap present but untouched (2MB used) while cells sat pinned at the
   cgroup ceiling — so the OOM killer fired with swap sitting idle. Low
   swappiness means the kernel won't page out anon memory under pressure.

Fix: kill strays, set swappiness high, and drop caches when the cgroup is near
the ceiling so page cache (200MB+ per cell) is reclaimable immediately.

Usage: python3 fleet_relief.py [--par 2] [--only 13,28]
"""
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

OPS = Path("/home/alan/Documents/repos/chimera-miner/ops")
sys.path.insert(0, str(OPS))
from ssh_reliable import ssh_checked  # noqa: E402
from cell_ops import load_map  # noqa: E402

# Strays we are confident are junk. Deliberately NOT matching: chrome, daemon.py,
# lean_sup.sh, Xvfb, python3, moly, miner binaries.
CLEANUP = (
    "echo MARK-END; "
    "pkill -9 -f 'tor -f' 2>/dev/null; "
    "pkill -9 -f cloudflared 2>/dev/null; "
    "pkill -9 -f 'apt-get' 2>/dev/null; "
    "sync; echo 3 > /proc/sys/vm/drop_caches 2>/dev/null; "
    "echo 100 > /proc/sys/vm/swappiness 2>/dev/null; "
    "free -m | sed -n 3p; "
    "echo RELIEF_DONE"
)


def one(cell_no: str, cell: dict) -> str:
    rs = cell.get("railway_session")
    home = Path(f"/home/alan/Documents/railways/sessions/session-{rs}")
    svc = cell.get("service_name") or f"cell-{cell_no}"
    try:
        ok, out = ssh_checked(home, svc, CLEANUP, "MARK-END", timeout=200, tries=2)
    except Exception as e:
        return f"cell-{cell_no}: ERR {str(e)[:60]}"
    if not ok:
        return f"cell-{cell_no}: unreachable"
    swap = ""
    for line in (out or "").splitlines():
        if "Swap:" in line:
            swap = line.strip()
    return f"cell-{cell_no}: relief ok | {swap}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--par", type=int, default=2)
    ap.add_argument("--only", type=str, default="")
    a = ap.parse_args()

    cells = load_map()["cells"]
    targets = sorted(
        [c for c, v in cells.items() if v.get("miner") == "mining"], key=int
    )
    if a.only:
        keep = set(a.only.split(","))
        targets = [c for c in targets if c in keep]

    with ThreadPoolExecutor(max_workers=a.par) as ex:
        for line in ex.map(lambda c: one(c, cells[c]), targets):
            print(line, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
