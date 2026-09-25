#!/usr/bin/env python3
"""Farm N Railway accounts via OnKernel CDP + fresh mobile proxy per browser.

Loads ALL unlocked OnK keys (not Batch-B only). Skips billing/unpaid from
/tmp/onk-paid-probe/results.jsonl when present. Prefer last keys (least burned).

Usage:
  # one test
  python3 src/railway/farm_onk_1k.py --target 1 --par 1 --once

  # scale (keep --par modest on laptop; OnK browsers are remote)
  python3 src/railway/farm_onk_1k.py --target 100 --par 10
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path("/home/alae/Documents/repos/automation-toolkit")
SCRIPT = REPO / "src/railway/account_creation.py"
SESSIONS = Path("/home/alae/Documents/railways")
LOG_DIR = Path("/home/alae/onk-rail-1k")
API = "https://api.onkernel.com"
PAID_PROBE = Path("/tmp/onk-paid-probe/results.jsonl")

# Multi-country mobile (not US-only) — rotate per worker
MOBILE_COUNTRIES = [
    c.strip().lower()
    for c in os.environ.get(
        "HOLY_MOBILE_COUNTRIES",
        "gb,de,fr,nl,ie,es,it,be,at,se",
    ).split(",")
    if c.strip()
] or ["gb"]

_lock = threading.Lock()
_stats = {"ok": 0, "fail": 0, "started": 0}
_stop = threading.Event()
_session_seq = 0


def load_bad_emails() -> set[str]:
    bad: set[str] = set()
    if not PAID_PROBE.is_file():
        return bad
    try:
        for line in PAID_PROBE.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("status") in ("BILLING", "AUTH", "FAIL") and r.get("email"):
                bad.add(str(r["email"]).lower())
    except Exception:
        pass
    return bad


def load_keys() -> list[dict]:
    """All distinct unlocked OnK keys; skip paid-probe bad; prefer last (least used)."""
    bad = load_bad_emails()
    seen: set[str] = set()
    out: list[dict] = []
    for fp in sorted((REPO / "finals" / "sessions").glob("onk_*.json")):
        if fp.name.endswith((".cookies.json", ".storage.json")):
            continue
        try:
            d = json.loads(fp.read_text())
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        k = d.get("api_key") or ""
        if d.get("tag") != "unlocked" or not isinstance(k, str) or not k.startswith("sk_") or k in seen:
            continue
        email = (d.get("email") or "").lower()
        if email in bad:
            print(f"→ skip paid/auth: {email}", flush=True)
            continue
        seen.add(k)
        out.append({"email": d.get("email"), "api_key": k, "file": str(fp)})
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
    except Exception as e:
        return 0, str(e)


def ensure_mobile_proxy(key: str, name: str, country: str) -> bool:
    body = {"name": name, "type": "mobile", "config": {"country": country}}
    code, raw = api(key, "POST", "/proxies", body)
    if code in (200, 201):
        return True
    c2, b2 = api(key, "GET", "/proxies")
    if c2 == 200:
        try:
            for p in json.loads(b2):
                if p.get("name") == name and p.get("id"):
                    api(key, "DELETE", f"/proxies/{p['id']}")
        except Exception:
            pass
        code, raw = api(key, "POST", "/proxies", body)
        if code in (200, 201):
            return True
    print(f"  proxy create fail {code}: {raw[:200]}", flush=True)
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


def next_session_num() -> int:
    global _session_seq
    with _lock:
        if _session_seq == 0:
            nums = []
            if SESSIONS.is_dir():
                for d in SESSIONS.iterdir():
                    if d.is_dir() and d.name.startswith("session-"):
                        try:
                            nums.append(int(d.name.split("-", 1)[1]))
                        except Exception:
                            pass
            _session_seq = (max(nums) + 1) if nums else 1
        n = _session_seq
        _session_seq += 1
        return n


def worker(job_id: int, key_row: dict, once: bool) -> dict:
    if _stop.is_set():
        return {"job": job_id, "skipped": True}

    with _lock:
        _stats["started"] += 1

    key = key_row["api_key"]
    email = key_row["email"]
    country = MOBILE_COUNTRIES[(job_id - 1) % len(MOBILE_COUNTRIES)]
    proxy_name = f"mobile-{country}-{uuid.uuid4().hex[:10]}"
    log = LOG_DIR / f"job_{job_id:04d}.log"
    t0 = time.time()
    sess_num = next_session_num()

    if not ensure_mobile_proxy(key, proxy_name, country):
        with _lock:
            _stats["fail"] += 1
        return {"job": job_id, "ok": False, "err": "proxy"}

    holy = ""
    try:
        holy = (REPO / "finals" / "secrets" / "holy_secret_key.local").read_text().strip()
    except Exception:
        pass

    env = {
        **os.environ,
        "KERNEL_API_KEY": key,
        "LD_PRELOAD": "",
        "HOME": str(Path.home()),
        "SKIP_MEGA": "1",
        "PYTHONUNBUFFERED": "1",
        "HOLY_SESSION_NUM": str(sess_num),
        "GH_PUSH": os.environ.get("GH_PUSH", "1"),
    }
    if holy:
        env["HOLY_SECRET_KEY"] = holy
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
              "ALL_PROXY", "all_proxy"):
        env.pop(k, None)

    cmd = [
        sys.executable, "-u", str(SCRIPT),
        "--kernel",
        "--kernel-proxy", proxy_name,
        "--no-warp",
    ]
    if once:
        cmd.append("--once")

    ok = False
    session_name = ""
    try:
        with open(log, "w") as lf:
            lf.write(
                f"# job={job_id} key_email={email} proxy={proxy_name} "
                f"country={country} HOLY_SESSION_NUM={sess_num} once={once}\n"
            )
            lf.flush()
            p = subprocess.run(
                cmd, env=env, cwd=str(REPO),
                stdout=lf, stderr=subprocess.STDOUT, timeout=3600,
            )
            ok = p.returncode == 0
        text = log.read_text(errors="replace")
        import re as _re
        m = _re.search(r"MADE account with service:\s*(session-\d+)", text)
        if not m:
            m = _re.search(r"SERVICE OK[^\n]*?(session-\d+)", text)
        if m:
            session_name = m.group(1)
            vpath = SESSIONS / session_name / "verified.json"
            ok = vpath.is_file() and "No new verified.json" not in text
        else:
            # also accept pinned session if verified landed there
            pinned = SESSIONS / f"session-{sess_num}" / "verified.json"
            if pinned.is_file():
                session_name = f"session-{sess_num}"
                ok = True
            else:
                ok = False
    except Exception as e:
        with open(log, "a") as lf:
            lf.write(f"\nEXC: {e}\n")

    delete_proxy_named(key, proxy_name)

    with _lock:
        if ok:
            _stats["ok"] += 1
        else:
            _stats["fail"] += 1
        cur_ok = _stats["ok"]
        cur_fail = _stats["fail"]

    print(
        f"[{time.strftime('%H:%M:%S')}] job={job_id} ok={ok} "
        f"session={session_name or '-'} country={country} key={email} "
        f"elapsed={time.time()-t0:.0f}s  totals ok={cur_ok} fail={cur_fail}",
        flush=True,
    )
    return {
        "job": job_id, "ok": ok, "proxy": proxy_name, "country": country,
        "email": email, "session": session_name, "log": str(log),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=1000)
    ap.add_argument("--par", type=int, default=10)
    ap.add_argument("--max-jobs", type=int, default=0)
    ap.add_argument("--once", action="store_true",
                    help="Pass --once to Holy (no until-service retry)")
    ap.add_argument("--from-end", action="store_true", default=True,
                    help="Use last N unlocked keys (default on)")
    args = ap.parse_args()

    keys = load_keys()
    if not keys:
        print("❌ no healthy unlocked OnKernel keys", file=sys.stderr)
        return 1
    # prefer last (least burned on early waves)
    if args.from_end:
        # keep full pool; workers round-robin from end by reversing
        keys = list(reversed(keys))
        print(f"→ OnK keys: {len(keys)} unlocked healthy (from end first: {keys[0].get('email')})")
    else:
        print(f"→ OnK keys: {len(keys)} unlocked healthy (from start: {keys[0].get('email')})")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (LOG_DIR / "keys.json").write_text(json.dumps(
        [{"email": k["email"], "file": k["file"]} for k in keys], indent=2))

    max_jobs = args.max_jobs or (
        args.target if args.once and args.target <= 3
        else max(args.target * 3, args.target + 50)
    )
    print(
        f"🚀 farm target={args.target} par={args.par} keys={len(keys)} "
        f"max_jobs={max_jobs} once={args.once} countries={MOBILE_COUNTRIES}",
        flush=True,
    )

    submitted = 0
    with ThreadPoolExecutor(max_workers=args.par) as ex:
        futs = {}
        while submitted < max_jobs:
            with _lock:
                if _stats["ok"] >= args.target:
                    _stop.set()
                    break
            while len(futs) < args.par and submitted < max_jobs and not _stop.is_set():
                with _lock:
                    if _stats["ok"] >= args.target:
                        _stop.set()
                        break
                submitted += 1
                key_row = keys[(submitted - 1) % len(keys)]
                fut = ex.submit(worker, submitted, key_row, args.once)
                futs[fut] = submitted
                time.sleep(1.0)
            if not futs:
                break
            done_fut = next(as_completed(futs))
            futs.pop(done_fut, None)
            try:
                done_fut.result()
            except Exception as e:
                print(f"worker exc: {e}", flush=True)
            with _lock:
                if _stats["ok"] >= args.target:
                    _stop.set()

        for fut in as_completed(list(futs.keys())):
            try:
                fut.result()
            except Exception as e:
                print(f"worker exc: {e}", flush=True)

    print(f"🏁 DONE ok={_stats['ok']} fail={_stats['fail']} started={_stats['started']}")
    (LOG_DIR / "summary.json").write_text(json.dumps(_stats, indent=2))
    return 0 if _stats["ok"] >= args.target else 2


if __name__ == "__main__":
    raise SystemExit(main())
