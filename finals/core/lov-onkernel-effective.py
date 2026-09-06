#!/usr/bin/env python3
"""Lovable effective signup via OnKernel stealth browser (not ZenRows).
Wraps lov-api-effective.run(cdp_url=kernel_cdp).

Usage:
  KERNEL_API_KEY=sk_... python3 finals/core/lov-onkernel-effective.py --end
  KERNEL_API_KEY=sk_... python3 finals/core/lov-onkernel-effective.py --end --email x@gmail.com
"""
import argparse, asyncio, json, os, subprocess, sys

KERNEL_API_KEY = os.environ.get("KERNEL_API_KEY", "sk_c5b30f67-625f-6e93-7f2e-56f75ce14fe9.pCAWhVNxWJvxBiB_HtL8UkIHBbSzPWmNcUHCt0Ey380")
os.environ["LD_PRELOAD"] = ""
for _k in ("HTTP_PROXY","HTTPS_PROXY","http_proxy","https_proxy","ALL_PROXY","all_proxy"):
    os.environ.pop(_k, None)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# module file is lov-api-effective.py with dash -> import via importlib
import importlib.util
_spec = importlib.util.spec_from_file_location("lov_effective", os.path.join(os.path.dirname(os.path.abspath(__file__)), "lov-api-effective.py"))
assert _spec and _spec.loader
lov_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lov_mod)


def create_kernel():
    env = {**os.environ, "KERNEL_API_KEY": KERNEL_API_KEY}
    out = subprocess.check_output(
        ["kernel","browsers","create","--stealth","--timeout","600",
         "--start-url","https://lovable.dev/signup","-o","json"],
        env=env, text=True, timeout=90)
    d = json.loads(out)
    print(f"LIVE: {d.get('browser_live_view_url')} | SID: {d.get('session_id')}", file=sys.stderr)
    return d["cdp_ws_url"], d["session_id"]


def delete_kernel(sid):
    try:
        subprocess.run(["kernel","browsers","delete",sid],
            env={**os.environ,"KERNEL_API_KEY":KERNEL_API_KEY},
            timeout=15, capture_output=True)
    except Exception:
        pass


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--end", action="store_true")
    p.add_argument("--email")
    p.add_argument("--password")
    a = p.parse_args()
    cdp, sid = create_kernel()
    try:
        res = await lov_mod.run(cdp_url=cdp, headless=None,
            proxy_country="gb", force_raw=False,
            email_override=a.email, password_override=a.password,
            auto_close=True)
        print(json.dumps(res, indent=2))
    finally:
        delete_kernel(sid)


if __name__ == "__main__":
    asyncio.run(main())
