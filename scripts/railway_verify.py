#!/usr/bin/env python3
"""True health sweep: whoami -> list -> init (create) -> delete, per session.
Classifies each account: ok / trial / rate / restricted / unauthorized / error.
Writes finals/railway_verify.json + refreshes sessions/*/email.txt.

Usage: python3 scripts/railway_verify.py [--par 8] [--only session-1,session-2]
whoami alone only proves the token; init proves the account can create.
"""
import argparse, json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path("/home/alan/Documents/railways")
BASE = REPO / "sessions"
OUT = REPO / "finals" / "railway_verify.json"
WORK = Path("/tmp/rvwork")
RAILWAY = "/home/alan/.railway/bin/railway"


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
        return -2, f"ERR:{e}"[:120]


def classify_init(out):
    lo = out.lower()
    if re.search(r"rate.?limit|429|too many", lo):
        return "rate"
    if re.search(r"trial|verify your|verification|upgrade|payment|past due|delinquen|402", lo):
        return "trial"
    if re.search(r"forbidden|restricted|banned|suspended|deactivat|403", lo):
        return "restricted"
    if re.search(r"unauthor|401|login|expired|invalid.?token", lo):
        return "unauthorized"
    return "error"


def verify_one(name):
    rec = {"session": name}
    sdir = BASE / name
    cfg = sdir / ".railway" / "config.json"
    if not cfg.exists():
        rec.update(status="no-config")
        return rec
    env = env_for(sdir)
    cwd = WORK / name
    cwd.mkdir(parents=True, exist_ok=True)

    rc, out = run([RAILWAY, "whoami"], env, cwd, 60)
    first = out.splitlines()[0][:120] if out else ""
    m = re.search(r"Logged in as (\S+)", out)
    if m:
        email = m.group(1)
        rec["email"] = email
        try:
            (sdir / "email.txt").write_text(email + "\n")
        except Exception:
            pass
    else:
        rec.update(status="unauthorized", whoami=first)
        return rec
    rec["whoami"] = first

    rc, out = run([RAILWAY, "list", "--json"], env, cwd, 90)
    try:
        projs = json.loads(out) if out.strip().startswith(("[", "{")) else None
        rec["projects_before"] = len(projs) if isinstance(projs, list) else projs
    except Exception:
        rec["projects_before"] = "parse-err"

    pname = f"vrfy-{name.replace('session-', '')}-{int(time.time()) % 100000}"
    rc, out = run([RAILWAY, "init", "--name", pname, "--json"], env, cwd, 120)
    pid = None
    try:
        data = json.loads(out) if out.strip().startswith("{") else None
        pid = (data or {}).get("id") or (data or {}).get("projectId")
    except Exception:
        pass
    if not pid:
        m2 = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", out)
        pid = m2.group(0) if m2 and rc == 0 else None
    if rc != 0 or not pid:
        rec.update(status=classify_init(out), init_out=out[:300])
        return rec
    rec["canary_id"] = pid

    rc2, out2 = run([RAILWAY, "delete", "--project", pid, "--yes", "--json"], env, cwd, 120)
    rec["deleted"] = (rc2 == 0)
    rec.update(status="ok" if rc2 == 0 else "ok-nodelete", delete_out="" if rc2 == 0 else out2[:200])
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--par", type=int, default=8)
    ap.add_argument("--only", type=str, default="")
    a = ap.parse_args()
    if a.only:
        names = [s.strip() for s in a.only.split(",")]
    else:
        names = sorted([d.name for d in BASE.iterdir()
                        if d.is_dir() and d.name.startswith("session-") and d.name.split("-")[1].isdigit()],
                       key=lambda x: int(x.split("-")[1]))
    print(f"verifying {len(names)} sessions x{a.par}", flush=True)
    merged = {}
    if OUT.exists():
        try:
            for r in json.load(open(OUT)):
                merged[r["session"]] = r
        except Exception:
            pass
    out = []
    with ThreadPoolExecutor(max_workers=a.par) as ex:
        for i, rec in enumerate(ex.map(verify_one, names)):
            out.append(rec)
            merged[rec["session"]] = rec
            if (i + 1) % 5 == 0 or (i + 1) == len(names):
                tally = {}
                for r in merged.values():
                    tally[r.get("status")] = tally.get(r.get("status"), 0) + 1
                print(f"{i+1}/{len(names)} {tally}", flush=True)
    out = [merged[k] for k in sorted(merged, key=lambda x: int(x.split("-")[1]))]
    json.dump(out, open(OUT, "w"), indent=1)
    tally = {}
    for r in out:
        tally[r.get("status")] = tally.get(r.get("status"), 0) + 1
    print("FINAL", tally)
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
