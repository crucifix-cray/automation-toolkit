#!/usr/bin/env python3
"""Refresh a 2FA session cookies via OnKernel: email+pwd+TOTP -> dashboard -> save.
Usage: KERNEL_API_KEY=sk_... python3 finals/core/lov-session-refresh-totp.py 38
"""
import sys as _sys
num = _sys.argv[1] if len(_sys.argv) > 1 else "38"
import asyncio, json, subprocess, os, sys
K = "sk_f0a9980a-d5e6-fc2e-869e-ce2143c00595.HZD7XmkCxPGjvbgur-zL2qIa8sEQfXmdDgolE-XXAOk"
out = subprocess.check_output(["kernel","browsers","create","--stealth","--timeout","600","-o","json"], env={**os.environ,"KERNEL_API_KEY":K}, text=True)
cdp = json.loads(out)["cdp_ws_url"]
print("CDP ok")
async def main():
    from playwright.async_api import async_playwright
    cfg = json.load(open(f"scripts/sessions/session-{num}/config.json"))
    email, pwd, sec = cfg["email"], cfg["password"], cfg["totp_secret"]
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp(cdp, timeout=30000)
        ctx = b.contexts[0] if b.contexts else await b.new_context()
        page = await ctx.new_page()
        await page.goto("https://lovable.dev/login?redirect=%2Fdashboard", timeout=40000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        await page.locator('input[placeholder="Email"]').fill(email)
        await page.locator('[data-testid="auth-submit-button"]').click()
        await page.wait_for_timeout(3000)
        await page.locator('input[placeholder="Password"]').fill(pwd)
        await page.locator('[data-testid="auth-submit-button"]').click()
        await page.wait_for_timeout(6000)
        txt = await page.evaluate("() => document.body.innerText.slice(0,800)")
        print("after pwd:", txt[:120].replace("\n"," "))
        if "verification code" in txt.lower() or "two-factor" in txt.lower() or "authenticator" in txt.lower():
            import pyotp
            code = pyotp.TOTP(sec).now()
            print("TOTP:", code)
            inp = page.locator('input[inputmode="numeric"], input[autocomplete="one-time-code"], input[type="text"], input:not([type])').first
            try:
                await inp.wait_for(state="visible", timeout=8000)
                await inp.fill(code)
            except Exception:
                await page.evaluate("""(code) => {
                    const el = document.querySelector('#totp-code') || [...document.querySelectorAll('input')].find(i=>/code|token|otp|auth/i.test((i.placeholder||'')+(i.name||'')+(i.id||''))) || [...document.querySelectorAll('input')].find(i=>i.offsetParent!==null);
                    if(!el) throw new Error('no totp input found');
                    el.focus();
                    document.execCommand('selectAll', false, null);
                    document.execCommand('insertText', false, code); }""", code)
            await page.wait_for_timeout(1000)
            try:
                await page.get_by_role("button", name="Verify").click(timeout=5000)
            except Exception:
                await page.locator('[data-testid="auth-submit-button"]').click()
            await page.wait_for_timeout(6000)
        print("url:", page.url)
        if "/dashboard" in page.url or "/projects" in page.url:
            ck = await ctx.cookies()
            json.dump(ck, open(f"scripts/sessions/session-{num}/cookies.json","w"), indent=2)
            print(f"SAVED {len(ck)} cookies")
        else:
            print("NOT on dashboard")
            print(await page.evaluate("() => document.body.innerText.slice(0,300)"))
        await b.close()
asyncio.run(main())
