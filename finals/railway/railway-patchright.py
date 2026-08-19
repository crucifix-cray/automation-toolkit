#!/usr/bin/env python3
"""Railway Account Creator - Patchright (stealth Chromium)"""

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
RAILWAY_LOGIN = "https://railway.com/login"
RAILWAY_OAUTH = "https://backboard.railway.com/oauth"
RAILWAY_CLIENT_ID = "rlwy_oaci_onEklvmksh1hRUiCo7E2zX12"
RAILWAY_GRAPHQL = "https://backboard.railway.com/graphql/v2"
RAILWAY_SCOPES = "openid email profile offline_access workspace:admin project:admin ssh_keys"
PKCE_CHARSET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"

SESSIONS_DIR = Path.home() / "Documents" / "railways"
MEGA_REMOTE = "mega:railway_sessions"
ACTION_TIMEOUT = 30_000


class DisposeLolInbox:
    """Dispose.lol Gmail scraper"""
    
    def __init__(self, context):
        self.context = context
        self.page = None
        self.address = None
        self.BASE_URL = "https://dispose.lol"
    
    async def create(self):
        """Get dispose.lol Gmail"""
        print("📧 Creating dispose.lol Gmail...")
        print("⚠️  Make sure Proton VPN is OFF - it conflicts with dispose.lol")
        self.page = await self.context.new_page()
        
        print("  Loading dispose.lol...")
        await self.page.goto(self.BASE_URL, wait_until="load", timeout=60000)
        
        # Wait for Cloudflare challenge to pass
        print("  Waiting for Cloudflare...")
        for attempt in range(30):
            page_content = await self.page.content()
            if 'Verify you are human' in page_content or 'Cloudflare' in page_content:
                print(f"  🔒 Cloudflare detected (attempt {attempt + 1}/30)")
                await self.page.wait_for_timeout(2000)
            else:
                print("  ✅ Cloudflare passed")
                break
        else:
            await self.page.screenshot(path="/tmp/disposelol-cloudflare.png", full_page=True)
            raise Exception("Cloudflare challenge timeout - see /tmp/disposelol-cloudflare.png")
        
        await self.page.wait_for_timeout(2000)
        
        # Click "Create an inbox" button if it exists
        print("  Checking for inbox...")
        try:
            create_btn = self.page.get_by_text("Create an inbox", exact=True)
            await create_btn.wait_for(state="visible", timeout=5000)
            await create_btn.click(timeout=5000)
            print("  ✅ Clicked Create button")
            await self.page.wait_for_timeout(5000)
        except Exception as e:
            print(f"  ℹ️  Inbox already exists or button not found")
            await self.page.wait_for_timeout(2000)
        
        print("  Extracting email...")
        
        # Method 1: Look for input field with email value
        try:
            email_input = await self.page.locator('input[type="text"][value*="@"]').first.get_attribute('value')
            if email_input and '@' in email_input:
                self.address = email_input.strip()
                print(f"✅ Mailbox: {self.address}")
                return self.address
        except:
            pass
        
        # Method 2: Copy button click and get value from input
        print("  Method 1 failed, trying Copy button...")
        try:
            copy_buttons = await self.page.locator('button:has-text("Copy")').all()
            print(f"  DEBUG: Found {len(copy_buttons)} Copy buttons")
            if copy_buttons:
                # Click first Copy button to potentially populate clipboard/input
                await copy_buttons[0].click(timeout=3000)
                await self.page.wait_for_timeout(500)
                
                # Check for input field near the button
                email_input = await self.page.locator('input[type="text"]').first.get_attribute('value')
                if email_input and '@' in email_input:
                    self.address = email_input.strip()
                    print(f"✅ Mailbox: {self.address}")
                    return self.address
                
                # Check aria-label
                for btn in copy_buttons[:3]:
                    label = await btn.get_attribute('aria-label')
                    if label:
                        print(f"  DEBUG: Button aria-label: {label[:100]}")
        except Exception as e:
            print(f"  Copy button check failed: {str(e)[:80]}")
        
        # Method 3: Text walker for any email
        print("  Method 2 failed, trying text walker...")
        email_text = await self.page.evaluate(r'''() => {
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null);
            let node;
            while (node = walker.nextNode()) {
                const text = node.textContent.trim();
                if (text.includes('@') && text.length < 100 && text.length > 10) {
                    // Check if looks like email
                    if (/[\w\.-]+@[\w\.-]+\.[a-z]{2,}/i.test(text)) {
                        return text;
                    }
                }
            }
            return null;
        }''')
        
        if email_text and '@' in email_text:
            import re
            match = re.search(r'([\w\.-]+@[\w\.-]+\.[a-z]{2,})', email_text, re.IGNORECASE)
            if match:
                self.address = match.group(1)
                print(f"✅ Mailbox: {self.address}")
                return self.address
        
        # Method 4: Check ALL input fields
        print("  Method 3 failed, checking all inputs...")
        try:
            all_inputs = await self.page.locator('input').all()
            print(f"  DEBUG: Found {len(all_inputs)} input fields")
            for inp in all_inputs:
                val = await inp.get_attribute('value')
                placeholder = await inp.get_attribute('placeholder')
                if val and '@' in val:
                    print(f"  DEBUG: Input value: {val}")
                    import re
                    match = re.search(r'([\w\.-]+@[\w\.-]+\.[a-z]{2,})', val, re.IGNORECASE)
                    if match:
                        self.address = match.group(1)
                        print(f"✅ Mailbox: {self.address}")
                        return self.address
                if placeholder and '@' in placeholder:
                    print(f"  DEBUG: Input placeholder: {placeholder}")
        except Exception as e:
            print(f"  All inputs check failed: {str(e)[:80]}")
        
        # Method 5: Page text regex
        print("  Method 4 failed, trying page text...")
        page_text = await self.page.text_content('body')
        if page_text:
            import re
            match = re.search(r'([\w\.-]+@[\w\.-]+\.[a-z]{2,})', page_text, re.IGNORECASE)
            if match:
                self.address = match.group(1)
                print(f"✅ Mailbox: {self.address}")
                return self.address
        
        # Failed - take screenshot
        await self.page.screenshot(path="/tmp/disposelol-error.png", full_page=True)
        
        # Debug: save page HTML
        html = await self.page.content()
        with open('/tmp/disposelol-page.html', 'w') as f:
            f.write(html)
        print("  DEBUG: Saved HTML to /tmp/disposelol-page.html")
        
        raise Exception("Could not find email - see /tmp/disposelol-error.png and /tmp/disposelol-page.html")
    
    async def wait_for_railway_code(self, timeout_seconds=300):
        """Poll for Railway OTP"""
        print("📥 Waiting for OTP...")
        pattern = re.compile(r'\b(\d{6})\b')
        deadline = time.time() + timeout_seconds
        
        while time.time() < deadline:
            await self.page.reload(wait_until="load")
            await self.page.wait_for_timeout(2000)
            
            buttons = await self.page.locator('button[aria-label^="View "]').all()
            for button in buttons:
                aria_label = await button.get_attribute('aria-label')
                if aria_label and 'railway' in aria_label.lower():
                    subject = aria_label.replace('View ', '')
                    print(f"  ✅ Found: {subject}")
                    match = pattern.search(subject)
                    if match:
                        otp = match.group(1)
                        print(f"  🎯 OTP: {otp}")
                        return otp
            
            await asyncio.sleep(3)
        raise TimeoutError("OTP timeout")


async def sign_in_to_railway(page, mailbox):
    """Sign in to Railway"""
    print("\n🚂 Signing in...")
    await page.goto(RAILWAY_LOGIN, wait_until="domcontentloaded")
    await page.wait_for_load_state("networkidle", timeout=15000)
    
    email_btn = page.get_by_role("button", name="Log in using email", exact=True)
    await expect(email_btn).to_be_visible(timeout=10000)
    await expect(email_btn).to_be_enabled(timeout=10000)
    await email_btn.click()
    print("✓ Clicked email login")
    
    await page.wait_for_timeout(3000)
    
    email_input = page.get_by_placeholder("hello@email.com")
    await expect(email_input).to_be_visible(timeout=15000)
    await email_input.fill(mailbox.address)
    print(f"✓ Filled: {mailbox.address}")
    
    # Wait for human to solve Turnstile
    print("\n" + "="*60)
    print("⏸️  PLEASE SOLVE THE CLOUDFLARE TURNSTILE MANUALLY")
    print("   (Click the checkbox in the browser window)")
    print("="*60)
    
    continue_btn = page.get_by_role("button", name="Continue with Email", exact=True)
    await expect(continue_btn).to_be_enabled(timeout=180000)
    print("✅ Turnstile solved!")
    
    await page.wait_for_timeout(1000)
    await continue_btn.click()
    print("✅ Clicked Continue")
    
    print("⏳ Waiting 15s for email...")
    await asyncio.sleep(15)
    code = await mailbox.wait_for_railway_code()
    
    print("  Entering OTP...")
    await page.wait_for_timeout(3000)
    
    # Try multiple methods to fill OTP
    otp_filled = False
    
    # Method 1: Direct visible inputs
    try:
        all_inputs = page.locator('input[type="text"]:visible')
        count = await all_inputs.count()
        if count >= 6:
            for i, digit in enumerate(code[:6]):
                await all_inputs.nth(i).fill(digit)
                await asyncio.sleep(0.1)
            print("  ✅ OTP entered (direct)")
            otp_filled = True
    except Exception as e:
        print(f"  Method 1 failed: {e}")
    
    # Method 2: Magic.link iframe
    if not otp_filled:
        try:
            await page.wait_for_selector('iframe[src*="magic"]', timeout=10000)
            magic_frame = page.frame_locator('iframe[src*="magic"]')
            inputs = magic_frame.locator('input[type="text"]')
            await inputs.first.wait_for(state="visible", timeout=5000)
            for i, digit in enumerate(code):
                await inputs.nth(i).fill(digit)
                await asyncio.sleep(0.1)
            print("  ✅ OTP entered (iframe)")
            otp_filled = True
        except Exception as e:
            print(f"  Method 2 failed: {e}")
    
    if not otp_filled:
        await page.screenshot(path="/tmp/railway_otp_fail.png")
        raise RuntimeError("Could not enter OTP - see /tmp/railway_otp_fail.png")
    
    await expect(page).to_have_url(re.compile(r"/dashboard"), timeout=300000)
    print("✅ Logged in!")


async def accept_tos(page):
    """Accept ToS - handles both dialogs"""
    print("\n📜 Accepting ToS...")
    await page.wait_for_timeout(2000)
    
    # Handle up to 2 ToS dialogs
    for dialog_num in range(2):
        dialog = page.get_by_role("dialog", name=re.compile(r"Terms", re.I)).last
        try:
            await dialog.wait_for(state="visible", timeout=15000)
            print(f"  ✅ Found ToS dialog {dialog_num + 1}")
        except:
            if dialog_num == 0:
                print("✓ No ToS dialogs")
            else:
                print(f"✓ No more ToS dialogs (completed {dialog_num})")
            return
        
        # Scroll dialog to bottom
        print(f"  Scrolling dialog {dialog_num + 1}...")
        try:
            await dialog.evaluate("el => el.scrollTo(0, el.scrollHeight)")
            await page.wait_for_timeout(1000)
        except:
            pass
        
        # Click all checkboxes/buttons in this dialog
        for attempt in range(6):
            clicked_something = False
            
            for name in [
                "I agree with Railway's Terms of Service",
                "I agree to the Fair Use Policy",
                "I agree with Railway's Acceptable Use Policy",
                "I accept the Terms of Service",
                "I accept the Fair Use Policy",
            ]:
                button = page.get_by_role("button", name=name, exact=True)
                try:
                    count = await button.count()
                    if count > 0:
                        await button.click(timeout=3000)
                        print(f"  ✅ Clicked: {name}")
                        clicked_something = True
                        await page.wait_for_timeout(1000)
                        break
                except:
                    pass
            
            if not clicked_something:
                break
            
            await page.wait_for_timeout(1500)
        
        print(f"  ✅ ToS dialog {dialog_num + 1} completed")
        await page.wait_for_timeout(2000)
    
    print("✅ All ToS accepted")


def _pkce_challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


async def get_oauth_tokens(page) -> dict:
    """Get OAuth tokens"""
    print("\n🔐 Getting tokens...")
    verifier = "".join(secrets.choice(PKCE_CHARSET) for _ in range(128))
    challenge = _pkce_challenge(verifier)
    state = secrets.token_urlsafe(32)
    
    result_holder = {}
    async def callback_handler(reader, writer):
        request_line = (await reader.read(65536)).decode(errors="replace").split("\r\n")[0]
        path = request_line.split(" ")[1] if " " in request_line else "/"
        if not result_holder:
            result_holder["query"] = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")
        await writer.drain()
        writer.close()
    
    server = await asyncio.start_server(callback_handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    redirect_uri = f"http://127.0.0.1:{port}/callback"
    
    try:
        url = f"{RAILWAY_OAUTH}/auth?" + urllib.parse.urlencode({
            "response_type": "code",
            "client_id": RAILWAY_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "scope": RAILWAY_SCOPES,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "prompt": "consent",
        })
        
        print("  Navigating to OAuth...")
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        
        print("  Waiting for Accept button...")
        for attempt in range(60):
            if result_holder:
                print("  ✅ Callback received!")
                break
            
            # Try both button texts
            accept_btn = page.get_by_role("button", name="Accept and Connect CLI", exact=True)
            authorize_btn = page.get_by_role("button", name="Authorize", exact=True)
            
            accept_count = await accept_btn.count()
            auth_count = await authorize_btn.count()
            
            if accept_count > 0:
                try:
                    if attempt == 0:
                        print(f"  Found 'Accept and Connect CLI' button")
                    await accept_btn.click(force=True, timeout=3000)
                    print("  ✅ Clicked Accept and Connect CLI")
                    await page.wait_for_timeout(2000)
                except Exception as e:
                    if attempt % 10 == 0:
                        print(f"  Click attempt {attempt + 1} failed: {str(e)[:80]}")
            elif auth_count > 0:
                try:
                    if attempt == 0:
                        print(f"  Found 'Authorize' button")
                    await authorize_btn.click(force=True, timeout=3000)
                    print("  ✅ Clicked Authorize")
                    await page.wait_for_timeout(2000)
                except Exception as e:
                    if attempt % 10 == 0:
                        print(f"  Click attempt {attempt + 1} failed: {str(e)[:80]}")
            
            await page.wait_for_timeout(2000)
        
        if not result_holder:
            await page.screenshot(path="/tmp/oauth-timeout.png")
            raise RuntimeError("OAuth timeout - see /tmp/oauth-timeout.png")
        
        code = result_holder["query"]["code"][0]
        body = urllib.parse.urlencode({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": RAILWAY_CLIENT_ID,
            "code_verifier": verifier,
        }).encode()
        
        # Get cookies from page for token request
        cookies = await page.context.cookies()
        cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
        
        req = urllib.request.Request(
            f"{RAILWAY_OAUTH}/token",
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": cookie_header,
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Origin": "https://railway.com",
                "Referer": "https://railway.com/",
            }
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            tokens = json.loads(resp.read().decode())
        print("✅ Tokens received")
        return tokens
    finally:
        server.close()
        await server.wait_closed()


def get_user(cookies):
    """Get user from API"""
    session = {c["name"]: c["value"] for c in cookies 
               if c["domain"] == "backboard.railway.com" and c["name"] in ("rw.session", "rw.session.sig")}
    
    if not session:
        print("  ⚠️  No session cookies found, using empty user")
        return {"id": "unknown", "email": "unknown"}
    
    cookie_header = "; ".join(f"{k}={v}" for k, v in session.items())
    
    req = urllib.request.Request(
        RAILWAY_GRAPHQL,
        data=json.dumps({"query": "query { me { id email } }"}).encode(),
        headers={
            "Content-Type": "application/json",
            "Cookie": cookie_header,
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Origin": "https://railway.com",
            "Referer": "https://railway.com/",
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        return (data.get("data") or {}).get("me") or {}
    except urllib.error.HTTPError as e:
        print(f"  ⚠️  API call failed ({e.code}), using cookie-based user")
        # Extract user from cookies if API fails
        return {"id": session.get("rw.session", "unknown")[:16], "email": "from_cookies"}


def write_session(session_dir: Path, tokens: dict, user: dict, cookies: list):
    """Write session files"""
    session_dir.mkdir(parents=True, exist_ok=True)
    cli_home = session_dir / ".railway"
    (cli_home / "sessions").mkdir(parents=True, exist_ok=True)
    
    config = {
        "user": {
            "accessToken": tokens["access_token"],
            "id": user["id"],
            "refreshToken": tokens.get("refresh_token"),
            "tokenExpiresAt": int(time.time()) + int(tokens.get("expires_in", 300)),
        },
    }
    (cli_home / "config.json").write_text(json.dumps(config, indent=2))
    (session_dir / "browser_cookies.json").write_text(json.dumps({"cookies": cookies}, indent=2))
    print(f"✅ Session: {session_dir}")


async def run():
    """Create one account"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        context.set_default_timeout(ACTION_TIMEOUT)
        page = await context.new_page()
        
        mailbox = DisposeLolInbox(context=context)
        await mailbox.create()
        
        try:
            await sign_in_to_railway(page, mailbox)
            await accept_tos(page)
            tokens = await get_oauth_tokens(page)
            user = get_user(await context.cookies())
            
            session_dir = SESSIONS_DIR / f"session-{int(time.time())}"
            write_session(session_dir, tokens, user, await context.cookies())
            
            print("\n" + "="*60)
            print(f"✅ SUCCESS")
            print(f"📁 {session_dir}")
            print(f"📧 {mailbox.address}")
            print("="*60)
            
            input("\n⏸️  Press Enter to close...")
        finally:
            await browser.close()


if __name__ == "__main__":
    print("="*60)
    print("🚂 Railway Account Creator - Patchright")
    print("="*60)
    asyncio.run(run())
