#!/usr/bin/env python3
"""Loop-farm ZenRows accounts via OnKernel until limit. 5-7min random gaps.
Writes LIMIT.lock (mega_db + finals) + pushes when limit hit.

Usage:
  HOME=scripts/railways/session-1 KERNEL_API_KEY=sk_... nohup python3 finals/core/farm_zenrows_loop.py > /tmp/farm_loop.log 2>&1 &
"""
import asyncio, importlib.util, json, os, random, subprocess, sys
from datetime import datetime, timezone

KERNEL_API_KEY = os.environ.get("KERNEL_API_KEY", "sk_c5b30f67-625f-6e93-7f2e-56f75ce14fe9.pCAWhVNxWJvxBiB_HtL8UkIHBbSzPWmNcUHCt0Ey380")
os.environ["KERNEL_API_KEY"] = KERNEL_API_KEY
os.environ["LD_PRELOAD"] = ""
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(_k, None)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
OUT = os.path.normpath(os.path.join(HERE, "..", "zenrows_onkernel_farmed.json"))
LOCK1 = os.path.join(REPO, "mega_db", "db", "browsers+proxies", "zenrows", "LIMIT.lock")
LOCK2 = os.path.join(REPO, "finals", "zenrows_LIMIT.lock")
DAILY_CAP = int(os.environ.get("FARM_DAILY_CAP", "20"))
FAIL_STREAK_LIMIT = int(os.environ.get("FARM_FAIL_STREAK", "6"))

spec = importlib.util.spec_from_file_location(
    "zkf", os.path.join(HERE, "zenrows-kernel-final.py"))
assert spec and spec.loader
zkf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(zkf)

sys.path.insert(0, HERE)
import importlib
_f10 = importlib.import_module("farm_zenrows_10") if False else None


def _load():
    if os.path.exists(OUT):
        try:
            return json.load(open(OUT))
        except Exception:
            return []
    return []


def _save(accs):
    tmp = OUT + ".tmp"
    json.dump(accs, open(tmp, "w"), indent=2)
    os.replace(tmp, OUT)


def _push(msg):
    try:
        subprocess.run(["git", "add", "finals/zenrows_onkernel_farmed.json",
                        "mega_db/db/browsers+proxies/zenrows/LIMIT.lock",
                        "finals/zenrows_LIMIT.lock"],
                       cwd=REPO, capture_output=True)
        subprocess.run(["git", "commit", "-m", msg], cwd=REPO, capture_output=True)
        subprocess.run(["git", "push"], cwd=REPO, capture_output=True, timeout=60)
    except Exception as e:
        print(f"push err {e}", flush=True)


def _lock(reason, accs):
    payload = {
        "limited": True,
        "reason": reason,
        "at": datetime.now(timezone.utc).isoformat(),
        "keys_farmed": len(accs),
        "last_success": accs[-1].get("farmed_at") if accs else None,
    }
    for p in (LOCK1, LOCK2):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        json.dump(payload, open(p, "w"), indent=2)
    _push(f"lock: zenrows farm limited ({reason})")
    print(f"LOCKED: {reason}", flush=True)


async def main():
    accs = _load()
    print(f"LOOP START keys={len(accs)} cap={DAILY_CAP} streak_limit={FAIL_STREAK_LIMIT}", flush=True)
    streak = 0
    while True:
        if len(accs) >= DAILY_CAP:
            _lock("daily-cap", accs)
            return
        n = len(accs) + 1
        print(f"--- key {n} (streak={streak}) ---", flush=True)
        try:
            res = await zkf.run_once()
            res["farmed_at"] = datetime.now(timezone.utc).isoformat()
            res["via"] = "onkernel-loop"
            accs.append(res)
            _save(accs)
            _push(f"chore: farm zenrows key {n} {res.get('email')}")
            print(f"OK {n}: {res.get('email')} / {res.get('api_key','')[:8]}...", flush=True)
            streak = 0
        except SystemExit as e:
            streak += 1
            print(f"FAIL key {n} exit={e.code} streak={streak}", flush=True)
        except Exception as e:
            streak += 1
            print(f"FAIL key {n} {str(e)[:150]} streak={streak}", flush=True)
        if streak >= FAIL_STREAK_LIMIT:
            _lock(f"fail-streak-{streak}", accs)
            return
        gap = random.randint(300, 420)
        print(f"gap {gap}s...", flush=True)
        await asyncio.sleep(gap)


if __name__ == "__main__":
    asyncio.run(main())
