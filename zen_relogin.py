#!/usr/bin/env python3
"""zen_relogin.py — re-login Lovable sessions through ZenRows CDP (one key per session).

Usage: python3 zen_relogin.py --sessions 41 [--par 2] [--country us]
Writes fresh cookies.json + localstorage + indexeddb.json (fresh refresh_token)
into railways/scripts/sessions/session-N/.

Each session gets its OWN ZenRows key (never share IPs across logins).
"""
import argparse
import asyncio
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE = Path("/home/alan/Documents/railways")
sys.path.insert(0, str(BASE / ".." / "repos" / "automation-toolkit" / "src" / "lovable"))
sys.path.insert(0, str(BASE / ".." / "repos" / "automation-toolkit" / "src"))

LOGIN_URL = "https://lovable.dev/login"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/131.0.0.0 Safari/537.36")


def load_keys():
    d = json.load(open(BASE / "finals" / "zenrows_onkernel_farmed.json"))
    return [x["api_key"] for x in d if x.get("api_key")]


async def relogin_one(session_n: int, api_key: str, country: str) -> dict:
    from playwright.async_api import async_playwright
    res = {"session": session_n, "status": "FAILED", "reason": ""}
    sdir = BASE / "scripts" / "sessions" / f"session-{session_n}"
    try:
        cfg = json.loads((sdir / "config.json").read_text())
    except Exception as e:
        res["reason"] = f"config read: {e}"
        return res
    email, password = cfg.get("email", "").strip(), cfg.get("password", "").strip()
    totp_secret = cfg.get("totp_secret", "").strip()
    if not email or not password:
        res["reason"] = "missing email/password"
        return res
    cdp = f"wss://browser.zenrows.com?apikey={api_key}&proxy_country={country}"
    try:
        async with async_playwright() as p:
            try:
                browser = await p.chromium.connect_over_cdp(cdp, timeout=45000)
            except Exception as e:
                res["reason"] = f"CDP connect: {str(e)[:100]}"
                return res
            try:
                ctx = await browser.new_context(viewport={"width": 1280, "height": 720},
                                                user_agent=UA)
                page = await ctx.new_page()
                await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(2000)
                try:
                    ok_btn = page.locator("[data-testid='consent-accept-all-button'], button:has-text('OK')").first
                    if await ok_btn.is_visible():
                        await ok_btn.click(timeout=1500)
                except Exception:
                    pass
                ein = page.locator("input[type='email'], input[name='email']").first
                await ein.wait_for(state="visible", timeout=15000)
                await ein.fill(email)
                await page.wait_for_timeout(400)
                await page.locator("button[data-testid='auth-submit-button']").first.click()
                pin = page.locator("input[type='password'], input[name='password']").first
                try:
                    await pin.wait_for(state="visible", timeout=12000)
                except Exception:
                    body = (await page.locator("body").inner_text())[:300].lower()
                    if "suspicious activity" in body:
                        res["reason"] = "suspicious-activity IP block"
                    else:
                        res["reason"] = f"no password field: {body[:120]}"
                    await ctx.close()
                    return res
                await pin.fill(password)
                await page.wait_for_timeout(400)
                try:
                    sub = page.locator("button[data-testid='auth-submit-button'], button[type='submit']").first
                    if await sub.is_visible():
                        await sub.click()
                except Exception:
                    await pin.press("Enter")
                await page.wait_for_timeout(4000)
                # TOTP if challenged
                if totp_secret:
                    try:
                        tin = page.locator("input[inputmode='numeric'], input[name='code'], input[autocomplete='one-time-code']").first
                        if await tin.is_visible(timeout=6000):
                            import pyotp
                            await tin.fill(pyotp.TOTP(totp_secret).now())
                            await page.wait_for_timeout(1500)
                            try:
                                await page.locator("button[type='submit']").first.click()
                            except Exception:
                                await tin.press("Enter")
                            await page.wait_for_timeout(4000)
                    except Exception:
                        pass
                u = page.url or ""
                ok = "/dashboard" in u or "/projects" in u
                if not ok:
                    try:
                        b = (await page.locator("body").inner_text())[:200].lower()
                        ok = "log in" not in b and "sign in" not in b and len(b) > 100
                    except Exception:
                        pass
                if not ok:
                    res["reason"] = f"still on login: {u[:80]}"
                    await ctx.close()
                    return res
                # save full trio
                try:
                    from session_state import save_full_state
                    good = await save_full_state(ctx, page, sdir)
                except Exception as e:
                    res["reason"] = f"save state: {str(e)[:100]}"
                    await ctx.close()
                    return res
                ncookies = len(json.loads((sdir / "cookies.json").read_text())) if (sdir / "cookies.json").exists() else 0
                res["status"] = "REVIVED" if good else "PARTIAL"
                res["reason"] = f"cookies={ncookies}"
                await ctx.close()
            finally:
                try:
                    await browser.close()
                except Exception:
                    pass
    except Exception as e:
        res["reason"] = f"exception: {str(e)[:120]}"
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", required=True, help="comma list of lov session numbers")
    ap.add_argument("--par", type=int, default=2)
    ap.add_argument("--country", default="us")
    ap.add_argument("--key", default="", help="pin a specific ZenRows API key (default: rotate file keys)")
    a = ap.parse_args()
    sessions = [int(x) for x in a.sessions.split(",")]
    keys = load_keys()
    if a.key:
        keys = [a.key]
        print(f"pinned key {a.key[:8]}...", flush=True)
    print(f"sessions={sessions} keys_available={len(keys)} par={a.par}", flush=True)
    jobs = [(s, keys[i % len(keys)]) for i, s in enumerate(sessions)]

    def run(job):
        s, k = job
        t0 = time.time()
        r = asyncio.run(relogin_one(s, k, a.country))
        r["secs"] = round(time.time() - t0, 1)
        print(f"session-{s}: {r['status']} ({r['reason']}) [{r['secs']}s]", flush=True)
        return r

    results = []
    with ThreadPoolExecutor(max_workers=a.par) as ex:
        for r in ex.map(run, jobs):
            results.append(r)
    ok = sum(1 for r in results if r["status"] in ("REVIVED", "PARTIAL"))
    print(f"done: {ok}/{len(results)} revived", flush=True)
    Path("/tmp/zen_relogin_results.json").write_text(json.dumps(results, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
