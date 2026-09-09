#!/usr/bin/env python3
"""Audit railway sessions: 20 parallel, isolated HOME each (raw IP, no proxy).
Records email, verified_at, whoami, project count. -> finals/railway_audit.json

Usage: python3 scripts/railway_audit.py
Each session lives in sessions/session-N with auth at .railway/config.json.
CLI reads $HOME/.railway/config.json, so HOME=<session dir> is all that's needed.
Refresh tokens auto-refresh expired accessTokens on whoami (verified 2026-09-09:
107/107 OK after 11d-expired accessTokens refreshed in place).
"""
import json, os, subprocess
from concurrent.futures import ThreadPoolExecutor

REPO = "/home/alan/Documents/railways"
BASE = os.path.join(REPO, "sessions")
OUT = os.path.join(REPO, "finals", "railway_audit.json")
PAR = 20
RAILWAY = "/home/alan/.railway/bin/railway"


def env_for(session_dir):
    env = dict(os.environ, HOME=os.path.join(BASE, session_dir), LD_PRELOAD="")
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        env.pop(k, None)
    return env


def audit_one(session_dir):
    rec = {"session": session_dir}
    try:
        rec["email_txt"] = open(os.path.join(BASE, session_dir, "email.txt")).read().strip()
    except Exception:
        rec["email_txt"] = ""
    env = env_for(session_dir)
    if not os.path.exists(os.path.join(BASE, session_dir, ".railway", "config.json")):
        rec.update(status="no-config", whoami="", projects=-1)
        return rec
    try:
        w = subprocess.run([RAILWAY, "whoami"], capture_output=True, text=True, env=env, timeout=60)
        rec["whoami"] = (w.stdout + w.stderr).strip().splitlines()[0][:120] if (w.stdout + w.stderr).strip() else ""
        if w.returncode != 0 or "nauth" in rec["whoami"].lower() or "n последнее" in rec["whoami"]:
            rec.update(status="unauthorized", projects=-1)
            return rec
    except Exception as e:
        rec.update(status=f"whoami-err:{str(e)[:60]}", projects=-1)
        return rec
    try:
        l = subprocess.run([RAILWAY, "list", "--json"], capture_output=True, text=True, env=env, timeout=90)
        try:
            projs = json.loads(l.stdout) if l.stdout.strip() else []
            rec["projects"] = len(projs) if isinstance(projs, list) else 0
            rec["project_names"] = [p.get("name", "?") for p in projs] if isinstance(projs, list) else []
        except Exception:
            rec["projects"] = -2
            rec["project_names"] = []
        rec["status"] = "ok"
    except Exception as e:
        rec.update(status=f"list-err:{str(e)[:60]}", projects=-1)
    return rec


def main():
    sessions = sorted([d for d in os.listdir(BASE) if d.startswith("session-")],
                      key=lambda x: int(x.split("-")[1]))
    print(f"auditing {len(sessions)} sessions x{PAR}", flush=True)
    out = []
    with ThreadPoolExecutor(max_workers=PAR) as ex:
        for i, rec in enumerate(ex.map(audit_one, sessions)):
            out.append(rec)
            if (i + 1) % 10 == 0:
                print(f"{i+1}/{len(sessions)}", flush=True)
    json.dump(out, open(OUT, "w"), indent=1)
    ok = sum(1 for r in out if r.get("status") == "ok")
    una = sum(1 for r in out if r.get("status") == "unauthorized")
    noc = sum(1 for r in out if r.get("status") == "no-config")
    tot = sum(r.get("projects", 0) for r in out if r.get("projects", 0) > 0)
    print(f"ok={ok} unauthorized={una} no-config={noc} total_projects={tot}")
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
