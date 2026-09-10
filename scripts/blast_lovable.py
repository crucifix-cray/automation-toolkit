#!/usr/bin/env python3
"""Blast script2 remixes across Railway cells: 1 Lovable session per cell.
50 Lovable sessions (2..51, s1 skipped) -> 50 cells, 10 parallel.
Per cell: ship bundle -> setup stack (marker /data/.lovready) ->
launch script2 --mode remix x10 detached. Scoreboard = Mega DB.

Usage: python3 scripts/blast_lovable.py [--par 10] [--only 2,3,4]
       python3 scripts/blast_lovable.py --status   (Mega DB project counts)
"""
import argparse, json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path("/home/alan/Documents/railways")
BUNDLE = Path("/tmp/cellbundle.tgz")
RCLONE_CONF = REPO / "railway-docker/rclone.conf"
SOURCE_URL = "https://lovable.dev/projects/9941886d-d66f-4be6-8c77-5517809a36bb"
HELPER = REPO / "scripts/cell_ssh.sh"

SETUP = r"""
set -e
mkdir -p /data /app/work
if [ ! -f /data/.lovready ]; then
  export PATH="/opt/venv/bin:$PATH"
  /root/.local/bin/uv pip install -q --python /opt/venv/bin/python invisible_playwright pyotp
  /opt/venv/bin/python -m invisible_playwright fetch
  curl -s https://rclone.org/install.sh | bash
  mkdir -p ~/.config/rclone
  touch /data/.lovready
  echo LOVREADY
else
  echo LOVREADY-CACHED
fi
""".strip()


def load_json(p):
    return json.load(open(p))


def _clean_env(sess=None):
    """Return env dict with proxies stripped and HOME set for the session."""
    e = dict(os.environ, LD_PRELOAD="")
    if sess:
        e["HOME"] = str(REPO / "sessions" / sess)
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        e.pop(k, None)
    return e


def run(args, timeout, sess=None):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=_clean_env(sess))
        return p.returncode, ((p.stdout or "") + "\n" + (p.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT"
    except Exception as e:
        return -2, f"ERR:{e}"[:150]


def resolve_env(sess):
    env = _clean_env(sess)
    for cwd in (Path(f"/tmp/cellwork/{sess}-svc"), REPO):
        try:
            p = subprocess.run(["/home/alan/.railway/bin/railway", "status", "--json"],
                               capture_output=True, text=True, env=env, cwd=str(cwd), timeout=60)
            data = json.loads(p.stdout[p.stdout.index("{"):])
            for e in ((data.get("environments") or {}).get("edges") or []):
                n = e.get("node") or {}
                if not n.get("deletedAt") and n.get("id"):
                    return n["id"]
        except Exception:
            pass
    return ""


def cell_exec(sess, proj, env, svc, cmd, timeout=300):
    return run([str(HELPER), sess, proj, env, svc, "--", "bash", "-c", cmd], timeout, sess=sess)


def ship_bundle(sess, proj, env, svc):
    """Pipe 12MB tarball through ssh stdin."""
    import subprocess as sp
    try:
        helper = [str(HELPER), sess, proj, env, svc, "--",
                  "mkdir -p /app/work && tar -xzf - -C /app/work"]
        with open(BUNDLE, "rb") as f:
            p = sp.run(helper, stdin=f, capture_output=True, timeout=300, env=_clean_env(sess))
        out = (p.stdout.decode() if isinstance(p.stdout, bytes) else p.stdout or "") + (p.stderr.decode() if isinstance(p.stderr, bytes) else p.stderr or "")
        return p.returncode, out.strip()[-300:]
    except sp.TimeoutExpired:
        return -1, "TIMEOUT"
    except Exception as e:
        return -2, f"ERR:{e}"[:150]


def blast_one(lov, cell):
    """lov: lovable session number. cell: (rail_session, proj, env, svc)."""
    rsess, proj, env, svc = cell
    rec = {"lovable": lov, "cell": rsess}
    t0 = time.time()
    # 1. ship bundle (skip if already there)
    rc, out = cell_exec(rsess, proj, env, svc, "ls /app/work/chimera-miner/script2_remix_link.py 2>/dev/null && echo HAS-BUNDLE", timeout=60)
    if "HAS-BUNDLE" not in out:
        rc, out = ship_bundle(rsess, proj, env, svc)
        if rc != 0 and "TIMEOUT" not in out:
            return {**rec, "status": "ship-fail", "out": out[-200:]}
    # 2. rclone conf + lov.env + verify bundle
    conf = RCLONE_CONF.read_text()
    rc, out = cell_exec(rsess, proj, env, svc,
                        f"mkdir -p ~/.config/rclone && cat > ~/.config/rclone/rclone.conf << 'EOF'\n{conf}\nEOF\n"
                        f"cat > /app/work/lov.env << 'EOF'\n"
                        f"CHIMERA_SESSIONS_DIR=/app/work/scripts/sessions\nSKIP_FEATURE=1\nPROXY_PORT=9\nEOF\n"
                        f"ls /app/work/scripts/sessions/session-{lov}/config.json && echo BUNDLE-OK")
    if "BUNDLE-OK" not in out:
        rc, out = ship_bundle(rsess, proj, env, svc)
        rc, out = cell_exec(rsess, proj, env, svc, "ls /app/work/scripts/sessions/session-{}/config.json && echo BUNDLE-OK".format(lov))
        if "BUNDLE-OK" not in out:
            return {**rec, "status": "ship-fail", "out": out[-200:]}
    # 3. setup stack
    rc, out = cell_exec(rsess, proj, env, svc, SETUP, timeout=600)
    if "LOVREADY" not in out:
        return {**rec, "status": "setup-fail", "out": out[-300:]}
    # 4. launch script2 detached
    launch = (f"cd /app/work/chimera-miner && set -a && . /app/work/lov.env && set +a && "
              f"LD_PRELOAD='' nohup /opt/venv/bin/python -u script2_remix_link.py "
              f"--session {lov} --count 10 --mode remix --source-url {SOURCE_URL} --headless "
              f"> /app/work/remix-{lov}.log 2>&1 & echo LAUNCHED-$!")
    rc, out = cell_exec(rsess, proj, env, svc, launch, timeout=120)
    if "LAUNCHED" not in out:
        return {**rec, "status": "launch-fail", "out": out[-200:]}
    return {**rec, "status": "running", "elapsed": int(time.time() - t0)}


def mega_count():
    env = _clean_env()
    try:
        p = subprocess.run(["rclone", "cat", "mega:chimera/database.json"], capture_output=True, text=True, env=env, timeout=60)
        db = json.loads(p.stdout)
        projs = db.get("projects", [])
        from collections import Counter
        return len(projs), dict(Counter((x.get("created_by") or "?") for x in projs))
    except Exception as e:
        return -1, str(e)[:150]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--par", type=int, default=3)
    ap.add_argument("--only", type=str, default="")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    if a.status:
        n, by = mega_count()
        print(f"mega projects: {n}")
        print(json.dumps(by, indent=1)[:2000])
        return
    cells = sorted(json.load(open(REPO / "cells.json")), key=lambda c: int(c["session"].split("-")[1]))
    # need project+env+service per cell
    svc = {c["session"]: c for c in json.load(open(REPO / "services.json"))}
    avail = []
    for c in cells:
        if not c.get("project") or svc.get(c["session"], {}).get("status") != "ready":
            continue
        env = c.get("env") or resolve_env(c["session"])
        if not env:
            continue
        avail.append((c["session"], c["project"], env, f"cell-{c['session'].split('-')[1]}"))
    lovs = [int(x) for x in a.only.split(",")] if a.only else list(range(2, 52))
    pairs = list(zip(lovs, avail[:len(lovs)]))
    # persist resolved envs
    try:
        allcells = json.load(open(REPO / "cells.json"))
        bysess = {c["session"]: c for c in allcells}
        for _, (rs, _, env, _) in pairs:
            if env:
                bysess[rs]["env"] = env
        json.dump(sorted(bysess.values(), key=lambda c: c["session"]), open(REPO / "cells.json", "w"), indent=1)
    except Exception as e:
        print(f"env persist skipped: {e}", flush=True)
    print(f"blasting {len(pairs)} cells x{a.par} (source keeper 9941886d)", flush=True)
    out = []
    with ThreadPoolExecutor(max_workers=a.par) as ex:
        futs = {ex.submit(blast_one, lov, cell): (lov, cell[0]) for lov, cell in pairs}
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


if __name__ == "__main__":
    main()
