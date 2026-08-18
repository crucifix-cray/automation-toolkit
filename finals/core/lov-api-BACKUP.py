#!/usr/bin/env python3
"""Lovable automation with TRUE API-ONLY mode (no TempMail page).

This version uses ONLY the TempMailHub API - NO page scraping, NO TempMail tab.
Based on the working monitor_inbox.sh approach.

Features:
- ✅ TRUE API-ONLY (no TempMail page)
- ✅ Ad blocking (Lovable page only)
- ✅ WARP proxy support (optional)
- ✅ Gmail validation (no dots/+)
- ✅ Mailbox testing before use
- ✅ Email deduplication
- ✅ Password reset flow
- ✅ Session saving
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
from datetime import datetime
from pathlib import Path
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
USED_EMAILS_FILE = os.environ.get(
    "USED_EMAILS_FILE", "/home/alan/Documents/used-tempmailhub-emails.txt"
)

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
            return {
                "server": WARP_PROXY,
                "bypass": "api.tempmailhub.org,api.lovable.dev,127.0.0.1,localhost",
            }
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
    os.makedirs(os.path.dirname(USED_EMAILS_FILE), exist_ok=True)
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


def api_request(endpoint: str, method: str = "POST", data: dict = None, timeout: int = 60) -> tuple[int, str]:
    """Make API request to TempMailHub."""
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
                if data:
                    req.data = json.dumps(data).encode('utf-8')
                else:
                    req.data = b'{}'
            
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.status, response.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode(errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last_error = error
            if attempt < 2:
                import time
                time.sleep(3)
    
    raise FlowError(f"TempMailHub API request failed: {last_error}")


def lovable_email_available(email: str) -> bool:
    """Fast pre-check: does this email already have a Lovable account?
    On any error, be optimistic - let the browser flow decide."""
    import json as _json
    import urllib.request as _urllib

    req = _urllib.Request(
        "https://api.lovable.dev/auth/check-auth-provider",
        data=_json.dumps({"email": email}).encode(),
        headers={
            "Content-Type": "application/json",
            "Origin": "https://lovable.dev",
            "Referer": "https://lovable.dev/",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        },
        method="POST",
    )
    try:
        with _urllib.request.urlopen(req, timeout=15) as response:
            data = _json.loads(response.read().decode())
            return not data.get("user_exists", True)
    except Exception:
        return True


def create_working_email() -> tuple[str, str]:
    """Create valid Gmail via API with mailbox validation (like monitor script)."""
    import time
    
    used_emails = load_used_emails()
    print(f"📋 Loaded {len(used_emails)} used emails", file=sys.stderr)
    
    max_attempts = 30
    for attempt in range(1, max_attempts + 1):
        print(f"🔄 Attempt {attempt}/{max_attempts}: Creating email via API...", file=sys.stderr)
        
        # Create email via API - REQUEST GMAIL EXPLICITLY
        status, raw = api_request("/emails", data={"domain": "gmail.com"})
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
        
        print(f"  📧 Created: {email} (ID: {email_id})", file=sys.stderr)
        
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
        print(f"  🔍 Testing mailbox via API...", file=sys.stderr)
        
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
                if not lovable_email_available(email):
                    print(f"  ⚠️  Email already registered on Lovable - trying next...", file=sys.stderr)
                    time.sleep(1)
                    continue
                print(f"  ✅ Mailbox working!", file=sys.stderr)
                print(f"🎉 FOUND WORKING GMAIL: {email} (ID: {email_id})", file=sys.stderr)
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


async def read_reset_link(email_id: str, timeout: float = 180, page: Page | None = None) -> str:
    """Poll API for Lovable reset email (with optional browser health check)."""
    import time
    deadline = time.time() + timeout
    check_count = 0
    
    while time.time() < deadline:
        check_count += 1
        if check_count % 5 == 1:
            print(f"  📥 Check #{check_count}: Polling API for emails...", file=sys.stderr)
        
        # Check if browser is still alive (if page provided)
        if page:
            try:
                await page.evaluate("1 + 1", timeout=2_000)
            except Exception as exc:
                if "closed" in str(exc).lower() or "crashed" in str(exc).lower() or "terminated" in str(exc).lower():
                    raise FlowError(f"Browser died during email polling: {exc}") from exc
        
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
    """Navigate with timeout and Cloudflare handling."""
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    except PlaywrightTimeoutError:
        # Cloudflare may keep the initial navigation open while it verifies the browser
        pass


async def body_text(page: Page) -> str:
    """Get page body text."""
    try:
        return await page.locator("body").inner_text(timeout=3_000)
    except PlaywrightTimeoutError:
        return ""


async def click_exact(page: Page, text: str) -> None:
    """Click button/link with exact text - FORCE CLICK with fallbacks."""
    # Try button first
    locator = page.get_by_role("button", name=text, exact=True)
    if await locator.count() == 0:
        # Try menuitem
        locator = page.get_by_role("menuitem", name=text, exact=True)
    if await locator.count() == 0:
        # Try any text
        locator = page.get_by_text(text, exact=True)
    if await locator.count() == 0:
        raise FlowError(f"Could not find clickable text {text!r}")
    
    # FORCE CLICK - this is the key!
    try:
        await locator.last.click(timeout=15_000, force=True)
    except Exception as exc:
        if "closed" in str(exc).lower() or "target page" in str(exc).lower():
            raise FlowError(f"Page closed while clicking {text!r}") from exc
        raise


async def wait_for_lovable_ready(page: Page) -> None:
    """Wait for Lovable page to be ready."""
    deadline = asyncio.get_running_loop().time() + 75
    while asyncio.get_running_loop().time() < deadline:
        text = await body_text(page)
        
        # Wait for Cloudflare security check
        if "Performing security verification" in text:
            await page.wait_for_timeout(2_500)
            continue
        
        # Retry on error
        if "We hit a snag" in text:
            try:
                await page.reload(wait_until="domcontentloaded", timeout=30_000)
            except PlaywrightTimeoutError:
                pass
            await page.wait_for_timeout(2_500)
            continue
        
        if "Log in" in text or ("/dashboard" in page.url and "Dashboard" in text):
            return
        
        await page.wait_for_timeout(1_000)
    
    raise FlowError("Lovable did not finish loading or its security check")


async def dismiss_cookie_banner(page: Page) -> None:
    """Dismiss cookie banner if present."""
    try:
        for label in ("Reject all", "Accept all", "OK"):
            reject = page.get_by_role("button", name=label, exact=True)
            if await reject.count() and await reject.last.is_visible():
                await reject.last.click(timeout=2_000, force=True)
                return
    except:
        pass


async def sign_out_if_needed(page: Page) -> None:
    """Sign out if already logged in."""
    account = page.locator('button[aria-label="Account menu"]')
    
    # If on dashboard but account menu not visible, try reload
    if "/dashboard" in page.url and await account.count() == 0:
        try:
            await page.reload(wait_until="domcontentloaded", timeout=30_000)
        except PlaywrightTimeoutError:
            pass
        await page.wait_for_timeout(2_500)
    
    # Check if on dashboard
    if "/dashboard" in page.url:
        try:
            await account.last.wait_for(state="visible", timeout=20_000)
        except PlaywrightTimeoutError:
            # Account menu didn't appear, might be logged out already
            return
    
    if await account.count() == 0 or not await account.last.is_visible():
        return
    
    # Try to open menu and click sign out (with retry)
    sign_out = page.get_by_role("menuitem", name="Sign out", exact=True)
    for _menu_try in range(3):
        if await sign_out.count() and await sign_out.last.is_visible():
            await sign_out.last.click(force=True)
            break
        try:
            await account.last.evaluate("node => node.click()")
            await page.wait_for_timeout(500)
        except Exception:
            pass
    else:
        # Menu didn't open after 3 tries
        return
    
    # Wait for sign out to complete
    deadline = asyncio.get_running_loop().time() + 30
    while asyncio.get_running_loop().time() < deadline:
        if "/dashboard" not in page.url and "Log in" in await body_text(page):
            return
        await page.wait_for_timeout(500)


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
    
    # Wait for email input to appear (with retry)
    email_input = page.locator('input[type="email"]').last
    for login_try in range(2):
        try:
            await email_input.wait_for(state="visible", timeout=15_000)
            break
        except PlaywrightTimeoutError:
            if login_try:
                raise FlowError("Lovable login modal did not render its email field")
            await click_exact(page, "Log in")
    
    await email_input.fill(email)
    await click_exact(page, "Continue")
    
    deadline = asyncio.get_running_loop().time() + 25
    while asyncio.get_running_loop().time() < deadline:
        text = await body_text(page)
        forgot_password = page.get_by_text("Forgot password?", exact=True)
        
        # Check for existing account (password input + forgot password button)
        if (
            page.url.startswith("https://lovable.dev/login")
            and await page.locator('input[type="password"]').count()
            and await forgot_password.count()
        ):
            return "reset"
        
        # Check for new account
        if "No account found" in text or "Create your account" in text:
            return "signup"
        
        await page.wait_for_timeout(500)
    
    raise FlowError(f"Lovable did not react to the email on {page.url}")


async def do_password_reset(page: Page, email: str) -> None:
    """Request password reset."""
    password_input = page.locator('input[type="password"]')
    await password_input.wait_for(timeout=20_000)
    if not (await password_input.input_value()).strip():
        await password_input.fill("dummy1234")
    await click_exact(page, "Forgot password?")
    
    reset_email = page.locator('input[placeholder*="email"]')
    if await reset_email.count() == 0:
        reset_email = page.locator('input[type="email"]')
    current_email = (await reset_email.last.input_value()).strip().lower()
    if current_email != email.lower():
        await click_exact(page, "Use a different email")
        reset_email = page.locator('input[placeholder*="email"]')
        await reset_email.last.fill(email)
    
    send = page.get_by_role("button", name="Send reset link", exact=True)
    if await send.count() == 0:
        send = page.get_by_role("button", name=re.compile(r"Send reset", re.I))
    await send.last.click(force=True)
    await page.wait_for_timeout(3_000)


async def do_signup(page: Page, email: str, password: str) -> str:
    """Attempt signup flow."""
    try:
        passwords = page.locator('input[type="password"]')
        await passwords.nth(0).wait_for(timeout=20_000)
        await passwords.nth(0).fill(password)
        if await passwords.count() >= 2:
            await passwords.nth(1).fill(password)
        await click_exact(page, "Create your account")
        
        deadline = asyncio.get_running_loop().time() + 60
        while asyncio.get_running_loop().time() < deadline:
            text = await body_text(page)
            if "/dashboard" in page.url and "Dashboard" in text:
                return "dashboard"
            if any(hint in text for hint in ("verif", "code", "Check your email", "confirm your email")):
                return "verify"
            if (
                page.url.startswith("https://lovable.dev/login")
                and await page.locator('input[type="password"]').count()
            ):
                return "login"
            await page.wait_for_timeout(500)
        
        raise FlowError("Lovable did not finish the account creation")
    
    except Exception as exc:
        # Debug screenshot on failure
        try:
            screenshot_path = "/tmp/lovable_signup_debug.png"
            await page.screenshot(path=screenshot_path)
            print(f"📸 Signup debug screenshot saved: {screenshot_path}", file=sys.stderr)
        except Exception as snap_error:
            print(f"Screenshot on signup failure failed: {snap_error}", file=sys.stderr)
        
        try:
            stored_text = await body_text(page)
        except Exception:
            stored_text = ""
        
        print(
            f"Signup debug: url={page.url} text={stored_text[:300]!r}".replace("\n", " "),
            file=sys.stderr,
        )
        raise


async def set_password_and_verify(page: Page, reset_url: str, password: str) -> None:
    """Set password via reset link."""
    await navigate(page, reset_url)
    
    # Check for invalid link
    if "invalid verification code" in (await body_text(page)).lower():
        raise FlowError("Lovable reset link is invalid or stale")
    
    new_password = page.locator('input[name="newPassword"]')
    confirm_password = page.locator('input[name="confirmPassword"]')
    await new_password.wait_for(timeout=30_000)
    await new_password.fill(password)
    await confirm_password.fill(password)
    await click_exact(page, "Reset Password")
    
    # Wait for confirmation and redirect (Firebase is SLOW on GH Actions)
    deadline = asyncio.get_running_loop().time() + 90
    while asyncio.get_running_loop().time() < deadline:
        text = await body_text(page)
        
        # Already on dashboard - success!
        if "/dashboard" in page.url and "Dashboard" in text:
            return
        
        # Password updated - keep waiting for redirect
        if "Your password has been updated" in text:
            await page.wait_for_timeout(3_000)
            continue
        
        # Check for password rejection
        lowered = text.lower()
        if any(
            hint in lowered
            for hint in (
                "password must contain", "password is too weak", "change your password",
                "choose a new password", "password was rejected",
            )
        ):
            raise FlowError("Lovable rejected the password")
        
        await page.wait_for_timeout(1_500)
    else:
        raise FlowError("Lovable did not confirm password reset or redirect to dashboard")
    
    # Final dashboard wait with account menu check
    await wait_for_dashboard(page, timeout=90)


async def wait_for_dashboard(page: Page, timeout: float = 90) -> None:
    """Wait for dashboard to load with account menu verification."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        current = await body_text(page)
        if "/dashboard" in page.url and "Dashboard" in current:
            # Verify account menu is present
            account_menu = page.locator('button[aria-label="Account menu"]')
            if await account_menu.count():
                return
        await page.wait_for_timeout(1_500)
    
    raise FlowError(f"Lovable did not reach the dashboard: {page.url}")


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
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
        ],
        proxy=proxy_settings(),
    )


def keep_browser_open() -> bool:
    """Check if we should keep browser open."""
    return os.getenv("KEEP_BROWSER_OPEN", "1").lower() in ("1", "true", "yes")


async def run(cdp_url: str | None, auto_close: bool = False) -> dict[str, object]:
    async with async_playwright() as playwright:
        browser = await connect_browser(playwright, cdp_url)
        if browser.contexts:
            context = browser.contexts[0]
        else:
            context = await browser.new_context(viewport={"width": 1440, "height": 900})
        
        # Create Lovable page (NO TempMail page - TRUE API-ONLY!)
        lovable_page = await context.new_page()
        await install_ad_blocker(lovable_page)
        print(f"🌐 Browser egress IP: {await verify_egress_ip(context)}")
        
        last_error: Optional[Exception] = None
        for attempt in range(1, 4):
            try:
                # TRUE API-ONLY: Create email via API (no page at all)
                print(f"\n🔄 Attempt {attempt}/3: Creating account via TRUE API-ONLY mode...", file=sys.stderr)
                email, email_id = create_working_email()
                password = email if re.search(r"\d", email) else f"{email}1"
                
                mode = await request_login(lovable_page, email)
                
                if mode == "signup":
                    print("📝 Lovable: No account found, creating one...")
                    try:
                        signup_result = await do_signup(lovable_page, email, password)
                    except Exception as exc:
                        print(f"⚠️  Signup failed ({exc}), using reset path...", file=sys.stderr)
                        await navigate(lovable_page, f"{LOVABLE_URL}login")
                        await request_login(lovable_page, email)
                        await do_password_reset(lovable_page, email)
                        reset_url = await read_reset_link(email_id, timeout=180, page=lovable_page)
                        await set_password_and_verify(lovable_page, reset_url, password)
                    else:
                        if signup_result == "verify":
                            print("📧 Lovable: Email verification required...")
                            reset_url = await read_reset_link(email_id, timeout=180, page=lovable_page)
                            await navigate(lovable_page, reset_url)
                            await wait_for_dashboard(lovable_page, timeout=60)
                        elif signup_result == "login":
                            print("🔐 Account created, logging in...")
                            await lovable_page.locator('input[type="password"]').last.fill(password)
                            await click_exact(lovable_page, "Log in")
                            await wait_for_dashboard(lovable_page, timeout=45)
                else:
                    print("🔄 Lovable: Account exists, requesting password reset...")
                    await do_password_reset(lovable_page, email)
                    reset_url = await read_reset_link(email_id, timeout=180, page=lovable_page)
                    await set_password_and_verify(lovable_page, reset_url, password)
                
                break
            except Exception as exc:
                last_error = exc
                print(f"❌ Attempt {attempt} failed: {exc}", file=sys.stderr)
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
        
        # Save session
        sessions_dir = Path(
            os.environ.get(
                "CHIMERA_SESSIONS_DIR",
                "/home/alan/Documents/automation-toolkit/scripts/sessions",
            )
        )
        sessions_dir.mkdir(exist_ok=True)
        
        # Generate unique session ID (collision-proof across machines)
        import time as _time
        runner = os.getenv("RUNNER_ID", "").strip()
        if runner:
            session_id = f"session-{runner}-{int(_time.time())}"
        else:
            session_id = f"session-{int(_time.time())}-{os.getpid()}"
        
        session_dir = sessions_dir / session_id
        session_dir.mkdir(exist_ok=True)
        session_num = session_id
        
        # Save cookies
        cookies = await context.cookies()
        cookies_file = session_dir / "cookies.json"
        with open(cookies_file, "w") as f:
            json.dump(cookies, f, indent=2)
        print(f"✅ Saved {len(cookies)} cookies to {cookies_file}", file=sys.stderr)
        
        # Save credentials
        config = {
            "email": email,
            "password": password,
            "created_at": datetime.now().isoformat(),
            "dashboard_url": lovable_page.url,
            "verified": True,
            "api_only": True,
        }
        config_file = session_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)
        print(f"✅ Saved session config to {config_file}", file=sys.stderr)
        
        # Sync session to Chimera Mega DB (with distributed lock for GH runners)
        if os.environ.get("CHIMERA_SKIP_MEGA_SYNC", "").lower() in ("1", "true", "yes"):
            print("⏭️  Skipping Mega DB sync (CHIMERA_SKIP_MEGA_SYNC set)", file=sys.stderr)
        else:
            try:
                sys.path.insert(
                    0,
                    os.environ.get(
                        "CHIMERA_MINER_DIR", "/home/alan/Documents/chimera-miner"
                    ),
                )
                from mega_db import load_db, save_db, mega_distributed_lock
                with mega_distributed_lock():
                    db = load_db()
                    db.add_session(session_id, email, status="active")
                    save_db(db)
                print(f"✅ Synced {session_id} to Mega DB", file=sys.stderr)
            except Exception as e:
                print(f"⚠️  Mega DB sync failed (non-fatal): {e}", file=sys.stderr)
        
        result = {
            "verified": True,
            "email": email,
            "password": password,
            "dashboard_url": lovable_page.url,
            "session_dir": str(session_dir),
            "session_number": session_num,
        }
        
        print("\n" + "="*60)
        print("🎉 SUCCESS!")
        print("="*60)
        print(json.dumps(result, indent=2))
        
        # Close browser based on --end flag
        if auto_close:
            print("\n✅ Auto-closing browser (--end flag set)", file=sys.stderr)
            if not cdp_url:
                await browser.close()
        elif keep_browser_open() and not cdp_url:
            print("\n✋ Browser staying open. Press Enter to close...", file=sys.stderr)
            input()
            await browser.close()
        elif not cdp_url:
            await browser.close()
        
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Lovable account via TempMailHub API-ONLY")
    parser.add_argument("--cdp-url", help="Connect to existing browser via CDP")
    parser.add_argument("--end", action="store_true", help="Close browser when done (don't wait for Enter)")
    args = parser.parse_args()
    
    cdp = args.cdp_url or os.getenv("BU_CDP_WS")
    
    try:
        result = asyncio.run(run(cdp, auto_close=args.end))
    except FlowError as e:
        print(f"\n❌ Automation failed: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
