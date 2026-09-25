#!/usr/bin/env python3
"""Verify MADE Railway accounts: railway up → wait SUCCESS → mark good → railway down.

Usage:
  python3 /home/alae/onk-rail-1k/verify_up_down.py --today --par 8
  python3 /home/alae/onk-rail-1k/verify_up_down.py --all --par 8
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

DEST = Path("/home/alae/Documents/railways")
WORK = Path("/tmp/rv-up-verify")
OUT = Path("/home/alae/onk-rail-1k/verify_up_down.jsonl")
SUMMARY = Path("/home/alae/onk-rail-1k/verify_up_down_summary.json")
DOCKERFILE = 'FROM alpine:3.20\nCMD ["sleep", "infinity"]\n'


def sessions(today_only: bool) -> list[tuple[Path, dict]]:
    out = []
    for d in sorted(
        DEST.glob("session-*"),
        key=lambda p: int(p.name.split("-")[1]) if p.name.split("-")[1].isdigit() else 0,
    ):
        v = d / "verified.json"
        if not v.is_file():
            continue
        try:
            m = json.loads(v.read_text())
        except Exception:
            continue
        if not (m.get("project_name") and m.get("service_id")):
            continue
        if today_only and not str(m.get("verified_at") or "").startswith("2026-09-25"):
            continue
        out.append((d, m))
    return out


def env_for(home: Path) -> dict:
    e = {**os.environ, "HOME": str(home), "LD_PRELOAD": ""}
    for k in list(e):
        if k.lower().endswith("_proxy") or k.startswith("RAILWAY_"):
            e.pop(k, None)
    return e


def run(args: list[str], env: dict, cwd: Path, timeout: int) -> tuple[int, str]:
    try:
        p = subprocess.run(
            args, env=env, cwd=str(cwd), capture_output=True, text=True, timeout=timeout
        )
        return p.returncode, ((p.stdout or "") + "\n" + (p.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT"
    except Exception as e:
        return -2, f"ERR:{e}"


def poll_status(env: dict, cwd: Path, max_wait: int = 300) -> str:
    deadline = time.time() + max_wait
    last = ""
    while time.time() < deadline:
        rc, out = run(["railway", "service", "status"], env, cwd, 60)
        last = out
        u = out.upper()
        if "RESTRICTED" in u or "SUSPENDED" in u or "FORBIDDEN" in u:
            return f"BLOCKED:{out[:120]}"
        if "SUCCESS" in u:
            return "SUCCESS"
        if any(x in u for x in ("FAILED", "CRASHED", "REMOVED")):
            return f"BAD:{out[:120]}"
        time.sleep(12)
    return f"TIMEOUT:{last[:120]}"


def mark_good(session_dir: Path, meta: dict, detail: str) -> None:
    meta = dict(meta)
    meta["up_verified"] = True
    meta["up_verified_at"] = datetime.now(timezone.utc).isoformat()
    meta["up_verify_detail"] = detail[:200]
    (session_dir / "verified.json").write_text(json.dumps(meta, indent=2))
    # also stamp a marker file
    (session_dir / "UP_GOOD").write_text(meta["up_verified_at"] + "\n")


def mark_bad(session_dir: Path, meta: dict, reason: str) -> None:
    meta = dict(meta)
    meta["up_verified"] = False
    meta["up_verified_at"] = datetime.now(timezone.utc).isoformat()
    meta["up_verify_detail"] = reason[:300]
    (session_dir / "verified.json").write_text(json.dumps(meta, indent=2))
    (session_dir / "UP_BAD").write_text(reason[:500] + "\n")


def verify_one(item: tuple[Path, dict]) -> dict:
    d, m = item
    name = d.name
    proj = m["project_name"]
    svc = m.get("service_name") or f"hlth-{name.split('-')[-1]}"
    env = env_for(d)
    cwd = WORK / name
    shutil.rmtree(cwd, ignore_errors=True)
    cwd.mkdir(parents=True)
    (cwd / "Dockerfile").write_text(DOCKERFILE)

    rec = {"session": name, "project": proj, "service": svc, "email": m.get("email")}

    rc, out = run(
        ["railway", "link", "-p", proj, "-e", "production", "-s", svc], env, cwd, 90
    )
    if rc != 0 and "linked" not in out.lower():
        rec["status"] = "link_fail"
        rec["detail"] = out[:200]
        mark_bad(d, m, rec["status"] + ":" + rec["detail"])
        return rec

    rc, out = run(["railway", "whoami"], env, cwd, 60)
    if rc != 0 or "Logged in" not in out:
        rec["status"] = "whoami_fail"
        rec["detail"] = out[:200]
        mark_bad(d, m, rec["status"] + ":" + rec["detail"])
        return rec

    # railway up with retries (parallel uploads often 500)
    up_out = ""
    up_ok = False
    for attempt in range(1, 5):
        rc, out = run(["railway", "up", "-d", "-y", "--service", svc], env, cwd, 180)
        up_out = out
        if "Build Logs" in out or "https://railway.com/project/" in out:
            up_ok = True
            break
        lo = out.lower()
        if any(x in lo for x in ("restricted", "banned", "suspended", "forbidden", "payment")):
            rec["status"] = "blocked"
            rec["detail"] = out[:250]
            mark_bad(d, m, rec["status"] + ":" + rec["detail"])
            run(["railway", "down", "-y", "--service", svc], env, cwd, 90)
            return rec
        # transient
        if "500" in out or "timeout" in lo or "try again" in lo or rc != 0:
            time.sleep(5 * attempt)
            continue
        break

    if not up_ok:
        rec["status"] = "up_fail"
        rec["detail"] = up_out[:250]
        mark_bad(d, m, rec["status"] + ":" + rec["detail"])
        run(["railway", "down", "-y", "--service", svc], env, cwd, 90)
        return rec

    st = poll_status(env, cwd, max_wait=420)
    if st == "SUCCESS":
        rec["status"] = "GOOD"
        mark_good(d, m, st)
    else:
        rec["status"] = "deploy_fail"
        rec["detail"] = st
        mark_bad(d, m, st)

    # always down after
    rc2, out2 = run(["railway", "down", "-y", "--service", svc], env, cwd, 120)
    rec["down_rc"] = rc2
    if rc2 != 0:
        rec["down_detail"] = out2[:150]

    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", action="store_true", help="Only 2026-09-25 verified")
    ap.add_argument("--all", action="store_true", help="All with project+service")
    ap.add_argument("--par", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--min-id", type=int, default=0, help="Only session-N with N >= MIN_ID")
    ap.add_argument("--domain", type=str, default="",
                    help="Only emails at these comma-separated domains (e.g. high.edu.pl,gmail.com)")
    ap.add_argument("--retry-bad", action="store_true", help="Include previously UP_BAD")
    args = ap.parse_args()
    today_only = not args.all
    items = sessions(today_only=today_only)
    # skip already GOOD unless forced
    filtered = []
    for d, m in items:
        if (d / "UP_GOOD").is_file() and m.get("up_verified") is True:
            continue
        if (d / "UP_BAD").is_file() and not args.retry_bad and m.get("up_verified") is False:
            # still retry — wipe stale BAD from 500 storm
            (d / "UP_BAD").unlink(missing_ok=True)
        filtered.append((d, m))
    items = filtered
    if args.min_id:
        items = [(d, m) for (d, m) in items
                 if d.name.split("-")[1].isdigit() and int(d.name.split("-")[1]) >= args.min_id]
    if args.domain:
        doms = {d.strip().lower() for d in args.domain.split(",") if d.strip()}
        keep = []
        for (d, m) in items:
            try:
                em = open(d / "email.txt").read().strip().split()[0]
                if em.split("@")[1].lower() in doms:
                    keep.append((d, m))
            except Exception:
                pass
        items = keep
    if args.limit:
        items = items[: args.limit]
    print(f"verify up/down: {len(items)} sessions par={args.par}", flush=True)
    WORK.mkdir(parents=True, exist_ok=True)
    if not OUT.exists():
        OUT.write_text("")
    results = []
    with ThreadPoolExecutor(max_workers=args.par) as ex:
        futs = {ex.submit(verify_one, it): it[0].name for it in items}
        for fut in as_completed(futs):
            try:
                r = fut.result()
            except Exception as e:
                r = {"session": futs[fut], "status": f"exc:{e}"}
            results.append(r)
            with OUT.open("a") as f:
                f.write(json.dumps(r) + "\n")
            print(
                f"[{len(results)}/{len(items)}] {r.get('session')} → {r.get('status')}",
                flush=True,
            )

    from collections import Counter

    # recount from disk markers for truth
    good = sum(1 for d in DEST.glob("session-*") if (d / "UP_GOOD").is_file())
    bad = sum(1 for d in DEST.glob("session-*") if (d / "UP_BAD").is_file())
    c = Counter(r.get("status") for r in results)
    summary = {
        "batch_total": len(results),
        "batch_counts": dict(c),
        "disk_UP_GOOD": good,
        "disk_UP_BAD": bad,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    SUMMARY.write_text(json.dumps(summary, indent=2))
    print("FINAL batch", dict(c), flush=True)
    print(f"DISK UP_GOOD={good} UP_BAD={bad}", flush=True)
    print(f"summary: {SUMMARY}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
