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

from patchright.async_api import async_playwright, expect, TimeoutError as PlaywrightTimeout

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

ACTION_TIMEOUT = 30_000
EMAIL_TIMEOUT = 300_000


# ============================================================================
# DISPOSE.LOL INBOX - SCRAPING APPROACH (PROVEN WORKING)
# ============================================================================
class DisposeLolInbox:
    """
    Dispose.lol Gmail inbox using HTML scraping
    Based on working test_dispose_inbox.py
    
    FIXED: Uses separate browser page for dispose.lol to avoid navigating Railway page
    """
    
    BASE_URL = "https://dispose.lol"
    
    def __init__(self, context):
        """
        Args:
            context: Playwright browser context (to create separate pages)
        """
        self.context = context
        self.dispose_page = None  # Separate page for dispose.lol operations
        self.railway_page = None  # Reference to Railway page (set externally)
        self.address = None
        self.session_initialized = False
    
    async def _ensure_session(self):
        """Load dispose.lol to initialize session on separate page"""
        if not self.session_initialized:
            print("🌐 Initializing dispose.lol session...")
            
            # Create separate page for dispose.lol if not exists
            if not self.dispose_page:
                self.dispose_page = await self.context.new_page()
                print("  ✅ Created separate dispose.lol page")
            
            await self.dispose_page.goto(self.BASE_URL, wait_until="load", timeout=60000)
            await self.dispose_page.wait_for_timeout(3000)
            self.session_initialized = True
            print("✅ Session initialized")
    
    async def create(self):
        """
        Create dispose.lol Gmail address by scraping page
        Returns: Gmail address (e.g., "user123@gmail.com")
        """
        print("\n📧 Creating dispose.lol Gmail...")
        await self._ensure_session()
        
        print("  🔍 Scraping email address...")
        
        # Get page content and find @gmail.com address
        try:
            content = await self.dispose_page.content()
            import re
            gmail_match = re.search(r'\b[a-zA-Z0-9._%+-]+@gmail\.com\b', content)
            
            if gmail_match:
                self.address = gmail_match.group(0)
                print(f"✅ Mailbox ready: {self.address}")
                return self.address
            else:
                raise Exception("No @gmail.com address found on page")
                
        except Exception as e:
            print(f"❌ Failed to scrape email: {e}")
            raise
    
    async def wait_for_railway_code(self, timeout_seconds=300):
        """
        Poll dispose.lol inbox for Railway OTP by scraping HTML
        
        FIXED: Uses separate dispose_page, does NOT navigate Railway page
        
        Args:
            timeout_seconds: Max time to wait for OTP
            
        Returns:
            str: 6-digit OTP code
        """
        print("\n📥 Waiting for Railway OTP...")
        pattern = re.compile(r'\b(\d{6})\b')
        deadline = time.time() + timeout_seconds
        check_count = 0
        
        # Ensure dispose page is ready
        await self._ensure_session()
        
        print("  ✅ Using separate dispose.lol page (Railway page stays untouched)")
        
        while time.time() < deadline:
            check_count += 1
            
            # Navigate dispose_page ONLY (Railway page stays on OTP modal)
            await self.dispose_page.goto(self.BASE_URL, wait_until="load")
            await self.dispose_page.wait_for_timeout(2000)
            
            # Scrape messages using aria-label selector
            # Format: <button aria-label="View 312925 is your Railway login code">
            message_buttons = await self.dispose_page.locator('button[aria-label^="View "]').all()
            
            if check_count % 10 == 1:
                print(f"  Check #{check_count}: {len(message_buttons)} message(s)")
            
            for button in message_buttons:
                aria_label = await button.get_attribute('aria-label')
                
                if aria_label and 'railway' in aria_label.lower():
                    # Extract subject: "View 312925 is your Railway login code" -> "312925 is your Railway login code"
                    subject = aria_label.replace('View ', '')
                    print(f"  ✅ Found Railway message: {subject}")
                    
                    # Extract 6-digit OTP
                    match = pattern.search(subject)
                    if match:
                        otp = match.group(1)
                        print(f"  🎯 Extracted OTP: {otp}")
                        
                        # DON'T navigate Railway page - just return OTP
                        # Railway page is still on OTP modal, ready for input
                        print(f"  ✅ Railway page untouched - ready for OTP entry")
                        
                        return otp
            
            await asyncio.sleep(3)
        
        raise TimeoutError(f"Railway OTP not received within {timeout_seconds}s")
    
    async def close(self):
        """Close dispose.lol page"""
        if self.dispose_page:
            await self.dispose_page.close()
            print("✅ Closed dispose.lol page")


# ============================================================================
# WARP IP ROTATION
# ============================================================================
def _warp_proxy_alive():
    """Check warp-cli WarpProxy 40000 is Connected and SOCKS5 alive"""
    try:
        r = subprocess.run(["warp-cli", "status"], capture_output=True, text=True, timeout=5)
        if "Connected" not in r.stdout:
            return False
        import socket
        with socket.create_connection(("127.0.0.1", 40000), timeout=2):
            return True
    except:
        return False

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
        # try to start warp-cli
        r = subprocess.run(["warp-cli", "connect"], capture_output=True, text=True, timeout=30)
        time.sleep(3)
        if _warp_proxy_alive():
            print("✅ WARP started WarpProxy on 127.0.0.1:40000")
            return True
        # legacy wg-quick fallback
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
    
    # Navigate to Railway login
    await page.goto(RAILWAY_LOGIN, wait_until="domcontentloaded")
    await page.wait_for_load_state("networkidle", timeout=15000)
    
    # Click "Log in using email"
    email_btn = page.get_by_role("button", name="Log in using email", exact=True)
    await expect(email_btn).to_be_visible(timeout=10000)
    await expect(email_btn).to_be_enabled(timeout=10000)
    await email_btn.click()
    print("✓ Clicked 'Log in using email'")
    
    await page.wait_for_timeout(2000)
    
    # Fill email
    email_input = page.get_by_placeholder("hello@email.com")
    await expect(email_input).to_be_visible(timeout=15000)
    await email_input.fill(mailbox.address)
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
    
    # Solve Turnstile if present - passive mode for WARP (per RAILWAY_AUTOMATION.md)
    # WARP proxy IPs often auto-validate; ClickSolver fails with "success element does not exist" on this site,
    # so we use passive polling directly - proven working method.
    if turnstile_exists:
        print("🤖 Turnstile detected - using passive wait (WARP proxy auto-validate)...")
        print("  ℹ️  Skipping ClickSolver (fails on this WARP IP), will poll Continue button directly")
        # Optional single manual click attempt on iframe checkbox if present (fast, no solver)
        try:
            iframe = page.locator('iframe[src*="challenges.cloudflare.com"]')
            if await iframe.count() > 0:
                # Try quick click on the Turnstile widget area to trigger validation
                box = await iframe.first.bounding_box()
                if box:
                    await page.mouse.click(box["x"] + box["width"]/2, box["y"] + box["height"]/2)
                    print("  ✅ Clicked Turnstile widget center")
        except:
            pass
        print("⏳ Waiting for Turnstile validation...")
        await page.wait_for_timeout(3000)
        print("⏳ Fast polling Continue button (every 0.5s, max 180s) - per docs...")
    else:
        print("✓ No visible Turnstile")
    
    # Wait for Continue button and click - passive polling 180s via fast poll
    continue_btn = page.get_by_role("button", name="Continue with Email", exact=True)
    print("⏳ Waiting for Continue button to enable...")
    
    try:
        # Use fast polling instead of single expect to handle Turnstile delay
        for poll in range(240):  # 120s /0.5
            try:
                if await continue_btn.is_enabled(timeout=1000):
                    print(f"✅ Button enabled! (poll {poll+1}) Clicking NOW...")
                    await page.wait_for_timeout(500)
                    await continue_btn.click(timeout=5000)
                    print("✅ Clicked 'Continue with Email'")
                    break
            except:
                pass
            await page.wait_for_timeout(500)
            if poll % 10 == 0 and poll > 0:
                print(f"  ... still waiting {poll*0.5:.0f}s")
        else:
            # fallback single expect 60s
            await expect(continue_btn).to_be_enabled(timeout=60000)
            print("✅ Button enabled!")
            await page.wait_for_timeout(1000)
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
        await page.wait_for_url("**/dashboard**", timeout=30000)
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
                # verify isolation: warp=on via proxy, warp=off direct
                import urllib.request, json as _j
                try:
                    import socket
                    with socket.create_connection(("127.0.0.1", 40000), timeout=2):
                        print("✅ WARP proxy 127.0.0.1:40000 alive (browser-only, other apps not affected)")
                except:
                    print("⚠️  Proxy port 40000 not reachable, continuing direct")
                    use_warp = False
        
        print("\n🚀 Launching browser...")
        # Initialize browser - ONLY browser uses proxy, system/direct stays warp=off
        # CRITICAL: use socks4 for railway.com (socks5 fails with ERR_SOCKS_CONNECTION_FAILED code 5 due IPv6 NAT64)
        async with async_playwright() as p:
            proxy_settings = {"server": "socks4://127.0.0.1:40000", "bypass": "127.0.0.1,localhost"} if use_warp else None
            if proxy_settings:
                print(f"🌐 Browser proxy: {proxy_settings['server']} bypass={proxy_settings['bypass']} (isolated, socks4 for railway.com compat)")
            browser = await p.chromium.launch(
                headless=False,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled'
                ]
            )
            context = await browser.new_context(proxy=proxy_settings)
            context.set_default_timeout(ACTION_TIMEOUT)
            page = await context.new_page()
            # verify egress inside browser
            try:
                await page.goto("https://cloudflare.com/cdn-cgi/trace", timeout=10000)
                body = await page.content()
                if "warp=on" in body:
                    print("✅ Browser egress warp=on verified (isolated tunnel)")
                    # grab ip for log
                    for l in body.splitlines():
                        if l.startswith("ip=") or l.startswith("warp="):
                            print(f"  {l.strip()}")
                else:
                    print("⚠️  Browser egress not via WARP")
                await page.goto("about:blank")
            except Exception as e:
                print(f"⚠️  Egress check failed: {e}")
            
            print("✅ Browser ready")
            
            # Create dispose.lol mailbox (pass context, not page)
            mailbox = DisposeLolInbox(context=context)
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
