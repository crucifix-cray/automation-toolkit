#!/usr/bin/env python3
"""verify_all.py — deep-verify every Lovable session WITHOUT full login.

Per session (one browser, fresh context each):
  Phase 1: load cookies -> project (or dashboard) page -> AUTHED or WALLED?
  Phase 2 (walled only): email-submit probe -> DISABLED / PASSWORD-FIELD / other.
No password is ever submitted. Minimal disable risk.
Results -> verify_all.jsonl
"""
import asyncio
import json
import sys
import time
from pathlib import Path

BASE = Path("/home/alan/Documents/railways")
SDIR = BASE / "scripts" / "sessions"

WALL_HINTS = ("don't have access", "private", "request access", "log in",
              "sign in", "suspicious activity", "disabled")


async def check_one(b, n: int, project: str | None) -> dict:
    res = {"session": n, "cookies": "missing", "page": "?", "email_probe": "-"}
    sdir = SDIR / f"session-{n}"
    cj = sdir / "config.json"
    if not cj.exists():
        res["reason"] = "no config"
        return res
    try:
        cfg = json.loads(cj.read_text())
    except Exception:
        res["reason"] = "bad config"
        return res
    email = cfg.get("email", "")
    ckp = sdir / "cookies.json"
    ck = []
    if ckp.exists():
        try:
            ck = json.load(open(ckp))
        except Exception:
            pass
    res["cookies"] = len(ck)
    ctx = None
    try:
        ctx = await b.new_context(viewport={"width": 1280, "height": 800})
        if ck:
            try:
                await ctx.add_cookies(ck)
            except Exception:
                pass
        pg = await ctx.new_page()
        url = f"https://lovable.dev/projects/{project}" if project else "https://lovable.dev/dashboard"
        try:
            await pg.goto(url, wait_until="domcontentloaded", timeout=45000)
            await pg.wait_for_timeout(4000)
        except Exception as e:
            res["page"] = f"goto-fail {str(e)[:50]}"
            await ctx.close()
            return res
        u = pg.url or ""
        try:
            body = (await pg.locator("body").inner_text())[:250].lower()
        except Exception:
            body = ""
        if "/login" in u or any(h in body for h in WALL_HINTS):
            res["page"] = "WALLED"
        else:
            res["page"] = "AUTHED"
            await ctx.close()
            return res
        # Phase 2: email probe (no password submit)
        try:
            await pg.goto("https://lovable.dev/login", wait_until="domcontentloaded", timeout=45000)
            await pg.wait_for_timeout(3500)
            for t in ["Reject all", "Accept all"]:
                try:
                    btn = pg.locator(f"button:has-text('{t}')").first
                    if await btn.is_visible(timeout=4000):
                        await btn.click()
                        await pg.wait_for_timeout(1500)
                        break
                except Exception:
                    pass
            await pg.locator("input[type=email]").first.fill(email)
            await pg.wait_for_timeout(600)
            try:
                await pg.locator("button[data-testid=auth-submit-button]").first.click(timeout=10000)
            except Exception:
                try:
                    await pg.evaluate("() => { const b=document.querySelector(\"button[data-testid='auth-submit-button']\"); if(b) b.click(); }")
                except Exception:
                    pass
            await pg.wait_for_timeout(6000)
            b2 = ""
            try:
                b2 = (await pg.locator("body").inner_text())[:220].lower()
            except Exception:
                pass
            if "disabled" in b2:
                res["email_probe"] = "DISABLED"
            elif await pg.locator("input[type=password]").first.is_visible(timeout=4000):
                res["email_probe"] = "PASSWORD-FIELD(alive)"
            elif "suspicious" in b2:
                res["email_probe"] = "SUSPICIOUS"
            else:
                res["email_probe"] = f"other:{b2[:70]}"
        except Exception as e:
            res["email_probe"] = f"probe-exc {str(e)[:60]}"
        await ctx.close()
    except Exception as e:
        res["reason"] = f"exc {str(e)[:80]}"
        try:
            if ctx:
                await ctx.close()
        except Exception:
            pass
    return res


async def main(sessions, projects):
    from playwright.async_api import async_playwright
    out = BASE / "verify_all.jsonl"
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True, channel="chrome",
                                    args=["--no-sandbox", "--disable-dev-shm-usage"])
        for n in sessions:
            t0 = time.time()
            r = await check_one(b, n, projects.get(n))
            r["secs"] = round(time.time() - t0, 1)
            print(f"session-{n}: cookies={r['cookies']} page={r['page']} probe={r['email_probe']} [{r['secs']}s]", flush=True)
            with open(out, "a") as f:
                f.write(json.dumps(r) + "\n")
        await b.close()


if __name__ == "__main__":
    import argparse
    sys.path.insert(0, "/home/alan/Documents/repos/chimera-miner/ops")
    from cell_ops import load_map
    cells = load_map()["cells"]
    proj = {}
    for c, v in cells.items():
        try:
            n = int(str(v.get("lov_session")).replace("session-", ""))
        except Exception:
            continue
        if v.get("lovable_project"):
            proj[n] = v["lovable_project"]
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", default="all")
    a = ap.parse_args()
    if a.sessions == "all":
        ss = sorted({int(p.name.split("-")[1]) for p in SDIR.iterdir()
                     if p.is_dir() and p.name.startswith("session-")
                     and p.name.split("-")[1].isdigit()})
    else:
        ss = [int(x) for x in a.sessions.split(",")]
    asyncio.run(main(ss, proj))
