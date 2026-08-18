#!/usr/bin/env python3
"""
Railway CLI Account Creator - Dispose.lol API Edition
Complete implementation with OAuth, ToS acceptance, and CLI session registration
Uses dispose.lol API instead of browser scraping
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

# Optional auto-solve for Cloudflare Turnstile; falls back to human solving
try:
    from playwright_captcha import CaptchaType, ClickSolver, FrameworkType
    CAPTCHA_SOLVER_AVAILABLE = True
except ImportError:
    CAPTCHA_SOLVER_AVAILABLE = False
    print("⚠️  playwright-captcha not installed - human fallback will be used", file=sys.stderr)

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
CLOUDFLARE_TIMEOUT = 180_000


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
    """
    Dispose.lol Gmail inbox using REAL API with documented payloads
    Based on: dispose lol Mail Automation.txt
    """
    
    BASE_URL = "https://dispose.lol"
    REMOTE_PREFIX = "/_app/remote/1i1fsx0"
    
    def __init__(self, context):
        """
        Args:
            context: Playwright browser context - creates its own dedicated tab
        """
        if not context:
            raise Exception("No browser context provided")
        self.context = context
        self.page = None
        self.address = None
        self.session_initialized = False
    
    async def _ensure_session(self):
        """Load dispose.lol in its own tab (stays there, parallel to Railway tab)"""
        if not self.session_initialized:
            print("🌐 Initializing dispose.lol session...")
            self.page = await self.context.new_page()
            await self.page.goto(self.BASE_URL, wait_until="load", timeout=60000)
            # dispose.lol can challenge the mail tab too - clear it or the API dies
            await wait_for_cloudflare(self.page, "dispose.lol")
            await self.page.wait_for_timeout(3000)
            self.session_initialized = True
            print("✅ Session initialized (dispose_mailbox cookie obtained)")
    
    async def create(self):
        """
        Create dispose.lol Gmail address via getOrCreateMailbox
        Returns: Gmail address (e.g., "user123@gmail.com")
        """
        print("\n📧 Creating dispose.lol Gmail via REAL API...")
        
        await self._ensure_session()
        
        # Call getOrCreateMailbox with EMPTY payload as documented
        result = await self.page.evaluate(f"""
            async () => {{
                const response = await fetch('https://dispose.lol{self.REMOTE_PREFIX}/getOrCreateMailbox', {{
                    method: 'POST',
                    credentials: 'include',
                    headers: {{
                        'Content-Type': 'application/json',
                        'x-sveltekit-pathname': '/',
                        'x-sveltekit-search': ''
                    }},
                    body: JSON.stringify({{
                        payload: "",
                        refreshes: []
                    }})
                }});
                
                const envelope = await response.json();
                
                if (envelope.type === 'error') {{
                    throw new Error(envelope.error?.message || 'getOrCreateMailbox failed');
                }}
                
                if (envelope.type !== 'result') {{
                    throw new Error('Unexpected response type: ' + envelope.type);
                }}
                
                // Parse devalue result
                return JSON.parse(envelope.result);
            }}
        """)
        
        # Result is in devalue table format: 
        # [{"address":1,"showSet":2,"error":3,"needsCaptcha":2}, "email@gmail.com", false, null]
        # Index 0 is the object with pointers, other indices are the actual values
        
        if result and isinstance(result, list) and len(result) >= 2:
            # Parse devalue table format
            meta = result[0] if isinstance(result[0], dict) else {}
            
            # Get address from table - meta['address'] is the index
            address_idx = meta.get('address')
            if address_idx and address_idx < len(result):
                self.address = result[address_idx]
            
            # Check needsCaptcha
            captcha_idx = meta.get('needsCaptcha')
            if captcha_idx and captcha_idx < len(result) and result[captcha_idx]:
                raise Exception("CAPTCHA required - cannot create mailbox")
            
            # Check error
            error_idx = meta.get('error')
            if error_idx and error_idx < len(result) and result[error_idx]:
                raise Exception(f"Mailbox error: {result[error_idx]}")
            
            if self.address:
                print(f"✅ Mailbox ready: {self.address}")
                return self.address
        
        raise Exception(f"Failed to parse Gmail response: {result}")
    
    async def get_messages(self):
        """
        Get messages via getMailboxMessages
        Uses documented payload for current anonymous mailbox
        """
        await self._ensure_session()
        
        # Documented payload for current mailbox: W3siYXNzaWdubWVudElkIjotMX1d
        # This encodes: [{"assignmentId":-1}] where -1 is the undefined sentinel
        
        result = await self.page.evaluate(f"""
            async () => {{
                // Use documented payload for current anonymous mailbox
                const payload = "W3siYXNzaWdubWVudElkIjotMX1d";
                
                const response = await fetch('https://dispose.lol{self.REMOTE_PREFIX}/getMailboxMessages?payload=' + encodeURIComponent(payload), {{
                    credentials: 'include',
                    headers: {{
                        'x-sveltekit-pathname': '/',
                        'x-sveltekit-search': ''
                    }}
                }});
                
                const envelope = await response.json();
                
                if (envelope.type === 'error') {{
                    throw new Error(envelope.error?.message || 'getMailboxMessages failed');
                }}
                
                if (envelope.type !== 'result') {{
                    throw new Error('Unexpected response type: ' + envelope.type);
                }}
                
                // Parse devalue result
                return JSON.parse(envelope.result);
            }}
        """)
        
        # Result is in devalue table format:
        # [{"address":1,"mailboxKey":1,"messages":2,...}, "email@gmail.com", [...messages...], ...]
        
        if result and isinstance(result, list) and len(result) >= 1:
            meta = result[0] if isinstance(result[0], dict) else {}
            
            # Get messages from table
            messages_idx = meta.get('messages')
            if messages_idx and messages_idx < len(result):
                raw_messages = result[messages_idx]
                if isinstance(raw_messages, list):
                    # devalue flattens nested objects: ints are indices into the result table
                    def resolve(v):
                        return result[v] if isinstance(v, int) and 0 <= v < len(result) else v
                    messages = []
                    for m in raw_messages:
                        if isinstance(m, dict):
                            messages.append({k: resolve(v) for k, v in m.items()})
                        else:
                            messages.append(resolve(m))
                    return messages
        
        return []
    
    async def wait_for_railway_code(self, timeout_seconds=300):
        """
        Poll dispose.lol API for Railway OTP
        
        Args:
            timeout_seconds: Max time to wait for OTP
            
        Returns:
            str: 6-digit OTP code
        """
        print("\n📥 Waiting for Railway OTP via REAL API...")
        pattern = re.compile(r'\b(\d{6})\b')
        deadline = time.time() + timeout_seconds
        check_count = 0
        
        while time.time() < deadline:
            check_count += 1
            
            # Get messages via API
            messages = await self.get_messages()
            
            if check_count % 10 == 1:
                print(f"  Check #{check_count}: {len(messages)} message(s)")
            
            for msg in messages:
                subject = msg.get('subject', '')
                if not isinstance(subject, str):
                    continue
                
                if 'railway' in subject.lower():
                    print(f"  ✅ Found Railway message: {subject}")
                    
                    # Extract 6-digit OTP
                    match = pattern.search(subject)
                    if match:
                        otp = match.group(1)
                        print(f"  🎯 Extracted OTP: {otp}")
                        return otp
            
            await asyncio.sleep(12)  # Match site's 12-second polling interval
        
        raise TimeoutError(f"Railway OTP not received within {timeout_seconds}s")
    
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


async def wait_for_cloudflare(page, page_name: str) -> None:
    """Wait for a human to complete a visible Cloudflare challenge.

    Invisible 1x1 Turnstile frames are routine risk checks, not a checkbox.
    Only a real visible challenge pauses the flow and asks for human help.
    """
    challenge_widgets = page.locator(
        'iframe[src*="challenges.cloudflare.com"], '
        'input[type="checkbox"][name*="cf-turnstile"], '
        "#challenge-stage, #cf-chl-widget"
    )
    challenge_copy = page.get_by_text(
        re.compile(r"Verify you are human|Checking your browser|Just a moment", re.I)
    ).first

    challenge = None
    if await challenge_copy.count() and await challenge_copy.is_visible():
        challenge = challenge_copy
    else:
        for index in range(await challenge_widgets.count()):
            widget = challenge_widgets.nth(index)
            if not await widget.is_visible():
                continue
            box = await widget.bounding_box()
            if box and box["width"] >= 100 and box["height"] >= 40:
                challenge = widget
                break

    if challenge is None:
        return

    await page.bring_to_front()
    print(
        f"Cloudflare verification is visible on {page_name}. "
        "Complete the checkbox in that tab; the script will continue automatically."
    )
    try:
        await expect(challenge).to_be_hidden(timeout=CLOUDFLARE_TIMEOUT)
    except AssertionError as error:
        raise RuntimeError(
            f"Cloudflare verification on {page_name} was not completed in time."
        ) from error


async def auto_click_turnstile(page):
    """Try to clear the Turnstile checkbox: ClickSolver first, then a direct
    click on the challenge iframe (interactive Turnstile responds to it)."""
    if CAPTCHA_SOLVER_AVAILABLE:
        try:
            async with ClickSolver(
                framework=FrameworkType.PLAYWRIGHT,
                page=page,
                max_attempts=1,
                attempt_delay=2
            ) as solver:
                await solver.solve_captcha(
                    captcha_container=page,
                    captcha_type=CaptchaType.CLOUDFLARE_TURNSTILE
                )
            print("✅ Turnstile auto-solved!")
            return True
        except Exception as e:
            print(f"⚠️  ClickSolver failed: {str(e)[:80]} - trying direct click")

    for attempt in range(3):
        try:
            iframe = page.locator('iframe[src*="challenges.cloudflare.com"]').first
            if await iframe.count() == 0:
                return False
            box = await iframe.bounding_box()
            if not box:
                return False
            await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            await page.wait_for_timeout(2500)
            solved = await page.evaluate(
                "() => (document.querySelector('input[name=\"cf-turnstile-response\"]')?.value || '').length > 10"
            )
            if solved:
                print("✅ Turnstile cleared by direct click!")
                return True
        except Exception:
            pass
    return False


async def sign_in_to_railway(page, mailbox: DisposeLolInbox):
    """Sign in to Railway with email"""
    print("\n🚂 Signing in to Railway...")
    
    await page.goto(RAILWAY_LOGIN, wait_until="domcontentloaded")
    await page.wait_for_load_state("networkidle", timeout=15000)
    await wait_for_cloudflare(page, "Railway login page")
    
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
    
    # Detect Turnstile like the previous mode did
    print("🔍 Checking for Cloudflare Turnstile...")
    await page.wait_for_timeout(2000)
    
    turnstile_exists = False
    try:
        turnstile_iframe = page.locator('iframe[src*="challenges.cloudflare.com"]')
        if await turnstile_iframe.count() > 0:
            turnstile_exists = True
            print("✓ Found Cloudflare Turnstile iframe")
    except:
        pass
    
    if not turnstile_exists:
        try:
            has_turnstile = await page.evaluate('''() => {
                const input = document.querySelector('input[name="cf-turnstile-response"]');
                const container = input?.parentElement?.parentElement;
                return container && container.offsetHeight > 0;
            }''')
            if has_turnstile:
                turnstile_exists = True
                print("✓ Found Cloudflare Turnstile widget")
        except:
            pass
    
    # Auto-solve (ClickSolver + direct checkbox click), then human fallback
    if turnstile_exists:
        print("🤖 Attempting to solve Cloudflare Turnstile...")
        await auto_click_turnstile(page)
    else:
        print("ℹ️  No turnstile detected yet - checking after submit too")
    
    # If a challenge is still visible, wait for a human to complete it
    await wait_for_cloudflare(page, "Railway sign-in")
    print("✓ No visible Cloudflare challenge (or it was solved)")

    # Wait for Continue button
    continue_btn = page.get_by_role("button", name="Continue with Email", exact=True)
    print("⏳ Waiting for Continue button...")
    
    try:
        await expect(continue_btn).to_be_enabled(timeout=60000)
        print("✅ Button enabled!")
        await page.wait_for_timeout(1000)
        await continue_btn.click(timeout=5000)
        print("✅ Clicked 'Continue with Email'")
    except:
        screenshot_path = f"/tmp/turnstile-timeout-{int(time.time())}.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        print(f"❌ Screenshot: {screenshot_path}")
        raise RuntimeError(f"Turnstile/button timeout")

    # Challenges often appear on submit - handle them (script2 mode)
    await wait_for_cloudflare(page, "Railway OTP page")
    
    # Wait for Railway to send email
    print("⏳ Waiting 15s for Railway email...")
    await asyncio.sleep(15)
    
    # Get OTP from mailbox via API
    code = await mailbox.wait_for_railway_code()
    print(f"✅ Got OTP: {code}")
    
    # Fill OTP
    print("  Entering OTP...")
    await page.wait_for_timeout(3000)
    
    otp_filled = False
    
    # Try direct modal first
    try:
        all_inputs = page.locator('input[type="text"]:visible')
        count = await all_inputs.count()
        
        if count >= 6:
            for i, digit in enumerate(code[:6]):
                await all_inputs.nth(i).fill(digit)
                await asyncio.sleep(0.1)
            print("  ✅ Filled OTP (direct method)")
            otp_filled = True
    except Exception as e:
        print(f"  Direct method failed: {e}")
    
    # Try iframe method
    if not otp_filled:
        try:
            await page.wait_for_selector('iframe[src*="auth.magic.link"], iframe[src*="magic"]', timeout=10000)
            magic_frame = page.frame_locator('iframe[src*="auth.magic.link"], iframe[src*="magic"]')
            inputs = magic_frame.locator('input[type="text"]')
            
            await inputs.first.wait_for(state="visible", timeout=5000)
            
            for i, digit in enumerate(code):
                await inputs.nth(i).fill(digit)
                await asyncio.sleep(0.1)
            print("  ✅ Filled OTP (iframe method)")
            otp_filled = True
        except Exception as e:
            print(f"  Iframe method failed: {e}")
    
    if not otp_filled:
        await page.screenshot(path="/tmp/railway_otp_failure.png")
        raise RuntimeError("Could not find OTP inputs")
    
    # Wait for dashboard
    await wait_for_cloudflare(page, "Railway dashboard")
    await expect(page).to_have_url(re.compile(r"/dashboard(?:/|$)"), timeout=EMAIL_TIMEOUT)
    print("✅ Logged in to dashboard")


async def accept_railway_policies(page):
    """Accept ToS"""
    print("\n📜 Accepting Terms of Service...")
    await wait_for_cloudflare(page, "Railway ToS page")
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
        
        if "error" in callback_query:
            description = callback_query.get("error_description", [""])[0]
            raise RuntimeError(f"OAuth error: {callback_query['error'][0]} {description}")
        
        if "code" not in callback_query or callback_query.get("state", [""])[0] != state:
            raise RuntimeError("OAuth callback missing code or state mismatch")
        
        # Exchange code for tokens
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
            raise RuntimeError("No user identity from Railway API")
        
        print(f"  ✅ Got user: {me.get('email', me['id'])}")
        return me
        
    except urllib.error.HTTPError as error:
        error_body = error.read().decode()
        raise RuntimeError(f"Railway API user lookup failed: {error.code} - {error_body}")


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
    """Rotate WARP IP"""
    print("\n🔄 Rotating WARP IP...")
    old_ip = check_current_ip()
    print(f"  Current IP: {old_ip}")
    
    try:
        result = subprocess.run(["wgcf", "update"], capture_output=True, text=True, 
                              timeout=30, cwd=str(Path.home()))
        if result.returncode != 0:
            print(f"  ⚠️ wgcf update failed: {result.stderr.strip()}")
            return False
        
        result = subprocess.run(["wgcf", "generate"], capture_output=True, text=True, 
                              timeout=30, cwd=str(Path.home()))
        if result.returncode != 0:
            print(f"  ⚠️ wgcf generate failed: {result.stderr.strip()}")
            return False
        
        print("  ✅ New WARP config generated")
        return True
    except Exception as e:
        print(f"  ⚠️ WARP rotation failed: {e}")
        return False


def start_warp():
    """Start WARP"""
    print("\n🌐 Checking WARP...")
    
    # Check for wireproxy
    try:
        result = subprocess.run(["pgrep", "-f", "wireproxy"], capture_output=True, timeout=2)
        if result.returncode == 0:
            print("  ✅ Wireproxy SOCKS5 detected")
            return True
    except:
        pass
    
    # Try WireGuard interface
    is_root = os.geteuid() == 0 if hasattr(os, 'geteuid') else False
    sudo_cmd = [] if is_root else ["sudo"]
    
    try:
        result = subprocess.run([*sudo_cmd, "wg", "show", "wgcf"], 
                              capture_output=True, timeout=5)
        if result.returncode == 0:
            print("  ℹ️  WARP already running, restarting...")
            subprocess.run([*sudo_cmd, "wg-quick", "down", "wgcf"], 
                         capture_output=True, timeout=10)
            time.sleep(1)
        
        result = subprocess.run([*sudo_cmd, "wg-quick", "up", "wgcf"],
                              capture_output=True, text=True, timeout=30,
                              cwd=str(Path.home()))
        
        if result.returncode != 0:
            print(f"  ⚠️ WireGuard start failed: {result.stderr.strip()}")
            return False
        
        time.sleep(3)
        new_ip = check_current_ip()
        print(f"  ✅ WARP started - IP: {new_ip}")
        return True
    except Exception as e:
        print(f"  ⚠️ WARP start failed: {e}")
        return False


def stop_warp():
    """Stop WARP"""
    print("\n🛑 Stopping WARP...")
    try:
        subprocess.run(["sudo", "wg-quick", "down", "wgcf"],
                      capture_output=True, timeout=10)
        print("  ✅ WARP stopped")
        return True
    except:
        return False


def test_railway_cli(session_dir: Path):
    """Test Railway CLI"""
    print("\n🧪 Testing Railway CLI...")
    try:
        result = subprocess.run(["railway", "whoami"], cwd=str(session_dir), 
                              capture_output=True, text=True, timeout=10,
                              env={**os.environ, "HOME": str(session_dir)})
        if result.returncode == 0:
            print(f"✅ Railway CLI test: {result.stdout.strip()}")
        else:
            print(f"⚠️  CLI test failed: {result.stderr.strip()}")
    except FileNotFoundError:
        print("⚠️  Railway CLI not found")


def check_stop_signal():
    """Check if stop.txt exists in Mega"""
    try:
        result = subprocess.run(["rclone", "ls", "mega:stop.txt"],
                              capture_output=True, timeout=10)
        return result.returncode == 0
    except:
        return False


def get_account_count():
    """Get current account count from Mega"""
    try:
        result = subprocess.run(["rclone", "cat", f"{MEGA_REMOTE}/counter.txt"],
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return int(result.stdout.strip())
        return 0
    except:
        return 0


def increment_account_count():
    """Increment account counter"""
    try:
        count = get_account_count() + 1
        subprocess.run(["rclone", "rcat", f"{MEGA_REMOTE}/counter.txt"],
                      input=str(count).encode(), capture_output=True, timeout=10)
        return count
    except:
        return 0


async def launch_railway_browser(playwright, label: str):
    """Launch a persistent-context Chromium like script2: real profile dir,
    1440x900 viewport, headed - looks like a human browser session."""
    profile_dir = SESSIONS_DIR / ".profiles" / label
    profile_dir.mkdir(parents=True, exist_ok=True)
    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=False,
        viewport={"width": 1440, "height": 900},
        args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
    )
    context.set_default_timeout(ACTION_TIMEOUT)
    return context


async def run(use_warp=False):
    """Run single account creation"""
    warp_started = False
    mailbox = None
    
    try:
        if use_warp:
            if rotate_warp_ip():
                warp_started = start_warp()
        
        async with async_playwright() as p:
            context = await launch_railway_browser(p, "single")
            page = await context.new_page()
            
            # Create mailbox in dedicated tab (stays on dispose.lol, Railway flow on page)
            mailbox = DisposeLolInbox(context=context)
            await mailbox.create()
            
            try:
                await sign_in_to_railway(page, mailbox)
                await accept_railway_policies(page)
                session_dir = await register_cli_session(context, page, SESSIONS_DIR)
                
                sync_to_mega(session_dir)
                test_railway_cli(session_dir)
                
                print("\n" + "="*60)
                print(f"✅ SUCCESS! Railway CLI session created")
                print(f"📁 Session: {session_dir}")
                print(f"📧 Email: {mailbox.address}")
                print("="*60)
                
                input("\n⏸️  Press Enter to close browser...")
            finally:
                await context.close()
    finally:
        if warp_started:
            stop_warp()


async def run_continuous(use_warp=False, max_accounts=8000):
    """Continuous account creation loop"""
    accounts_created = 0
    
    print("\n" + "="*60)
    print("🔁 CONTINUOUS MODE")
    print(f"Target: {max_accounts} accounts")
    print("="*60 + "\n")
    
    while True:
        if check_stop_signal():
            print("\n🛑 STOP SIGNAL DETECTED")
            break
        
        current_count = get_account_count()
        print(f"\n📊 Current account count: {current_count}/{max_accounts}")
        
        if current_count >= max_accounts:
            print(f"\n✅ TARGET REACHED! {current_count} accounts")
            break
        
        print("\n" + "="*60)
        print(f"🔄 Creating account #{accounts_created + 1}")
        print("="*60 + "\n")
        
        warp_started = False
        
        try:
            if use_warp:
                if rotate_warp_ip():
                    warp_started = start_warp()
            
            async with async_playwright() as p:
                context = await launch_railway_browser(p, f"account-{accounts_created + 1}")
                page = await context.new_page()
                
                mailbox = DisposeLolInbox(context=context)
                await mailbox.create()
                
                try:
                    await sign_in_to_railway(page, mailbox)
                    await accept_railway_policies(page)
                    session_dir = await register_cli_session(context, page, SESSIONS_DIR)
                    
                    sync_to_mega(session_dir)
                    new_count = increment_account_count()
                    
                    print(f"\n✅ Account #{accounts_created + 1} created!")
                    print(f"   Email: {mailbox.address}")
                    print(f"   Total: {new_count}/{max_accounts}")
                    
                    accounts_created += 1
                finally:
                    await context.close()
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
            print("\n⏳ Waiting 30s before retry...")
            time.sleep(30)
        finally:
            if warp_started:
                stop_warp()
        
        print("\n⏸️  Waiting 10s before next account...")
        time.sleep(10)
    
    print(f"\n🏁 FINISHED - Created {accounts_created} accounts")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Railway Account Creator - Dispose.lol API Edition")
    parser.add_argument("--warp", action="store_true", help="Use WARP IP rotation")
    parser.add_argument("--continuous", action="store_true", help="Continuous mode")
    parser.add_argument("--max-accounts", type=int, default=8000, help="Max accounts (default: 8000)")
    args = parser.parse_args()
    
    print("="*60)
    print("🚂 Railway Account Creator - Dispose.lol API Edition")
    print("="*60)
    print(f"📁 Sessions: {SESSIONS_DIR}")
    print(f"☁️  Mega: {MEGA_REMOTE}")
    print(f"🌐 WARP: {'Enabled' if args.warp else 'Disabled'}")
    print(f"🔁 Mode: {'CONTINUOUS' if args.continuous else 'SINGLE'}")
    print("="*60)
    
    try:
        if args.continuous:
            asyncio.run(run_continuous(use_warp=args.warp, max_accounts=args.max_accounts))
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
