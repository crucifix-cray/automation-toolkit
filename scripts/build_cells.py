#!/usr/bin/env python3
"""Build persistent worker cells: 1 per ok Railway account.
Per session: init project cell-N -> sandbox create -> exec cell_provision.sh
-> checkpoint cellbase -> idle-destroy (checkpoint persists, zero burn).

Cells are NOT 24/7: Railway caps idle at 5min. Persistence = checkpoint;
boot live with: railway sandbox create -p <project> --checkpoint cellbase.
Registry: cells.json (ids only, safe to commit).

Usage: python3 scripts/build_cells.py [--par 10] [--only session-111,session-112]
Raw IP only (proxy env stripped), isolated HOME per session.
"""
import argparse, json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path("/home/alan/Documents/railways")
BASE = REPO / "sessions"
REG = REPO / "cells.json"
WORK = Path("/tmp/cellwork")
RAILWAY = "/home/alan/.railway/bin/railway"
SETUP = (REPO / "scripts/cell_provision.sh").read_text()


def load_registry():
    try:
        return {c["session"]: c for c in json.load(open(REG))}
    except Exception:
        return {}


def save_registry(reg):
    json.dump(sorted(reg.values(), key=lambda c: c["session"]), open(REG, "w"), indent=1)


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


def resolve_env(env, cwd):
    try:
        rc, out = run([RAILWAY, "status", "--json"], env, cwd, 60)
        data = json.loads(out[out.index("{"):])
        for e in ((data.get("environments") or {}).get("edges") or []):
            n = e.get("node") or {}
            if not n.get("deletedAt") and n.get("id"):
                return n["id"]
    except Exception:
        pass
    return ""


def build_one(name, reg):
    rec = reg.get(name, {"session": name})
    sdir = BASE / name
    if not (sdir / ".railway" / "config.json").exists():
        return {"session": name, "status": "no-config"}
    if rec.get("checkpoint") == "cellbase" and rec.get("project"):
        return {**rec, "status": "ready"}
    env = env_for(sdir)
    cwd = WORK / name
    cwd.mkdir(parents=True, exist_ok=True)
    n = name.replace("session-", "")

    if not rec.get("project"):
        pid, out = None, ""
        for attempt in range(6):
            rc, out = run([RAILWAY, "init", "--name", f"cell-{n}", "--json"], env, cwd, 120)
            try:
                pid = json.loads(out[out.index("{"):])["id"] if "{" in out else None
            except Exception:
                pid = None
            if pid:
                break
            if "too quickly" in out and attempt < 5:
                time.sleep(35)
                continue
            break
        if not pid:
            # Railway often creates the project yet still reports rate-limit:
            # adopt cell-N if it exists before giving up.
            try:
                rc2, out2 = run([RAILWAY, "list", "--json"], env, cwd, 90)
                for p in json.loads(out2[out2.index("["):]):
                    if p.get("name") == f"cell-{n}" and not p.get("deletedAt"):
                        pid = p["id"]
                        break
            except Exception:
                pass
        if not pid:
            return {"session": name, "status": "init-fail", "out": out[:200]}
        rec["project"] = pid
        save_registry({**load_registry(), name: rec})

    if not rec.get("env"):
        rec["env"] = resolve_env(env, cwd) or resolve_env(env, REPO)
        if rec.get("env"):
            grid = load_registry()
            grid[name] = {**grid.get(name, {}), **rec}
            save_registry(grid)
    ee = ["-e", rec["env"]] if rec.get("env") else []
    rc, out = run([RAILWAY, "sandbox", "create", "-p", rec["project"], *ee,
                   "--idle-timeout-minutes", "5", "--json"], env, cwd, 180)
    if rc != 0 or '"id"' not in out:
        return {**rec, "status": "sandbox-fail", "out": out[:200]}
    time.sleep(20)
    rc, out = run([RAILWAY, "sandbox", "exec", "-p", rec["project"], *ee, "--", "bash", "-c", SETUP],
                  env, cwd, 600)
    if rc != 0 or "CELL READY" not in out:
        return {**rec, "status": "provision-fail", "out": out[-300:]}
    rc, out = run([RAILWAY, "sandbox", "checkpoint", "create", "cellbase",
                   "-p", rec["project"], *ee, "--json"], env, cwd, 300)
    if rc != 0:
        return {**rec, "status": "checkpoint-fail", "out": out[:200]}
    rec["checkpoint"] = "cellbase"
    # running box idle-destroys in <=5min; checkpoint persists, zero burn
    rec["status"] = "ready"
    grid = load_registry()
    grid[name] = rec
    save_registry(grid)
    return dict(rec)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--par", type=int, default=10)
    ap.add_argument("--only", type=str, default="")
    a = ap.parse_args()
    vrf = json.load(open(REPO / "finals/railway_verify.json"))
    oks = sorted([r["session"] for r in vrf if r["status"] == "ok"],
                 key=lambda x: int(x.split("-")[1]))
    names = [s.strip() for s in a.only.split(",")] if a.only else oks
    print(f"building {len(names)} cells x{a.par}", flush=True)
    reg = load_registry()
    out = []
    import functools
    with ThreadPoolExecutor(max_workers=a.par) as ex:
        futs = {ex.submit(build_one, n, dict(reg)): n for n in names}
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
    print(f"registry: {REG} ({len(grid)} entries)")


if __name__ == "__main__":
    main()
