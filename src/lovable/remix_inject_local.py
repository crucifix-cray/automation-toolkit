#!/usr/bin/env python3
"""Remix + inject via LOCAL Camoufox (max stealth) — reuses lov-remix-inject logic.

Usage:
  python3 finals/core/lov-remix-inject-local.py --session 1
  python3 finals/core/lov-remix-inject-local.py --session 1 --headed
  python3 finals/core/lov-remix-inject-local.py --all --limit 5
"""
import argparse
import asyncio
import glob
import json
import os
import sys

CORE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(CORE))
SESSIONS = os.path.join(REPO, "scripts", "sessions")
sys.path.insert(0, CORE)

for k in list(os.environ):
    if k.lower().endswith("_proxy") or k == "LD_PRELOAD":
        os.environ.pop(k, None)

import importlib
import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "lov_remix_inject", os.path.join(CORE, "lov-remix-inject.py")
)
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)


async def apply_stealth(page):
    try:
        from playwright_stealth import Stealth

        await Stealth().apply_stealth_async(page)
    except Exception as e:
        print(f"stealth pkg skip: {e}", flush=True)
    await page.add_init_script(
        """() => {
        try{ Object.defineProperty(navigator,'webdriver',{get:()=>undefined}); }catch(e){}
        try{ if(!window.chrome) window.chrome={}; window.chrome.runtime={}; window.chrome.loadTimes=()=>({}); }catch(e){}
        try{ Object.defineProperty(navigator,'plugins',{get:()=>{const p=[{name:'Chrome PDF Plugin'},{name:'Chrome PDF Viewer'},{name:'Native Client'}]; return p;}}); }catch(e){}
        try{ const g=navigator.permissions&&navigator.permissions.query; if(g){navigator.permissions.query=(p)=>{if(p&&p.name==='notifications')return Promise.resolve({state:'prompt'}); return g(p);};} }catch(e){}
    }"""
    )


async def run_one(num, headed=False):
    from camoufox.async_api import AsyncCamoufox
    from camoufox.addons import DefaultAddons

    async with AsyncCamoufox(
        headless=not headed,
        humanize=True,
        os="windows",
        block_webrtc=True,
        allow_webgl=True,
        locale="en-US",
        exclude_addons=[DefaultAddons.UBO],
    ) as browser:
        ctx = await browser.new_context(
            locale="en-US",
            timezone_id="America/New_York",
            viewport={"width": 1366, "height": 768},
        )
        page = await ctx.new_page()
        await apply_stealth(page)
        # remix_one creates its own page; close probe page and run
        await page.close()
        # fake pw object: remix_one only uses ctx.new_page + page ops
        res = await R.remix_one(None, ctx, str(num))
        try:
            fresh = await ctx.cookies()
            ck_path = os.path.join(SESSIONS, f"session-{num}", "cookies.json")
            # save ALL cookies (incl. lovableproject.com preview auth), not just lovable.dev
            json.dump(fresh, open(ck_path, "w"), indent=2)
        except Exception as e:
            print(f"cookie save warn: {e}", flush=True)
        try:
            await ctx.close()
        except Exception:
            pass
        return res


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--headed", action="store_true")
    a = ap.parse_args()

    if a.all:
        targets, seen = [], set()
        for f in sorted(
            glob.glob(os.path.join(SESSIONS, "session-*", "config.json")),
            key=lambda p: int(os.path.basename(os.path.dirname(p)).split("-")[1]),
        ):
            num = os.path.basename(os.path.dirname(f)).split("-")[1]
            d = json.load(open(f))
            if d.get("email") in seen:
                continue
            seen.add(d.get("email"))
            targets.append(num)
        if a.limit:
            targets = targets[: a.limit]
        print(f"sessions: {len(targets)} ({len(seen)} unique emails)", flush=True)
    elif a.session:
        targets = [a.session]
    else:
        raise SystemExit("pass --session N or --all")

    results = []
    for n in targets:
        try:
            res = await run_one(n, headed=a.headed)
        except Exception as e:
            res = {"session": n, "success": False, "reason": f"local: {e}"[:200]}
        results.append(res)
        print(json.dumps(res), flush=True)
        print(
            f"{'✅' if res.get('success') else '❌'} session-{n} {res.get('project_id') or res.get('reason', '?')}",
            flush=True,
        )
    ok = sum(1 for r in results if r.get("success"))
    print(f"\n{ok}/{len(results)} remixed+injected (local camoufox)", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
