#!/usr/bin/env python3
"""
Railway CLI Account Creator using Mail.tm API
Replaces broken TempMail API with stable mail.tm service

Features:
- mail.tm API (more reliable than TempMail for service emails)
- WARP IP rotation support (optional)
- Tor proxy support (optional)  
- Playwright browser automation
- Saves session to ~/Documents/railways/
- Syncs to Mega cloud storage (optional)
"""

import asyncio
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import requests
from patchright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# Import playwright-captcha for auto Cloudflare Turnstile solving
try:
    from playwright_captcha import CaptchaType, ClickSolver, FrameworkType
    CAPTCHA_SOLVER_AVAILABLE = True
except ImportError:
    CAPTCHA_SOLVER_AVAILABLE = False
    print("⚠️  playwright-captcha not installed. Install with: pip install playwright-captcha", file=sys.stderr)

# Configuration
BASE_URL = "https://api.mail.tm"
RAILWAY_URL = "https://railway.com"
SESSIONS_DIR = Path.home() / "Documents" / "railways"
MEGA_REMOTE = "mega:railway_sessions"

# Timeouts (milliseconds)
ACTION_TIMEOUT = 30_000
EMAIL_TIMEOUT = 300_000


class MailTmInbox:
    """Mail.tm API client - creates mailbox and polls for Railway OTP"""
    
    def __init__(self, proxy=None):
        self.proxy = proxy
        self.token = None
        self.address = None
        self.password = None
        self.account_id = None
        
    def _request(self, method, endpoint, json_data=None):
        """Make API request with optional proxy support"""
        url = f"{BASE_URL}{endpoint}"
        headers = {"Content-Type": "application/json"}
        
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        
        proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None
        
        try:
            if method == "GET":
                resp = requests.get(url, headers=headers, proxies=proxies, timeout=20)
            elif method == "POST":
                resp = requests.post(url, headers=headers, json=json_data, proxies=proxies, timeout=20)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ API request failed: {e}")
            raise
    
    def create(self):
        """Create new mail.tm account"""
        print("📧 Creating mail.tm account...", flush=True)
        
        # Get available domains
        print("  Fetching domains...", flush=True)
        domains_resp = self._request("GET", "/domains")
        
        # Handle both list and hydra:member format
        if isinstance(domains_resp, dict) and "hydra:member" in domains_resp:
            domains = domains_resp["hydra:member"]
        else:
            domains = domains_resp
        
        domain = domains[0]["domain"]
        print(f"  Using domain: {domain}", flush=True)
        
        # Generate unique username
        timestamp = int(time.time() * 1000) % 10**10
        username = f"railway{timestamp}"
        self.address = f"{username}@{domain}"
        self.password = "Railway2024!"
        
        # Create account
        print(f"  Creating account: {self.address}", flush=True)
        account_resp = self._request("POST", "/accounts", {
            "address": self.address,
            "password": self.password
        })
        
        self.account_id = account_resp.get("id")
        print(f"  ✅ Account created (ID: {self.account_id})", flush=True)
        
        # Get authentication token
        print("  Getting auth token...", flush=True)
        token_resp = self._request("POST", "/token", {
            "address": self.address,
            "password": self.password
        })
        
        self.token = token_resp["token"]
        print(f"  ✅ Mailbox ready: {self.address}", flush=True)
        
        return self.address
    
    def wait_for_railway_code(self, timeout_seconds=300):
        """Poll mailbox for Railway OTP code"""
        print(f"📥 Waiting for Railway OTP (timeout: {timeout_seconds}s)...", flush=True)
        
        pattern = re.compile(r"\b(\d{6})\s+is your Railway", re.IGNORECASE)
        deadline = time.time() + timeout_seconds
        check_count = 0
        
        while time.time() < deadline:
            check_count += 1
            
            # Get messages
            try:
                resp = self._request("GET", "/messages")
                
                # Handle both list and hydra:member format
                if isinstance(resp, dict) and "hydra:member" in resp:
                    messages = resp["hydra:member"]
                else:
                    messages = resp if isinstance(resp, list) else []
                
                if check_count % 10 == 1:  # Log every 10th check
                    print(f"  Check #{check_count}: {len(messages)} message(s) in inbox", flush=True)
                
                for msg in messages:
                    subject = msg.get("subject", "")
                    intro = msg.get("intro", "")
                    msg_id = msg.get("id", "")
                    
                    # Check if it's from Railway
                    if "railway" in subject.lower() or "railway" in intro.lower():
                        print(f"  ✅ Found Railway email: {subject}", flush=True)
                        
                        # Try to extract code from intro/subject first
                        match = pattern.search(subject + " " + intro)
                        
                        if match:
                            code = match.group(1)
                            print(f"  ✅ Found OTP in preview: {code}", flush=True)
                            return code
                        
                        # Fetch full message
                        print(f"    Fetching full message...", flush=True)
                        full_msg = self._request("GET", f"/messages/{msg_id}")
                        
                        text = full_msg.get("text", "")
                        html = full_msg.get("html", [])
                        if isinstance(html, list):
                            html = " ".join(html)
                        
                        full_content = f"{subject} {intro} {text} {html}"
                        match = pattern.search(full_content)
                        
                        if match:
                            code = match.group(1)
                            print(f"  ✅ Found OTP in full message: {code}", flush=True)
                            return code
                
            except Exception as e:
                print(f"  ⚠️  Error checking messages: {e}", flush=True)
            
            time.sleep(3)
        
        raise TimeoutError("❌ Railway OTP email never arrived")


async def solve_turnstile(page, continue_btn, timeout_ms):
    """Handle Cloudflare Turnstile challenge using playwright-captcha"""
    print("🔐 Cloudflare Turnstile challenge detected...", flush=True)
    
    if CAPTCHA_SOLVER_AVAILABLE:
        print("   Using playwright-captcha auto-solver...", flush=True)
        try:
            solver = ClickSolver(
                framework=FrameworkType.PLAYWRIGHT_ASYNC,
                captcha_type=CaptchaType.CLOUDFLARE_TURNSTILE
            )
            
            # Let solver handle the captcha
            await solver.solve_captcha(page)
            print("   ✅ Captcha solved by auto-solver", flush=True)
            
            # Wait for button to be enabled
            await continue_btn.wait_for(state="enabled", timeout=10000)
            print("   ✅ Button enabled after solve", flush=True)
            return
            
        except Exception as e:
            print(f"   ⚠️  Auto-solver failed: {e}, falling back to manual click", flush=True)
    else:
        print("   ⚠️  playwright-captcha not available, using manual click", flush=True)
    
    # Fallback: manual click approach
    print("   Waiting for Turnstile widget to load...", flush=True)
    await asyncio.sleep(3)
    
    deadline = time.time() + (timeout_ms / 1000)
    poll_count = 0
    checkbox_clicked = False
    
    while time.time() < deadline:
        # Check if button is already enabled
        try:
            if await continue_btn.is_enabled(timeout=500):
                print(f"   ✅ Challenge passed after {poll_count}s", flush=True)
                return
        except:
            pass
        
        # Try to click checkbox (max once every 10 seconds)
        if not checkbox_clicked and poll_count % 10 == 0 and poll_count > 0:
            try:
                iframes = page.locator('iframe')
                count = await iframes.count()
                
                for i in range(count):
                    iframe_element = iframes.nth(i)
                    box = await iframe_element.bounding_box()
                    
                    if box and 250 < box['width'] < 350 and 50 < box['height'] < 100:
                        x = box['x'] + box['width'] * 0.15
                        y = box['y'] + box['height'] / 2
                        print(f"   Clicking Turnstile at ({x:.0f}, {y:.0f})...", flush=True)
                        await page.mouse.click(x, y)
                        await asyncio.sleep(5)
                        checkbox_clicked = True
                        break
            except Exception as e:
                print(f"   DEBUG: Click failed: {e}", flush=True)
        
        poll_count += 1
        await asyncio.sleep(1)
    
    raise TimeoutError("❌ Cloudflare challenge did not pass in time")


async def create_railway_account(mailbox: MailTmInbox, headless=False):
    """Automate Railway signup with Patchright"""
    print("\n🚂 Starting Railway account creation...", flush=True)
    
    async with async_playwright() as p:
        # Launch browser with Patchright (has built-in stealth)
        print("🌐 Launching browser...", flush=True)
        browser = await p.chromium.launch(
            channel="chrome",
            headless=headless
        )
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            # Navigate to Railway
            print(f"  Navigating to {RAILWAY_URL}...", flush=True)
            await page.goto(RAILWAY_URL, wait_until="domcontentloaded")
            
            # Check if already logged in
            if re.search(r"/dashboard(?:/|$)", page.url):
                print("  ✅ Already logged in!", flush=True)
                return
            
            # Click "Sign in"
            print("  Clicking 'Sign in'...", flush=True)
            await page.get_by_role("button", name="Sign in", exact=True).click()
            
            # Click "Log in using email"
            print("  Clicking 'Log in using email'...", flush=True)
            await page.get_by_role("button", name="Log in using email", exact=True).click()
            
            # Fill email
            print(f"  Entering email: {mailbox.address}", flush=True)
            email_input = page.locator('input[name="email"], input[placeholder="hello@email.com"]').last
            await email_input.wait_for(state="visible", timeout=ACTION_TIMEOUT)
            await email_input.fill(mailbox.address)
            
            # Wait for Turnstile
            continue_btn = page.get_by_role("button", name="Continue with Email", exact=True)
            await solve_turnstile(page, continue_btn, EMAIL_TIMEOUT)
            
            # Click continue
            print("  Clicking 'Continue with Email'...", flush=True)
            await continue_btn.click()
            
            # Wait for Railway to send email
            print("  Waiting 5s for Railway to send email...", flush=True)
            await asyncio.sleep(5)
            
            # Get OTP from mailbox
            code = mailbox.wait_for_railway_code(timeout_seconds=300)
            
            # Fill OTP
            print(f"  Entering OTP: {code}", flush=True)
            
            # Try multiple methods to find OTP input
            otp_filled = False
            
            # Method 1: Look for Magic.link modal with 6 input boxes (no iframe)
            try:
                # The modal is directly on the page, not in iframe
                # Find the container with "Please enter the code sent to"
                modal = page.locator('[role="dialog"], [class*="modal"]').filter(has_text="Please enter the code")
                
                if await modal.count() > 0:
                    print("    Found Magic.link modal (direct, no iframe)", flush=True)
                    
                    # Find all input boxes in the modal
                    inputs = modal.locator('input[type="text"], input[inputmode="numeric"]')
                    input_count = await inputs.count()
                    print(f"    Found {input_count} input boxes", flush=True)
                    
                    if input_count == 6:
                        # Fill each digit
                        for i, digit in enumerate(code):
                            await inputs.nth(i).fill(digit)
                            await asyncio.sleep(0.1)
                        otp_filled = True
                        print("    ✅ Filled OTP in modal", flush=True)
            except Exception as e:
                print(f"    Method 1 failed: {e}", flush=True)
            
            # Method 2: Try iframe approach (fallback)
            if not otp_filled:
                try:
                    magic_frame = page.frame_locator('iframe[src*="auth.magic.link"], iframe[src*="magic"], iframe[title*="Magic"]')
                    inputs = magic_frame.locator('input[type="text"], input[inputmode="numeric"]')
                    await inputs.first.wait_for(state="visible", timeout=10000)
                    
                    for i, digit in enumerate(code):
                        await inputs.nth(i).fill(digit)
                        await asyncio.sleep(0.1)
                    otp_filled = True
                    print("    ✅ Filled OTP via iframe", flush=True)
                except Exception as e:
                    print(f"    Method 2 failed: {e}", flush=True)
            
            # Method 3: Find ANY 6 inputs that look like OTP
            if not otp_filled:
                try:
                    # Look for 6 consecutive text inputs
                    all_inputs = page.locator('input[type="text"]:visible, input[inputmode="numeric"]:visible')
                    count = await all_inputs.count()
                    print(f"    Found {count} visible text inputs on page", flush=True)
                    
                    # Try to find a group of 6
                    if count >= 6:
                        # Use the first 6
                        for i, digit in enumerate(code):
                            await all_inputs.nth(i).fill(digit)
                            await asyncio.sleep(0.1)
                        otp_filled = True
                        print("    ✅ Filled OTP via generic inputs", flush=True)
                except Exception as e:
                    print(f"    Method 3 failed: {e}", flush=True)
            
            if not otp_filled:
                raise RuntimeError(f"❌ Could not find OTP input. Code was: {code}")
            
            # Wait for dashboard redirect
            print("  Waiting for redirect to dashboard...", flush=True)
            await page.wait_for_url(re.compile(r"/dashboard(?:/|$)"), timeout=EMAIL_TIMEOUT)
            
            # Accept ToS if prompted
            print("  Checking for Terms of Service dialog...", flush=True)
            try:
                dialog = page.get_by_role("dialog").filter(has_text="Terms of Service").last
                if await dialog.count() > 0 and await dialog.is_visible():
                    print("    Accepting ToS...", flush=True)
                    
                    # Scroll to bottom
                    scroll_area = dialog.locator("div.overflow-y-auto").last
                    await scroll_area.evaluate("""element => {
                        element.scrollTop = element.scrollHeight;
                        element.dispatchEvent(new Event('scroll', { bubbles: true }));
                    }""")
                    
                    # Click agree buttons
                    for btn_name in [
                        "I agree with Railway's Terms of Service",
                        "I agree to the Fair Use Policy"
                    ]:
                        try:
                            btn = dialog.get_by_role("button", name=btn_name, exact=True)
                            await btn.wait_for(state="visible", timeout=5000)
                            await btn.click()
                        except:
                            pass
            except:
                pass
            
            print(f"\n✅ SUCCESS! Railway account created", flush=True)
            print(f"   Email: {mailbox.address}", flush=True)
            print(f"   Password: {mailbox.password}", flush=True)
            print(f"   Dashboard: {page.url}", flush=True)
            
            # Save session
            save_session(mailbox, page.url)
            
            # Keep browser open
            input("\n⏸️  Press Enter to close browser...")
            
        except Exception as e:
            print(f"\n❌ Error during automation: {e}", flush=True)
            print(f"   Current URL: {page.url}", flush=True)
            input("   Fix manually in browser, then press Enter to exit...")
            raise
        finally:
            await browser.close()


def save_session(mailbox, dashboard_url):
    """Save Railway session details"""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    session_file = SESSIONS_DIR / f"railway_{timestamp}.json"
    
    session_data = {
        "email": mailbox.address,
        "password": mailbox.password,
        "account_id": mailbox.account_id,
        "dashboard_url": dashboard_url,
        "created_at": timestamp
    }
    
    session_file.write_text(json.dumps(session_data, indent=2))
    print(f"\n💾 Session saved: {session_file}", flush=True)
    
    # Sync to Mega if available
    try:
        result = subprocess.run(
            ["rclone", "copy", str(session_file), MEGA_REMOTE],
            capture_output=True,
            timeout=30
        )
        if result.returncode == 0:
            print(f"☁️  Synced to Mega: {MEGA_REMOTE}", flush=True)
    except:
        pass


def get_current_ip(proxy=None):
    """Get current IP address"""
    try:
        proxies = {"http": proxy, "https": proxy} if proxy else None
        resp = requests.get("https://api.ipify.org", proxies=proxies, timeout=10)
        return resp.text.strip()
    except:
        return "unknown"


def rotate_warp_ip():
    """Rotate WARP IP using wgcf (system-wide WireGuard)"""
    print("🔄 Rotating WARP IP via wgcf...", flush=True)
    
    # Get current IP
    current_ip = get_current_ip()
    print(f"🌐 Current IP (before): {current_ip}", flush=True)
    
    try:
        # Run wgcf update in home directory where wgcf-account.toml exists
        result = subprocess.run(
            ["wgcf", "update"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(Path.home())
        )
        
        if result.returncode != 0:
            print(f"⚠️  wgcf update failed: {result.stderr.strip()}", flush=True)
            return False
        
        # Regenerate WireGuard config
        result = subprocess.run(
            ["wgcf", "generate"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(Path.home())
        )
        
        if result.returncode != 0:
            print(f"⚠️  wgcf generate failed: {result.stderr.strip()}", flush=True)
            return False
        
        print("✅ WARP config regenerated", flush=True)
        
        # Restart wg-quick to apply new config (requires sudo)
        try:
            subprocess.run(["sudo", "wg-quick", "down", "wgcf"], capture_output=True, timeout=10)
            time.sleep(1)
            subprocess.run(["sudo", "wg-quick", "up", "wgcf"], capture_output=True, timeout=10)
            time.sleep(2)
            print("✅ WireGuard interface restarted", flush=True)
        except:
            print("⚠️  Could not restart WireGuard (run manually: sudo wg-quick down wgcf && sudo wg-quick up wgcf)", flush=True)
        
        # Get new IP
        new_ip = get_current_ip()
        print(f"🌐 New IP (after): {new_ip}", flush=True)
        
        if new_ip != current_ip:
            print(f"✅ IP changed successfully!", flush=True)
            return True
        else:
            print(f"⚠️  IP did not change", flush=True)
            return False
        
    except Exception as e:
        print(f"⚠️  WARP rotation failed: {e}", flush=True)
        return False


def check_warp_proxy():
    """Check if WARP SOCKS proxy is running"""
    try:
        proxy = "socks5h://127.0.0.1:40000"
        resp = requests.get("https://api.ipify.org", proxies={"http": proxy, "https": proxy}, timeout=5)
        print(f"✅ WARP proxy is running (IP: {resp.text.strip()})", flush=True)
        return proxy
    except:
        print("⚠️  WARP proxy (127.0.0.1:40000) is not running; using direct connection.", flush=True)
        return None


def check_tor_proxy():
    """Check if Tor SOCKS proxy is running"""
    try:
        proxy = "socks5h://127.0.0.1:9050"
        resp = requests.get("https://check.torproject.org/api/ip", 
                          proxies={"http": proxy, "https": proxy}, 
                          timeout=10)
        data = resp.json()
        if data.get("IsTor"):
            print(f"✅ Tor proxy is running (IP: {data.get('IP')})", flush=True)
            return proxy
        else:
            print("⚠️  Proxy at 9050 is not Tor", flush=True)
            return None
    except:
        print("⚠️  Tor proxy (127.0.0.1:9050) is not running; using direct connection.", flush=True)
        return None


async def main():
    print("=" * 50)
    print("🚂 Railway Account Creator - Mail.tm Edition")
    print("=" * 50)
    print(f"📁 Sessions directory: {SESSIONS_DIR}")
    print(f"🌐 Mega remote: {MEGA_REMOTE}")
    print()
    
    # WARP disabled - it breaks network connectivity
    # Only use Tor proxy (safe, script-only)
    proxy = None
    if "--tor" in sys.argv:
        proxy = check_tor_proxy()
    
    if not proxy:
        print("🌐 Using direct connection (no proxy)", flush=True)
    print()
    
    # Create mailbox
    mailbox = MailTmInbox(proxy=proxy)
    mailbox.create()
    
    # Create Railway account
    headless = "--headless" in sys.argv
    await create_railway_account(mailbox, headless=headless)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user", flush=True)
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}", flush=True)
        sys.exit(1)
