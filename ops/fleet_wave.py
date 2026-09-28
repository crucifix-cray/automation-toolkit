#!/usr/bin/env python3
"""Cyclic wave driver: keep firing the VPS fleet until TARGET accounts banked.

Each cycle: fire unfired+failed boxes (adaptive par) -> wait for jobs ->
harvest new farm/lov-* branches into finals/lovables_harvest.json ->
commit+push. Stops when banked >= TARGET.

Adaptive throttle handling: watch the first 15 starts of each cycle; if
rc=255 (SSH gateway throttle) exceeds 30%, kill the run, back off
(5/10/20 min), halve par (floor 6), retry.

Usage:
  python3 ops/fleet_wave.py --target 500 --par 10 --cmd-file /tmp/payload_fire.sh
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path("/home/alan/Documents/railways")
HARVEST = REPO / "finals" / "lovables_harvest.json"
SSH_REG = REPO / "finals" / "fleet_ssh_registry.json"


def sh(cmd: str, timeout: int = 120) -> tuple[int, str]:
    env = dict(os.environ, LD_PRELOAD="")
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
              "ALL_PROXY", "all_proxy"):
        env.pop(k, None)
    try:
        p = subprocess.run(cmd, shell=True, cwd=str(REPO), env=env,
                           capture_output=True, text=True, timeout=timeout)
        return p.returncode, ((p.stdout or "") + (p.stderr or ""))[-500:]
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT"


def banked() -> int:
    try:
        return sum(1 for r in json.loads(HARVEST.read_text())
                   if str(r.get("verified")) == "True")
    except Exception:
        return 0


def recent_throttle_rate(n: int = 15) -> float:
    try:
        d = json.loads(SSH_REG.read_text())
    except Exception:
        return 0.0
    items = list(d.values())[-n:]
    if not items:
        return 0.0
    bad = sum(1 for v in items
              if v.get("status") == "fail" and "255" in str(v.get("out", "")))
    return bad / len(items)


def harvest() -> int:
    """Fetch farm/lov-* branches, merge new verified sessions. Returns new count."""
    sh("git fetch origin '+refs/heads/farm/lov-*:refs/remotes/origin/farm/lov-*'",
       timeout=300)
    try:
        branches = [b.strip() for b in subprocess.check_output(
            ["git", "branch", "-r"], text=True, cwd=str(REPO)).splitlines()
            if "farm/lov-" in b]
    except Exception:
        return 0
    try:
        old = json.loads(HARVEST.read_text())
    except Exception:
        old = []
    known = {r.get("branch") for r in old}
    new = 0
    for b in branches:
        name = b.split("/")[-1]
        if name in known:
            continue
        try:
            files = subprocess.check_output(
                ["git", "show", "--name-only", "--format=", b],
                text=True, cwd=str(REPO)).splitlines()
            v = [f for f in files if f.endswith("verified.json")]
            email, verified = None, None
            if v:
                d = json.loads(subprocess.check_output(
                    ["git", "show", f"{b}:{v[0]}"], text=True, cwd=str(REPO)))
                email, verified = d.get("email"), d.get("verified")
            old.append({"branch": name, "email": email, "verified": verified})
            if str(verified) == "True":
                new += 1
        except Exception as e:
            old.append({"branch": name, "error": str(e)[:60]})
    json.dump(old, open(HARVEST, "w"), indent=1)
    sh("git add finals/lovables_harvest.json && git commit -m 'harvest: wave pickup' "
       "&& git push", timeout=180)
    return new


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=500)
    ap.add_argument("--par", type=int, default=10)
    ap.add_argument("--cmd-file", required=True)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--job-wait", type=int, default=1200,
                    help="seconds to let jobs run before harvest")
    a = ap.parse_args()

    par = a.par
    backoff = 300
    wave = 0
    while banked() < a.target:
        wave += 1
        need = a.target - banked()
        print(f"===== WAVE {wave}: banked={banked()} need={need} par={par} =====",
              flush=True)
        rc, _ = sh(
            f"setsid nohup python3 ops/fleet_ssh.py --cmd-file {a.cmd_file} "
            f"--par {par} --timeout 90 --fire-and-forget "
            f"--no-resume --jid-offset {wave * 503} "
            f"--offset {(wave * 100) % 504} --target 150 "
            f"> /tmp/wave{wave}.log 2>&1 < /dev/null & disown; echo launched",
            timeout=60)
        # watch first 15 starts for throttle
        time.sleep(240)
        rate = recent_throttle_rate(15)
        print(f"throttle rate in first 15: {rate:.0%}", flush=True)
        if rate > 0.30:
            sh("ps aux | grep -F 'fleet_ssh' | grep -v grep | awk '{print $2}' "
               "| xargs -r kill -9", timeout=30)
            print(f"THROTTLED - backing off {backoff//60} min, par {par}->{max(6, par//2)}",
                  flush=True)
            par = max(6, par // 2)
            time.sleep(backoff)
            backoff = min(backoff * 2, 1200)
            continue
        backoff = 300
        if par < a.par:
            par = min(a.par, par + 2)
        print(f"waiting {a.job_wait//60} min for jobs...", flush=True)
        time.sleep(a.job_wait)
        new = harvest()
        print(f"harvested +{new} -> banked={banked()}", flush=True)
    print(f"DONE: banked={banked()} >= {a.target}", flush=True)


if __name__ == "__main__":
    main()
