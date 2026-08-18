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
def rotate_warp_ip():
    """Rotate WARP IP by updating wgcf account"""
    print("🔄 Rotating WARP IP...")
    try:
        # Check if wgcf is configured
        if not Path("/etc/wireguard/wgcf.conf").exists():
            print("⚠️  WARP not configured (wgcf.conf missing)")
            return False
        
        subprocess.run(["sudo", "wgcf", "update"], capture_output=True, timeout=30, check=True)
        subprocess.run(["sudo", "wgcf", "generate"], capture_output=True, timeout=30, check=True)
        subprocess.run(["sudo", "wg-quick", "down", "wgcf"], capture_output=True, timeout=10)
        subprocess.run(["sudo", "wg-quick", "up", "wgcf"], capture_output=True, timeout=30, check=True)
        print("✅ WARP IP rotated")
        return True
    except Exception as e:
        print(f"⚠️  WARP rotation failed: {e}")
        return False


def start_warp():
    """Start WARP/WireGuard"""
    print("🚀 Starting WARP...")
    try:
        result = subprocess.run(
            ["sudo", "wg-quick", "up", "wgcf"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0 or "already exists" in result.stderr:
            print("✅ WARP started")
            return True
        print(f"⚠️  WARP start failed: {result.stderr}")
        return False
    except Exception as e:
        print(f"⚠️  WARP start error: {e}")
        return False


def stop_warp():
    """Stop WARP/WireGuard"""
    try:
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
    
    # Check for Cloudflare Turnstile
    print("🔍 Checking for Cloudflare Turnstile...")
    await page.wait_for_timeout(2000)
    
    turnstile_exists = False
    try:
        turnstile_iframe = page.locator('iframe[src*="challenges.cloudflare.com"]')
        count = await turnstile_iframe.count()
        if count > 0:
            turnstile_exists = True
            print(f"✓ Found Cloudflare Turnstile iframe")
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
                print(f"✓ Found Cloudflare Turnstile widget")
        except:
            pass
    
    # Solve Turnstile if present
    if turnstile_exists and CAPTCHA_SOLVER_AVAILABLE:
        print("🤖 Auto-solving Cloudflare Turnstile...")
        try:
            async with ClickSolver(
                framework=FrameworkType.PATCHRIGHT,
                page=page,
                max_attempts=1,
                attempt_delay=2
            ) as solver:
                await solver.solve_captcha(
                    captcha_container=page,
                    captcha_type=CaptchaType.CLOUDFLARE_TURNSTILE
                )
            print("✅ Turnstile solved!")
        except Exception as e:
            print(f"⚠️  Solver error (may still work): {str(e)[:100]}", file=sys.stderr)
        
        print("⏳ Waiting for Turnstile validation...")
        await page.wait_for_timeout(3000)
    elif turnstile_exists:
        print("⚠️  Turnstile detected but solver not available")
    else:
        print("✓ No visible Turnstile")
    
    # Wait for Continue button and click
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


async def accept_railway_policies(page):
    """Accept Railway ToS and Privacy Policy"""
    print("\n📜 Accepting Railway policies...")
    
    try:
        # Wait for the policy dialog to appear
        await page.wait_for_timeout(3000)
        
        # Look for scroll button and check if it's disabled
        scroll_btn = page.get_by_role("button", name="Scroll to read all terms")
        
        try:
            await expect(scroll_btn).to_be_visible(timeout=5000)
            is_disabled = await scroll_btn.is_disabled()
            
            if not is_disabled:
                print("  📜 Scrolling through terms...")
                # Scroll to bottom of terms container
                await page.evaluate('''() => {
                    const dialog = document.querySelector('[role="dialog"]');
                    if (dialog) {
                        const scrollable = dialog.querySelector('[style*="overflow"]') || dialog;
                        scrollable.scrollTop = scrollable.scrollHeight;
                    }
                }''')
                await page.wait_for_timeout(2000)
                
                # Wait for scroll button to be enabled
                await scroll_btn.click()
                print("  ✅ Scrolled to bottom")
                await page.wait_for_timeout(1000)
        except Exception as e:
            print(f"  ℹ️  No scroll required or already scrolled: {e}")
        
        # Now look for the Continue button
        continue_btn = page.get_by_role("button", name="Continue")
        await expect(continue_btn).to_be_visible(timeout=10000)
        await expect(continue_btn).to_be_enabled(timeout=10000)
        await continue_btn.click()
        print("✅ Policies accepted")
        
        await page.wait_for_timeout(3000)
    except Exception as e:
        print(f"⚠️  Policy acceptance issue: {e}")
        # Try alternative: look for any Continue button
        try:
            print("  🔍 Trying alternative method...")
            await page.get_by_text("Continue").click(timeout=5000)
            print("✅ Clicked Continue (alternative method)")
            await page.wait_for_timeout(3000)
        except:
            print(f"⚠️  Could not accept policies automatically")


async def register_cli_session(context, page, sessions_dir: Path):
    """
    Register Railway CLI session using OAuth PKCE flow
    Saves session files to local directory
    """
    print("\n🔧 Registering Railway CLI session...")
    
    # Generate PKCE challenge
    code_verifier = ''.join(secrets.choice(PKCE_CHARSET) for _ in range(128))
    code_challenge_bytes = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(code_challenge_bytes).rstrip(b'=').decode()
    
    # Build OAuth URL
    state = str(uuid.uuid4())
    params = {
        "client_id": RAILWAY_CLIENT_ID,
        "redirect_uri": "http://localhost:9911/cli-auth",
        "response_type": "code",
        "scope": RAILWAY_SCOPES,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state
    }
    oauth_url = f"{RAILWAY_OAUTH}/authorize?{urllib.parse.urlencode(params)}"
    
    print(f"  🔗 OAuth URL: {oauth_url[:80]}...")
    
    # Navigate and authorize
    try:
        await page.goto(oauth_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        
        # Check if we got an error page
        page_text = await page.text_content("body")
        if "not found" in page_text.lower() or "error" in page_text.lower():
            print(f"  ⚠️  OAuth page error: {page_text[:200]}")
            raise Exception("OAuth endpoint returned error")
        
        # Look for authorize button
        authorize_btn = page.get_by_role("button", name="Authorize")
        await expect(authorize_btn).to_be_visible(timeout=10000)
        await authorize_btn.click()
        print("✓ Clicked Authorize")
        
        # Wait for redirect
        await page.wait_for_url("**/cli-auth**", timeout=15000)
        redirect_url = page.url
        auth_code = urllib.parse.parse_qs(urllib.parse.urlparse(redirect_url).query)["code"][0]
        print(f"✓ Got authorization code: {auth_code[:20]}...")
        
    except Exception as e:
        print(f"⚠️  OAuth authorization error: {e}")
        # Take screenshot for debugging
        screenshot_path = f"/tmp/oauth-error-{int(time.time())}.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        print(f"  📸 Screenshot saved: {screenshot_path}")
        print(f"  📍 Current URL: {page.url}")
        raise
    
    # Exchange code for tokens
    token_data = {
        "client_id": RAILWAY_CLIENT_ID,
        "code": auth_code,
        "code_verifier": code_verifier,
        "grant_type": "authorization_code",
        "redirect_uri": "http://localhost:9911/cli-auth"
    }
    
    import requests
    resp = requests.post(f"{RAILWAY_OAUTH}/token", json=token_data, timeout=30)
    resp.raise_for_status()
    tokens = resp.json()
    
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]
    print("✓ Got access and refresh tokens")
    
    # Get user info
    headers = {"Authorization": f"Bearer {access_token}"}
    user_resp = requests.post(
        RAILWAY_GRAPHQL,
        json={"query": "{ me { id email name } }"},
        headers=headers,
        timeout=30
    )
    user_resp.raise_for_status()
    user_data = user_resp.json()["data"]["me"]
    user_id = user_data["id"]
    user_email = user_data["email"]
    
    print(f"✓ User: {user_email} (ID: {user_id})")
    
    # Create session directory
    session_dir = next_session_dir(sessions_dir)
    session_dir.mkdir(parents=True, exist_ok=True)
    
    # Save tokens
    config = {
        "user": {
            "id": user_id,
            "email": user_email,
            "name": user_data.get("name", "")
        },
        "tokens": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer"
        },
        "config": {}
    }
    
    config_file = session_dir / "config.json"
    config_file.write_text(json.dumps(config, indent=2))
    print(f"✓ Saved config: {config_file}")
    
    # Save email for reference
    email_file = session_dir / "email.txt"
    email_file.write_text(user_email)
    
    # Save timestamp
    timestamp_file = session_dir / "created_at.txt"
    timestamp_file.write_text(datetime.now(timezone.utc).isoformat())
    
    print(f"✅ Session saved: {session_dir}")
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
        # Start WARP if requested
        if use_warp:
            print("\n🌐 Setting up WARP...")
            if not Path("/etc/wireguard/wgcf.conf").exists():
                print("⚠️  WARP not configured, skipping")
                use_warp = False
            elif rotate_warp_ip():
                warp_started = start_warp()
                if not warp_started:
                    print("⚠️  WARP failed, continuing direct")
            else:
                print("⚠️  WARP rotation failed, continuing direct")
        
        print("\n🚀 Launching browser...")
        # Initialize browser
        async with async_playwright() as p:
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
