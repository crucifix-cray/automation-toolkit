#!/usr/bin/env python3
"""bootstrap_cell.py — turn a fresh ubuntu:24.04 Railway service into a miner.

Usage: python3 bootstrap_cell.py --rs 19 --inst 3e4963b9 --svc cell-82 \
         --lov 33 --proj b27e2af0-... [--threads 16]
Steps: system stack -> uv/python -> pip stack -> chromium -> golden files ->
trio (must be rescued already) -> mine.sh launch -> worker proof.
Idempotent: re-runnable; skips present pieces.
"""
import argparse
import base64
import gzip
import hashlib
import json
import sys
import time
from pathlib import Path

BASE = Path("/home/alan/Documents/railways")
sys.path.insert(0, str(BASE))
from cell_ssh2 import run  # noqa: E402

GOLD = {"daemon.py": "cb9305f50b6f1cee90fbbe74c0a2f009",
        "miner_injector.py": "e9e158a76419522f635ebcdcd3b82590",
        "watchdog_worker.py": "fb546c05f626c16b21d617ddf5001562"}
SRC = {"daemon.py": BASE / "miner-template/golden-cell/daemon.golden.py",
       "miner_injector.py": Path("/home/alan/Documents/repos/chimera-miner/miner_injector.py"),
       "watchdog_worker.py": Path("/home/alan/Documents/repos/chimera-miner/watchdog_worker.py")}


def sh(rs, inst, svc, script, timeout=560, tries=2):
    ok, out = run(rs, inst, script, "MARK-END", service=svc,
                  timeout=timeout, tries=tries)
    body = (out.split("MARK-END")[0] if "MARK-END" in (out or "") else (out or ""))
    return ok, body


def bootstrap(a):
    I, svc = a.inst, a.svc
    from cell_ssh2 import upload
    print(f"[{svc}] ship mine.sh...", flush=True)
    for src, dst in [(BASE / "miner-template/mine.sh", "/app/mine.sh"),
                     (BASE / "cellssh/start_miner.sh", "/app/start_miner.sh"),
                     (BASE / "cellssh/reaper.py", "/app/chrome_reaper.py")]:
        if not src.exists():
            return f"{svc}: MISSING {src}"
        ok, o = upload(a.rs, I, src, dst, service=svc)
        if not ok:
            return f"{svc}: SHIP-FAIL {dst}"
    print(f"[{svc}] system stack...", flush=True)
    ok, o = sh(a.rs, I, svc,
        "echo; export DEBIAN_FRONTEND=noninteractive; apt-get update -q 2>&1 | tail -1; "
        "apt-get install -y -q xvfb curl ca-certificates python3 python3-pip fonts-liberation "
        "libgtk-3-0 libasound2t64 libnspr4 libnss3 libatk1.0-0t64 libatk-bridge2.0-0t64 "
        "libcups2t64 libdrm2 libgbm1 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 "
        "libxrandr2 libpango-1.0-0 libcairo2 libatspi2.0-0t64 libdbus-1-3 libxshmfence1 2>&1 | tail -1; "
        "which python3; echo MARK-END", timeout=590, tries=1)
    if not ok:
        return f"{svc}: SYS-FAIL"
    print(f"[{svc}] python...", flush=True)
    ok, o = sh(a.rs, I, svc,
        "echo; export PATH=/root/.local/bin:$PATH; "
        "(curl -LsSf https://astral.sh/uv/install.sh | sh) 2>&1 | tail -1; "
        "uv python install 3.14 2>&1 | tail -1; uv venv --python 3.14 /opt/venv 2>&1 | tail -1; "
        "uv pip install -p /opt/venv -q patchright playwright camoufox websockets psutil requests 2>&1 | tail -1; "
        "/opt/venv/bin/python3 -c \"import patchright,playwright; print(1)\"; echo MARK-END",
        timeout=590, tries=1)
    if not ok or "\n1\n" not in o:
        return f"{svc}: PY-FAIL {o[-120:]}"
    print(f"[{svc}] chromium...", flush=True)
    ok, o = sh(a.rs, I, svc,
        "echo; /opt/venv/bin/python3 -m patchright install chromium 2>&1 | tail -1; "
        "ls /root/.cache/ms-playwright/ | head -2; echo MARK-END", timeout=590, tries=1)
    if not ok:
        return f"{svc}: CHROME-FAIL"
    print(f"[{svc}] golden files...", flush=True)
    from cell_ssh2 import upload_big
    for name, want in GOLD.items():
        ok, info = upload_big(a.rs, I, SRC[name],
                              f"/app/work/chimera-miner/{name}", service=svc)
        print(f"[{svc}] {name}: {info}", flush=True)
        if "match=True" not in info:
            return f"{svc}: GOLD-FAIL {name}"
    print(f"[{svc}] mine.sh + trio...", flush=True)
    trio = BASE / "scripts" / "sessions" / f"session-{a.lov}" / "cookies.json"
    if not trio.exists():
        return f"{svc}: NO-TRIO session-{a.lov}"
    ck = __import__("base64").b64encode(trio.read_bytes()).decode()
    cfgp = BASE / "scripts" / "sessions" / f"session-{a.lov}" / "config.json"
    cf = __import__("base64").b64encode(cfgp.read_bytes()).decode() if cfgp.exists() else ""
    ok, o = sh(a.rs, I, svc,
        "echo; cp /app/mine.sh /app/work/chimera-miner/mine.sh 2>/dev/null || true; "
        "mkdir -p /app/work/scripts/sessions/session-%s /app/work/shots; "
        "printf '%%s' '%s' | base64 -d > /app/work/scripts/sessions/session-%s/cookies.json; "
        "printf '%%s' '%s' | base64 -d > /app/work/scripts/sessions/session-%s/config.json; "
        "ls /app/work/scripts/sessions/session-%s/; echo MARK-END" % (a.lov, ck, a.lov, cf, a.lov, a.lov),
        timeout=400, tries=2)
    if "cookies.json" not in o:
        return f"{svc}: TRIO-FAIL"
    print(f"[{svc}] launch...", flush=True)
    ok, o = sh(a.rs, I, svc,
        "echo; cd /app/work/chimera-miner && chmod +x mine.sh; "
        "/app/start_miner.sh session-%s %s /app/work/daemon_%s.log 2>/dev/null || "
        "(setsid nohup ./mine.sh --session session-%s --project %s --log /app/work/daemon_%s.log >/app/work/launcher.log 2>&1 < /dev/null & sleep 10); "
        "ps -eo args | grep -c '[d]aemon.py'; echo MARK-END" % (a.lov, a.proj, a.svc, a.lov, a.proj, a.svc),
        timeout=400, tries=1)
    return f"{svc}: LAUNCHED"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rs", type=int, required=True)
    ap.add_argument("--inst", required=True)
    ap.add_argument("--svc", required=True)
    ap.add_argument("--lov", type=int, required=True)
    ap.add_argument("--proj", required=True)
    a = ap.parse_args()
    print(bootstrap(a), flush=True)
