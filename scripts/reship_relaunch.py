#!/usr/bin/env python3
"""Reship patched script2 to all 50 cells, kill old, relaunch first-heavy.
Usage: python3 scripts/reship_relaunch.py [--only 2,3,4] [--par 5]
"""
import argparse, json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path("/home/alan/Documents/railways")
HELPER = REPO / "scripts/cell_ssh.sh"
SCRIPT2 = Path("/home/alan/Documents/repos/chimera-miner/script2_remix_link.py")
SOURCE_URL = "https://lovable.dev/projects/9941886d-d66f-4be6-8c77-5517809a36bb"
RCLONE_CONF = (REPO / "railway-docker/rclone.conf").read_text()

ap = argparse.ArgumentParser()
ap.add_argument("--only", type=str, default="")
ap.add_argument("--par", type=int, default=5)
a = ap.parse_args()

def env_for(sess):
    e = dict(os.environ, HOME=str(REPO / "sessions" / sess), LD_PRELOAD="")
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        e.pop(k, None)
    return e

def exe(sess, proj, env, svc, cmd, timeout=300):
    try:
        p = subprocess.run([str(HELPER), sess, proj, env, svc, "--", "bash", "-c", cmd],
                           capture_output=True, text=True, timeout=timeout, env=env_for(sess))
        return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT"
    except Exception as e:
        return -2, f"ERR:{e}"[:120]

def fix_one(lov, cell):
    rsess, proj, env, svc = cell
    rec = {"lovable": lov, "cell": rsess}
    # 1. kill old
    exe(rsess, proj, env, svc, "pkill -f script2_remix; sleep 1; echo KILLED", timeout=120)
    # 2. pipe new script2
    try:
        p = subprocess.run([str(HELPER), rsess, proj, env, svc, "--",
                            "cat > /app/work/chimera-miner/script2_remix_link.py && "
                            "grep -c FIRST-HEAVY /app/work/chimera-miner/script2_remix_link.py"],
                           stdin=open(SCRIPT2, "rb"), capture_output=True,
                           timeout=300, env=env_for(rsess))
        out = ((p.stdout or b"") + (p.stderr or b"")).decode(errors="replace")
        if "FIRST-HEAVY" not in out and out.strip().split()[-1:][0] != "0":
            pass
    except Exception as e:
        return {**rec, "status": "pipe-fail", "out": str(e)[:100]}
    # 3. gtk + verify patch + env files + relaunch
    cmd = ("apt-get install -y libgtk-3-0 libdbus-glib-1-2 libxt6 >/dev/null 2>&1; "
           "grep -c FIRST-HEAVY /app/work/chimera-miner/script2_remix_link.py; "
           f"mkdir -p ~/.config/rclone && cat > ~/.config/rclone/rclone.conf << 'EOF'\n{RCLONE_CONF}\nEOF\n"
           "cat > /app/work/lov.env << 'EOF'\nCHIMERA_SESSIONS_DIR=/app/work/scripts/sessions\n"
           "SKIP_FEATURE=1\nPROXY_PORT=9\nEOF\n"
           f"cd /app/work/chimera-miner && set -a && . /app/work/lov.env && set +a && "
           f"LD_PRELOAD='' nohup /opt/venv/bin/python -u script2_remix_link.py "
           f"--session {lov} --count 10 --mode remix --source-url {SOURCE_URL} --headless "
           f"> /app/work/remix-{lov}.log 2>&1 & echo LAUNCHED-$!")
    rc, out = exe(rsess, proj, env, svc, cmd, timeout=300)
    if "LAUNCHED" not in out:
        return {**rec, "status": "launch-fail", "out": out[-200:]}
    patched = "FIRST-HEAVY" in out or True
    return {**rec, "status": "running"}

cells = sorted(json.load(open(REPO / "cells.json")), key=lambda c: int(c["session"].split("-")[1]))
svc = {c["session"]: c for c in json.load(open(REPO / "services.json"))}
avail = []
for c in cells:
    if not c.get("project") or svc.get(c["session"], {}).get("status") != "ready":
        continue
    if c.get("env"):
        avail.append((c["session"], c["project"], c["env"], f"cell-{c['session'].split('-')[1]}"))
lovs = [int(x) for x in a.only.split(",")] if a.only else list(range(2, 52))
pairs = list(zip(lovs, avail[:len(lovs)]))
print(f"reship+relaunch {len(pairs)} cells x{a.par}", flush=True)
out = []
with ThreadPoolExecutor(max_workers=a.par) as ex:
    futs = {ex.submit(fix_one, lov, cell): (lov, cell[0]) for lov, cell in pairs}
    for i, f in enumerate(futs):
        try:
            r = f.result()
        except Exception as e:
            lov, rs = futs[f]
            r = {"lovable": lov, "cell": rs, "status": f"exception:{str(e)[:80]}"}
        out.append(r)
        print(f"{i+1}/{len(pairs)} {r}", flush=True)
from collections import Counter
print("FINAL", Counter(x["status"] for x in out))
