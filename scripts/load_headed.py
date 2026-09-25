#!/usr/bin/env python3
"""Headed local Camoufox with a Lovable session trio + project.
Usage: python3 load_headed.py 25 [project-uuid]
Keeps the browser open (Ctrl+C to close).
"""
import asyncio, json, os, sys

num = sys.argv[1] if len(sys.argv) > 1 else "25"
ATK = "/home/alae/Documents/repos/automation-toolkit"
SESS = f"{ATK}/scripts/sessions/session-{num}"

async def main():
    from camoufox.async_api import AsyncCamoufox
    cfg = json.load(open(f"{SESS}/config.json"))
    proj = sys.argv[2] if len(sys.argv) > 2 else cfg.get("project_id")
    url = f"https://lovable.dev/projects/{proj}" if proj else "https://lovable.dev/dashboard"
    cookies = json.load(open(f"{SESS}/cookies.json"))
    cookies = [c for c in cookies if "lovable" in c.get("domain", "")]
    try:
        ls = json.load(open(f"{SESS}/localstorage.json"))
    except Exception:
        ls = {}
    print(f"session-{num} {cfg.get('email')} -> {url} ({len(cookies)} cookies, {len(ls)} LS keys)", flush=True)
    async with AsyncCamoufox(headless=False, args=["--start-maximized"]) as browser:
        ctx = await browser.new_context(viewport=None)
        await ctx.add_cookies(cookies)
        if ls:
            await ctx.add_init_script(f"() => {{ for (const [k,v] of Object.entries({json.dumps(ls)})) try {{ localStorage.setItem(k,v); }} catch(e){{}} }}")
        page = await ctx.new_page()
        await page.goto(url, timeout=60000, wait_until="domcontentloaded")
        await page.wait_for_timeout(6000)
        print(f"loaded: {page.url}", flush=True)
        # stay open
        while True:
            await asyncio.sleep(60)

asyncio.run(main())
