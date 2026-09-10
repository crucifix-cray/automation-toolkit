#!/usr/bin/env python3
"""Roll persistent worker services: 1 per ok account (51).
Per session: link cell-N project -> up Dockerfile -> poll SUCCESS
-> volume /data -> verify STACK OK in logs. Registry: services.json.

Usage: python3 scripts/build_services.py [--par 10] [--only session-111,session-112]
Raw IP only, isolated HOME per session. Resume-safe (skips SUCCESS services).
"""
import argparse, json, os, shutil, subprocess, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path("/home/alan/Documents/railways")
BASE = REPO / "sessions"
SRC = REPO / "scripts/cell_service"
REG = REPO / "services.json"
WORK = Path("/tmp/cellwork")
RAILWAY = "/home/alan/.railway/bin/railway"


def load_registry():
    try:
        return {c["session"]: c for c in json.load(open(REG))}
    except Exception:
        return {}


def save_registry(reg):
    tmp = str(REG) + ".tmp"
    json.dump(sorted(reg.values(), key=lambda c: c["session"]), open(tmp, "w"), indent=1)
    os.replace(tmp, REG)


def env_for(sdir):
    env = dict(os.environ, HOME=str(sdir), LD_PRELOAD="")
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        env.pop(k, None)
    return env


def run(args, env, cwd, timeout):
    try:
        p = subprocess.run(args, capture_output=True, text=True, env=env, cwd=str(cwd), timeout=timeout)
        return p.returncode, ((p.stdout or "") + "\n" + (p.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT"
    except Exception as e:
        return -2, f"ERR:{e}"[:150]


def svc_status(env, cwd):
    rc, out = run([RAILWAY, "service", "status", "--all"], env, cwd, 60)
    for line in out.splitlines():
        if "cell-" in line and "|" in line:
            parts = [x.strip() for x in line.split("|")]
            if len(parts) >= 3:
                return parts[2]
    return ""


def build_one(name, cells):
    rec = {"session": name}
    sdir = BASE / name
    if not (sdir / ".railway" / "config.json").exists():
        return {**rec, "status": "no-config"}
    proj = (cells.get(name) or {}).get("project")
    if not proj:
        return {**rec, "status": "no-cell-project"}
    env = env_for(sdir)
    cwd = WORK / f"{name}-svc"
    shutil.rmtree(cwd, ignore_errors=True)
    cwd.mkdir(parents=True)
    shutil.copy(SRC / "Dockerfile", cwd / "Dockerfile")
    shutil.copy(SRC / "start.sh", cwd / "start.sh")
    n = name.replace("session-", "")

    run([RAILWAY, "link", "-p", proj], env, cwd, 60)
    st = svc_status(env, cwd)
    if "SUCCESS" not in st:
        rc, out = run([RAILWAY, "up", "-d", "-y"], env, cwd, 120)
        for _ in range(24):  # ~12min build window
            time.sleep(30)
            st = svc_status(env, cwd)
            if "SUCCESS" in st or "FAILED" in st or "CRASH" in st:
                break
    if "SUCCESS" not in st:
        return {**rec, "project": proj, "status": "deploy-fail", "out": st[:150]}
    rec.update(project=proj, status="deployed")

    run([RAILWAY, "link", "-p", proj, "-s", f"cell-{n}"], env, cwd, 60)
    rc, out = run([RAILWAY, "volume", "add", "-m", "/data", "--json"], env, cwd, 120)
    if rc == 0 and '"id"' in out:
        try:
            rec["volume"] = json.loads(out[out.index("{"):])["id"]
        except Exception:
            pass
    rc, out = run([RAILWAY, "logs", "-s", f"cell-{n}", "--lines", "30"], env, cwd, 90)
    if "STACK OK" in out:
        rec["status"] = "ready"
    else:
        rec["status"] = "no-stack-log"
        rec["out"] = out[-200:]
    grid = load_registry()
    grid[name] = {**grid.get(name, {}), **rec}
    save_registry(grid)
    return dict(rec)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--par", type=int, default=10)
    ap.add_argument("--only", type=str, default="")
    a = ap.parse_args()
    cells = {c["session"]: c for c in json.load(open(REPO / "cells.json"))}
    vrf = json.load(open(REPO / "finals/railway_verify.json"))
    oks = sorted([r["session"] for r in vrf if r["status"] == "ok"],
                 key=lambda x: int(x.split("-")[1]))
    names = [s.strip() for s in a.only.split(",")] if a.only else oks
    print(f"services for {len(names)} sessions x{a.par}", flush=True)
    out = []
    with ThreadPoolExecutor(max_workers=a.par) as ex:
        futs = {ex.submit(build_one, n, cells): n for n in names}
        for i, f in enumerate(futs):
            try:
                r = f.result()
            except Exception as e:
                r = {"session": futs[f], "status": f"exception:{str(e)[:80]}"}
            out.append(r)
            if (i + 1) % 5 == 0 or (i + 1) == len(names):
                from collections import Counter
                print(f"{i+1}/{len(names)}", Counter(x["status"] for x in out), flush=True)
    from collections import Counter
    print("FINAL", Counter(x["status"] for x in out))
    grid = load_registry()
    for r in out:
        if r.get("project"):
            grid[r["session"]] = {**grid.get(r["session"], {}), **r}
    save_registry(grid)
    print(f"registry: {REG}")


if __name__ == "__main__":
    main()
