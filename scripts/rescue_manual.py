#!/usr/bin/env python3
"""rescue_manual.py — one-by-one headed rescue with TOTP (Camoufox, raw IP).

Usage: python3 rescue_manual.py --sessions 25,26,27
Per session: fresh context -> email -> password -> TOTP -> dashboard ->
trio (cookies + localstorage + indexeddb attempt) -> write files.
Results to rescue_manual.jsonl. Screenshots on failure: /tmp/manfail_N.png
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
            res["reason"] = "no-email-field"
            await ctx.close()
            return res
        await pg.wait_for_timeout(600)
        await pg.locator("button[data-testid=auth-submit-button]").first.click()
        await pg.wait_for_timeout(5000)
        try:
            await pg.locator("input[type=password]").first.fill(pwd)
        except Exception:
            try:
                b2 = (await pg.locator("body").inner_text())[:180].lower()
                res["reason"] = "disabled" if "disabled" in b2 else (
                    "suspicious" if "suspicious" in b2 else "google-only?")
            except Exception:
                res["reason"] = "no-password-field"
            await pg.screenshot(path=f"/tmp/manfail_{n}.png")
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
            except Exception as e:
                res["reason"] = f"totp-exc {str(e)[:60]}"
        u = pg.url or ""
        if "/dashboard" not in u and "/projects" not in u:
            try:
                await pg.screenshot(path=f"/tmp/manfail_{n}.png")
                b2 = (await pg.locator("body").inner_text())[:160].lower()
                res["reason"] = "disabled" if "disabled" in b2 else f"stuck:{u[:50]}"
            except Exception:
                res["reason"] = f"stuck:{u[:50]}"
            await ctx.close()
            return res
        ck = [dict(c) for c in await ctx.cookies()]
        ls = await pg.evaluate("() => { const o={}; for (let i=0;i<localStorage.length;i++){ const k=localStorage.key(i); try{o[k]=localStorage.getItem(k)}catch(e){} } return o; }")
        idb = await pg.evaluate("""async () => {
          return new Promise((resolve) => {
            try {
              const req = indexedDB.open('firebaseLocalStorageDb');
              req.onsuccess = () => {
                try {
                  const db = req.result;
                  if (!db.objectStoreNames.contains('firebaseLocalStorage')) { resolve([]); return; }
                  const tx = db.transaction('firebaseLocalStorage','readonly');
                  const all = tx.objectStore('firebaseLocalStorage').getAll();
                  all.onsuccess = () => resolve(all.result || []);
                  all.onerror = () => resolve([]);
                } catch(e) { resolve([]); }
              };
              req.onerror = () => resolve([]);
            } catch(e) { resolve([]); }
          });
        }""")
        rt = any(isinstance(r, dict) and isinstance(r.get("value"), dict)
                 and (r["value"].get("stsTokenManager") or {}).get("refreshToken")
                 for r in (idb or []))
        bak = SDIR / f"session-{n}.bak-{int(time.time())}"
        shutil.copytree(sdir, bak)
        json.dump(ck, open(sdir / "cookies.json", "w"), indent=1)
        json.dump(ls, open(sdir / "localstorage.json", "w"), indent=1)
        if idb:
            json.dump(idb, open(sdir / "indexeddb.json", "w"), indent=1)
        res["status"] = "REVIVED"
        res["reason"] = f"cookies={len(ck)} ls={len(ls)} idb={len(idb or [])} rt={rt}"
        await ctx.close()
    except Exception as e:
        res["reason"] = f"exc: {str(e)[:90]}"
        try:
            if ctx:
                await ctx.close()
        except Exception:
            pass
    return res


async def main(sessions):
    from camoufox.async_api import AsyncCamoufox
    out = BASE / "rescue_manual.jsonl"
    async with AsyncCamoufox(headless=False, humanize=True,
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
    a = ap.parse_args()
    asyncio.run(main([int(x) for x in a.sessions.split(",")]))
