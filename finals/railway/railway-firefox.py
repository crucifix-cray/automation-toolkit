#!/usr/bin/env python3
"""
Railway CLI Account Creator - Firefox + dispose.lol
Converted from Chromium to Firefox for better stealth
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
from playwright.async_api import async_playwright, expect, TimeoutError as PlaywrightTimeout

# Import playwright-captcha for auto Cloudflare Turnstile solving
try:
    from playwright_captcha import CaptchaType, ClickSolver, FrameworkType
    CAPTCHA_SOLVER_AVAILABLE = True
except ImportError:
    CAPTCHA_SOLVER_AVAILABLE = False
    print("⚠️  playwright-captcha not installed", file=sys.stderr)

# Constants
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
            return max(session_numbers) + 1
        return 1
            
    except Exception:
        return 1


class DisposeLolInbox:
    """Dispose.lol Gmail - scrape page in separate tab"""
    
    def __init__(self, context=None):
        self.context = context
        self.page = None
        self.address = None
        self.session_initialized = False
        self.BASE_URL = "https://dispose.lol"
    
    async def _ensure_page(self):
        """Load dispose.lol page in new tab"""
        if not self.context:
            raise Exception("No browser context provided")
        
        if not self.session_initialized:
            self.page = await self.context.new_page()
            await self.page.goto(self.BASE_URL, wait_until="load", timeout=60000)
            await self.page.wait_for_timeout(3000)
            self.session_initialized = True
    
    async def create(self):
        """Get dispose.lol Gmail by scraping page"""
        print("📧 Creating dispose.lol Gmail...")
        await self._ensure_page()
        
        await self.page.wait_for_timeout(5000)
        
        try:
            email_text = await self.page.evaluate('''() => {
                const walker = document.createTreeWalker(
                    document.body,
                    NodeFilter.SHOW_TEXT,
                    null
                );
                
                let node;
                while (node = walker.nextNode()) {
                    const text = node.textContent.trim();
                    if (text.includes('@gmail.com') && text.length < 100) {
                        return text;
                    }
                }
                return null;
            }''')
            
            if email_text and '@gmail.com' in email_text:
                self.address = email_text.strip()
                print(f"✅ Mailbox ready: {self.address}")
                return self.address
        except Exception as e:
            print(f"  ⚠️ JavaScript extraction failed: {e}")
        
        await self.page.screenshot(path="/tmp/disposelol-error.png", full_page=True)
        raise Exception("Could not find dispose.lol email - check /tmp/disposelol-error.png")
    
    async def wait_for_railway_code(self, timeout_seconds=300):
        """Poll for Railway OTP by scraping dispose.lol page"""
        print("📥 Waiting for Railway OTP...")
        pattern = re.compile(r'\b(\d{6})\b')
        deadline = time.time() + timeout_seconds
        check_count = 0
        
        while time.time() < deadline:
            check_count += 1
            
            await self.page.reload(wait_until="load")
            await self.page.wait_for_timeout(2000)
            
            message_buttons = await self.page.locator('button[aria-label^="View "]').all()
            
            if check_count % 10 == 1:
                print(f"  Check #{check_count}: {len(message_buttons)} message(s)")
            
            for button in message_buttons:
                aria_label = await button.get_attribute('aria-label')
                
                if aria_label and 'railway' in aria_label.lower():
                    subject = aria_label.replace('View ', '')
                    print(f"  ✅ Found Railway message: {subject}")
                    
                    match = pattern.search(subject)
                    if match:
                        otp = match.group(1)
                        print(f"  🎯 Extracted OTP: {otp}")
                        return otp
            
            await asyncio.sleep(3)
        
        raise TimeoutError("Railway OTP not received")


async def sign_in_to_railway(railway_page, mailbox):
    """Sign in to Railway with email"""
    print("\n🚂 Signing in to Railway...")
    
    await railway_page.goto(RAILWAY_LOGIN, wait_until="domcontentloaded")
    await railway_page.wait_for_load_state("networkidle", timeout=15000)
    
    email_btn = railway_page.get_by_role("button", name="Log in using email", exact=True)
    await expect(email_btn).to_be_visible(timeout=10000)
    await expect(email_btn).to_be_enabled(timeout=10000)
    await email_btn.click()
    print("✓ Clicked 'Log in using email'")
    
    await railway_page.wait_for_timeout(2000)
    
    email_input = railway_page.get_by_placeholder("hello@email.com")
    await expect(email_input).to_be_visible(timeout=15000)
    await email_input.fill(mailbox.address)
    print(f"✓ Filled email: {mailbox.address}")
    
    print("🔍 Checking for Cloudflare Turnstile...")
    await railway_page.wait_for_timeout(2000)
    
    turnstile_exists = False
    try:
        turnstile_iframe = railway_page.locator('iframe[src*="challenges.cloudflare.com"]')
        if await turnstile_iframe.count() > 0:
            turnstile_exists = True
            print("✓ Found Cloudflare Turnstile iframe")
    except:
        pass
    
    if not turnstile_exists:
        try:
            has_turnstile = await railway_page.evaluate('''() => {
                const input = document.querySelector('input[name="cf-turnstile-response"]');
                const container = input?.parentElement?.parentElement;
                return container && container.offsetHeight > 0;
            }''')
            if has_turnstile:
                turnstile_exists = True
                print("✓ Found Cloudflare Turnstile widget")
        except:
            pass
    
    if turnstile_exists and CAPTCHA_SOLVER_AVAILABLE:
        print("🤖 Auto-solving Cloudflare Turnstile...")
        try:
            async with ClickSolver(
                framework=FrameworkType.PLAYWRIGHT,
                page=railway_page,
                max_attempts=1,
                attempt_delay=2
            ) as solver:
                await solver.solve_captcha(
                    captcha_container=railway_page,
                    captcha_type=CaptchaType.CLOUDFLARE_TURNSTILE
                )
            print("✅ Turnstile auto-solved!")
        except Exception as e:
            print(f"⚠️  ClickSolver: {str(e)[:80]}")
            print("  Waiting for manual completion...")
        
        await railway_page.wait_for_timeout(3000)
    elif turnstile_exists:
        print("⚠️  Turnstile detected - please solve manually")
    
    continue_btn = railway_page.get_by_role("button", name="Continue with Email", exact=True)
    print("⏳ Waiting for Continue button...")
    
    try:
        await expect(continue_btn).to_be_enabled(timeout=60000)
        print("✅ Button enabled!")
        await railway_page.wait_for_timeout(1000)
        await continue_btn.click(timeout=5000)
        print("✅ Clicked 'Continue with Email'")
    except:
        screenshot_path = f"/tmp/railway-signin-{int(time.time())}.png"
        await railway_page.screenshot(path=screenshot_path, full_page=True)
        raise RuntimeError(f"Button timeout - {screenshot_path}")
    
    print("⏳ Waiting 15s for email...")
    await asyncio.sleep(15)
    
    code = await mailbox.wait_for_railway_code()
    print(f"✅ Got OTP: {code}")
    
    print("  Entering OTP...")
    await railway_page.wait_for_timeout(3000)
    
    otp_filled = False
    
    try:
        all_inputs = railway_page.locator('input[type="text"]:visible')
        count = await all_inputs.count()
        if count >= 6:
            for i, digit in enumerate(code[:6]):
                await all_inputs.nth(i).fill(digit)
                await asyncio.sleep(0.1)
            print("  ✅ Filled OTP")
            otp_filled = True
    except:
        pass
    
    if not otp_filled:
        try:
            await railway_page.wait_for_selector('iframe[src*="magic"]', timeout=10000)
            magic_frame = railway_page.frame_locator('iframe[src*="magic"]')
            inputs = magic_frame.locator('input[type="text"]')
            await inputs.first.wait_for(state="visible", timeout=5000)
            for i, digit in enumerate(code):
                await inputs.nth(i).fill(digit)
                await asyncio.sleep(0.1)
            print("  ✅ Filled OTP (iframe)")
            otp_filled = True
        except:
            pass
    
    if not otp_filled:
        await railway_page.screenshot(path="/tmp/railway_otp_fail.png")
        raise RuntimeError("Could not find OTP inputs")
    
    await expect(railway_page).to_have_url(re.compile(r"/dashboard(?:/|$)"), timeout=EMAIL_TIMEOUT)
    print("✅ Logged in!")


async def accept_railway_policies(railway_page):
    """Accept ToS"""
    print("\n📜 Accepting ToS...")
    await railway_page.wait_for_timeout(2000)
    
    dialog = railway_page.get_by_role("dialog", name=re.compile(r"Terms of Service", re.I)).last
    try:
        await dialog.wait_for(state="visible", timeout=ACTION_TIMEOUT)
    except:
        print("✓ No ToS dialog")
        return
    
    for iteration in range(6):
        try:
            await dialog.evaluate("""dialog => {
                for (const el of [dialog, ...dialog.querySelectorAll('*')]) {
                    if (el.scrollHeight > el.clientHeight + 10) {
                        el.scrollTop = el.scrollHeight;
                    }
                }
            }""")
        except:
            break
        
        for name in ["I agree with Railway's Terms of Service", "I agree to the Fair Use Policy"]:
            button = railway_page.get_by_role("button", name=name, exact=True)
            try:
                await expect(button).to_be_visible(timeout=3000)
                await button.click(timeout=5000)
                print(f"  ✅ {name}")
                break
            except:
                continue
        
        await railway_page.wait_for_timeout(1500)
    
    print("✅ ToS accepted")


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


async def get_oauth_tokens(railway_page) -> dict:
    """Get Railway OAuth tokens"""
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
        
        await railway_page.goto(authorization_url, wait_until="domcontentloaded")
        
        deadline = loop.time() + 120
        while loop.time() < deadline:
            if result_holder:
                break
            authorize = railway_page.get_by_role("button", name="Authorize", exact=True)
            if await authorize.count():
                try:
                    await authorize.click(timeout=5000)
                except:
                    pass
            await railway_page.wait_for_timeout(2000)
        
        if not result_holder:
            raise RuntimeError("OAuth callback timeout")
        
        callback_query = result_holder["query"]
        
        if "error" in callback_query:
            raise RuntimeError(f"OAuth error: {callback_query['error'][0]}")
        
        if "code" not in callback_query:
            raise RuntimeError("No OAuth code")
        
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
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        with urllib.request.urlopen(request, timeout=30) as response:
            tokens = json.loads(response.read().decode())
        print("✅ OAuth tokens received")
        return tokens
        
    finally:
        callback_server.close()
        await callback_server.wait_closed()


def get_web_user(cookies: list[dict]) -> dict:
    """Get user from Railway API"""
    session = {c["name"]: c["value"] for c in cookies 
               if c["domain"] == "backboard.railway.com" and c["name"] in ("rw.session", "rw.session.sig")}
    
    if not session.get("rw.session"):
        raise RuntimeError("No rw.session cookie")
    
    cookie_header = "; ".join(f"{k}={v}" for k, v in session.items())
    request = urllib.request.Request(RAILWAY_GRAPHQL, 
                                    data=json.dumps({"query": "query { me { id email } }"}).encode(),
                                    headers={"Content-Type": "application/json", "Cookie": cookie_header})
    
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode())
    
    me = (data.get("data") or {}).get("me") or {}
    if not me.get("id"):
        raise RuntimeError("No user identity")
    
    return me


def write_cli_session(session_dir: Path, tokens: dict, user: dict, cookies: list[dict]):
    """Write Railway CLI session"""
    session_dir.mkdir(parents=True, exist_ok=True)
    cli_home = session_dir / ".railway"
    (cli_home / "sessions").mkdir(parents=True, exist_ok=True)
    (cli_home / "config.lock").write_text("")
    
    now = datetime.now(timezone.utc)
    expires_at = int(now.timestamp()) + int(tokens.get("expires_in", 300))
    
    config = {
        "user": {
            "accessToken": tokens["access_token"],
            "id": user["id"],
            "refreshToken": tokens.get("refresh_token"),
            "tokenExpiresAt": expires_at,
        },
    }
    
    (cli_home / "config.json").write_text(json.dumps(config, indent=2))
    (session_dir / "browser_cookies.json").write_text(json.dumps({"cookies": cookies}, indent=2))
    
    session_payload = {
        "agent_session_id": str(uuid.uuid4()),
        "created_at": now.isoformat(),
    }
    (cli_home / "sessions" / f"{secrets.token_hex(8)}.session").write_text(json.dumps(session_payload))
    
    print(f"✅ Session: {session_dir}")


async def register_cli_session(context, railway_page) -> Path:
    """Register CLI session"""
    print("\n🔧 Registering session...")
    cookies = await context.cookies()
    tokens = await get_oauth_tokens(railway_page)
    user = get_web_user(cookies)
    session_num = get_next_session_number()
    session_dir = SESSIONS_DIR / f"session-{session_num}"
    write_cli_session(session_dir, tokens, user, cookies)
    return session_dir


def sync_to_mega(session_dir: Path):
    """Sync to Mega"""
    print(f"\n☁️  Syncing to Mega...")
    try:
        subprocess.run(["rclone", "copy", str(session_dir), f"{MEGA_REMOTE}/{session_dir.name}"], 
                      capture_output=True, timeout=120, check=True)
        print(f"✅ Synced")
    except:
        print("⚠️  Sync failed")


async def run():
    """Run single account creation"""
    async with async_playwright() as p:
        browser = await p.firefox.launch(
            headless=False,
            firefox_user_prefs={
                'dom.webdriver.enabled': False,
                'useAutomationExtension': False
            }
        )
        context = await browser.new_context()
        context.set_default_timeout(ACTION_TIMEOUT)
        railway_page = await context.new_page()
        
        mailbox = DisposeLolInbox(context=context)
        await mailbox.create()
        
        try:
            await sign_in_to_railway(railway_page, mailbox)
            await accept_railway_policies(railway_page)
            session_dir = await register_cli_session(context, railway_page)
            
            sync_to_mega(session_dir)
            
            print(f"\n{'='*60}")
            print(f"✅ SUCCESS!")
            print(f"📁 {session_dir}")
            print(f"📧 {mailbox.address}")
            print(f"{'='*60}")
            
            input("\n⏸️  Press Enter to close...")
            
        finally:
            await browser.close()


if __name__ == "__main__":
    print("="*60)
    print("🚂 Railway Account Creator - Firefox Edition")
    print("="*60)
    print(f"📁 Sessions: {SESSIONS_DIR}")
    print(f"☁️  Mega: {MEGA_REMOTE}")
    print("="*60)
    
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
