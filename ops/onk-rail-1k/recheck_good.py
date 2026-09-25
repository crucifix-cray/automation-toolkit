#!/usr/bin/env python3
"""Re-probe UP_GOOD sessions to check they are STILL healthy now.

UP_GOOD means "passed up→SUCCESS→down at verify time". Railway can restrict a
workspace AFTER that. This re-runs the deploy gate on a sample and reports
how many are still deployable, so we know the real number instead of trusting
a stale marker.

Usage: python3 recheck_good.py --ids-file /tmp/recheck-sample.txt --par 8
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

DEST = Path("/home/alae/Documents/railways")
WORK = Path("/tmp/rv-recheck")
DOCKERFILE = 'FROM alpine:3.20\nCMD ["sleep", "infinity"]\n'
BLOCK = ("restricted", "banned", "suspended", "forbidden", "payment",
         "attach a payment", "contact support")


def env_for(home: Path) -> dict:
    e = {**os.environ, "HOME": str(home), "LD_PRELOAD": "",
         "BROWSER": "/home/alae/bin/no-browser",
         "PATH": "/home/alae/bin:" + os.environ.get("PATH", "/usr/bin")}
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        e.pop(k, None)
    return e


def run(cmd, env, cwd, timeout):
    return subprocess.run(cmd, env=env, cwd=str(cwd), capture_output=True,
                          text=True, timeout=timeout)


def check(name: str) -> dict:
    d = DEST / name
    v = d / "verified.json"
    if not v.is_file():
        return {"session": name, "status": "no_verified"}
    try:
        m = json.loads(v.read_text())
    except Exception:
        return {"session": name, "status": "bad_json"}
    proj, svc = m.get("project_name"), m.get("service_name") or f"hlth-{name.split('-')[-1]}"
    if not (proj and m.get("service_id")):
        return {"session": name, "status": "no_project_meta"}
    env = env_for(d)
    cwd = WORK / name
    shutil.rmtree(cwd, ignore_errors=True)
    cwd.mkdir(parents=True)
    (cwd / "Dockerfile").write_text(DOCKERFILE)

    r = run(["railway", "link", "-p", proj, "-e", "production", "-s", svc], env, cwd, 90)
    if r.returncode != 0 and "linked" not in (r.stdout + r.stderr).lower():
        return {"session": name, "status": "link_fail", "detail": (r.stderr or r.stdout)[:150]}

    r = run(["railway", "up", "-d", "-y", "--service", svc], env, cwd, 180)
    out = r.stdout + r.stderr
    low = out.lower()
    blocked = next((b for b in BLOCK if b in low), None)
    if blocked:
        run(["railway", "down", "-y", "--service", svc], env, cwd, 90)
        # non-destructive: keep the original UP_GOOD, flag it as now-dead so
        # the honest healthy count can exclude it.
        (d / "RECHECK_FAIL").write_text(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {blocked}\n")
        return {"session": name, "status": "RESTRICTED", "detail": blocked,
                "email": (d / "email.txt").read_text().strip() if (d / "email.txt").is_file() else ""}
    if "Build Logs" in out or "railway.com/project/" in out:
        time.sleep(25)
        run(["railway", "down", "-y", "--service", svc], env, cwd, 90)
        # fresh-stamp so count_ready reflects verified-now, not verified-once
        (d / "UP_GOOD").write_text(time.strftime("%Y-%m-%dT%H:%M:%S") + "\n")
        (d / "RECHECK_FAIL").unlink(missing_ok=True)
        return {"session": name, "status": "still_good"}
    run(["railway", "down", "-y", "--service", svc], env, cwd, 90)
    return {"session": name, "status": "up_fail", "detail": out[:200]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids-file")
    ap.add_argument("--all", action="store_true", help="sweep every UP_GOOD session")
    ap.add_argument("--par", type=int, default=8)
    a = ap.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    if a.all:
        names = sorted((d.name for d in DEST.glob("session-*") if (d / "UP_GOOD").is_file()),
                       key=lambda n: int(n.split("-")[1]))
    else:
        names = [x.strip() for x in open(a.ids_file) if x.strip()]
    print(f"recheck: {len(names)} sessions par={a.par}", flush=True)
    out = []
    with ThreadPoolExecutor(max_workers=a.par) as ex:
        futs = [ex.submit(check, n) for n in names]
        for f in as_completed(futs):
            try:
                r = f.result()
            except Exception as e:
                r = {"session": "?", "status": f"exc:{str(e)[:60]}"}
            out.append(r)
            print(f"{r['session']:>14} → {r['status']}  {str(r.get('detail',''))[:60]}", flush=True)
    from collections import Counter
    c = Counter(r["status"] for r in out)
    print("SUMMARY", dict(c), flush=True)
    Path("/home/alae/onk-rail-1k/recheck_summary.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
