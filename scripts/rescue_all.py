#!/usr/bin/env python3
"""rescue_all.py — re-login Lovable sessions headfully, save fresh trios.

Camoufox headed + raw IP (no proxy env). One browser, fresh context per
session. Saves cookies.json (+ localStorage dump) into
railways/scripts/sessions/session-N/ (backs up old dir first).

Usage: python3 rescue_all.py --sessions 2,7,8 [--headless]
Results appended to rescue_results.jsonl
"""
import argparse
import asyncio
import json
import shutil
import sys
import time
from pathlib import Path

BASE = Path("/home/alan/Documents/railways")
SDIR = BASE / "scripts" / "sessions"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/131.0.0.0 Safari/537.36")


async def rescue_one(b, n: int) -> dict:
    res = {"session": n, "status": "FAILED", "reason": ""}
    sdir = SDIR / f"session-{n}"
    try:
        cfg = json.loads((sdir / "config.json").read_text())
    except Exception as e:
        res["reason"] = f"config: {e}"
        return res
    email, pwd, totp = cfg.get("email", ""), cfg.get("password", ""), cfg.get("totp_secret", "")
    if not email or not pwd:
        res["reason"] = "no creds"
        return res
    ctx = None
    try:
        ctx = await b.new_context(viewport={"width": 1280, "height": 800})
        pg = await ctx.new_page()
        await pg.goto("https://lovable.dev/login", wait_until="domcontentloaded", timeout=90000)
        await pg.wait_for_timeout(4000)
        for t in ["Reject all", "Accept all"]:
            try:
                btn = pg.locator(f"button:has-text('{t}')").first
                if await btn.is_visible(timeout=3000):
                    await btn.click()
                    await pg.wait_for_timeout(1500)
                    break
            except Exception:
                pass
        try:
            await pg.locator("input[type=email]").first.fill(email)
        except Exception:
            body = (await pg.locator("body").inner_text())[:150].lower()
            res["reason"] = "disabled?" if "disabled" in body else "no email field"
            await ctx.close()
            return res
        await pg.wait_for_timeout(600)
        await pg.locator("button[data-testid=auth-submit-button]").first.click()
        await pg.wait_for_timeout(5000)
        try:
            await pg.locator("input[type=password]").first.fill(pwd)
        except Exception:
            body = (await pg.locator("body").inner_text())[:200].lower()
            if "suspicious activity" in body:
                res["reason"] = "suspicious-activity"
            elif "google" in body and "password" not in body:
                res["reason"] = "google-only (api_only)"
            else:
                res["reason"] = "no password field"
            await ctx.close()
            return res
        await pg.wait_for_timeout(600)
        await pg.locator("button:has-text('Log in')").first.click()
        await pg.wait_for_timeout(9000)
        if totp:
            try:
                tin = pg.locator("input[inputmode=numeric], input[name=code], input[autocomplete=one-time-code]").first
                if await tin.is_visible(timeout=8000):
                    import pyotp
                    await tin.fill(pyotp.TOTP(totp).now())
                    await pg.wait_for_timeout(1000)
                    await pg.locator("button:has-text('Verify')").first.click()
                    await pg.wait_for_timeout(8000)
            except Exception:
                pass
        u = pg.url or ""
        if "/dashboard" not in u and "/projects" not in u:
            try:
                await pg.screenshot(path=f"/tmp/fail_{n}.png")
                b2 = (await pg.locator("body").inner_text())[:200].lower()
                if "disabled" in b2:
                    res["reason"] = "ACCOUNT-DISABLED"
                elif "suspicious activity" in b2:
                    res["reason"] = "suspicious-activity"
                elif "incorrect" in b2 or "wrong" in b2 or "invalid" in b2:
                    res["reason"] = "bad-credentials?"
                elif "verify" in b2 and "code" in b2:
                    res["reason"] = "totp-failed?"
                else:
                    res["reason"] = f"stuck: {u[:60]}"
            except Exception:
                res["reason"] = f"stuck: {u[:60]}"
            await ctx.close()
            return res
        ck = [dict(c) for c in await ctx.cookies()]
        ls = await pg.evaluate("() => { const o={}; for (let i=0;i<localStorage.length;i++){ const k=localStorage.key(i); try{o[k]=localStorage.getItem(k)}catch(e){} } return o; }")
        bak = SDIR / f"session-{n}.bak-{int(time.time())}"
        shutil.copytree(sdir, bak)
        json.dump(ck, open(sdir / "cookies.json", "w"), indent=1)
        json.dump(ls, open(sdir / "localstorage.json", "w"), indent=1)
        res["status"] = "REVIVED"
        res["reason"] = f"cookies={len(ck)} ls={len(ls)}"
        await ctx.close()
    except Exception as e:
        res["reason"] = f"exception: {str(e)[:100]}"
        try:
            if ctx:
                await ctx.close()
        except Exception:
            pass
    return res


async def main(sessions, headed):
    from camoufox.async_api import AsyncCamoufox
    out = BASE / "rescue_results.jsonl"
    async with AsyncCamoufox(headless=not headed, humanize=True,
                             args=["--no-sandbox", "--disable-dev-shm-usage"]) as b:
        for n in sessions:
            t0 = time.time()
            r = await rescue_one(b, n)
            r["secs"] = round(time.time() - t0, 1)
            print(f"session-{n}: {r['status']} ({r['reason']}) [{r['secs']}s]", flush=True)
            with open(out, "a") as f:
                f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", required=True)
    ap.add_argument("--headed", action="store_true", default=True)
    a = ap.parse_args()
    asyncio.run(main([int(x) for x in a.sessions.split(",")], a.headed))
