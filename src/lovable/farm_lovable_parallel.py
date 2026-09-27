#!/usr/bin/env python3
"""Parallel Lovable farm over the 101 live OnK keys.

Each worker runs farm_lovable_ultimate.py --once with its own OnK key and
LOV_TAG (isolated state), staggered. Zenvex-first mailbox chain, no custom
proxy (trial orgs can't use them), suspicious-activity -> kill browser +
fresh browser/IP handled inside the script.

Usage:
  python3 src/lovable/farm_lovable_parallel.py --par 8 --target 505 --stagger 10
  python3 src/lovable/farm_lovable_parallel.py --par 3 --target 3 --dry-run
"""
from __future__ import annotations

import argparse
import fcntl
import glob
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path("/home/alan/Documents/railways")
SCRIPT = REPO / "src" / "lovable" / "farm_lovable_ultimate.py"
OUT_JSONL = REPO / "finals" / "lovables_farmed.jsonl"
OK_RE = re.compile(r"(?:✅|🎉).*?(?:MADE|OK|done|account|project)", re.I)


def load_keys() -> list[dict]:
    out = []
    for fp in sorted(glob.glob(str(REPO / "finals" / "sessions" / "onk-*" / "session.json"))):
        try:
            d = json.loads(open(fp).read())
        except Exception:
            continue
        k = d.get("api_key") or ""
        if isinstance(k, str) and k.startswith("sk_"):
            out.append({"email": d.get("email"), "api_key": k,
                        "dir": Path(fp).parent.name})
    return out


def clean_env(key: str) -> dict:
    e = dict(os.environ, KERNEL_API_KEY=key, LD_PRELOAD="")
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        e.pop(k, None)
    return e


def stray_cleanup(key: str) -> int:
    n = 0
    try:
        req = urllib.request.Request("https://api.onkernel.com/browsers",
                                     headers={"Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=20) as r:
            items = json.loads(r.read())
        for b in items:
            sid = b.get("session_id") or b.get("id")
            if not sid:
                continue
            try:
                req = urllib.request.Request(f"https://api.onkernel.com/browsers/{sid}",
                                             headers={"Authorization": f"Bearer {key}"},
                                             method="DELETE")
                with urllib.request.urlopen(req, timeout=20):
                    n += 1
            except Exception:
                pass
    except Exception:
        pass
    return n


def harvest(text: str, key_row: dict) -> dict | None:
    """Pull the created account/email/project out of the worker log."""
    m = re.search(r"📮 Using (\S+) via ([\w.]+)", text)
    email, provider = (m.group(1), m.group(2)) if m else (None, None)
    p = re.search(r'"railway_project_id"|"project_id":\s*"([^"]+)"', text)
    proj = re.search(r'project(?:_id)?["\s:=]+([a-z0-9\-]{8,})', text, re.I)
    sess = re.search(r"session-(\d+)", text)
    if not email and not sess:
        return None
    return {"email": email, "provider": provider, "onk": key_row["dir"],
            "session": f"session-{sess.group(1)}" if sess else None,
            "project_id": (p.group(1) if p and p.groups() else (proj.group(1) if proj else None)),
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def append(entry: dict) -> None:
    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSONL, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.write(json.dumps(entry) + "\n")
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def worker(wid: int, key_row: dict, stagger: int, timeout: int, zenvex_rounds: int,
           skip_zenvex: bool) -> dict:
    time.sleep(stagger * (wid % 8) + (wid // 8) * stagger * 8 * 0.35)
    log = f"/tmp/lovfarm_w{wid}.log"
    t0 = time.time()
    cmd = [sys.executable, str(SCRIPT), "--once", "--host-key", key_row["api_key"],
           "--proxy-country", "none", "--zenvex-rounds", str(zenvex_rounds)]
    if skip_zenvex:
        cmd.append("--skip-zenvex")
    try:
        with open(log, "w") as lf:
            lf.write(f"# w{wid} key={key_row['email']} cmd={' '.join(cmd)}\n")
            lf.flush()
            p = subprocess.run(cmd, env=clean_env(key_row["api_key"]), cwd=str(REPO),
                               stdout=lf, stderr=subprocess.STDOUT, timeout=timeout)
        text = Path(log).read_text(errors="replace")
        ok = p.returncode == 0 and bool(re.search(r"2FA|GH|invite|project|🎉|✅.*(done|OK)", text, re.I))
        entry = harvest(text, key_row)
        if ok and entry:
            append(entry)
        cleaned = stray_cleanup(key_row["api_key"])
        tail = " | ".join(text.strip().splitlines()[-3:])[:180]
        return {"wid": wid, "ok": ok, "entry": entry, "strays": cleaned,
                "secs": int(time.time() - t0), "tail": tail}
    except subprocess.TimeoutExpired:
        return {"wid": wid, "ok": False, "strays": stray_cleanup(key_row["api_key"]),
                "secs": timeout, "tail": "TIMEOUT"}
    except Exception as e:
        return {"wid": wid, "ok": False, "secs": int(time.time() - t0),
                "tail": f"harness:{str(e)[:100]}"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--par", type=int, default=8)
    ap.add_argument("--target", type=int, default=505)
    ap.add_argument("--keys", type=int, default=0)
    ap.add_argument("--stagger", type=int, default=10)
    ap.add_argument("--timeout", type=int, default=2400)
    ap.add_argument("--zenvex-rounds", type=int, default=3)
    ap.add_argument("--skip-zenvex", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    keys = load_keys()
    if a.keys:
        keys = keys[:a.keys]
    print(f"keys={len(keys)} par={a.par} target={a.target} stagger={a.stagger}s "
          f"zenvex_rounds={a.zenvex_rounds} skip_zenvex={a.skip_zenvex}", flush=True)
    if a.dry_run:
        for k in keys[:a.target]:
            print(" would run:", k["email"], k["api_key"][:12], flush=True)
        return
    if not keys:
        print("NO KEYS", flush=True)
        sys.exit(2)

    jobs = [(i, keys[i % len(keys)]) for i in range(a.target)]
    ok = 0
    with ThreadPoolExecutor(max_workers=a.par) as ex:
        futs = {ex.submit(worker, w, kr, a.stagger, a.timeout, a.zenvex_rounds, a.skip_zenvex): w
                for w, kr in jobs}
        for i, f in enumerate(as_completed(futs), 1):
            try:
                r = f.result()
            except Exception as e:
                r = {"wid": futs[f], "ok": False, "tail": str(e)[:80]}
            if r.get("ok"):
                ok += 1
            e = r.get("entry") or {}
            print(f"[{i}/{a.target}] w{r.get('wid')} {'OK' if r.get('ok') else 'fail'} "
                  f"{e.get('email','')} strays={r.get('strays',0)} {r.get('secs')}s "
                  f"{str(r.get('tail',''))[:90]}", flush=True)
    print(f"FINAL ok={ok} fail={a.target - ok}", flush=True)


if __name__ == "__main__":
    main()
