#!/usr/bin/env python3
"""Count UP_GOOD accounts only (passed railway up→down verify)."""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

DEST = Path("/home/alae/Documents/railways")
NEST = Path("/home/alae/Documents/railways/session-1/Documents/railways")
OUT = Path("/home/alae/onk-rail-1k/READY.json")
DONE = Path("/home/alae/onk-rail-1k/DONE.json")


def main() -> None:
    moved = 0
    if NEST.is_dir():
        for d in list(NEST.glob("session-*")):
            if not (d / "verified.json").is_file():
                continue
            t = DEST / d.name
            if t.exists() and (t / "verified.json").is_file():
                continue
            if t.exists():
                shutil.rmtree(t)
            shutil.move(str(d), str(t))
            moved += 1

    good = 0
    bad = 0
    dead = 0
    for d in DEST.glob("session-*"):
        if (d / "UP_GOOD").is_file():
            # a recheck that later found the workspace restricted/undeployable
            # no longer counts as healthy
            if (d / "RECHECK_FAIL").is_file():
                dead += 1
            else:
                good += 1
        elif (d / "UP_BAD").is_file():
            bad += 1
    print(
        f"{time.strftime('%H:%M:%S')} UP_GOOD={good} UP_BAD={bad} "
        f"recheck_dead={dead} salvaged={moved}",
        flush=True,
    )
    OUT.write_text(json.dumps(
        {"up_good": good, "up_bad": bad, "recheck_dead": dead, "ts": time.time()}, indent=2))
    if good >= 1000:
        DONE.write_text(json.dumps({"up_good": good, "done": True, "ts": time.time()}, indent=2))


if __name__ == "__main__":
    main()
