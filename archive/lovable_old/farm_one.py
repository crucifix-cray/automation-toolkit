#!/usr/bin/env python3
"""Single farmed account -> file-locked JSON append + push. For parallel runs."""
import asyncio, fcntl, importlib.util, json, os, subprocess, sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
OUT = os.path.normpath(os.path.join(HERE, "..", "zenrows_onkernel_farmed.json"))

spec = importlib.util.spec_from_file_location("zkf", os.path.join(HERE, "zenrows-kernel-final.py"))
assert spec and spec.loader
zkf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(zkf)


async def main():
    res = None
    for _att in range(1, 5):
        try:
            res = await zkf.run_once()
            break
        except SystemExit as e:
            print(f"attempt {_att}/4 exit={e.code}, fresh browser...", flush=True)
            await asyncio.sleep(10)
        except Exception as e:
            print(f"attempt {_att}/4 err={str(e)[:120]}, fresh browser...", flush=True)
            await asyncio.sleep(10)
    if res is None:
        print("all 4 attempts failed", flush=True)
        sys.exit(1)
    res["farmed_at"] = datetime.now(timezone.utc).isoformat()
    res["via"] = "onkernel-parallel"
    with open(OUT, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0)
            try:
                accs = json.load(f)
            except Exception:
                accs = []
            if any(a.get("email", "").lower() == res.get("email", "").lower() for a in accs):
                print(f"DUP {res.get('email')} already saved, skip", flush=True)
            else:
                accs.append(res)
                f.seek(0)
                f.truncate()
                json.dump(accs, f, indent=2)
                print(f"SAVED {res.get('email')} total={len(accs)}", flush=True)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    subprocess.run(["git", "add", "finals/zenrows_onkernel_farmed.json"], cwd=REPO, capture_output=True)
    subprocess.run(["git", "commit", "-m", f"chore: farm {res.get('email')}"], cwd=REPO, capture_output=True)
    subprocess.run(["git", "pull", "--rebase"], cwd=REPO, capture_output=True, timeout=60)
    subprocess.run(["git", "push"], cwd=REPO, capture_output=True, timeout=60)
    print("pushed", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
