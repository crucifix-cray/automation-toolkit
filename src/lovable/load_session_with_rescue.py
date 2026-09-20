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

# Default API keys
DEFAULT_KERNEL_KEY = os.environ.get("KERNEL_API_KEY", "sk_f0a9980a-d5e6-fc2e-869e-ce2143c00595.HZD7XmkCxPGjvbgur-zL2qIa8sEQfXmdDgolE-XXAOk")
DEFAULT_ZENROWS_KEY = os.environ.get("ZENROWS_API_KEY", "7213c8436771ba990ec226f68d64b3d6c1e666f3")


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


async def _save_full_state(context, page, session_dir):
    """Save cookies + localStorage + IndexedDB (Firebase refresh token) to disk.
    This is the FULL session state — restoring all three avoids re-login."""
    # 1. Cookies (existing behavior)
    fresh_cookies = await context.cookies()
    with open(session_dir / "cookies.json", "w") as f:
        json.dump(fresh_cookies, f, indent=2)
    print(f"   ✅ Saved {len(fresh_cookies)} cookies")
    # 2. localStorage
    try:
        ls_data = await page.evaluate("""() => {
            const out = {};
            for (let i = 0; i < localStorage.length; i++) {
                const k = localStorage.key(i);
                out[k] = localStorage.getItem(k);
            }
            return out;
        }""")
        with open(session_dir / "localstorage.json", "w") as f:
            json.dump(ls_data, f, indent=2)
        print(f"   ✅ Saved localStorage ({len(ls_data)} keys)")
    except Exception as e:
        print(f"   ⚠️  localStorage save failed: {e}")
    # 3. IndexedDB — Firebase auth (access + refresh token)
    try:
        idb_data = await page.evaluate("""async () => {
            return new Promise((resolve) => {
                try {
                    const req = indexedDB.open('firebaseLocalStorageDb');
                    req.onsuccess = () => {
                        const db = req.result;
                        const stores = Array.from(db.objectStoreNames);
                        if (!stores.length) { resolve([]); return; }
                        const tx = db.transaction(stores, 'readonly');
                        const out = [];
                        let pending = stores.length;
                        stores.forEach(sn => {
                            try {
                                const rq = tx.objectStore(sn).getAll();
                                rq.onsuccess = () => {
                                    rq.result.forEach(r => out.push({store: sn, key: r.fkey || r.key, value: r.value}));
                                    if (--pending === 0) resolve(out);
                                };
                                rq.onerror = () => { if (--pending === 0) resolve(out); };
                            } catch(e) { if (--pending === 0) resolve(out); }
                        });
                    };
                    req.onerror = () => resolve([]);
                } catch(e) { resolve([]); }
            });
        }""")
        with open(session_dir / "indexeddb.json", "w") as f:
            json.dump(idb_data, f, indent=2)
        has_refresh = any(
            r.get("value", {}).get("stsTokenManager", {}).get("refreshToken")
            for r in idb_data if isinstance(r.get("value"), dict)
        )
        print(f"   ✅ Saved IndexedDB ({len(idb_data)} records, refresh_token={'YES' if has_refresh else 'MISSING'})")
    except Exception as e:
        print(f"   ⚠️  IndexedDB save failed: {e}")


async def _load_full_state(context, page, session_dir, target_url="https://lovable.dev"):
    """Restore cookies + localStorage + IndexedDB before navigating.
    Must visit the domain once before injecting storage."""
    # 1. Cookies (existing behavior — caller already does add_cookies, skip if done)
    # 2. localStorage
    ls_file = session_dir / "localstorage.json"
    if ls_file.exists():
        try:
            with open(ls_file) as f:
                ls_data = json.load(f)
            # Need a page on the domain first
            await page.goto(target_url, timeout=30000, wait_until="domcontentloaded")
            await page.evaluate("(data) => { for (const [k, v] of Object.entries(data)) { try { localStorage.setItem(k, v); } catch(e) {} } }", ls_data)
            print(f"   ✅ Restored localStorage ({len(ls_data)} keys)")
        except Exception as e:
            print(f"   ⚠️  localStorage restore failed: {e}")
    # 3. IndexedDB — Firebase auth
    idb_file = session_dir / "indexeddb.json"
    if idb_file.exists():
        try:
            with open(idb_file) as f:
                idb_data = json.load(f)
            if idb_data:
                # Ensure we're on the domain
                if "lovable.dev" not in page.url:
                    await page.goto(target_url, timeout=30000, wait_until="domcontentloaded")
                restored = await page.evaluate("""(records) => {
                    return new Promise((resolve) => {
                        try {
                            const delReq = indexedDB.deleteDatabase('firebaseLocalStorageDb');
                            delReq.onsuccess = delReq.onerror = delReq.onblocked = () => {
                                const openReq = indexedDB.open('firebaseLocalStorageDb');
                                openReq.onupgradeneeded = () => {
                                    openReq.result.createObjectStore('firebaseLocalStorage', {keyPath: 'fkey'});
                                };
                                openReq.onsuccess = () => {
                                    const db = openReq.result;
                                    const tx = db.transaction('firebaseLocalStorage', 'readwrite');
                                    const store = tx.objectStore('firebaseLocalStorage');
                                    let done = 0;
                                    if (!records.length) { resolve(0); return; }
                                    records.forEach(r => {
                                        try {
                                            const putReq = store.put({fkey: r.key, value: r.value});
                                            putReq.onsuccess = putReq.onerror = () => { if (++done === records.length) resolve(done); };
                                        } catch(e) { if (++done === records.length) resolve(done); }
                                    });
                                };
                                openReq.onerror = () => resolve(-1);
                            };
                        } catch(e) { resolve(-1); }
                    });
                }""", idb_data)
                print(f"   ✅ Restored IndexedDB ({restored} records)")
        except Exception as e:
            print(f"   ⚠️  IndexedDB restore failed: {e}")


async def _refresh_firebase_token(page):
    """If Firebase access token expired but refresh token exists, mint a new one.
    Returns True if token is fresh (or was refreshed), False if no refresh possible."""
    try:
        result = await page.evaluate("""async () => {
            return new Promise((resolve) => {
                try {
                    const req = indexedDB.open('firebaseLocalStorageDb');
                    req.onsuccess = () => {
                        const db = req.result;
                        const tx = db.transaction('firebaseLocalStorage', 'readwrite');
                        const store = tx.objectStore('firebaseLocalStorage');
                        const getAll = store.getAll();
                        getAll.onsuccess = async () => {
                            for (const r of getAll.result) {
                                const v = r.value;
                                if (v && v.stsTokenManager && v.stsTokenManager.refreshToken) {
                                    const now = Date.now();
                                    const exp = v.stsTokenManager.expirationTime || 0;
                                    if (exp > now + 60000) { resolve({status: 'fresh', exp}); return; }
                                    // Expired — use refresh token to mint new access token
                                    try {
                                        const resp = await fetch(
                                            'https://securetoken.googleapis.com/v1/token?key=' + v.apiKey,
                                            {method: 'POST', headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                                             body: 'grant_type=refresh_token&refresh_token=' + v.stsTokenManager.refreshToken});
                                        const data = await resp.json();
                                        if (data.access_token) {
                                            v.stsTokenManager.accessToken = data.access_token;
                                            v.stsTokenManager.expirationTime = Date.now() + (parseInt(data.expires_in || '3600') * 1000);
                                            if (data.refresh_token) v.stsTokenManager.refreshToken = data.refresh_token;
                                            store.put({fkey: r.fkey, value: v});
                                            resolve({status: 'refreshed', exp: v.stsTokenManager.expirationTime});
                                        } else { resolve({status: 'refresh_failed', detail: JSON.stringify(data).slice(0,200)}); }
                                    } catch(e) { resolve({status: 'refresh_error', detail: String(e).slice(0,200)}); }
                                    return;
                                }
                            }
                            resolve({status: 'no_token'});
                        };
                        getAll.onerror = () => resolve({status: 'db_error'});
                    };
                    req.onerror = () => resolve({status: 'db_open_failed'});
                } catch(e) { resolve({status: 'error', detail: String(e).slice(0,200)}); }
            });
        }""")
        status = result.get("status", "unknown")
        if status == "fresh":
            print(f"   ✅ Firebase token fresh (expires {result.get('exp')})")
            return True
        elif status == "refreshed":
            print(f"   ✅ Firebase token REFRESHED without re-login (new expiry {result.get('exp')})")
            return True
        else:
            print(f"   ⚠️  Firebase token status: {status} {result.get('detail', '')}")
            return False
    except Exception as e:
        print(f"   ⚠️  Firebase refresh check failed: {e}")
        return False


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
            # Save FULL state: cookies + localStorage + IndexedDB (Firebase refresh token)
            await _save_full_state(context, page, session_dir)
            print(f"   ✅ Rescue successful! Full session state saved")
            return True
        else:
            print("   ❌ Login failed - still on login page")
            return False
            
    except Exception as e:
        print(f"   ❌ Rescue error: {e}")
        return False


async def load_session(session_num: str, target_url: str = "https://lovable.dev/dashboard", 
                       headless: bool = True, use_kernel: bool = False, use_zenrows: bool = False):
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
    print(f"   Mode: {'ZenRows CDP' if use_zenrows else 'OnKernel CDP' if use_kernel else 'Local'}")
    print(f"   Rescue mode: ✅ ENABLED (with 2FA + backup TOTP)")
    
    # Load cookies
    with open(cookies_file) as f:
        cookies = json.load(f)
    
    print(f"   Loaded {len(cookies)} cookies")
    
    # Setup browser
    from playwright.async_api import async_playwright
    
    if use_zenrows:
        print("   🌐 Using ZenRows CDP browser...")
        zenrows_wss = f"wss://browser.zenrows.com?apikey={DEFAULT_ZENROWS_KEY}&proxy_country=us"
        print(f"   ZenRows WSS: {zenrows_wss[:60]}...")
        
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(zenrows_wss, timeout=30000)
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            await context.add_cookies(cookies)
            page = await context.new_page()

            # Restore full state (localStorage + IndexedDB/Firebase) before navigating
            await _load_full_state(context, page, session_dir)

            # Try to load target URL
            await page.goto(target_url, timeout=40000, wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)

            # Check if cookies worked or need rescue
            current_url = page.url
            body_text = await _safe_text(page, 500)

            if "/login" in current_url or "/auth" in current_url or "Log in" in body_text:
                # Step 1: Try Firebase silent refresh (no credentials needed)
                print("   🔄 Cookies stale — trying Firebase silent refresh first...")
                if await _refresh_firebase_token(page):
                    await _save_full_state(context, page, session_dir)
                    await page.goto(target_url, timeout=40000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(2000)
                    print(f"\n✅ Session revived via Firebase refresh at: {page.url}")
                else:
                    # Step 2: Full rescue with credentials
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
                # Proactively refresh Firebase token + save full state while we're here
                await _refresh_firebase_token(page)
                await _save_full_state(context, page, session_dir)
            
            print("\n🌐 Browser session active. Press Ctrl+C to close.")
            
            # Keep browser open
            try:
                await asyncio.sleep(36000)  # 10 hours
            except KeyboardInterrupt:
                print("\n⚠️  Closing browser...")
            
            await browser.close()
            return True
    
    elif use_kernel:
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

            # Restore full state (localStorage + IndexedDB/Firebase) before navigating
            await _load_full_state(context, page, session_dir)

            # Try to load target URL
            await page.goto(target_url, timeout=40000, wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)

            # Check if cookies worked or need rescue
            current_url = page.url
            body_text = await _safe_text(page, 500)

            if "/login" in current_url or "/auth" in current_url or "Log in" in body_text:
                # Step 1: Try Firebase silent refresh (no credentials needed)
                print("   🔄 Cookies stale — trying Firebase silent refresh first...")
                if await _refresh_firebase_token(page):
                    await _save_full_state(context, page, session_dir)
                    await page.goto(target_url, timeout=40000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(2000)
                    print(f"\n✅ Session revived via Firebase refresh at: {page.url}")
                else:
                    # Step 2: Full rescue with credentials
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
                # Proactively refresh Firebase token + save full state while we're here
                await _refresh_firebase_token(page)
                await _save_full_state(context, page, session_dir)
            
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

            # Restore full state (localStorage + IndexedDB/Firebase) before navigating
            await _load_full_state(context, page, session_dir)

            # Try to load target URL
            await page.goto(target_url, timeout=40000, wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)

            # Check if cookies worked or need rescue
            current_url = page.url
            body_text = await _safe_text(page, 500)

            if "/login" in current_url or "/auth" in current_url or "Log in" in body_text:
                # Step 1: Try Firebase silent refresh (no credentials needed)
                print("   🔄 Cookies stale — trying Firebase silent refresh first...")
                if await _refresh_firebase_token(page):
                    await _save_full_state(context, page, session_dir)
                    await page.goto(target_url, timeout=40000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(2000)
                    print(f"\n✅ Session revived via Firebase refresh at: {page.url}")
                else:
                    # Step 2: Full rescue with credentials
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
                # Proactively refresh Firebase token + save full state while we're here
                await _refresh_firebase_token(page)
                await _save_full_state(context, page, session_dir)
            
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
    parser.add_argument("--zenrows", action="store_true", help="Use ZenRows CDP browser")
    
    args = parser.parse_args()
    
    headless = not args.headed
    
    try:
        success = asyncio.run(load_session(args.session, args.url, headless, args.kernel, args.zenrows))
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
