#!/usr/bin/env python3
"""Farm N Railway accounts via OnKernel CDP + fresh mobile-US proxy per browser.

Usage:
  python3 src/railway/farm_onk_1k.py --target 1000 --par 10
  python3 src/railway/farm_onk_1k.py --target 1000 --par 10 --keys-glob 'finals/sessions/onk_1790079*.json'
"""
from __future__ import annotations

import argparse
import json
import os
import glob
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path("/home/alae/Documents/repos/automation-toolkit")
SCRIPT = REPO / "src/railway/account_creation.py"
DEFAULT_GLOBS = [
    "finals/sessions/onk_1790079*.json",
    "finals/sessions/onk_1790080*.json",
]
LOG_DIR = Path("/tmp/onk-rail-1k")
API = "https://api.onkernel.com"


def load_keys(patterns: list[str]) -> list[dict]:
    seen = set()
    out = []
    for pat in patterns:
        for fp in sorted(glob.glob(str(REPO / pat))):
            if fp.endswith(".cookies.json") or fp.endswith(".storage.json"):
                continue
            try:
                d = json.load(open(fp))
            except Exception:
                continue
            if not isinstance(d, dict):
                continue
            k = d.get("api_key") or ""
            if not k.startswith("sk_") or k in seen:
                continue
            if not d.get("trial_unlocked", True):
                continue
            seen.add(k)
            out.append({"email": d.get("email"), "api_key": k, "file": fp})
    return out


def api(key: str, method: str, path: str, body: dict | None = None) -> tuple[int, str]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        API + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def ensure_mobile_proxy(key: str, name: str) -> bool:
    """Create a fresh mobile US proxy with unique name (change per browser)."""
    code, body = api(key, "POST", "/proxies", {
        "name": name,
        "type": "mobile",
        "config": {"country": "us"},
    })
    if code in (200, 201):
        return True
    # name collision — delete + recreate
    if code == 400 and "exist" in body.lower():
        # list + delete by name
        c2, b2 = api(key, "GET", "/proxies")
        if c2 == 200:
            try:
                for p in json.loads(b2):
                    if p.get("name") == name and p.get("id"):
                        api(key, "DELETE", f"/proxies/{p['id']}")
            except Exception:
                pass
        code, body = api(key, "POST", "/proxies", {
            "name": name,
            "type": "mobile",
            "config": {"country": "us"},
        })
        return code in (200, 201)
    print(f"  proxy create fail {code}: {body[:200]}", flush=True)
    return False


def delete_proxy_named(key: str, name: str) -> None:
    c, b = api(key, "GET", "/proxies")
    if c != 200:
        return
    try:
        for p in json.loads(b):
            if p.get("name") == name and p.get("id"):
                api(key, "DELETE", f"/proxies/{p['id']}")
    except Exception:
        pass


_lock = threading.Lock()
_stats = {"ok": 0, "fail": 0, "started": 0}


def worker(job_id: int, key_row: dict, target: int) -> dict:
    with _lock:
        if _stats["ok"] >= target:
            return {"job": job_id, "skipped": True}
        _stats["started"] += 1

    key = key_row["api_key"]
    email = key_row["email"]
    proxy_name = f"mobile-us-{uuid.uuid4().hex[:10]}"
    log = LOG_DIR / f"job_{job_id:04d}.log"
    t0 = time.time()

    if not ensure_mobile_proxy(key, proxy_name):
        with _lock:
            _stats["fail"] += 1
        return {"job": job_id, "ok": False, "err": "proxy"}

    env = {
        **os.environ,
        "KERNEL_API_KEY": key,
        "LD_PRELOAD": "",
        "HOME": str(Path.home()),
    }
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
              "ALL_PROXY", "all_proxy"):
        env.pop(k, None)

    cmd = [
        sys.executable, str(SCRIPT),
        "--kernel",
        "--kernel-proxy", proxy_name,
        "--once",
        "--no-warp",
    ]
    try:
        with open(log, "w") as lf:
            lf.write(f"# job={job_id} key_email={email} proxy={proxy_name}\n")
            lf.flush()
            p = subprocess.run(
                cmd, env=env, cwd=str(REPO),
                stdout=lf, stderr=subprocess.STDOUT, timeout=900,
            )
        ok = p.returncode == 0
        # treat SERVICE OK in log as success even if weird exit
        text = log.read_text(errors="replace")
        if "SERVICE OK" in text or "account MADE" in text:
            ok = True
    except Exception as e:
        ok = False
        with open(log, "a") as lf:
            lf.write(f"\nEXC: {e}\n")

    delete_proxy_named(key, proxy_name)

    with _lock:
        if ok:
            _stats["ok"] += 1
        else:
            _stats["fail"] += 1
        cur = dict(_stats)

    print(
        f"[{time.strftime('%H:%M:%S')}] job={job_id} ok={ok} "
        f"proxy={proxy_name} key={email} "
        f"elapsed={time.time()-t0:.0f}s  totals ok={cur['ok']} fail={cur['fail']}",
        flush=True,
    )
    return {"job": job_id, "ok": ok, "proxy": proxy_name, "email": email}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=1000)
    ap.add_argument("--par", type=int, default=10, help="parallel browsers")
    ap.add_argument("--keys-glob", action="append", default=None)
    ap.add_argument("--max-jobs", type=int, default=0,
                    help="hard cap on attempts (0 = target*3)")
    args = ap.parse_args()

    patterns = args.keys_glob or DEFAULT_GLOBS
    keys = load_keys(patterns)
    if not keys:
        print("❌ no unlocked OnKernel keys found", file=sys.stderr)
        return 1

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (LOG_DIR / "keys.json").write_text(json.dumps(
        [{"email": k["email"], "file": k["file"]} for k in keys], indent=2))

    max_jobs = args.max_jobs or max(args.target * 3, args.target + 50)
    print(f"🚀 farm target={args.target} par={args.par} keys={len(keys)} max_jobs={max_jobs}")
    for k in keys:
        print(f"  · {k['email']}  {k['api_key'][:18]}...")

    # seed a baseline mobile-us on each key (optional warm)
    for k in keys:
        ensure_mobile_proxy(k["api_key"], "mobile-us")

    job_id = 0
    with ThreadPoolExecutor(max_workers=args.par) as ex:
        futs = set()
        while True:
            with _lock:
                if _stats["ok"] >= args.target:
                    break
            if job_id >= max_jobs and not futs:
                break
            # fill pool
            while len(futs) < args.par and job_id < max_jobs:
                with _lock:
                    if _stats["ok"] >= args.target:
                        break
                key_row = keys[job_id % len(keys)]
                job_id += 1
                futs.add(ex.submit(worker, job_id, key_row, args.target))
                time.sleep(2)  # mild stagger
            if not futs:
                break
            done, futs = wait_first(futs)
            # drain completed
            for fut in list(futs):
                if fut.done():
                    futs.remove(fut)
                    try:
                        fut.result()
                    except Exception as e:
                        print(f"worker exc: {e}", flush=True)

        # wait remaining
        for fut in as_completed(list(futs)):
            try:
                fut.result()
            except Exception as e:
                print(f"worker exc: {e}", flush=True)

    print(f"🏁 DONE ok={_stats['ok']} fail={_stats['fail']} started={_stats['started']}")
    (LOG_DIR / "summary.json").write_text(json.dumps(_stats, indent=2))
    return 0 if _stats["ok"] >= args.target else 2


def wait_first(futs: set):
    """Block until at least one future completes; return (done_count_hint, remaining)."""
    # simple poll
    while True:
        done = {f for f in futs if f.done()}
        if done:
            for f in done:
                futs.discard(f)
                try:
                    f.result()
                except Exception as e:
                    print(f"worker exc: {e}", flush=True)
            return len(done), futs
        time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
