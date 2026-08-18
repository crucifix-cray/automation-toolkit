#!/usr/bin/env python3
"""
Railway CLI Account Creator - Mail.tm Edition
Complete implementation with OAuth, ToS acceptance, and CLI session registration
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
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
from patchright.async_api import async_playwright, expect, TimeoutError as PlaywrightTimeout

# Import playwright-captcha for auto Cloudflare Turnstile solving
try:
    from playwright_captcha import CaptchaType, ClickSolver, FrameworkType
    CAPTCHA_SOLVER_AVAILABLE = True
except ImportError:
    CAPTCHA_SOLVER_AVAILABLE = False
    print("⚠️  playwright-captcha not installed", file=sys.stderr)

# Constants
MAIL_TM_API = "https://api.mail.tm"
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


def get_next_session_number():
    """Get next available session number by checking Mega"""
    try:
        # List all session directories on Mega
        result = subprocess.run(
            ["rclone", "lsd", f"{MEGA_REMOTE}/"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            print("  ⚠️  Could not check Mega, starting from session-1")
            return 1
        
        # Parse session numbers from output
        session_numbers = []
        for line in result.stdout.split('\n'):
            if 'session-' in line:
                # Extract session number from "session-N" or "session-N-bridge"
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
            print("  📊 No sessions found on Mega, starting from session-1")
            return 1
            
    except Exception as e:
        print(f"  ⚠️  Error checking Mega: {e}, starting from session-1")
        return 1


def next_session_dir(base_dir: Path, session_num: int = None):
    """Get next session directory path"""
    if session_num is None:
        session_num = get_next_session_number()
    
    return base_dir / f"session-{session_num}"


class DisposeLolInbox:
    """Dispose.lol Gmail - scrape page instead of API"""
    
    def __init__(self, page=None):
        self.page = page  # Use SAME page as Railway (will navigate to dispose.lol)
        self.address = None
        self.session_initialized = False
        self.BASE_URL = "https://dispose.lol"
    
    async def _ensure_page(self):
        """Load dispose.lol page"""
        if not self.page:
            raise Exception("No page provided")
        
        if not self.session_initialized:
            await self.page.goto(self.BASE_URL, wait_until="load", timeout=60000)
            await self.page.wait_for_timeout(3000)
            self.session_initialized = True
    
    async def create(self):
        """Get dispose.lol Gmail by scraping page"""
        print("📧 Creating dispose.lol Gmail...")
        await self._ensure_page()
        
        # Scrape address from page
        address_elem = self.page.locator('[aria-labelledby="mail-address-heading"] p').first
        self.address = await address_elem.text_content()
        self.address = self.address.strip()
        
        print(f"✅ Mailbox ready: {self.address}")
        return self.address
    
    async def wait_for_railway_code(self, timeout_seconds=300):
        """Poll for Railway OTP by scraping dispose.lol page"""
        print("📥 Waiting for Railway OTP...")
        pattern = re.compile(r'\b(\d{6})\b')
        deadline = time.time() + timeout_seconds
        check_count = 0
        
        # Store current Railway URL to return to it later
        railway_url = self.page.url
        
        while time.time() < deadline:
            check_count += 1
            
            # Navigate to dispose.lol inbox to check messages
            await self.page.goto(self.BASE_URL, wait_until="load")
            await self.page.wait_for_timeout(2000)
            
            # Scrape messages from HTML using aria-label (has full subject)
            message_buttons = await self.page.locator('button[aria-label^="View "]').all()
            
            if check_count % 10 == 1:
                print(f"  Check #{check_count}: {len(message_buttons)} message(s)")
            
            for button in message_buttons:
                aria_label = await button.get_attribute('aria-label')
                
                if aria_label and 'railway' in aria_label.lower():
                    # Extract subject: "View 312925 is your Railway login code" -> "312925 is your Railway login code"
                    subject = aria_label.replace('View ', '')
                    print(f"  ✅ Found Railway message: {subject}")
                    
                    match = pattern.search(subject)
                    if match:
                        otp = match.group(1)
                        print(f"  🎯 Extracted OTP: {otp}")
                        
                        # Navigate back to Railway before returning
                        print(f"  🔙 Returning to Railway...")
                        await self.page.goto(railway_url, wait_until="load")
                        await self.page.wait_for_timeout(2000)
                        
                        return otp
            
            await asyncio.sleep(3)
        
        raise TimeoutError("Railway OTP not received")
    
    async def close(self):
        """Nothing to close - using shared page"""
        pass


async def dismiss_cookie_banner(page):
    """Dismiss cookie/survey banners"""
    try:
        osano = page.locator('[role="dialog"][aria-label*="Cookie"]').first
        if await osano.count() > 0 and await osano.is_visible():
            reject_btn = osano.locator('button.osano-cm-denyAll, button:has-text("Reject")').first
            if await reject_btn.count() > 0:
                await reject_btn.click(timeout=3000)
                await page.wait_for_timeout(500)
    except:
        pass


async def sign_in_to_railway(page, mailbox: DisposeLolInbox):
    """Sign in to Railway with email"""
    print("\n🚂 Signing in to Railway...")
    
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
    
    # Check if Cloudflare Turnstile appears and solve it
    print("🔍 Checking for Cloudflare Turnstile...")
    await page.wait_for_timeout(2000)  # Wait for Turnstile to load
    
    # Check if Turnstile iframe exists (indicates visible checkbox mode)
    turnstile_exists = False
    try:
        turnstile_iframe = page.locator('iframe[src*="challenges.cloudflare.com"]')
        count = await turnstile_iframe.count()
        if count > 0:
            turnstile_exists = True
            print(f"✓ Found Cloudflare Turnstile iframe")
    except:
        pass
    
    # Also check for the turnstile container div
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
    
    if turnstile_exists and CAPTCHA_SOLVER_AVAILABLE:
        print("🤖 Auto-solving Cloudflare Turnstile checkbox...")
        try:
            async with ClickSolver(
                framework=FrameworkType.PATCHRIGHT,
                page=page,
                max_attempts=1,  # Only try once, then fall back to waiting
                attempt_delay=2
            ) as solver:
                await solver.solve_captcha(
                    captcha_container=page,
                    captcha_type=CaptchaType.CLOUDFLARE_TURNSTILE
                )
            print("✅ Turnstile checkbox clicked and validated!")
            
        except Exception as e:
            # The solver may click the checkbox but fail to detect success
            # This is OK - we'll wait for the button to enable
            print(f"⚠️  ClickSolver error (checkbox may still be clicked): {str(e)[:100]}", file=sys.stderr)
            print("✅ Checkbox likely clicked, continuing...", file=sys.stderr)
        
        # Always wait for Cloudflare to process, even if solver had error
        print("⏳ Waiting for Turnstile to validate...")
        await page.wait_for_timeout(3000)
            
    elif turnstile_exists and not CAPTCHA_SOLVER_AVAILABLE:
        print("⚠️  Turnstile detected but solver not available - waiting for manual click")
    else:
        print("✓ No visible Turnstile - using invisible mode")
    
    # Wait for Continue button to enable
    continue_btn = page.get_by_role("button", name="Continue with Email", exact=True)
    print("⏳ Waiting for Continue button to enable...")
    
    try:
        await expect(continue_btn).to_be_enabled(timeout=60000)  # 60 seconds
        print("✅ Button enabled!")
        await page.wait_for_timeout(1000)
        await continue_btn.click(timeout=5000)
        print("✅ Clicked 'Continue with Email'")
    except:
        # Take screenshot before failing
        screenshot_path = f"/tmp/turnstile-timeout-{int(time.time())}.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        print(f"❌ Screenshot saved: {screenshot_path}")
        raise RuntimeError(f"Turnstile/button timeout - check {screenshot_path}")
    
    # Wait for Railway to send email
    print("⏳ Waiting 15s for Railway to send email...")
    await asyncio.sleep(15)
    
    # Get OTP from mailbox
    code = await mailbox.wait_for_railway_code()
    print(f"✅ Got OTP: {code}")
    
    # Fill OTP - wait for Magic.link modal/iframe
    print("  Entering OTP...")
    
    # Wait a bit for the modal/iframe to load
    await page.wait_for_timeout(3000)
    
    otp_filled = False
    
    # Method 1: Direct modal (no iframe)
    try:
        # Look for any visible text inputs (Magic.link creates 6 inputs)
        all_inputs = page.locator('input[type="text"]:visible')
        count = await all_inputs.count()
        print(f"  DEBUG: Found {count} visible text inputs")
        
        if count >= 6:
            # Fill the first 6
            for i, digit in enumerate(code[:6]):
                await all_inputs.nth(i).fill(digit)
                await asyncio.sleep(0.1)
            print("  ✅ Filled OTP (method 1)")
            otp_filled = True
    except Exception as e:
        print(f"  Method 1 failed: {e}")
    
    # Method 2: Look for iframe with Magic.link
    if not otp_filled:
        try:
            # Wait for Magic.link iframe
            await page.wait_for_selector('iframe[src*="auth.magic.link"], iframe[src*="magic"]', timeout=10000)
            magic_frame = page.frame_locator('iframe[src*="auth.magic.link"], iframe[src*="magic"]')
            inputs = magic_frame.locator('input[type="text"]')
            
            await inputs.first.wait_for(state="visible", timeout=5000)
            
            for i, digit in enumerate(code):
                await inputs.nth(i).fill(digit)
                await asyncio.sleep(0.1)
            print("  ✅ Filled OTP (method 2 - iframe)")
            otp_filled = True
        except Exception as e:
            print(f"  Method 2 failed: {e}")
    
    # Method 3: Look for inputs with inputmode="numeric"
    if not otp_filled:
        try:
            inputs = page.locator('input[inputmode="numeric"]:visible, input[inputmode="text"]:visible')
            count = await inputs.count()
            print(f"  DEBUG: Found {count} numeric/text inputs")
            
            if count >= 6:
                for i, digit in enumerate(code[:6]):
                    await inputs.nth(i).fill(digit)
                    await asyncio.sleep(0.1)
                print("  ✅ Filled OTP (method 3)")
                otp_filled = True
        except Exception as e:
            print(f"  Method 3 failed: {e}")
    
    if not otp_filled:
        # Take screenshot for debugging
        await page.screenshot(path="/tmp/railway_otp_failure.png")
        print("  Screenshot saved to /tmp/railway_otp_failure.png")
        raise RuntimeError("Could not find OTP inputs")
    
    # Wait for dashboard
    await expect(page).to_have_url(re.compile(r"/dashboard(?:/|$)"), timeout=EMAIL_TIMEOUT)
    print("✅ Logged in to dashboard")


async def accept_railway_policies(page):
    """Accept ToS"""
    print("\n📜 Accepting Terms of Service...")
    await page.wait_for_timeout(2000)
    await dismiss_cookie_banner(page)
    
    dialog = page.get_by_role("dialog", name=re.compile(r"Terms of Service", re.I)).last
    try:
        await dialog.wait_for(state="visible", timeout=ACTION_TIMEOUT)
    except:
        print("✓ No ToS dialog (already accepted)")
        return
    
    # Scroll and click agreements
    for iteration in range(6):
        await dismiss_cookie_banner(page)
        
        try:
            await dialog.evaluate("""dialog => {
                for (const el of [dialog, ...dialog.querySelectorAll('*')]) {
                    if (el.scrollHeight > el.clientHeight + 10) {
                        el.scrollTop = el.scrollHeight;
                        el.dispatchEvent(new Event('scroll', { bubbles: true }));
                    }
                }
            }""")
        except:
            break
        
        await dismiss_cookie_banner(page)
        
        for name in ["I agree with Railway's Terms of Service", "I agree to the Fair Use Policy"]:
            await dismiss_cookie_banner(page)
            button = page.get_by_role("button", name=name, exact=True)
            try:
                await expect(button).to_be_visible(timeout=3000)
                await expect(button).to_be_enabled(timeout=3000)
                await button.click(timeout=5000)
                print(f"  ✅ Clicked: {name}")
                break
            except:
                continue
        
        await page.wait_for_timeout(1500)
    
    print("✅ ToS accepted")


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


async def get_oauth_tokens(page) -> dict:
    """Get Railway OAuth tokens via PKCE flow"""
    print("\n🔐 Getting OAuth tokens...")
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
        body = b"<html><body>Railway login approved. Close this tab.</body></html>"
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n" + 
                    f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body)
        await writer.drain()
        writer.close()
    
    callback_server = await asyncio.start_server(callback_handler, "127.0.0.1", 0)
    callback_port = callback_server.sockets[0].getsockname()[1]
    redirect_uri = f"http://127.0.0.1:{callback_port}/callback"
    
    try:
        authorization_url = f"{RAILWAY_OAUTH}/auth?" + urllib.parse.urlencode({
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
        
        await page.goto(authorization_url, wait_until="domcontentloaded")
        
        deadline = loop.time() + 120
        while loop.time() < deadline:
            if result_holder:
                break
            await dismiss_cookie_banner(page)
            authorize = page.get_by_role("button", name="Authorize", exact=True)
            if await authorize.count():
                try:
                    await authorize.click(timeout=5000)
                    print("  Clicked 'Authorize' button")
                except:
                    pass
            await page.wait_for_timeout(2000)
        
        if not result_holder:
            raise RuntimeError("OAuth callback never received")
        
        callback_query = result_holder["query"]
        
        # Check for errors
        if "error" in callback_query:
            description = callback_query.get("error_description", [""])[0]
            raise RuntimeError(f"OAuth error: {callback_query['error'][0]} {description}")
        
        if "code" not in callback_query or callback_query.get("state", [""])[0] != state:
            raise RuntimeError("OAuth callback missing code or state mismatch")
        
        # Exchange code for tokens using the http_post_form pattern
        body = urllib.parse.urlencode({
            "grant_type": "authorization_code",
            "code": callback_query["code"][0],
            "redirect_uri": redirect_uri,
            "client_id": RAILWAY_CLIENT_ID,
            "code_verifier": verifier,
        }).encode()
        
        request = urllib.request.Request(
            f"{RAILWAY_OAUTH}/token",
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "railway-cli/5.35.0",
            }
        )
        
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                tokens = json.loads(response.read().decode())
            print("✅ OAuth tokens received")
            return tokens
        except urllib.error.HTTPError as error:
            error_body = error.read().decode()
            print(f"  ERROR: HTTP {error.code}")
            print(f"  Response: {error_body}")
            raise RuntimeError(f"Token exchange failed: HTTP {error.code} - {error_body}")
        
    finally:
        callback_server.close()
        await callback_server.wait_closed()


def get_web_user(cookies: list[dict]) -> dict:
    """Get user info from Railway API"""
    print("  Getting user info from Railway API...")
    
    session = {c["name"]: c["value"] for c in cookies 
               if c["domain"] == "backboard.railway.com" and c["name"] in ("rw.session", "rw.session.sig")}
    
    if not session.get("rw.session"):
        print(f"  ERROR: No rw.session cookie found")
        print(f"  Available cookies for backboard.railway.com:")
        for c in cookies:
            if "railway" in c["domain"]:
                print(f"    {c['domain']}: {c['name']}")
        raise RuntimeError("No rw.session cookie found")
    
    cookie_header = "; ".join(f"{k}={v}" for k, v in session.items())
    request = urllib.request.Request(RAILWAY_GRAPHQL, 
                                    data=json.dumps({"query": "query { me { id email } }"}).encode(),
                                    headers={
                                        "Content-Type": "application/json",
                                        "Cookie": cookie_header,
                                        "User-Agent": "railway-cli/5.35.0",
                                    })
    
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode())
        
        me = (data.get("data") or {}).get("me") or {}
        if not me.get("id"):
            print(f"  ERROR: No user identity in response")
            print(f"  Response: {json.dumps(data, indent=2)}")
            raise RuntimeError("No user identity from Railway API")
        
        print(f"  ✅ Got user: {me.get('email', me['id'])}")
        return me
        
    except urllib.error.HTTPError as error:
        error_body = error.read().decode()
        print(f"  ERROR: HTTP {error.code}")
        print(f"  Response: {error_body}")
        raise RuntimeError(f"Railway API user lookup failed: {error.code} - {error_body}")


def next_session_dir(railway_dir: Path) -> Path:
    highest = 0
    for candidate in railway_dir.glob("session-*"):
        try:
            num = int(candidate.name.split("-")[-1])
            highest = max(highest, num)
        except:
            continue
    return railway_dir / f"session-{highest + 1}"


def write_cli_session(session_dir: Path, tokens: dict, user: dict, cookies: list[dict]):
    """Write Railway CLI session files"""
    session_dir.mkdir(parents=True, exist_ok=True)
    cli_home = session_dir / ".railway"
    (cli_home / "sessions").mkdir(parents=True, exist_ok=True)
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
        "user": {
            "accessToken": tokens["access_token"],
            "id": user["id"],
            "refreshToken": tokens.get("refresh_token"),
            "token": None,
            "tokenExpiresAt": expires_at,
        },
    }
    
    (session_dir / "browser_cookies.json").write_text(json.dumps({"cookies": cookies}, indent=2))
    (session_dir / ".railway" / "config.json").write_text(json.dumps(config, indent=2))
    (session_dir / "railway_cli_config.json").write_text(json.dumps(config, indent=2))
    
    (cli_home / "version.json").write_text(json.dumps({
        "last_update_check": now.isoformat(),
        "latest_version": None,
        "download_failures": 0,
        "skipped_version": None,
        "last_package_manager_spawn": None,
    }, indent=2))
    
    session_payload = {
        "agent_session_id": str(uuid.uuid4()),
        "parent_pid": os.getpid(),
        "parent_btime": 0,
        "created_at": now.isoformat(),
    }
    session_name = f"{secrets.token_hex(8)}.session"
    (cli_home / "sessions" / session_name).write_text(json.dumps(session_payload))
    
    print(f"✅ CLI session written to {session_dir}")


async def register_cli_session(context, page, railway_dir: Path) -> Path:
    """Register complete Railway CLI session"""
    print("\n🔧 Registering Railway CLI session...")
    cookies = await context.cookies()
    tokens = await get_oauth_tokens(page)
    user = get_web_user(cookies)
    session_num = get_next_session_number()
    session_dir = next_session_dir(railway_dir, session_num)
    write_cli_session(session_dir, tokens, user, cookies)
    return session_dir


def sync_to_mega(session_dir: Path):
    """Sync session to Mega"""
    print(f"\n☁️  Syncing to Mega...")
    try:
        subprocess.run(["rclone", "copy", str(session_dir), f"{MEGA_REMOTE}/{session_dir.name}"], 
                      capture_output=True, timeout=120, check=True)
        print(f"✅ Synced to {MEGA_REMOTE}/{session_dir.name}")
    except:
        print("⚠️  Mega sync failed (non-fatal)")


def check_current_ip():
    """Get current public IP"""
    try:
        resp = requests.get("https://api.ipify.org", timeout=10)
        return resp.text.strip()
    except:
        return "unknown"


def rotate_warp_ip():
    """Rotate WARP IP by updating wgcf account"""
    print("\n🔄 Rotating WARP IP...")
    
    old_ip = check_current_ip()
    print(f"  Current IP: {old_ip}")
    
    try:
        # Run wgcf update in home directory where config exists
        result = subprocess.run(
            ["wgcf", "update"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(Path.home())
        )
        
        if result.returncode != 0:
            print(f"  ⚠️ wgcf update failed: {result.stderr.strip()}")
            return False
        
        # Regenerate profile
        result = subprocess.run(
            ["wgcf", "generate"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(Path.home())
        )
        
        if result.returncode != 0:
            print(f"  ⚠️ wgcf generate failed: {result.stderr.strip()}")
            return False
        
        print("  ✅ New WARP config generated")
        return True
        
    except Exception as e:
        print(f"  ⚠️ WARP rotation failed: {e}")
        return False


def start_warp():
    """Start WireGuard WARP interface or detect wireproxy"""
    print("\n🌐 Checking WARP...")
    
    # First check if wireproxy is running (Railway-compatible userspace proxy)
    try:
        result = subprocess.run(["pgrep", "-f", "wireproxy"], 
                              capture_output=True, timeout=2)
        if result.returncode == 0:
            print("  ✅ Wireproxy SOCKS5 detected (userspace WARP)")
            # Test SOCKS5 proxy
            try:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                sock.connect(("127.0.0.1", 40000))
                sock.close()
                print("  ✅ SOCKS5 proxy active at 127.0.0.1:40000")
                return True
            except:
                print("  ⚠️ Wireproxy running but SOCKS5 not responding")
                return False
    except:
        pass
    
    # Fall back to WireGuard interface (won't work in Railway but try anyway)
    # Check if running as root
    is_root = os.geteuid() == 0 if hasattr(os, 'geteuid') else False
    sudo_cmd = [] if is_root else ["sudo"]
    
    try:
        # Check if already running
        result = subprocess.run([*sudo_cmd, "wg", "show", "wgcf"], 
                              capture_output=True, timeout=5)
        if result.returncode == 0:
            print("  ℹ️  WARP already running, restarting...")
            subprocess.run([*sudo_cmd, "wg-quick", "down", "wgcf"], 
                         capture_output=True, timeout=10)
            time.sleep(1)
        
        # Start WireGuard
        result = subprocess.run(
            [*sudo_cmd, "wg-quick", "up", "wgcf"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(Path.home())
        )
        
        if result.returncode != 0:
            print(f"  ⚠️ WireGuard start failed: {result.stderr.strip()}")
            return False
        
        # Wait for connection to stabilize
        time.sleep(3)
        
        new_ip = check_current_ip()
        print(f"  ✅ WARP started - IP: {new_ip}")
        return True
        
    except Exception as e:
        print(f"  ⚠️ WARP start failed: {e}")
        return False


def stop_warp():
    """Stop WireGuard WARP interface"""
    print("\n🛑 Stopping WARP...")
    
    try:
        result = subprocess.run(
            ["sudo", "wg-quick", "down", "wgcf"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            print("  ✅ WARP stopped")
        else:
            print("  ℹ️  WARP already stopped")
        
        return True
        
    except Exception as e:
        print(f"  ⚠️ Failed to stop WARP: {e}")
        return False
    """Test Railway CLI"""
    print("\n🧪 Testing Railway CLI...")
    try:
        result = subprocess.run(["railway", "whoami"], cwd=str(session_dir), 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print(f"✅ Railway CLI test: {result.stdout.strip()}")
        else:
            print(f"⚠️  CLI test failed: {result.stderr.strip()}")
    except FileNotFoundError:
        print("⚠️  Railway CLI not found. Install: curl -fsSL https://railway.app/install.sh | sh")


async def run(use_warp=False):
    warp_started = False
    mailbox = None
    
    try:
        # Start WARP first if needed
        if use_warp:
            if rotate_warp_ip():
                warp_started = start_warp()
                if not warp_started:
                    print("⚠️  WARP failed to start, continuing with direct connection")
            else:
                print("⚠️  WARP rotation failed, using direct connection")
        
        async with async_playwright() as p:
            # Use lightweight Chromium
            browser = await p.chromium.launch(
                headless=False,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage'
                ]
            )
            context = await browser.new_context()
            context.set_default_timeout(ACTION_TIMEOUT)
            page = await context.new_page()
            
            # Create mailbox using SAME page
            mailbox = DisposeLolInbox(page=page)
            await mailbox.create()
            
            try:
                await sign_in_to_railway(page, mailbox)
                await accept_railway_policies(page)
                session_dir = await register_cli_session(context, page, SESSIONS_DIR)
                
                sync_to_mega(session_dir)
                test_railway_cli(session_dir)
                
                print(f"\n" + "="*50)
                print(f"✅ SUCCESS! Railway CLI session created")
                print(f"📁 Session: {session_dir}")
                print(f"📧 Email: {mailbox.address}")
                print(f"🔑 Password: {mailbox.password}")
                if use_warp:
                    print(f"🌐 Created with WARP IP: {check_current_ip()}")
                print(f"\nTo use this session:")
                print(f"  cd {session_dir}")
                print(f"  railway whoami")
                print("="*50)
                
                input("\n⏸️  Press Enter to close browser...")
                
            finally:
                await browser.close()
    
    finally:
        # Always stop WARP after script finishes
        if warp_started:
            stop_warp()


def test_railway_cli(session_dir: Path):
    """Test Railway CLI"""
    print("\n🧪 Testing Railway CLI...")
    try:
        result = subprocess.run(
            ["railway", "whoami"],
            cwd=str(session_dir),
            capture_output=True,
            text=True,
            timeout=10,
            env={**os.environ, "HOME": str(session_dir)}
        )
        if result.returncode == 0:
            print(f"✅ Railway CLI test: {result.stdout.strip()}")
        else:
            print(f"⚠️  CLI test failed: {result.stderr.strip()}")
    except FileNotFoundError:
        print("⚠️  Railway CLI not found. Install: curl -fsSL https://railway.app/install.sh | sh")


def check_stop_signal():
    """Check if stop.txt exists in Mega root"""
    try:
        result = subprocess.run(
            ["rclone", "ls", "mega:stop.txt"],
            capture_output=True,
            timeout=10
        )
        return result.returncode == 0  # True if file exists
    except:
        return False


def get_account_count():
    """Get current account count from Mega"""
    try:
        result = subprocess.run(
            ["rclone", "cat", f"{MEGA_REMOTE}/counter.txt"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
        return 0
    except:
        return 0


def increment_account_count():
    """Increment account counter in Mega"""
    try:
        count = get_account_count() + 1
        subprocess.run(
            ["rclone", "rcat", f"{MEGA_REMOTE}/counter.txt"],
            input=str(count).encode(),
            capture_output=True,
            timeout=10
        )
        return count
    except:
        return 0


def deploy_to_railway(session_dir: Path):
    """Deploy this script to new Railway account"""
    print("\n🚀 Deploying to new Railway account...")
    
    try:
        # Safety check: Don't deploy if we're at or near the limit
        current_count = get_account_count()
        if current_count >= 8000:
            print(f"  🛑 SAFETY LIMIT: {current_count} accounts reached, stopping deployment")
            return False
        
        # Check if railway CLI is available
        result = subprocess.run(["which", "railway"], capture_output=True, timeout=5)
        if result.returncode != 0:
            print("  ⚠️  Railway CLI not found, skipping deployment")
            return False
        
        # Create new project
        print("  Creating Railway project...")
        result = subprocess.run(
            ["railway", "init", "--name", f"farm-{int(time.time())}"],
            cwd=str(session_dir),
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "HOME": str(session_dir)}
        )
        
        if result.returncode != 0:
            print(f"  ⚠️  Project creation failed: {result.stderr}")
            return False
        
        print("  ✅ Project created")
        
        # Deploy Docker image (assumes we're in railway-docker directory)
        print("  Deploying Docker image...")
        docker_dir = Path(__file__).parent
        
        result = subprocess.run(
            ["railway", "up", "--detach"],
            cwd=str(docker_dir),
            capture_output=True,
            text=True,
            timeout=300,
            env={**os.environ, "HOME": str(session_dir)}
        )
        
        if result.returncode != 0:
            print(f"  ⚠️  Deployment failed: {result.stderr}")
            return False
        
        print("  ✅ Deployed successfully")
        return True
        
    except Exception as e:
        print(f"  ⚠️  Deployment error: {e}")
        return False


async def run_continuous(use_warp=False, max_accounts=8000, deploy_recursive=False):
    """Continuous account creation loop"""
    accounts_created = 0
    
    print("\n" + "="*60)
    print("🔁 CONTINUOUS MODE")
    print("="*60)
    print(f"Target: {max_accounts} accounts")
    print(f"Recursive deployment: {'✅ Enabled' if deploy_recursive else '❌ Disabled'}")
    print(f"Kill switch: Check mega:stop.txt")
    print("="*60 + "\n")
    
    while True:
        # Check stop signal
        if check_stop_signal():
            print("\n🛑 STOP SIGNAL DETECTED (mega:stop.txt exists)")
            print("   Gracefully shutting down...")
            break
        
        # Check account limit
        current_count = get_account_count()
        print(f"\n📊 Current account count: {current_count}/{max_accounts}")
        
        if current_count >= max_accounts:
            print(f"\n✅ TARGET REACHED! {current_count} accounts created")
            break
        
        # Create new account
        print(f"\n{'='*60}")
        print(f"🔄 Creating account #{accounts_created + 1} (Total: {current_count + 1}/{max_accounts})")
        print(f"{'='*60}\n")
        
        warp_started = False
        mailbox = None
        
        try:
            # Start WARP for this account first
            if use_warp:
                if rotate_warp_ip():
                    warp_started = start_warp()
                    if not warp_started:
                        print("⚠️  WARP failed, using direct connection")
            
            async with async_playwright() as p:
                # Use lightweight Chromium instead of Chrome for Testing
                browser = await p.chromium.launch(
                    headless=False,  # Use headed mode with VNC/Xvfb
                    args=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage',  # Required for Railway (small /dev/shm)
                        '--disable-accelerated-2d-canvas',
                        '--no-first-run',
                        '--no-zygote',
                        '--disable-gpu',
                        '--disable-software-rasterizer',
                        '--disable-extensions',
                        '--disable-background-networking',
                        '--disable-features=TranslateUI',
                        '--disable-ipc-flooding-protection',
                        '--disable-renderer-backgrounding'
                    ]
                )
                context = await browser.new_context()
                context.set_default_timeout(ACTION_TIMEOUT)
                page = await context.new_page()
                
                # Create mailbox using SAME page
                mailbox = DisposeLolInbox(page=page)
                await mailbox.create()
                
                try:
                    await sign_in_to_railway(page, mailbox)
                    await accept_railway_policies(page)
                    session_dir = await register_cli_session(context, page, SESSIONS_DIR)
                    
                    sync_to_mega(session_dir)
                    
                    # Increment counter
                    new_count = increment_account_count()
                    
                    print(f"\n✅ Account #{accounts_created + 1} created successfully!")
                    print(f"   Session: {session_dir.name}")
                    print(f"   Email: {mailbox.address}")
                    print(f"   Total: {new_count}/{max_accounts}")
                    
                    accounts_created += 1
                    
                    # Deploy recursively if enabled
                    if deploy_recursive and new_count < max_accounts:
                        print(f"\n🔁 Attempting recursive deployment...")
                        if deploy_to_railway(session_dir):
                            print(f"   ✅ Deployed to new account - it will create more accounts")
                        else:
                            print(f"   ⚠️  Deployment failed, will continue creating accounts here")
                    
                finally:
                    await browser.close()
            
        except Exception as e:
            print(f"\n❌ Account creation failed: {e}")
            import traceback
            traceback.print_exc()
            print("\n⏳ Waiting 30s before retry...")
            time.sleep(30)
        
        finally:
            # Always stop WARP after each account
            if warp_started:
                stop_warp()
        
        # Brief pause between accounts
        print("\n⏸️  Waiting 10s before next account...")
        time.sleep(10)
    
    print("\n" + "="*60)
    print(f"🏁 FINISHED")
    print(f"   Accounts created this session: {accounts_created}")
    print(f"   Total accounts: {get_account_count()}/{max_accounts}")
    print("="*60)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Railway CLI Session Creator - Mail.tm Edition")
    parser.add_argument("--warp", action="store_true", help="Use WARP with unique IP rotation")
    parser.add_argument("--continuous", action="store_true", help="Run continuously until max accounts reached")
    parser.add_argument("--max-accounts", type=int, default=8000, help="Maximum accounts to create (default: 8000)")
    parser.add_argument("--deploy-recursive", action="store_true", help="Deploy to each new account for exponential growth")
    args = parser.parse_args()
    
    print("="*60)
    print("🚂 Railway CLI Session Creator - Mail.tm Edition")
    print("="*60)
    print(f"📁 Sessions directory: {SESSIONS_DIR}")
    print(f"☁️  Mega remote: {MEGA_REMOTE}")
    if args.warp:
        print(f"🌐 WARP: Enabled (unique IP per run)")
    if args.continuous:
        print(f"🔁 Mode: CONTINUOUS (target: {args.max_accounts} accounts)")
    else:
        print(f"🔁 Mode: SINGLE ACCOUNT")
    print()
    
    try:
        if args.continuous:
            asyncio.run(run_continuous(
                use_warp=args.warp,
                max_accounts=args.max_accounts,
                deploy_recursive=args.deploy_recursive
            ))
        else:
            asyncio.run(run(use_warp=args.warp))
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)



def deploy_to_new_railway(session_dir: Path, deploy_recursive: bool = False):
    """Deploy this script to a new Railway project using the newly created account"""
    if not deploy_recursive:
        return False
    
    # Safety check: Don't deploy if we're at or near the limit
    current_count = get_account_count()
    if current_count >= 8000:
        print(f"\n🛑 SAFETY LIMIT: {current_count} accounts reached, stopping deployment")
        return False
    
    print("\n🚀 Deploying to new Railway sandbox...")
    
    try:
        # Set HOME to use the new session
        env = os.environ.copy()
        env["HOME"] = str(session_dir)
        
        # Get current session number for next deployment
        current_num = int(session_dir.name.split("-")[-1])
        next_num = current_num + 1
        
        # Create new Railway project
        project_name = f"farm-gen{next_num}-{int(time.time())}"
        print(f"  Creating project: {project_name}")
        
        result = subprocess.run(
            ["railway", "init", "--name", project_name],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
            cwd=str(Path(__file__).parent)
        )
        
        if result.returncode != 0:
            print(f"  ⚠️  Failed to create project: {result.stderr}")
            return False
        
        print(f"  ✅ Created project: {project_name}")
        
        # Deploy current script to new project
        print(f"  📤 Deploying to Railway...")
        result = subprocess.run(
            ["railway", "up", "--detach"],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
            cwd=str(Path(__file__).parent)
        )
        
        if result.returncode != 0:
            print(f"  ⚠️  Deployment failed: {result.stderr}")
            return False
        
        print(f"  ✅ Deployed successfully!")
        print(f"  🦠 New sandbox will create session-{next_num + 1} and replicate...")
        return True
        
    except Exception as e:
        print(f"  ⚠️  Deployment error: {e}")
        return False
