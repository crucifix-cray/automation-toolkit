#!/usr/bin/env python3
"""Deploy the VPS worker base image to every farmed jar (one-time stand-up).

Each jar: link project/env/service -> `railway up` the shared build context.
Resume-safe via finals/fleet_deploy_registry.json. Verifies a new SUCCESS
deployment appears.

Usage:
  python3 ops/fleet_deploy.py --par 18 --target 502
  python3 ops/fleet_deploy.py --only cxs33   # single-jar test
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path("/home/alan/Documents/railways")
RAILWAY = "/home/alan/.railway/bin/railway"
SRC = REPO / "docker" / "vps_worker"
REG = REPO / "finals" / "fleet_deploy_registry.json"


def base_env() -> dict:
    e = dict(os.environ, LD_PRELOAD="")
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
              "ALL_PROXY", "all_proxy"):
        e.pop(k, None)
    return e


def load_jars(only: str = "") -> list[Path]:
    jars = sorted(Path(REPO / "finals" / "sessions").glob("farmed-*/"))
    for d in sorted(Path(REPO).glob("session-[0-9]*")):
        if d.is_dir() and (d / "verified.json").is_file():
            jars.append(d)
    if only:
        jars = [j for j in jars if only in j.name]
    return [j for j in jars
            if (j / ".railway" / "config.json").is_file()
            and (j / "verified.json").is_file()]


def jar_ids(jar: Path) -> tuple[str, str, str] | None:
    try:
        d = json.loads((jar / "verified.json").read_text())
        return (d["railway_project_id"], d["environment_id"],
                d.get("service_name") or d.get("service_id"))
    except Exception:
        return None


def run(args: list[str], jar: Path, cwd: Path, timeout: int) -> tuple[int, str]:
    env = dict(base_env(), HOME=str(jar))
    try:
        p = subprocess.run([RAILWAY] + args, env=env, cwd=str(cwd),
                           capture_output=True, text=True, timeout=timeout)
        return p.returncode, ((p.stdout or "") + "\n" + (p.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT"
    except Exception as e:
        return -2, f"ERR:{str(e)[:100]}"


def svc_ok(jar: Path, build: Path, proj: str, envid: str) -> tuple[bool, str]:
    rc, out = run(["service", "list", "-p", proj, "-e", envid, "--json"],
                  jar, build, 90)
    try:
        for s in json.loads(out[out.index("["):]):
            if s.get("deploymentStopped"):
                continue
            d = s.get("latestDeployment") or {}
            if d.get("id"):
                return True, d["id"][:8]
    except Exception:
        pass
    return False, out[-120:]


def one(jar: Path, build: Path) -> dict:
    rec = {"jar": jar.name}
    ids = jar_ids(jar)
    if not ids:
        return {**rec, "status": "no-ids"}
    proj, envid, svc = ids
    rc, out = run(["link", "-p", proj, "-e", envid, "-s", svc, "--json"],
                  jar, build, 60)
    if rc != 0 and "serviceName" not in out:
        return {**rec, "status": "link-fail", "out": out[-150:]}
    rc, out = run(["up", "-d", "-y", "--ci"], jar, build, 900)
    if rc != 0:
        return {**rec, "status": "up-fail", "out": out[-200:]}
    time.sleep(20)
    for _ in range(6):
        ok, info = svc_ok(jar, build, proj, envid)
        if ok:
            return {**rec, "status": "ok", "deploy": info}
        time.sleep(30)
    return {**rec, "status": "no-deploy", "out": info[-150:]}


def main() -> None:
    ap = argparse.ArgumentParser(description="Deploy VPS base image to all jars")
    ap.add_argument("--par", type=int, default=18)
    ap.add_argument("--target", type=int, default=0)
    ap.add_argument("--only", default="")
    a = ap.parse_args()

    build = Path("/tmp/vpsbuild_fleet")
    shutil.rmtree(build, ignore_errors=True)
    build.mkdir(parents=True)
    shutil.copy(SRC / "Dockerfile", build / "Dockerfile")
    shutil.copy(SRC / "entrypoint.sh", build / "entrypoint.sh")

    jars = load_jars(a.only)
    if a.target:
        jars = jars[:a.target]
    print(f"jars={len(jars)} par={a.par}", flush=True)

    try:
        reg = json.loads(REG.read_text())
    except Exception:
        reg = {}
    todo = [j for j in jars if reg.get(j.name, {}).get("status") != "ok"]
    print(f"todo={len(todo)} (skipped {len(jars) - len(todo)} done)", flush=True)

    ok = fail = 0
    with ThreadPoolExecutor(max_workers=a.par) as ex:
        futs = {ex.submit(one, j, build): j for j in todo}
        for i, f in enumerate(as_completed(futs), 1):
            try:
                r = f.result()
            except Exception as e:
                r = {"jar": futs[f].name, "status": f"harness:{str(e)[:70]}"}
            reg[r["jar"]] = {**r, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            if r.get("status") == "ok":
                ok += 1
            else:
                fail += 1
            if i % 10 == 0 or i == len(todo):
                tmp = str(REG) + ".tmp"
                json.dump(reg, open(tmp, "w"), indent=1)
                os.replace(tmp, str(REG))
                print(f"[{i}/{len(todo)}] ok={ok} fail={fail} last={r['jar']}:{r['status']}",
                      flush=True)
    tmp = str(REG) + ".tmp"
    json.dump(reg, open(tmp, "w"), indent=1)
    os.replace(tmp, str(REG))
    print(f"FINAL ok={ok} fail={fail}", flush=True)


if __name__ == "__main__":
    main()
