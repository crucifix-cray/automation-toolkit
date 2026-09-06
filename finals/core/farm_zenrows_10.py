#!/usr/bin/env python3
"""Farm 10 fresh ZenRows accounts via OnKernel. Saves incrementally to JSON.

Usage:
  KERNEL_API_KEY=sk_... nohup python3 finals/core/farm_zenrows_10.py > /tmp/farm_zen10.log 2>&1 &
"""
import asyncio, importlib.util, json, os, sys, time
from datetime import datetime, timezone

KERNEL_API_KEY = os.environ.get("KERNEL_API_KEY", "sk_c5b30f67-625f-6e93-7f2e-56f75ce14fe9.pCAWhVNxWJvxBiB_HtL8UkIHBbSzPWmNcUHCt0Ey380")
os.environ["KERNEL_API_KEY"] = KERNEL_API_KEY
os.environ["LD_PRELOAD"] = ""
for _k in ("HTTP_PROXY","HTTPS_PROXY","http_proxy","https_proxy","ALL_PROXY","all_proxy"):
    os.environ.pop(_k, None)

TARGET = int(os.environ.get("FARM_COUNT", "10"))
OUT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "zenrows_onkernel_farmed.json"))

spec = importlib.util.spec_from_file_location(
    "zkf", os.path.join(os.path.dirname(os.path.abspath(__file__)), "zenrows-kernel-final.py"))
assert spec and spec.loader
zkf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(zkf)


def load_existing():
    if os.path.exists(OUT):
        try:
            return json.load(open(OUT))
        except Exception:
            return []
    return []


def save_all(accs):
    tmp = OUT + ".tmp"
    json.dump(accs, open(tmp, "w"), indent=2)
    os.replace(tmp, OUT)


async def main():
    accs = load_existing()
    print(f"START farm target={TARGET} existing={len(accs)} out={OUT}", flush=True)
    fails = 0
    while len(accs) < TARGET and fails < 15:
        n = len(accs) + 1
        print(f"--- account {n}/{TARGET} (fails={fails}) ---", flush=True)
        try:
            res = await zkf.run_once()
            res["farmed_at"] = datetime.now(timezone.utc).isoformat()
            res["via"] = "onkernel"
            accs.append(res)
            save_all(accs)
            print(f"OK {n}/{TARGET}: {res.get('email')} / {res.get('api_key','')[:8]}... saved", flush=True)
            fails = 0
        except SystemExit as e:
            fails += 1
            print(f"FAIL {n} SystemExit({e.code}) fails={fails}", flush=True)
            await asyncio.sleep(10)
        except Exception as e:
            fails += 1
            print(f"FAIL {n} {e} fails={fails}", flush=True)
            await asyncio.sleep(10)
    print(f"DONE total={len(accs)} fails={fails}", flush=True)
    print(json.dumps(accs, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
