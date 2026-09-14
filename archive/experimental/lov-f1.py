#!/usr/bin/env python3
"""Lovable automation with TempMailHub API-only approach.

This version uses ONLY the TempMailHub API (no page scraping) based on the 
working monitor_inbox.sh approach.

Features:
- ✅ Ad blocking
- ✅ WARP proxy support (optional)
- ✅ API-only email creation/validation
- ✅ Password reset flow
- ✅ Gmail validation (no dots/+)
- ✅ Mailbox testing before use
- ✅ Email deduplication
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)
from playwright.async_api import async_playwright


TEMPMAIL_API = "https://api.tempmailhub.org"
LOVABLE_URL = "https://lovable.dev/"
RESET_LINK_RE = re.compile(r"https?://[^\"'\\\s<>]*lovable\.dev[^\"'\\\s<>]*", re.I)
WARP_PROXY = "socks5://127.0.0.1:40000"
USED_EMAILS_FILE = "/home/alan/Documents/used-tempmailhub-emails.txt"

AD_BLOCK_PATTERNS = (
    "doubleclick.net", "googlesyndication.com", "googleadservices.com",
    "google-analytics.com", "googletagmanager.com/gtag", "analytics.google.com",
    "adservice.google", "adroll.com", "outbrain.com", "taboola.com",
    "amazon-adsystem.com", "moatads.com", "scorecardresearch.com", "criteo.com",
    "teads.tv", "doubleverify.com", "yieldmo.com", "adnxs.com", "adsafeprotected.com",
    "adzerk.net", "pubmatic.com", "casalemedia.com", "openx.net", "rubiconproject.com",
)


class FlowError(RuntimeError):
    """Raised when a site does not reach the expected state."""


def proxy_settings() -> dict | None:
    """WARP SOCKS proxy config (optional)."""
    import socket
    try:
        with socket.create_connection(("127.0.0.1", 40000), timeout=2):
            return {"server": WARP_PROXY}
    except OSError:
        print("WARP proxy (127.0.0.1:40000) is not running; using direct connection.", file=sys.stderr)
        return None


def load_used_emails() -> set:
    """Load already-used emails."""
    try:
        with open(USED_EMAILS_FILE, "r") as f:
            return set(line.strip().lower() for line in f if line.strip())
    except FileNotFoundError:
        return set()


def save_used_email(email: str) -> None:
    """Save email to used list."""
    with open(USED_EMAILS_FILE, "a") as f:
        f.write(f"{email.lower()}\n")
    print(f"💾 Saved {email} to used list", file=sys.stderr)


def is_valid_gmail(email: str) -> bool:
    """Validate Gmail: must be @gmail.com with NO dots or + before @"""
    if not email or '@gmail.com' not in email.lower():
        return False
    local_part = email.split('@')[0]
    if '.' in local_part or '+' in local_part:
        return False
    return True


def api_request(endpoint: str, method: str = "POST", timeout: int = 30) -> tuple[int, str]:
    """Make API request to TempMailHub (similar to monitor script)."""
    url = f"{TEMPMAIL_API}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "Origin": "https://tempmailhub.org"
    }
    
    last_error = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=headers, method=method)
            if method == "POST":
                req.data = b'{}'
            
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.status, response.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode(errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last_error = error
            if attempt < 2:
                import time
                time.sleep(2)
    
    raise FlowError(f"TempMailHub API request failed: {last_error}")


def create_working_email() -> tuple[str, str]:
    """Create valid Gmail via API with mailbox validation (like monitor script)."""
    import time
    
    used_emails = load_used_emails()
    print(f"📋 Loaded {len(used_emails)} used emails", file=sys.stderr)
    
    max_attempts = 30
    for attempt in range(1, max_attempts + 1):
        print(f"Attempt {attempt}/{max_attempts}: Creating email...", file=sys.stderr)
        
        # Create email via API
        status, raw = api_request("/emails")
        if status != 201:
            print(f"  ❌ Failed to create (status {status})", file=sys.stderr)
            time.sleep(2)
            continue
        
        try:
            account = json.loads(raw)
            email = account["email"]
            email_id = str(account["email_id"])
        except (KeyError, ValueError) as exc:
            print(f"  ❌ Malformed response", file=sys.stderr)
            time.sleep(2)
            continue
        
        print(f"  Created: {email} (ID: {email_id})", file=sys.stderr)
        
        # Skip already-used emails
        if email.lower() in used_emails:
            print(f"  ⚠️  Already used - skipping", file=sys.stderr)
            time.sleep(1)
            continue
        
        # Validate Gmail format
        if not is_valid_gmail(email):
            print(f"  ❌ Invalid Gmail format (has dots/+ or not @gmail.com)", file=sys.stderr)
            time.sleep(1)
            continue
        
        print(f"  ✅ Valid Gmail format", file=sys.stderr)
        print(f"  Testing mailbox...", file=sys.stderr)
        
        # Wait for mailbox initialization
        time.sleep(2)
        
        # Test mailbox (like monitor script does)
        status, msg_response = api_request(f"/emails/messages?email_id={email_id}")
        
        # Check for errors (like monitor script)
        if "imap" in msg_response.lower() and "failed" in msg_response.lower():
            print(f"  ❌ IMAP auth error - trying next...", file=sys.stderr)
            continue
        elif "authentication" in msg_response.lower() and "failed" in msg_response.lower():
            print(f"  ❌ Auth failed - trying next...", file=sys.stderr)
            continue
        elif not msg_response or msg_response == "":
            print(f"  ❌ Empty response - trying next...", file=sys.stderr)
            continue
        elif status == 200:
            # Check if mailbox is working
            if "norecentemails" in msg_response.lower() or '"emails":[' in msg_response:
                print(f"  ✅ Mailbox working!", file=sys.stderr)
                print(f"✅ FOUND WORKING GMAIL: {email} (ID: {email_id})", file=sys.stderr)
                return email, email_id
        
        print(f"  ❓ Unknown response - trying next...", file=sys.stderr)
        time.sleep(1)
    
    raise FlowError(f"Could not find working Gmail mailbox after {max_attempts} attempts")


def read_messages(email_id: str) -> list:
    """Read messages from mailbox via API."""
    status, raw = api_request(f"/emails/messages?email_id={email_id}", timeout=15)
    if status != 200:
        return []
    
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    
    # Extract emails list
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("emails", "messages", "mails", "items", "data"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


async def read_reset_link(email_id: str, timeout: float = 180) -> str:
    """Poll API for Lovable reset email."""
    import time
    deadline = time.time() + timeout
    check_count = 0
    
    while time.time() < deadline:
        check_count += 1
        if check_count % 5 == 1:
            print(f"  📥 Check #{check_count}: Polling for emails...", file=sys.stderr)
        
        messages = read_messages(email_id)
        
        for message in messages:
            subject = str(message.get("subject") or message.get("title") or "")
            if "lovable" not in subject.lower():
                continue
            
            # Extract link from message body
            body = json.dumps(message, default=str)
            match = RESET_LINK_RE.search(body)
            if match:
                link = html.unescape(match.group(0))
                print(f"✅ Found Lovable reset link!", file=sys.stderr)
                return link
        
        await asyncio.sleep(8)
    
    raise FlowError("Timed out waiting for Lovable reset email")


async def install_ad_blocker(page: Page) -> None:
    """Block ads/trackers in-process."""
    def should_block(url: str) -> bool:
        lowered = url.lower()
        return any(needle in lowered for needle in AD_BLOCK_PATTERNS)
    
    async def handler(route):
        if should_block(route.request.url):
            await route.abort()
        else:
            await route.continue_()
    
    await page.route("**/*", handler)
    await page.add_init_script(
        "() => { Object.defineProperty(navigator, 'webdriver', {get: () => undefined}); }"
    )


async def navigate(page: Page, url: str) -> None:
    """Navigate with timeout."""
    await page.goto(url, wait_until="domcontentloaded", timeout=60_000)


async def body_text(page: Page) -> str:
    """Get page body text."""
    return await page.locator("body").inner_text()


async def click_exact(page: Page, text: str) -> None:
    """Click button/link with exact text."""
    await page.get_by_role("button", name=text, exact=True).click()


async def wait_for_lovable_ready(page: Page) -> None:
    """Wait for Lovable page to be ready."""
    deadline = asyncio.get_running_loop().time() + 30
    while asyncio.get_running_loop().time() < deadline:
        text = await body_text(page)
        if "Log in" in text or "Dashboard" in text:
            return
        await page.wait_for_timeout(500)
    raise FlowError("Lovable page did not load")


async def dismiss_cookie_banner(page: Page) -> None:
    """Dismiss cookie banner if present."""
    try:
        reject = page.get_by_role("button", name="Reject all")
        if await reject.count():
            await reject.click(timeout=2_000)
    except:
        pass


async def sign_out_if_needed(page: Page) -> None:
    """Sign out if already logged in."""
    try:
        menu = page.locator('button[aria-label="Account menu"]')
        if await menu.count():
            await menu.click(timeout=2_000)
            await page.get_by_role("menuitem", name="Sign out").click(timeout=2_000)
            await page.wait_for_timeout(2_000)
    except:
        pass


async def request_login(page: Page, email: str) -> str:
    """Submit email and determine signup vs reset path."""
    await navigate(page, LOVABLE_URL)
    await wait_for_lovable_ready(page)
    await dismiss_cookie_banner(page)
    await sign_out_if_needed(page)
    
    if "/dashboard" in page.url:
        await navigate(page, LOVABLE_URL)
        await wait_for_lovable_ready(page)
    
    await click_exact(page, "Log in")
    await page.locator('input[type="email"]').last.fill(email)
    await click_exact(page, "Continue")
    
    deadline = asyncio.get_running_loop().time() + 25
    while asyncio.get_running_loop().time() < deadline:
        text = await body_text(page)
        if "No account found" in text or "Create your account" in text:
            return "signup"
        if page.url.startswith("https://lovable.dev/login") and await page.locator('input[type="password"]').count():
            return "reset"
        await page.wait_for_timeout(500)
    
    raise FlowError(f"Lovable did not react to email on {page.url}")


async def do_password_reset(page: Page, email: str) -> None:
    """Request password reset."""
    await page.get_by_role("link", name="Forgot password?").click()
    await page.locator('input[type="email"]').fill(email)
    await click_exact(page, "Reset Password")
    await page.wait_for_timeout(2_000)


async def do_signup(page: Page, email: str, password: str) -> str:
    """Attempt signup flow."""
    await page.locator('input[name="email"]').fill(email)
    await page.locator('input[name="password"]').fill(password)
    await click_exact(page, "Sign up")
    
    deadline = asyncio.get_running_loop().time() + 30
    while asyncio.get_running_loop().time() < deadline:
        text = await body_text(page)
        if "verify" in text.lower() or "check your email" in text.lower():
            return "verify"
        if "/dashboard" in page.url:
            return "login"
        await page.wait_for_timeout(500)
    
    return "verify"


async def set_password_and_verify(page: Page, reset_url: str, password: str) -> None:
    """Set password via reset link."""
    await navigate(page, reset_url)
    new_password = page.locator('input[name="newPassword"]')
    confirm_password = page.locator('input[name="confirmPassword"]')
    await new_password.wait_for(timeout=30_000)
    await new_password.fill(password)
    await confirm_password.fill(password)
    await click_exact(page, "Reset Password")
    
    deadline = asyncio.get_running_loop().time() + 45
    while asyncio.get_running_loop().time() < deadline:
        text = await body_text(page)
        if "Your password has been updated" in text:
            break
        if "/dashboard" in page.url and "Dashboard" in text:
            return
        if "Password must contain" in text:
            raise FlowError("Lovable rejected password requirements")
        await page.wait_for_timeout(500)
    else:
        raise FlowError("Lovable did not confirm password reset")
    
    await wait_for_dashboard(page, timeout=45)


async def wait_for_dashboard(page: Page, timeout: float = 60) -> None:
    """Wait for dashboard to load."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if "/dashboard" in page.url:
            text = await body_text(page)
            if "Dashboard" in text:
                return
        await page.wait_for_timeout(500)
    raise FlowError("Dashboard did not load")


async def verify_egress_ip(context: BrowserContext) -> str:
    """Check browser egress IP."""
    page = await context.new_page()
    try:
        await page.goto("https://cloudflare.com/cdn-cgi/trace", timeout=15_000)
        text = await page.locator("body").inner_text()
        return text.strip()
    except Exception as e:
        return f"egress probe failed ({e})"
    finally:
        await page.close()


async def connect_browser(playwright_support, cdp_url: str | None) -> Browser:
    """Connect to external CDP browser or launch our own."""
    if cdp_url:
        browser = await playwright_support.chromium.connect_over_cdp(cdp_url, timeout=60_000)
        if not browser.contexts:
            raise FlowError("Connected browser has no context")
        return browser
    
    return await playwright_support.chromium.launch(
        channel="chrome",
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
        proxy=proxy_settings(),
    )


async def get_lovable_page(context: BrowserContext) -> Page:
    """Get or create Lovable page."""
    for page in context.pages:
        if "lovable.dev" in page.url:
            return page
    return await context.new_page()


def keep_browser_open() -> bool:
    """Check if we should keep browser open."""
    return os.getenv("KEEP_BROWSER", "").lower() in ("1", "true", "yes")


async def run(cdp_url: str | None) -> dict[str, object]:
    async with async_playwright() as playwright:
        browser = await connect_browser(playwright, cdp_url)
        if browser.contexts:
            context = browser.contexts[0]
        else:
            context = await browser.new_context(viewport={"width": 1440, "height": 900})
        
        lovable_page = await get_lovable_page(context)
        await install_ad_blocker(lovable_page)
        print(f"Browser egress IP: {await verify_egress_ip(context)}")
        
        last_error: Optional[Exception] = None
        for attempt in range(1, 4):
            try:
                # Create email via API (like monitor script)
                email, email_id = create_working_email()
                password = email if re.search(r"\d", email) else f"{email}1"
                
                mode = await request_login(lovable_page, email)
                
                if mode == "signup":
                    print("Lovable: No account found, creating one...")
                    try:
                        signup_result = await do_signup(lovable_page, email, password)
                    except Exception as exc:
                        print(f"Signup failed ({exc}), using reset path...", file=sys.stderr)
                        await navigate(lovable_page, f"{LOVABLE_URL}login")
                        await request_login(lovable_page, email)
                        await do_password_reset(lovable_page, email)
                        reset_url = await read_reset_link(email_id, timeout=180)
                        await set_password_and_verify(lovable_page, reset_url, password)
                    else:
                        if signup_result == "verify":
                            print("Lovable: Email verification required...")
                            reset_url = await read_reset_link(email_id, timeout=180)
                            await navigate(lovable_page, reset_url)
                            await wait_for_dashboard(lovable_page, timeout=60)
                        elif signup_result == "login":
                            print("Account created, logging in...")
                            await lovable_page.locator('input[type="password"]').last.fill(password)
                            await click_exact(lovable_page, "Log in")
                            await wait_for_dashboard(lovable_page, timeout=45)
                else:
                    print("Lovable: Account exists, requesting password reset...")
                    await do_password_reset(lovable_page, email)
                    reset_url = await read_reset_link(email_id, timeout=180)
                    await set_password_and_verify(lovable_page, reset_url, password)
                
                break
            except Exception as exc:
                last_error = exc
                print(f"Attempt {attempt} failed: {exc}", file=sys.stderr)
        else:
            raise FlowError(f"All attempts failed: {last_error}") from last_error
        
        # Verify dashboard
        dashboard_text = await body_text(lovable_page)
        account_menu = lovable_page.locator('button[aria-label="Account menu"]')
        try:
            await account_menu.wait_for(state="visible", timeout=20_000)
        except PlaywrightTimeoutError as exc:
            raise FlowError("Dashboard account menu did not render") from exc
        
        if "/dashboard" not in lovable_page.url or "Dashboard" not in dashboard_text:
            raise FlowError("Dashboard loaded but account not verified")
        
        # Save email to used list
        save_used_email(email)
        
        result = {
            "verified": True,
            "email": email,
            "password": password,
            "dashboard_url": lovable_page.url,
        }
        
        print(json.dumps(result, indent=2))
        
        if keep_browser_open() and not cdp_url:
            print("Browser staying open. Press Enter to close...", file=sys.stderr)
            input()
            await browser.close()
        elif not cdp_url:
            await browser.close()
        
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Lovable account via TempMailHub API")
    parser.add_argument("--cdp-url", help="Connect to existing browser via CDP")
    args = parser.parse_args()
    
    cdp = args.cdp_url or os.getenv("BU_CDP_WS")
    
    try:
        asyncio.run(run(cdp))
    except FlowError as e:
        print(f"Automation failed: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
