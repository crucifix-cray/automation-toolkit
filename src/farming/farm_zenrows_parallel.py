#!/usr/bin/env python3
"""Parallel ZenRows farm over the 101 live OnK keys.

Each worker runs zenrows_kernel.py with its own KERNEL_API_KEY + ZEN_TAG
(isolated /tmp state), staggered to avoid thundering herds. Results merge
into finals/zenrows_onkernel_farmed.json under an fcntl lock.

Usage:
  python3 src/farming/farm_zenrows_parallel.py --par 8 --target 20
  python3 src/farming/farm_zenrows_parallel.py --par 10 --keys 30 --timeout 1500 --stagger 8

Box safety: 12 CPU / ~2GB free -> keep --par <= 10 until measured.
OnK safety: 1 browser per key per worker (org limit is 5 concurrent).
"""
from __future__ import annotations

import argparse
import fcntl
import glob
import json
import os
import random
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path("/home/alan/Documents/railways")
SCRIPT = REPO / "src" / "farming" / "zenrows_kernel.py"
REG = REPO / "finals" / "zenrows_onkernel_farmed.json"
JSONL = REPO / "finals" / "zenrows_farmed.jsonl"
SUCCESS_RE = re.compile(r"^SUCCESS (\S+) / (\S+) / ([a-f0-9]{32})", re.M)


def load_keys() -> list[dict]:
    out = []
    for fp in sorted(glob.glob(str(REPO / "finals" / "sessions" / "onk-*" / "session.json"))):
        try:
            d = json.loads(open(fp).read())
        except Exception:
            continue
        k = d.get("api_key") or ""
        if isinstance(k, str) and k.startswith("sk_"):
            out.append({"email": d.get("email"), "api_key": k, "dir": fp})
    return out


def clean_env(key: str, tag: str) -> dict:
    e = dict(os.environ, KERNEL_API_KEY=key, ZEN_TAG=tag, LD_PRELOAD="")
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        e.pop(k, None)
    return e


def stray_cleanup(key: str) -> int:
    """Delete all live browsers on this key. Returns count deleted."""
    import urllib.request
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


def merge_registry(entry: dict) -> None:
    REG.parent.mkdir(parents=True, exist_ok=True)
    with open(REG, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0)
            try:
                data = json.load(f)
                if not isinstance(data, list):
                    data = []
            except Exception:
                data = []
            if all(r.get("api_key") != entry["api_key"] for r in data):
                data.append(entry)
                f.seek(0)
                f.truncate()
                json.dump(data, f, indent=2)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    with open(JSONL, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.write(json.dumps(entry) + "\n")
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def worker(wid: int, key_row: dict, timeout: int, stagger: int, rnd: str) -> dict:
    tag = f"r{rnd}w{wid}"
    time.sleep(stagger * wid + random.uniform(0, stagger))
    # Spread provider rotation across workers (0..3 round-robin).
    try:
        open(f"/tmp/zen_{tag}_provider_rot.txt", "w").write(str(wid % 4))
    except Exception:
        pass
    log = f"/tmp/zenfarm_{tag}.log"
    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, str(SCRIPT)], env=clean_env(key_row["api_key"], tag),
                           capture_output=True, text=True, timeout=timeout)
        out = (p.stdout or "") + "\n" + (p.stderr or "")
        open(log, "w").write(out[-20000:])
        m = SUCCESS_RE.search(out)
        if m:
            email, _, api_key = m.groups()
            entry = {"email": email, "password": "Test1234!AbcZ2026", "api_key": api_key,
                     "url": "https://app.zenrows.com/overview",
                     "onk": key_row["dir"].split("/")[-2], "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            merge_registry(entry)
            return {"wid": wid, "status": "ok", "email": email, "secs": int(time.time() - t0)}
        tail = out.strip().splitlines()[-3:] if out.strip() else ["no-output"]
        cleaned = stray_cleanup(key_row["api_key"])
        return {"wid": wid, "status": "fail", "tail": " | ".join(t[-120:] for t in tail),
                "strays_cleaned": cleaned, "secs": int(time.time() - t0)}
    except subprocess.TimeoutExpired:
        cleaned = stray_cleanup(key_row["api_key"])
        return {"wid": wid, "status": "timeout", "strays_cleaned": cleaned, "secs": timeout}
    except Exception as e:
        return {"wid": wid, "status": f"error:{str(e)[:60]}", "secs": int(time.time() - t0)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--par", type=int, default=8)
    ap.add_argument("--target", type=int, default=0, help="total workers to run (0 = one round over --keys)")
    ap.add_argument("--keys", type=int, default=0, help="use first K live keys (0 = all)")
    ap.add_argument("--timeout", type=int, default=1500)
    ap.add_argument("--stagger", type=int, default=10)
    ap.add_argument("--round", type=str, default=time.strftime("%H%M"),
                    help="round stamp; tags/logs isolate per round (default HHMM)")
    a = ap.parse_args()

    keys = load_keys()
    if a.keys:
        keys = keys[:a.keys]
    print(f"live keys: {len(keys)} par={a.par} timeout={a.timeout}s stagger={a.stagger}s", flush=True)
    if not keys:
        print("NO LIVE KEYS", flush=True)
        sys.exit(2)

    total = a.target or len(keys)
    jobs = [(i, keys[i % len(keys)]) for i in range(total)]
    print(f"launching {total} workers in waves of {a.par}", flush=True)

    ok = fail = 0
    with ThreadPoolExecutor(max_workers=a.par) as ex:
        futs = {ex.submit(worker, wid, krow, a.timeout, a.stagger, a.round): wid for wid, krow in jobs}
        for f in as_completed(futs):
            try:
                r = f.result()
            except Exception as e:
                r = {"wid": futs[f], "status": f"harness:{str(e)[:60]}"}
            if r.get("status") == "ok":
                ok += 1
            else:
                fail += 1
            print(f"[{ok+fail}/{total}] w{r.get('wid')} {r.get('status')} {r.get('email','')} {str(r.get('tail',''))[:100]}", flush=True)
    print(f"FINAL ok={ok} fail={fail}", flush=True)


if __name__ == "__main__":
    main()
