#!/usr/bin/env python3
"""
Load Lovable session and access dashboard with automatic rescue mode.
If cookies are expired, automatically re-login with 2FA + backup TOTP support.

Usage:
  python3 src/lovable/load_session_with_rescue.py 1
  python3 src/lovable/load_session_with_rescue.py 1 --headed
  python3 src/lovable/load_session_with_rescue.py 1 --url "https://lovable.dev/projects/abc123"
  
  # With OnKernel CDP
  KERNEL_API_KEY=sk_... python3 src/lovable/load_session_with_rescue.py 1 --kernel
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

# Resolve paths
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
SESSIONS_DIR = REPO_ROOT / "scripts" / "sessions"

# Default Kernel API key
DEFAULT_KERNEL_KEY = os.environ.get("KERNEL_API_KEY", "sk_f0a9980a-d5e6-fc2e-869e-ce2143c00595.HZD7XmkCxPGjvbgur-zL2qIa8sEQfXmdDgolE-XXAOk")


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
    print(f"   🔑 TOTP: {code}")
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


async def _rescue_login(page, context, email, password, totp_secret, totp_backup, session_dir):
    """Rescue mode: Full re-login with 2FA and backup TOTP support."""
    print(f"\n🚑 RESCUE MODE: Cookies expired, re-logging in as {email}...")
    
    try:
        await page.goto("https://lovable.dev/login?redirect=%2Fdashboard", timeout=40000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        
        print("   📧 Filling email...")
        await page.locator('input[placeholder="Email"]').fill(email)
        await page.locator('[data-testid="auth-submit-button"]').click()
        await page.wait_for_timeout(3000)
        
        print("   🔑 Filling password...")
        await page.locator('input[placeholder="Password"]').fill(password)
        await page.locator('[data-testid="auth-submit-button"]').click()
        await page.wait_for_timeout(6000)
        
        txt = await _safe_text(page, 800)
        
        if "invalid" in txt.lower():
            print("   ❌ Invalid credentials")
            return False
        
        # Handle 2FA if triggered
        if "verification code" in txt.lower() or "two-factor" in txt.lower() or "authenticator" in txt.lower():
            if not totp_secret:
                print("   ❌ 2FA required but no TOTP secret available")
                return False
            
            print("   🔐 2FA detected, filling TOTP code...")
            await _totp_fill(page, totp_secret)
            await page.wait_for_timeout(6000)
            
            # Check if primary TOTP failed, try backup
            txt2 = await _safe_text(page, 800)
            if (
                totp_backup
                and totp_backup != totp_secret
                and ("verification code" in txt2.lower() or "two-factor" in txt2.lower() or "authenticator" in txt2.lower())
            ):
                print("   ⚠️  Primary TOTP rejected, trying backup secret...")
                await _totp_fill(page, totp_backup)
                await page.wait_for_timeout(6000)
        
        # Check if login succeeded
        final_txt = await _safe_text(page, 500)
        if "Log in" not in final_txt:
            # Save fresh cookies
            fresh_cookies = await context.cookies()
            cookies_file = session_dir / "cookies.json"
            with open(cookies_file, "w") as f:
                json.dump(fresh_cookies, f, indent=2)
            print(f"   ✅ Rescue successful! Saved {len(fresh_cookies)} fresh cookies")
            return True
        else:
            print("   ❌ Login failed - still on login page")
            return False
            
    except Exception as e:
        print(f"   ❌ Rescue error: {e}")
        return False


async def load_session(session_num: str, target_url: str = "https://lovable.dev/dashboard", 
                       headless: bool = True, use_kernel: bool = False):
    """Load session with automatic rescue mode if cookies expired."""
    
    session_dir = SESSIONS_DIR / f"session-{session_num}"
    config_file = session_dir / "config.json"
    cookies_file = session_dir / "cookies.json"
    
    # Validate session exists
    if not session_dir.exists():
        print(f"❌ Session directory not found: {session_dir}")
        return False
    
    if not config_file.exists():
        print(f"❌ Config file not found: {config_file}")
        return False
    
    if not cookies_file.exists():
        print(f"❌ Cookies file not found: {cookies_file}")
        return False
    
    # Load config
    with open(config_file) as f:
        config = json.load(f)
    
    email = config.get("email", "unknown")
    password = config.get("password", email)
    totp_secret = config.get("totp_secret")
    totp_backup = config.get("totp_secret_backup") or config.get("2fa_live_id")
    
    print(f"🔄 Loading session-{session_num} ({email})")
    print(f"   Target: {target_url}")
    print(f"   Headless: {headless}")
    print(f"   Rescue mode: ✅ ENABLED (with 2FA + backup TOTP)")
    
    # Load cookies
    with open(cookies_file) as f:
        cookies = json.load(f)
    
    print(f"   Loaded {len(cookies)} cookies")
    
    # Setup browser
    from playwright.async_api import async_playwright
    
    if use_kernel:
        print("   🌐 Using OnKernel CDP browser...")
        out = subprocess.check_output(
            ["kernel", "browsers", "create", "--stealth", "--timeout", "1200", "-o", "json"],
            env={**os.environ, "KERNEL_API_KEY": DEFAULT_KERNEL_KEY},
            text=True,
            timeout=120
        )
        kernel_data = json.loads(out)
        cdp_url = kernel_data["cdp_ws_url"]
        print(f"   CDP URL: {cdp_url[:60]}...")
        
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(cdp_url, timeout=30000)
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            await context.add_cookies(cookies)
            page = await context.new_page()
            
            # Try to load target URL
            await page.goto(target_url, timeout=40000, wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)
            
            # Check if cookies worked or need rescue
            current_url = page.url
            body_text = await _safe_text(page, 500)
            
            if "/login" in current_url or "/auth" in current_url or "Log in" in body_text:
                # Cookies expired - trigger rescue
                success = await _rescue_login(page, context, email, password, totp_secret, totp_backup, session_dir)
                if success:
                    # Retry target URL with fresh cookies
                    await page.goto(target_url, timeout=40000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(2000)
                    print(f"\n✅ Session loaded successfully at: {page.url}")
                else:
                    print(f"\n❌ Rescue failed - could not re-login")
                    await browser.close()
                    return False
            else:
                print(f"\n✅ Cookies still valid! Loaded at: {page.url}")
            
            print("\n🌐 Browser session active. Press Ctrl+C to close.")
            print(f"   Live view: {kernel_data.get('browser_live_view_url', 'N/A')}")
            
            # Keep browser open
            try:
                await asyncio.sleep(36000)  # 10 hours
            except KeyboardInterrupt:
                print("\n⚠️  Closing browser...")
            
            await browser.close()
            return True
    
    else:
        # Standard Playwright browser
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ]
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            )
            await context.add_cookies(cookies)
            page = await context.new_page()
            
            # Try to load target URL
            await page.goto(target_url, timeout=40000, wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)
            
            # Check if cookies worked or need rescue
            current_url = page.url
            body_text = await _safe_text(page, 500)
            
            if "/login" in current_url or "/auth" in current_url or "Log in" in body_text:
                # Cookies expired - trigger rescue
                success = await _rescue_login(page, context, email, password, totp_secret, totp_backup, session_dir)
                if success:
                    # Retry target URL with fresh cookies
                    await page.goto(target_url, timeout=40000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(2000)
                    print(f"\n✅ Session loaded successfully at: {page.url}")
                else:
                    print(f"\n❌ Rescue failed - could not re-login")
                    await browser.close()
                    return False
            else:
                print(f"\n✅ Cookies still valid! Loaded at: {page.url}")
            
            print("\n🌐 Browser session active. Press Ctrl+C to close.")
            
            # Keep browser open
            try:
                await asyncio.sleep(36000)  # 10 hours
            except KeyboardInterrupt:
                print("\n⚠️  Closing browser...")
            
            await browser.close()
            return True


def main():
    parser = argparse.ArgumentParser(
        description="Load Lovable session with automatic rescue mode (2FA + backup TOTP)"
    )
    parser.add_argument("session", type=str, help="Session number (e.g., 1, 2, 38)")
    parser.add_argument("--url", type=str, default="https://lovable.dev/dashboard", 
                       help="Target URL to load (default: dashboard)")
    parser.add_argument("--headed", action="store_true", help="Show browser window")
    parser.add_argument("--kernel", action="store_true", help="Use OnKernel CDP browser")
    
    args = parser.parse_args()
    
    headless = not args.headed
    
    try:
        success = asyncio.run(load_session(args.session, args.url, headless, args.kernel))
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
