#!/usr/bin/env python3
"""Refresh a 2FA session cookies via OnKernel: email+pwd+TOTP -> dashboard -> save.
Now with rescue mode: tries cookies first, falls back to full login with backup TOTP support.
Usage: KERNEL_API_KEY=sk_... python3 src/lovable/session_refresh.py 38
"""
import sys as _sys
num = _sys.argv[1] if len(_sys.argv) > 1 else "38"
import asyncio, json, subprocess, os, sys
K = os.environ.get("KERNEL_API_KEY", "sk_f0a9980a-d5e6-fc2e-869e-ce2143c00595.HZD7XmkCxPGjvbgur-zL2qIa8sEQfXmdDgolE-XXAOk")
out = subprocess.check_output(["kernel","browsers","create","--stealth","--timeout","600","-o","json"], env={**os.environ,"KERNEL_API_KEY":K}, text=True)
cdp = json.loads(out)["cdp_ws_url"]
print("CDP ok")

async def _safe_text(page, n=500, retries=4):
    """Safely extract body text with retries for navigation issues."""
    for _ in range(retries):
        try:
            return await page.evaluate(f"() => document.body.innerText.slice(0,{n})")
        except Exception as e:
            if "destroyed" in str(e).lower() or "navigation" in str(e).lower():
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=10000)
                except Exception:
                    pass
                await page.wait_for_timeout(2000)
                continue
            raise
    return await page.evaluate(f"() => document.body.innerText.slice(0,{n})")

async def _totp_fill(page, secret):
    """Fill TOTP code with multiple fallback strategies."""
    import pyotp
    code = pyotp.TOTP(secret).now()
    print(f"TOTP: {code}")
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
    return code

async def _login_with_rescue(page, ctx, email, password, totp_secret, totp_backup=None, cookies_path=None):
    """Rescue mode: Try cookies first, fall back to full login with backup TOTP support."""
    
    # Try loading existing cookies first if available
    if cookies_path and os.path.exists(cookies_path):
        try:
            print("🔄 Trying existing cookies first...")
            cookies = json.load(open(cookies_path))
            await ctx.add_cookies(cookies)
            await page.goto("https://lovable.dev/dashboard", timeout=40000, wait_until="domcontentloaded")
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            await page.wait_for_timeout(4000)
            
            # Check if cookies worked
            if "Log in" not in await _safe_text(page, 500):
                print("✅ Existing cookies still valid!")
                return True
            else:
                print("⚠️  Cookies expired, falling back to credential login...")
        except Exception as e:
            print(f"⚠️  Cookie test failed: {e}, proceeding to credential login...")
    
    # Full login flow
    await page.goto("https://lovable.dev/login?redirect=%2Fdashboard", timeout=40000, wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)
    await page.locator('input[placeholder="Email"]').fill(email)
    await page.locator('[data-testid="auth-submit-button"]').click()
    await page.wait_for_timeout(3000)
    await page.locator('input[placeholder="Password"]').fill(password)
    await page.locator('[data-testid="auth-submit-button"]').click()
    await page.wait_for_timeout(6000)
    
    txt = await _safe_text(page, 800)
    print("After password:", txt[:120].replace("\n", " "))
    
    if "invalid" in txt.lower():
        print("❌ Invalid credentials")
        return False
    
    # Handle 2FA if triggered
    if "verification code" in txt.lower() or "two-factor" in txt.lower() or "authenticator" in txt.lower():
        if not totp_secret:
            print("❌ 2FA required but no TOTP secret available")
            return False
        
        await _totp_fill(page, totp_secret)
        await page.wait_for_timeout(6000)
        
        # Check if primary TOTP failed, try backup
        txt2 = await _safe_text(page, 800)
        if (
            totp_backup
            and totp_backup != totp_secret
            and ("verification code" in txt2.lower() or "two-factor" in txt2.lower() or "authenticator" in txt2.lower())
        ):
            print("⚠️  Primary TOTP rejected, trying backup secret...")
            await _totp_fill(page, totp_backup)
            await page.wait_for_timeout(6000)
    
    return "Log in" not in await _safe_text(page, 500)

async def main():
    from playwright.async_api import async_playwright
    cfg = json.load(open(f"scripts/sessions/session-{num}/config.json"))
    email = cfg["email"]
    password = cfg.get("password", email)
    totp_secret = cfg.get("totp_secret")
    totp_backup = cfg.get("totp_secret_backup") or cfg.get("2fa_live_id")
    cookies_path = f"scripts/sessions/session-{num}/cookies.json"
    
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp(cdp, timeout=30000)
        ctx = b.contexts[0] if b.contexts else await b.new_context()
        page = await ctx.new_page()
        
        success = await _login_with_rescue(page, ctx, email, password, totp_secret, totp_backup, cookies_path)
        
        if not success:
            print("❌ Login failed")
            await b.close()
            sys.exit(1)
        
        print(f"✅ Login successful! URL: {page.url}")
        
        if "/dashboard" in page.url or "/projects" in page.url or "Log in" not in await _safe_text(page, 400):
            # Full trio: cookies + localStorage + Firebase IndexedDB (refresh_token)
            sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
            from session_state import save_full_state
            session_dir = os.path.dirname(cookies_path)
            ok_refresh = await save_full_state(ctx, page, session_dir)
            if not ok_refresh:
                print("⚠️  Login OK but refresh_token MISSING in IndexedDB — retry once on dashboard")
                try:
                    await page.goto("https://lovable.dev/dashboard", timeout=40000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(4000)
                    ok_refresh = await save_full_state(ctx, page, session_dir)
                except Exception as e:
                    print(f"⚠️  dashboard re-save failed: {e}")
            print(f"✅ FULL STATE saved to {session_dir} (refresh_token={'YES' if ok_refresh else 'NO'})")
        else:
            print("⚠️  NOT on dashboard")
            print(await page.evaluate("() => document.body.innerText.slice(0,300)"))
        
        await b.close()

asyncio.run(main())
