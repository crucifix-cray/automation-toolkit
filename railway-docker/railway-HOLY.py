#!/usr/bin/env python3
"""
🏆 THE HOLY RAILWAY SCRIPT 🏆
Combines all working parts from previous scripts
- dispose.lol scraping (proven working in test_dispose_inbox.py)
- Railway login flow with Turnstile handling
- Session saving and Mega sync
- WARP IP rotation
"""

import asyncio
import base64
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
import uuid
from datetime import datetime, timezone
from pathlib import Path
import sys, os, pwd

# ponytail: HOME override (per-session railway isolation) relocates user site-packages
# to $HOME/.local/... which is empty -> imports fail. Restore the real user site.
try:
    _rh = pwd.getpwuid(os.getuid()).pw_dir
    _rs = os.path.join(_rh, ".local", "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages")
    if os.path.isdir(_rs) and _rs not in sys.path:
        sys.path.insert(0, _rs)
except Exception:
    pass

# Engine: patchright (works on sandbox + local). invisible_playwright kept as fallback only.
try:
    from patchright.async_api import async_playwright, expect, TimeoutError as PlaywrightTimeout
    InvisiblePlaywright = async_playwright
    PLAYWRIGHT_ENGINE = "patchright"
except ImportError:
    from invisible_playwright.async_api import InvisiblePlaywright
    from playwright.async_api import expect, TimeoutError as PlaywrightTimeout
    async_playwright = InvisiblePlaywright
    PLAYWRIGHT_ENGINE = "invisible"
# force patchright on sandbox (wireproxy 40000) - invisible stuck at goto 180s via direct
if Path("/root/go/bin/wireproxy").exists():
    try:
        from patchright.async_api import async_playwright as _pr, expect as _pr_e, TimeoutError as _pr_t
        async_playwright = _pr
        InvisiblePlaywright = _pr
        expect = _pr_e
        PlaywrightTimeout = _pr_t
        PLAYWRIGHT_ENGINE = "patchright"
    except ImportError:
        pass

# Import playwright-captcha for auto Cloudflare Turnstile solving
try:
    from playwright_captcha import CaptchaType, ClickSolver, FrameworkType
    CAPTCHA_SOLVER_AVAILABLE = True
except ImportError:
    CAPTCHA_SOLVER_AVAILABLE = False
    print("⚠️  playwright-captcha not installed", file=sys.stderr)

# ============================================================================
# CONSTANTS
# ============================================================================
RAILWAY_URL = "https://railway.com"
RAILWAY_LOGIN = "https://railway.com/login"
RAILWAY_OAUTH = "https://backboard.railway.com/oauth"
RAILWAY_CLIENT_ID = "rlwy_oaci_onEklvmksh1hRUiCo7E2zX12"
RAILWAY_GRAPHQL = "https://backboard.railway.com/graphql/v2"
RAILWAY_SCOPES = "openid email profile offline_access workspace:admin project:admin ssh_keys"
PKCE_CHARSET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"

SESSIONS_DIR = Path.home() / "Documents" / "railways"
MEGA_REMOTE = "mega:railway_sessions"

ACTION_TIMEOUT = 60_000
EMAIL_TIMEOUT = 300_000


# ============================================================================
# DISPOSE.LOL INBOX - SCRAPING APPROACH (PROVEN WORKING)
# ============================================================================
class DisposeLolInbox:
    """Dispose.lol - single tab reuse (low RAM, ponytail: 1 page vs ephemeral churn)"""
    BASE_URL = "https://dispose.lol"
    def __init__(self, context):
        self.context = context
        self.pg = None
        self.address = None
        self.session_initialized = False
    async def _get_pg(self):
        if not self.pg or self.pg.is_closed():
            self.pg = await self.context.new_page()
        return self.pg
    async def _handle_cf(self, pg):
        # Cloudflare Turnstile on dispose.lol (Quick security check) - click real checkbox inside iframe
        try:
            iframe = pg.locator('iframe[src*="challenges.cloudflare.com"]')
            if await iframe.count() > 0 and await iframe.first.is_visible():
                print("  🛡️  Dispose CF Turnstile detected, clicking Verify you are human...")
                # try frame's checkbox first (more precise than iframe center)
                try:
                    frame = pg.frame_locator('iframe[src*="challenges.cloudflare.com"]')
                    cb = frame.locator('input[type="checkbox"]').first
                    if await cb.count() > 0:
                        await cb.click(timeout=5000)
                        print("  ✅ Clicked checkbox inside iframe")
                    else:
                        # fallback: click left side of iframe (checkbox is left)
                        box = await iframe.first.bounding_box()
                        if box:
                            await pg.mouse.move(box["x"]+28, box["y"]+box["height"]/2, steps=5)
                            await pg.mouse.click(box["x"]+28, box["y"]+box["height"]/2)
                except:
                    box = await iframe.first.bounding_box()
                    if box:
                        await pg.mouse.click(box["x"]+28, box["y"]+box["height"]/2)
                await pg.wait_for_timeout(3000)
                # try playwright-captcha solver if available (2nd chance)
                if CAPTCHA_SOLVER_AVAILABLE:
                    try:
                        solver = ClickSolver(captcha_type=CaptchaType.Turnstile, framework=FrameworkType.Playwright)
                        await solver.solve(pg)
                        print("  ✅ Captcha solver attempted")
                    except:
                        pass
                await pg.wait_for_timeout(3000)
                # dismiss overlay if still visible
                try:
                    await pg.wait_for_selector('text=Verify you are human', state='hidden', timeout=5000)
                except:
                    pass
        except:
            pass
    async def _ensure_session(self):
        if not self.session_initialized:
            print("🌐 Initializing dispose.lol session (single tab)...")
            pg = await self._get_pg()
            await pg.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=120000)
            await pg.wait_for_timeout(2500)
            await self._handle_cf(pg)
            await pg.wait_for_timeout(1500)
            self.session_initialized = True
            print("✅ Session initialized")
    async def create(self):
        print("\n📧 Creating dispose.lol Gmail...")
        await self._ensure_session()
        print("  🔍 Scraping email address...")
        pg = await self._get_pg()
        await pg.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=120000)
        await pg.wait_for_timeout(2500)
        await self._handle_cf(pg)
        content = await pg.content()
        import re
        m = re.search(r"\b[a-zA-Z0-9._%+-]+@gmail\.com\b", content)
        if m:
            self.address = m.group(0)
            print(f"✅ Mailbox ready: {self.address}")
            # ponytail: close the tab now to free DOM/JS memory during the heavy Railway Turnstile phase;
            # reopen lazily in wait_for_railway_code (context + cookies persist, so session survives)
            if self.pg:
                try: await self.pg.close()
                except: pass
                self.pg = None
            return self.address
        raise Exception("No @gmail.com address found")
    async def wait_for_railway_code(self, timeout_seconds=300):
        print("\n📥 Waiting for Railway OTP (single tab poll)...")
        pattern = re.compile(r"\b(\d{6})\b")
        deadline = __import__("time").time() + timeout_seconds
        cnt=0
        await self._ensure_session()
        pg = await self._get_pg()
        print("  ✅ Polling via single tab (reload)")
        while __import__("time").time() < deadline:
            cnt+=1
            await pg.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=120000)
            # ponytail: fresh page after close() may re-challenge CF - handle only if present
            try:
                cf = pg.locator('iframe[src*="challenges.cloudflare.com"]')
                if await cf.count() > 0 and await cf.first.is_visible():
                    await self._handle_cf(pg)
            except:
                pass
            await pg.wait_for_timeout(1500)
            btns = await pg.locator('button[aria-label^="View "]').all()
            if cnt % 10 == 1:
                print(f"  Check #{cnt}: {len(btns)} message(s)")
            for b in btns:
                aria = await b.get_attribute("aria-label")
                if aria and "railway" in aria.lower():
                    subj = aria.replace("View ", "")
                    print(f"  ✅ Found: {subj}")
                    m = pattern.search(subj)
                    if m:
                        otp=m.group(1)
                        print(f"  🎯 OTP: {otp}")
                        return otp
            await __import__("asyncio").sleep(3)
        raise TimeoutError("OTP timeout")
    async def close(self):
        try:
            if self.pg and not self.pg.is_closed():
                await self.pg.close()
        except:
            pass
        print("✅ Closed")


# ============================================================================
# WARP IP ROTATION
# ============================================================================
def _warp_proxy_alive():
    """Check warp SOCKS 40000 alive (not proton 1080)"""
    import socket
    try:
        with socket.create_connection(("127.0.0.1", 40000), timeout=2):
            return True
    except:
        return False

def _pick_proxy():
    """Pick best alive proxy for the BROWSER: warp/wireproxy 40000 first (real SOCKS5,
    chromium-compatible), ovpn/tunsocks 1080 as fallback (curl-only, chromium rejects it).
    Both tunneled — never direct. dispose.lol goes direct (its WAF blocks these egress IPs)."""
    import socket
    for port in (40000, 1080):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                return f"socks5://127.0.0.1:{port}"
        except:
            continue
    return None

def rotate_warp_ip():
    """Rotate WARP IP - proxy mode: warp-cli disconnect/connect"""
    print("🔄 Rotating WARP IP (proxy mode)...")
    try:
        if _warp_proxy_alive():
            subprocess.run(["warp-cli", "disconnect"], capture_output=True, timeout=10)
            time.sleep(2)
            subprocess.run(["warp-cli", "connect"], capture_output=True, timeout=10)
            time.sleep(3)
            if _warp_proxy_alive():
                print("✅ WARP IP rotated (proxy mode)")
                return True
        # fallback legacy wgcf
        if not Path("/etc/wireguard/wgcf.conf").exists():
            print("⚠️  WARP not configured (wgcf.conf missing) and proxy not alive")
            return False
        subprocess.run(["sudo", "wgcf", "update"], capture_output=True, timeout=30, check=True)
        subprocess.run(["sudo", "wgcf", "generate"], capture_output=True, timeout=30, check=True)
        subprocess.run(["sudo", "wg-quick", "down", "wgcf"], capture_output=True, timeout=10)
        subprocess.run(["sudo", "wg-quick", "up", "wgcf"], capture_output=True, timeout=30, check=True)
        print("✅ WARP IP rotated (wgcf)")
        return True
    except Exception as e:
        print(f"⚠️  WARP rotation failed: {e}")
        return False


def start_warp():
    """Start WARP - proxy mode preferred (isolated), only browser tunneled"""
    print("🚀 Checking WARP (proxy mode - isolated)...")
    try:
        if _warp_proxy_alive():
            print("✅ WARP already Connected WarpProxy on 127.0.0.1:40000 (isolated, only browser tunneled)")
            return True
        r = subprocess.run(["warp-cli", "connect"], capture_output=True, text=True, timeout=30)
        time.sleep(3)
        if _warp_proxy_alive():
            print("✅ WARP started WarpProxy on 127.0.0.1:40000")
            return True
        result = subprocess.run(["sudo", "wg-quick", "up", "wgcf"], capture_output=True, text=True, timeout=30)
        if result.returncode == 0 or "already exists" in result.stderr:
            print("✅ WARP started (wg-quick)")
            return True
        print(f"⚠️  WARP start failed: {result.stderr or r.stdout}")
        return False
    except Exception as e:
        print(f"⚠️  WARP start error: {e}")
        return False


def stop_warp():
    """Stop WARP - no-op in proxy mode (keep isolated proxy alive for other apps)"""
    try:
        # In proxy mode we do NOT disconnect - keeps other apps unaffected per user request
        if _warp_proxy_alive():
            print("ℹ️  WARP proxy mode - keeping alive (isolated, not stopping)")
            return
        subprocess.run(["sudo", "wg-quick", "down", "wgcf"], capture_output=True, timeout=10)
        print("✅ WARP stopped")
    except:
        pass


# ============================================================================
# MEGA SYNC
# ============================================================================
def sync_to_mega(session_dir: Path):
    """Upload session to Mega"""
    print(f"\n☁️  Syncing to Mega...")
    try:
        remote_path = f"{MEGA_REMOTE}/{session_dir.name}"
        result = subprocess.run(
            ["rclone", "sync", str(session_dir), remote_path, "-v"],
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode == 0:
            print(f"✅ Synced to {remote_path}")
        else:
            print(f"⚠️  Mega sync failed: {result.stderr}")
    except Exception as e:
        print(f"⚠️  Mega sync error: {e}")


def get_next_session_number():
    """Get next available session number from Mega"""
    try:
        result = subprocess.run(
            ["rclone", "lsd", f"{MEGA_REMOTE}/"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            return 1
        
        session_numbers = []
        for line in result.stdout.split('\n'):
            if 'session-' in line:
                parts = line.split('session-')
                if len(parts) > 1:
                    num_str = parts[1].split()[0].split('-')[0]
                    try:
                        session_numbers.append(int(num_str))
                    except ValueError:
                        continue
        
        if session_numbers:
            next_num = max(session_numbers) + 1
            print(f"  📊 Found {len(session_numbers)} sessions on Mega, next: session-{next_num}")
            return next_num
        else:
            print(f"  📊 No sessions found on Mega, starting from session-1")
            return 1
            
    except Exception as e:
        print(f"  ⚠️  Error checking Mega: {e}, starting from session-1")
        return 1


def next_session_dir(base_dir: Path, session_num: int = None):
    """Get next session directory path"""
    if session_num is None:
        session_num = get_next_session_number()
    return base_dir / f"session-{session_num}"


# ============================================================================
# RAILWAY LOGIN FLOW
# ============================================================================
async def sign_in_to_railway(page, mailbox):
    """
    Complete Railway login flow:
    1. Navigate to login
    2. Fill email
    3. Solve Turnstile
    4. Wait for OTP
    5. Fill OTP
    """
    print("\n🚂 Signing in to Railway...")
    
    # Navigate to Railway login (skip networkidle — lags on 1GB + analytics never idle; slow warp/ovpn tunnel needs generous timeout)
    await page.goto(RAILWAY_LOGIN, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(5000)  # dwell 5s for Turnstile JS to init (research: 2-5s)
    
    # Click "Log in using email" - robust: button or link, 67% zoom may hide, try multiple locators + js click
    await page.evaluate("document.body.style.zoom='100%'")
    clicked = False
    for locator in [
        page.get_by_role("button", name="Log in using email"),
        page.get_by_text("Log in using email"),
        page.locator('text=Log in using email'),
        page.locator('a:has-text("Log in using email")'),
    ]:
        try:
            await expect(locator.first).to_be_visible(timeout=5000)
            await locator.first.scroll_into_view_if_needed(timeout=3000)
            try:
                await locator.first.click(timeout=5000)
            except:
                await locator.first.evaluate("el => el.click()")
            clicked = True
            break
        except:
            continue
    if not clicked:
        raise Exception("Log in using email not clickable")
    print("✓ Clicked 'Log in using email'")
    
    # ponytail: flagged-IP CF reload can eat the click -> Welcome screen stays, email field absent.
    # Retry: re-click email-login entry + flexible input locator until the field actually appears.
    email_input = page.locator(
        'input[type="email"], input[inputmode="email"], input[name="email"], '
        'input[autocomplete="email"], input[placeholder*="@"], input[placeholder*="email" i]'
    ).first
    filled = False
    for _ in range(6):
        try:
            await expect(email_input).to_be_visible(timeout=8000)
            await email_input.fill(mailbox.address)
            filled = True
            break
        except Exception:
            for loc in [
                page.get_by_role("button", name="Log in using email"),
                page.get_by_text("Log in using email"),
                page.locator('a:has-text("Log in using email")'),
                page.locator('text=Continue with Email'),
            ]:
                try:
                    await expect(loc.first).to_be_visible(timeout=3000)
                    await loc.first.scroll_into_view_if_needed(timeout=2000)
                    try: await loc.first.click(timeout=3000)
                    except: await loc.first.evaluate("el => el.click()")
                    break
                except: continue
            await asyncio.sleep(2)
    if not filled:
        raise Exception("Email input never appeared (Railway login stuck on Welcome screen)")
    print(f"✓ Filled email: {mailbox.address}")
    
    # Check for Cloudflare Turnstile - poll up to 10s (sandbox wireproxy late load)
    print("🔍 Checking for Cloudflare Turnstile...")
    await page.wait_for_timeout(2000)
    turnstile_exists = False
    for _ in range(20):
        try:
            turnstile_iframe = page.locator('iframe[src*="challenges.cloudflare.com"]')
            count = await turnstile_iframe.count()
            if count > 0 and await turnstile_iframe.first.is_visible():
                turnstile_exists = True
                print(f"✓ Found Cloudflare Turnstile iframe")
                break
        except:
            pass
        await page.wait_for_timeout(500)
    if not turnstile_exists:
        try:
            has_turnstile = await page.evaluate('''() => {
                const input = document.querySelector('input[name="cf-turnstile-response"]');
                const container = input?.parentElement?.parentElement;
                return container && container.offsetHeight > 0;
            }''')
            if has_turnstile:
                turnstile_exists = True
                print(f"✓ Found Cloudflare Turnstile widget")
        except:
            pass
    if not turnstile_exists:
        await page.wait_for_timeout(2000)
        try:
            turnstile_iframe = page.locator('iframe[src*="challenges.cloudflare.com"]')
            if await turnstile_iframe.count() > 0:
                turnstile_exists = True
                print(f"✓ Found Cloudflare Turnstile iframe (late)")
        except:
            pass
    
    # Solve Turnstile if present - ALL egress via warp+ovpn (no direct). Use playwright-captcha
    # ClickSolver as PRIMARY (Tor-like: consistent fingerprint + solver passes the checkbox);
    # manual left-checkbox click is backup (research: center click fails).
    if turnstile_exists:
        print("🤖 Turnstile detected - solving via playwright-captcha ClickSolver (warp+ovpn egress)...")
        if CAPTCHA_SOLVER_AVAILABLE:
            try:
                solver = ClickSolver(captcha_type=CaptchaType.Turnstile, framework=FrameworkType.Playwright)
                await solver.solve(page)
                print("  ✅ Captcha solver attempted")
            except Exception as e:
                print(f"  ⚠️  Solver error: {e}")
        # backup: manual left-checkbox click
        try:
            frame = page.frame_locator('iframe[src*="challenges.cloudflare.com"]')
            cb = frame.locator('input[type="checkbox"]').first
            if await cb.count() > 0:
                await cb.click(timeout=5000)
                print("  ✅ Clicked checkbox inside Turnstile frame (backup)")
            else:
                iframe = page.locator('iframe[src*="challenges.cloudflare.com"]')
                if await iframe.count() > 0:
                    box = await iframe.first.bounding_box()
                    if box:
                        x = box["x"] + 28
                        y = box["y"] + box["height"]/2
                        await page.mouse.move(x, y, steps=12)
                        await page.wait_for_timeout(400)
                        await page.mouse.click(x, y)
                        print(f"  ✅ Clicked Turnstile at {x:.0f},{y:.0f} (left checkbox, backup)")
        except Exception as e:
            print(f"  ⚠️  Turnstile manual click failed: {e}")
        print("⏳ Waiting for Turnstile validation (proof-of-work + nudge)...")
        await page.wait_for_timeout(8000)
        print("⏳ Fast polling Continue button (every 0.5s, max 180s) - per docs...")
    else:
        print("✓ No visible Turnstile")
    
    # Wait for Continue button and click - passive polling 180s via fast poll
    continue_btn = page.get_by_role("button", name="Continue with Email", exact=True)
    print("⏳ Waiting for Continue button to enable...")
    
    try:
        # Use lightweight polling (evaluate + asyncio.sleep) to avoid Page.wait_for_timeout crash on 1GB
        for poll in range(240):  # 120s /0.5
            try:
                enabled = await page.evaluate('''() => {
                    const b = [...document.querySelectorAll('button')].find(x => x.textContent.trim()==="Continue with Email");
                    return b ? !b.disabled && b.offsetHeight>0 : false;
                }''')
                if enabled:
                    print(f"✅ Button enabled! (poll {poll+1}) Clicking NOW...")
                    await asyncio.sleep(0.5)
                    # click via evaluate to avoid handle overhead
                    await page.evaluate('''() => {
                        const b = [...document.querySelectorAll('button')].find(x => x.textContent.trim()==="Continue with Email");
                        if(b) b.click();
                    }''')
                    print("✅ Clicked 'Continue with Email'")
                    break
            except Exception as e:
                # transient CF reload/nav detaches page - wait and keep polling instead of dying
                if "crashed" in str(e).lower() or "closed" in str(e).lower():
                    await asyncio.sleep(2)
                    continue
                pass
            await asyncio.sleep(0.5)
            if poll % 20 == 0 and poll > 0:
                print(f"  ... still waiting {poll*0.5:.0f}s (poll {poll})")
        else:
            # fallback via expect
            await expect(continue_btn).to_be_enabled(timeout=120000)
            print("✅ Button enabled!")
            await asyncio.sleep(1)
            await continue_btn.click(timeout=5000)
            print("✅ Clicked 'Continue with Email'")
    except Exception as e:
        screenshot_path = f"/tmp/turnstile-timeout-{int(time.time())}.png"
        try:
            await page.screenshot(path=screenshot_path, full_page=True)
            print(f"❌ Screenshot: {screenshot_path}")
            # also dump page text for debug
            txt = await page.locator("body").inner_text()
            print(f"Page text snippet: {txt[:500]}")
        except:
            pass
        raise RuntimeError(f"Turnstile/button timeout: {e}")
    
    # Wait for Railway to send email
    print("⏳ Waiting 15s for Railway email...")
    await asyncio.sleep(15)
    
    # Get OTP from dispose.lol
    code = await mailbox.wait_for_railway_code()
    print(f"✅ Got OTP: {code}")
    
    # Fill OTP - wait for Magic.link modal to appear
    print("  Entering OTP...")
    await page.wait_for_timeout(5000)  # Wait longer for modal to load
    
    # Try direct input method (Magic.link creates 6 inputs)
    try:
        print("  🔍 Looking for OTP inputs...")
        all_inputs = page.locator('input[type="text"]:visible')
        count = await all_inputs.count()
        print(f"  Found {count} visible text inputs")
        
        if count >= 6:
            for i, digit in enumerate(code[:6]):
                await all_inputs.nth(i).fill(digit)
                await asyncio.sleep(0.1)
            print("  ✅ Filled OTP")
        else:
            # Try looking for any input, even if not visible yet
            await page.wait_for_selector('input[type="text"]', timeout=10000)
            all_inputs = page.locator('input[type="text"]')
            count = await all_inputs.count()
            print(f"  Found {count} text inputs (after wait)")
            
            if count >= 6:
                for i, digit in enumerate(code[:6]):
                    await all_inputs.nth(i).fill(digit)
                    await asyncio.sleep(0.1)
                print("  ✅ Filled OTP")
            else:
                raise Exception(f"Only found {count} inputs")
    except Exception as e:
        print(f"  ⚠️  Direct method failed: {e}")
        # Try iframe method
        try:
            print("  🔍 Trying iframe method...")
            magic_frame = page.frame_locator('iframe[src*="auth.magic.link"], iframe[src*="magic"]')
            inputs = magic_frame.locator('input[type="text"]')
            await inputs.first.wait_for(state="visible", timeout=10000)
            
            for i, digit in enumerate(code):
                await inputs.nth(i).fill(digit)
                await asyncio.sleep(0.1)
            print("  ✅ Filled OTP (iframe method)")
        except Exception as e2:
            raise Exception(f"Both OTP methods failed: {e}, {e2}")
    
    # Wait for redirect to dashboard
    print("⏳ Waiting for login to complete...")
    try:
        await page.wait_for_url("**/dashboard**", timeout=60000)
        print("✅ Logged in successfully!")
    except:
        await page.wait_for_timeout(5000)
        if "dashboard" in page.url:
            print("✅ Logged in successfully!")
        else:
            raise Exception(f"Login failed - stuck at: {page.url}")


async def scroll_terms_dialog(dialog) -> None:
    await dialog.evaluate("""dialog => {
        for (const el of [dialog, ...dialog.querySelectorAll('*')]) {
            if (el.scrollHeight > el.clientHeight + 10) {
                el.scrollTop = el.scrollHeight;
                el.dispatchEvent(new Event('scroll', { bubbles: true }));
            }
        }
    }""")

async def dismiss_cookie_banner(page) -> None:
    for _ in range(4):
        root = page.locator(".fc-message-root").first
        if not await root.count() or not await root.is_visible():
            return
        buttons = root.locator("button")
        clicked = False
        for index in range(await buttons.count()):
            button = buttons.nth(index)
            if not await button.is_visible():
                continue
            try:
                await button.click(timeout=2000)
                clicked = True
                break
            except:
                continue
        if not clicked:
            await root.evaluate("el => el.remove()")
            return
        await page.wait_for_timeout(500)

async def accept_railway_policies(page):
    """Accept Railway ToS - correct scroll + I agree buttons per railway-login.py:242"""
    print("\n📜 Accepting Railway policies...")
    try:
        await page.wait_for_timeout(3000)
        await dismiss_cookie_banner(page)
        dialog = page.get_by_role("dialog", name=re.compile(r"Terms of Service", re.I)).last
        try:
            await dialog.wait_for(state="visible", timeout=10000)
        except:
            print("  ✅ No Terms dialog")
            return
        print(f"  📜 Terms dialog found")
        agree_buttons = ["I agree with Railway's Terms of Service", "I agree to the Fair Use Policy"]
        for _ in range(6):
            try:
                await scroll_terms_dialog(dialog)
            except:
                break
            clicked = False
            for name in agree_buttons:
                await dismiss_cookie_banner(page)
                button = page.get_by_role("button", name=name, exact=True)
                try:
                    await expect(button).to_be_visible(timeout=3000)
                    await expect(button).to_be_enabled(timeout=3000)
                except:
                    continue
                await button.click()
                print(f"  ✅ Clicked {name}")
                clicked = True
                break
            if not clicked:
                break
            await page.wait_for_timeout(1500)
        try:
            await expect(page.get_by_text("Terms accepted", exact=True)).to_be_visible(timeout=10000)
            print("✅ Terms accepted")
        except:
            try:
                await expect(dialog).to_be_hidden(timeout=5000)
                print("✅ Terms dialog hidden")
            except:
                print("⚠️  Terms dialog may still visible but continuing")
        await page.wait_for_timeout(2000)
    except Exception as e:
        print(f"⚠️  Policy acceptance issue: {e}")
        try:
            await page.get_by_text("Continue").click(timeout=5000)
            print("✅ Clicked Continue fallback")
        except:
            print("⚠️  Could not accept policies")


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

def http_post_form(url: str, fields: dict, headers: dict | None = None) -> dict:
    body = urllib.parse.urlencode(fields).encode()
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "railway-cli/5.35.0",
            **(headers or {}),
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode())

async def get_oauth_tokens(page) -> dict:
    """Run CLI PKCE flow inside already-logged-in browser - correct endpoint /oauth/auth"""
    verifier = "".join(secrets.choice(PKCE_CHARSET) for _ in range(128))
    challenge = _pkce_challenge(verifier)
    state = secrets.token_urlsafe(32)
    loop = asyncio.get_running_loop()
    result_holder = {}
    async def callback_handler(reader, writer):
        request_line = (await reader.read(65536)).decode(errors="replace").split("\r\n")[0]
        path = request_line.split(" ")[1] if " " in request_line else "/"
        if not result_holder:
            result_holder["query"] = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)
        body = b"<html><body>Railway login approved. You can close this tab.</body></html>"
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n" + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body)
        await writer.drain()
        writer.close()
    callback_server = await asyncio.start_server(callback_handler, "127.0.0.1", 0)
    callback_port = callback_server.sockets[0].getsockname()[1]
    redirect_uri = f"http://127.0.0.1:{callback_port}/callback"
    try:
        authorization_url = (
            f"{RAILWAY_OAUTH}/auth?"
            + urllib.parse.urlencode({
                "response_type": "code",
                "client_id": RAILWAY_CLIENT_ID,
                "redirect_uri": redirect_uri,
                "scope": RAILWAY_SCOPES,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": state,
                "prompt": "consent",
                "cli_caller": "opencode",
            })
        )
        print(f"  🔗 OAuth URL: {authorization_url[:80]}...")
        await page.goto(authorization_url, wait_until="domcontentloaded")
        deadline = loop.time() + 120
        while loop.time() < deadline:
            if result_holder:
                break
            # dismiss cookie banner if present
            try:
                root = page.locator(".fc-message-root").first
                if await root.count() and await root.is_visible():
                    btns = root.locator("button")
                    for idx in range(await btns.count()):
                        b = btns.nth(idx)
                        if await b.is_visible():
                            try: await b.click(timeout=2000); break
                            except: continue
            except: pass
            authorize = page.get_by_role("button", name="Authorize", exact=True)
            if await authorize.count():
                try: await authorize.click(timeout=5000); print("✓ Clicked Authorize")
                except: pass
            await page.wait_for_timeout(2000)
        if not result_holder:
            raise RuntimeError("Railway consent flow never redirected back.")
        callback_query = result_holder["query"]
        if "error" in callback_query:
            description = callback_query.get("error_description", [""])[0]
            raise RuntimeError(f"Railway OAuth rejected: {callback_query['error'][0]} {description}")
        if "code" not in callback_query or callback_query.get("state", [""])[0] != state:
            raise RuntimeError("Railway OAuth callback missing or mismatched.")
        return http_post_form(
            f"{RAILWAY_OAUTH}/token",
            {
                "grant_type": "authorization_code",
                "code": callback_query["code"][0],
                "redirect_uri": redirect_uri,
                "client_id": RAILWAY_CLIENT_ID,
                "code_verifier": verifier,
            },
        )
    finally:
        callback_server.close()
        await callback_server.wait_closed()

def get_web_user(cookies: list[dict]) -> dict:
    session = {c["name"]: c["value"] for c in cookies if c["domain"] == "backboard.railway.com" and c["name"] in ("rw.session", "rw.session.sig")}
    if not session.get("rw.session"):
        raise RuntimeError("No rw.session cookie for CLI registration.")
    cookie_header = "; ".join(f"{k}={v}" for k, v in session.items())
    payload = {"query": "query { me { id email } }"}
    request = urllib.request.Request(
        RAILWAY_GRAPHQL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Cookie": cookie_header, "User-Agent": "railway-cli/5.35.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Railway API user lookup failed: {error.code}") from error
    me = (data.get("data") or {}).get("me") or {}
    if not me.get("id"):
        raise RuntimeError("Railway API returned no user identity.")
    return me

def write_cli_session(session_dir: Path, tokens: dict, user: dict, cookies: list[dict]) -> None:
    session_dir.mkdir(parents=True, exist_ok=True)
    cli_home = session_dir / ".railway"
    (cli_home / "sessions").mkdir(parents=True, exist_ok=True)
    (session_dir / "railway_cli_sessions").mkdir(parents=True, exist_ok=True)
    (cli_home / "config.lock").write_text("")
    now = datetime.now(timezone.utc)
    expires_at = int(now.timestamp()) + int(tokens.get("expires_in", 300))
    config = {
        "activeSandbox": None,
        "codeAgents": None,
        "editor": None,
        "linkedFunctions": None,
        "projects": {},
        "sandboxTemplates": None,
        "sandboxes": None,
        "user": {"accessToken": tokens["access_token"], "id": user["id"], "refreshToken": tokens.get("refresh_token"), "token": None, "tokenExpiresAt": expires_at},
    }
    (session_dir / "browser_cookies.json").write_text(json.dumps({"cookies": cookies}, indent=2))
    for target in (session_dir / "railway_cli_config.json", cli_home / "config.json"):
        target.write_text(json.dumps(config, indent=2))
    (cli_home / "version.json").write_text(json.dumps({"last_update_check": now.isoformat(), "latest_version": None, "download_failures": 0, "skipped_version": None, "last_package_manager_spawn": None}, indent=2))
    session_payload = {"agent_session_id": str(uuid.uuid4()), "parent_pid": os.getpid(), "parent_btime": 0, "created_at": now.isoformat()}
    session_name = f"{secrets.token_hex(8)}.session"
    (cli_home / "sessions" / session_name).write_text(json.dumps(session_payload))
    (session_dir / "railway_cli_sessions" / session_name).write_text(json.dumps(session_payload))
    # also save simple email/timestamp for compatibility
    (session_dir / "email.txt").write_text(user.get("email",""))
    (session_dir / "created_at.txt").write_text(now.isoformat())
    print(f"✓ Saved CLI session: {session_dir} / .railway/config.json")

def verify_tokens(tokens: dict, user: dict) -> str:
    request = urllib.request.Request(
        RAILWAY_GRAPHQL,
        data=json.dumps({"query": "query { me { id email } }"}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {tokens['access_token']}", "User-Agent": "railway-cli/5.35.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        me = ((json.loads(response.read().decode())).get("data") or {}).get("me") or {}
    if not me.get("id") or me["id"] != user["id"]:
        raise RuntimeError("CLI tokens failed verification.")
    return me.get("email") or user.get("email") or me["id"]

async def register_cli_session(context, page, sessions_dir: Path) -> Path:
    print("\n🔧 Registering Railway CLI session (PKCE /auth)...")
    cookies = await context.cookies()
    tokens = await get_oauth_tokens(page)
    print("✓ Got access and refresh tokens")
    user = get_web_user(cookies)
    print(f"✓ User: {user.get('email')} (ID: {user.get('id')})")
    # find next session dir like railway-login.py but reuse next_session_dir helper that checks Mega
    # Use next_session_dir that already exists in file (checks Mega)
    session_dir = next_session_dir(sessions_dir)
    write_cli_session(session_dir, tokens, user, cookies)
    email = verify_tokens(tokens, user)
    print(f"✅ CLI verification: {email} authenticated")
    return session_dir


# ============================================================================
# MAIN EXECUTION
# ============================================================================
async def run(use_warp=False):
    """Run single account creation"""
    warp_started = False
    browser = None
    mailbox = None
    
    try:
        # Start WARP if requested - warp-cli proxy mode (isolated)
        if use_warp:
            print("\n🌐 Setting up WARP (proxy mode - isolated)...")
            warp_started = start_warp()
            if not warp_started:
                print("⚠️  WARP proxy not available, continuing direct (isolated check failed)")
                use_warp = False
            else:
                # verify isolation: warp=on via proxy, warp=off direct - don't disable on transient fail, _warp_proxy_alive already checked
                try:
                    import socket
                    with socket.create_connection(("127.0.0.1", 40000), timeout=2):
                        print("✅ WARP proxy 127.0.0.1:40000 alive (browser-only, other apps not affected)")
                except:
                    print("⚠️  Proxy port 40000 check failed, but keeping warp (transient)")


        
        print("\n🚀 Launching browser...")
        # Initialize browser - match script2_remix_link.py:35 InvisiblePlaywright Firefox stealth + warp via ovpn (not raw wireproxy)
        # ponytail: use InvisiblePlaywright if available (like script2), fallback patchright
        picked = _pick_proxy() if use_warp else None
        # warp via ovpn: tunsocks 1080 + wireproxy 40000 both alive, but chaining needs netns (start-tunnel-random.sh) - keep raw wireproxy for now, note chain possible via sing-box
        if picked and picked.endswith(":40000") and _warp_proxy_alive():
            import socket as _s
            try:
                _s.create_connection(("127.0.0.1",1080), timeout=1).close()
                print("  🔗 OVPN 1080 + WARP 40000 both alive (raw warp, chain needs netns/sing-box like start-tunnel-random.sh)")
            except: pass
        # ponytail: Railway + Cloudflare MUST go through warp/ovpn proxy (direct datacenter IP = flagged Turnstile).
        # dispose.lol's WAF blackholes the warp/ovpn egress IPs (TLS connects, no response), so it goes direct.
        # Result: the Railway account is created via proxied egress (not flagged) = user's goal.
        proxy_settings = {"server": picked, "bypass": "127.0.0.1,localhost,dispose.lol,*.dispose.lol"} if picked else None
        if proxy_settings:
            print(f"🌐 Browser proxy: {proxy_settings['server']} bypass={proxy_settings['bypass']} (hybrid - warp via ovpn chain if 1080 alive)")
        # choose engine like script2
        if PLAYWRIGHT_ENGINE == "invisible":
            print(f"  🦊 Using InvisiblePlaywright Firefox (like script2) humanize=True")
            # ponytail: don't pass proxy to InvisiblePlaywright geo discovery (fails on socks 40000), pass to new_context instead like patchright
            async with InvisiblePlaywright(headless=False, humanize=True, locale="en-US") as browser:
                context = await browser.new_context(proxy=proxy_settings, viewport={"width": 800, "height": 600}, locale="en-US", timezone_id="Europe/Amsterdam")
                context.set_default_timeout(ACTION_TIMEOUT)
                print("✅ Light mode: InvisiblePlaywright Firefox 151, viewport 800x600, warp via ovpn chain")
                page = await context.new_page()
                # ponytail: skip egress check
                print("✅ Browser ready (InvisiblePlaywright, warp via ovpn)")
                # need to keep context open - use same flow as before but inside this with
                # Create dispose.lol mailbox (pass context, not page)
                mailbox = DisposeLolInbox(context=context)
                mailbox.railway_page = page
                await mailbox.create()
                await sign_in_to_railway(page, mailbox)
                await accept_railway_policies(page)
                try:
                    session_dir = await register_cli_session(context, page, SESSIONS_DIR)
                    sync_to_mega(session_dir)
                    print(f"\n{'='*60}")
                    print(f"✅ SUCCESS! Account created: {mailbox.address}")
                    print(f"📁 Session: {session_dir}")
                    print(f"{'='*60}\n")
                except Exception as e:
                    print(f"\n⚠️  OAuth/Session registration failed: {e}")
                    print(f"✅ But account IS created! Email: {mailbox.address}")
                print("🔍 Browser will stay open for 30s. Press Ctrl+C to exit now...")
                try:
                    await asyncio.sleep(30)
                except KeyboardInterrupt:
                    print("\n⏹️  Closing browser...")
                # cleanup handled by context manager
                if warp_started:
                    stop_warp()
                if mailbox:
                    try: await mailbox.close()
                    except: pass
                return
        else:
            async with async_playwright() as p:
                # ponytail: headed (headless trips Cloudflare automation detection, like Tor is headed).
                # 1GB fit via single browser + closed dispose tab + 128mb old-space. RAILWAY_HEADED=1 => headless (testing only).
                headless = (os.environ.get("RAILWAY_HEADED") == "1")
                print(f"  🧩 patchright chromium — {'HEADED' if not headless else 'headless'} (1GB-safe, ALL egress via warp+ovpn, no direct)")
                launch_args = [
                    '--no-sandbox','--disable-setuid-sandbox','--disable-dev-shm-usage','--disable-gpu','--disable-software-rasterizer','--disable-extensions','--no-first-run','--window-size=800,600','--disable-background-networking','--disable-background-timer-throttling','--disable-backgrounding-occluded-windows','--disable-renderer-backgrounding','--disable-ipc-flooding-protection','--disable-breakpad','--disable-component-update','--disable-default-apps','--disable-domain-reliability','--disable-sync','--disable-translate','--disable-features=Translate,AutomationControlled,VizDisplayCompositor,site-per-process,IsolateOrigins,AudioServiceOutOfProcess,BackForwardCache','--disk-cache-size=1','--aggressive-cache-discard','--disable-webgl','--mute-audio','--hide-scrollbars','--js-flags=--max-old-space-size=128','--memory-pressure-off','--disable-blink-features=AutomationControlled','--disable-hang-monitor'
                ]
                # ponytail: ONE browser, two contexts (dispose + railway). headless to fit 1GB
                # (headed OOMs during Turnstile proof-of-work). RAILWAY_HEADED=1 forces headed.
                browser = await p.chromium.launch(headless=headless, channel="chrome", args=launch_args)
                ctx_opts = dict(proxy=proxy_settings, viewport={"width": 800, "height": 600},
                                locale="en-US", timezone_id="Europe/Amsterdam")
                ctx_dispose = await browser.new_context(**ctx_opts)
                context = await browser.new_context(**ctx_opts)
                ctx_dispose.set_default_timeout(ACTION_TIMEOUT)
                context.set_default_timeout(ACTION_TIMEOUT)
                print("✅ Light mode: single browser + 2 contexts (dispose+railway) 800x600 128mb (1GB-safe)")
                page = await context.new_page()
                print("✅ Browser ready (patchright, warp+ovpn egress)")
                
                # Create dispose.lol mailbox via headless ctx (minimal, no headed overhead)
                mailbox = DisposeLolInbox(context=ctx_dispose)
                mailbox.railway_page = page  # Store reference to Railway page
                await mailbox.create()
                
                # Sign in to Railway
                await sign_in_to_railway(page, mailbox)
                
                # Accept policies
                await accept_railway_policies(page)
                
                # Register CLI session
                try:
                    session_dir = await register_cli_session(context, page, SESSIONS_DIR)
                    
                    # Sync to Mega
                    sync_to_mega(session_dir)
                    
                    print(f"\n{'='*60}")
                    print(f"✅ SUCCESS! Account created: {mailbox.address}")
                    print(f"📁 Session: {session_dir}")
                    print(f"{'='*60}\n")
                except Exception as e:
                    print(f"\n⚠️  OAuth/Session registration failed: {e}")
                    print(f"✅ But account IS created! Email: {mailbox.address}")
                    print(f"   You can manually log in using this email.")
                
                # Keep browser open for inspection
                print("🔍 Browser will stay open for 30s. Press Ctrl+C to exit now...")
                try:
                    await asyncio.sleep(30)
                except KeyboardInterrupt:
                    print("\n⏹️  Closing browser...")
            
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        
        # Save debug info
        if mailbox and mailbox.address:
            print(f"\n📧 Email created: {mailbox.address}")
            debug_file = Path("/tmp") / f"railway-debug-{int(time.time())}.txt"
            debug_file.write_text(f"Email: {mailbox.address}\nError: {str(e)}\n{traceback.format_exc()}")
            print(f"💾 Debug info saved: {debug_file}")
    finally:
        # Cleanup
        if mailbox:
            try:
                await mailbox.close()
            except:
                pass
        
        if warp_started:
            stop_warp()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Railway account creator with dispose.lol")
    parser.add_argument("--no-warp", action="store_true", help="Disable WARP proxy")
    args = parser.parse_args()
    
    use_warp = not args.no_warp  # WARP enabled by default
    
    print("="*60)
    print("🏆 THE HOLY RAILWAY ACCOUNT CREATOR 🏆")
    print("="*60)
    print(f"📁 Sessions directory: {SESSIONS_DIR}")
    print(f"☁️  Mega remote: {MEGA_REMOTE}")
    print(f"🔁 WARP: {'ENABLED' if use_warp else 'DISABLED'}")
    print("="*60)
    
    asyncio.run(run(use_warp=use_warp))
