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


class MailTmInbox:
    """Mail.tm API client"""
    
    def __init__(self, proxy=None):
        self.proxy = proxy
        self.token = None
        self.address = None
        self.password = None
        
    def _request(self, method, endpoint, json_data=None):
        url = f"{MAIL_TM_API}{endpoint}"
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        
        proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None
        
        if method == "GET":
            resp = requests.get(url, headers=headers, proxies=proxies, timeout=20)
        else:
            resp = requests.post(url, headers=headers, json=json_data, proxies=proxies, timeout=20)
        
        resp.raise_for_status()
        return resp.json()
    
    def create(self):
        """Create mail.tm account"""
        print("📧 Creating mail.tm account...")
        domains_resp = self._request("GET", "/domains")
        domains = domains_resp.get("hydra:member", domains_resp) if isinstance(domains_resp, dict) else domains_resp
        domain = domains[0]["domain"]
        
        timestamp = int(time.time() * 1000) % 10**10
        username = f"railway{timestamp}"
        self.address = f"{username}@{domain}"
        self.password = "Railway2024!"
        
        account_resp = self._request("POST", "/accounts", {"address": self.address, "password": self.password})
        token_resp = self._request("POST", "/token", {"address": self.address, "password": self.password})
        self.token = token_resp["token"]
        
        print(f"✅ Mailbox ready: {self.address}")
        return self.address
    
    def wait_for_railway_code(self, timeout_seconds=300):
        """Poll for Railway OTP"""
        print("📥 Waiting for Railway OTP...")
        pattern = re.compile(r"\b(\d{6})\s+is your Railway", re.I)
        deadline = time.time() + timeout_seconds
        check_count = 0
        
        while time.time() < deadline:
            check_count += 1
            resp = self._request("GET", "/messages")
            messages = resp.get("hydra:member", resp) if isinstance(resp, dict) else resp
            
            if check_count % 10 == 1:
                print(f"  Check #{check_count}: {len(messages)} message(s)")
            
            for msg in messages:
                subject = msg.get("subject", "")
                if "railway" in subject.lower():
                    print(f"  ✅ Found Railway email")
                    match = pattern.search(subject + " " + msg.get("intro", ""))
                    if match:
                        return match.group(1)
                    
                    full_msg = self._request("GET", f"/messages/{msg.get('id')}")
                    text = full_msg.get("text", "")
                    match = pattern.search(text)
                    if match:
                        return match.group(1)
            
            time.sleep(3)
        
        raise TimeoutError("Railway OTP not received")


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


async def sign_in_to_railway(page, mailbox: MailTmInbox):
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
    
    # Wait for Turnstile to load
    await page.wait_for_timeout(3000)
    
    # Check for button enabled (fast poll)
    continue_btn = page.get_by_role("button", name="Continue with Email", exact=True)
    print("⏳ Waiting for Turnstile to pass...")
    
    deadline = asyncio.get_running_loop().time() + 180
    while asyncio.get_running_loop().time() < deadline:
        try:
            if await continue_btn.is_enabled(timeout=500):
                print("✅ Turnstile passed!")
                await continue_btn.click(timeout=3000)
                print("✅ Clicked 'Continue with Email'")
                break
        except:
            await page.wait_for_timeout(500)
    else:
        raise RuntimeError("Turnstile timeout")
    
    # Wait for Railway to send email
    print("⏳ Waiting 15s for Railway to send email...")
    await asyncio.sleep(15)
    
    # Get OTP from mailbox
    code = mailbox.wait_for_railway_code()
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
    session_dir = next_session_dir(railway_dir)
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
    """Start WireGuard WARP interface"""
    print("\n🌐 Starting WARP...")
    
    try:
        # Check if already running
        result = subprocess.run(["sudo", "wg", "show", "wgcf"], 
                              capture_output=True, timeout=5)
        if result.returncode == 0:
            print("  ℹ️  WARP already running, restarting...")
            subprocess.run(["sudo", "wg-quick", "down", "wgcf"], 
                         capture_output=True, timeout=10)
            time.sleep(1)
        
        # Start WireGuard
        result = subprocess.run(
            ["sudo", "wg-quick", "up", "wgcf"],
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
        # Create mailbox BEFORE starting WARP (direct connection for API)
        mailbox = MailTmInbox()
        mailbox.create()
        
        # Now start WARP for Railway automation
        if use_warp:
            if rotate_warp_ip():
                warp_started = start_warp()
                if not warp_started:
                    print("⚠️  WARP failed to start, continuing with direct connection")
            else:
                print("⚠️  WARP rotation failed, using direct connection")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="chrome", headless=False)
            context = await browser.new_context()
            context.set_default_timeout(ACTION_TIMEOUT)
            page = await context.new_page()
            
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
        result = subprocess.run(["railway", "whoami"], cwd=str(session_dir), 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print(f"✅ Railway CLI test: {result.stdout.strip()}")
        else:
            print(f"⚠️  CLI test failed: {result.stderr.strip()}")
    except FileNotFoundError:
        print("⚠️  Railway CLI not found. Install: curl -fsSL https://railway.app/install.sh | sh")




if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Railway CLI Session Creator - Mail.tm Edition")
    parser.add_argument("--warp", action="store_true", help="Use WARP with unique IP rotation")
    args = parser.parse_args()
    
    print("="*50)
    print("🚂 Railway CLI Session Creator - Mail.tm Edition")
    print("="*50)
    print(f"📁 Sessions directory: {SESSIONS_DIR}")
    print(f"☁️  Mega remote: {MEGA_REMOTE}")
    if args.warp:
        print(f"🌐 WARP: Enabled (unique IP per run)")
    print()
    
    try:
        asyncio.run(run(use_warp=args.warp))
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
