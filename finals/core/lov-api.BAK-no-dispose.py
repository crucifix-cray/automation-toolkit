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
import random
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add core path for InvisiblePlaywright
TOOLKIT_CORE = Path(__file__).parent
sys.path.insert(0, str(TOOLKIT_CORE))

from invisible_playwright.async_api import InvisiblePlaywright
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)


TEMPMAIL_API = "https://api.tempmailhub.org"
LOVABLE_URL = "https://lovable.dev/"
RESET_LINK_RE = re.compile(r"https?://[^\"'\\\s<>]*lovable\.dev[^\"'\\\s<>]*", re.I)
WARP_PROXY = "socks5://127.0.0.1:40000"
TOR_PROXY = "socks5://127.0.0.1:9050"
USED_EMAILS_FILE = os.environ.get(
    "USED_EMAILS_FILE", str(Path.home() / "Documents" / "used-tempmailhub-emails.txt")
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


def proxy_settings(for_api: bool = False) -> dict | None:
    """Check proxies in order - enhanced for isolation.
    Browser: 40000 (warp=on fastest 0.5s) → 9050 (tor 3/3 valid) → chain 9051-9054 → direct
    API: 9050 (tor 3/3 valid) → 40000 (warp) → chain → direct (direct gives 3/3 but shares IP, so proxy preferred for GH 429)
    Excludes 9251 (IPv6 PySocks error) and handles socks5/socks4 fallback."""
    import socket

    if os.environ.get("FORCE_NO_PROXY") == "1":
        print("🌐 --raw flag: forcing direct connection (no proxy)", file=sys.stderr)
        return None

    candidates = []
    forced = os.environ.get("PROXY_PORT") or os.environ.get("LOV_PROXY_PORT")
    if forced:
        try:
            candidates.append(int(forced))
        except: pass
    else:
        if for_api:
            # API needs valid gmail + unique IP: tor 9050 best (3/3), warp 40000 fallback
            candidates = [9050, 40000, 9051, 9052, 9053, 9054]
        else:
            # Browser needs warp=on + speed: warp 40000 fastest, then tor
            candidates = [40000, 9050, 9051, 9052, 9053, 9054]

    for port in candidates:
        if port == 9251:  # skip broken IPv6 tor proxy
            continue
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                # warp 40000 supports both socks5/socks4, tor needs socks5
                # keep socks5 for all (tested: warp socks5 1/3 valid, socks4 1/3 same, but socks5 gives warp=on)
                server = f"socks5://127.0.0.1:{port}"
                # extra check: warp port 40000 alive test via socks5 already passed, but verify socks4 fallback later in api_request if needed
                print(f"✅ Using proxy 127.0.0.1:{port} ({'API' if for_api else 'browser'})", file=sys.stderr)
                return {
                    "server": server,
                    "bypass": "127.0.0.1,localhost",
                    "port": port,
                }
        except OSError:
            continue

    if for_api:
        # API can work direct (3/3 valid) but loses unique IP - warn but allow
        print("⚠️  No API proxy found; using direct (may 429 on parallel runs)", file=sys.stderr)
    else:
        print("⚠️  No browser proxy found; using direct (warp=off)", file=sys.stderr)
    return None


def load_used_emails() -> set:
    """Load already-used emails - handles permission/path errors."""
    for path in [USED_EMAILS_FILE, str(Path.home() / "Documents" / "used-tempmailhub-emails.txt"), "/tmp/used-tempmailhub-emails.txt"]:
        try:
            with open(path, "r") as f:
                return set(line.strip().lower() for line in f if line.strip())
        except FileNotFoundError:
            return set()
        except (PermissionError, OSError) as e:
            print(f"⚠️  Cannot read used-emails from {path}: {e} - trying fallback", file=sys.stderr)
            continue
    return set()


def save_used_email(email: str) -> None:
    """Save email to used list - never crashes on permission/path errors."""
    global USED_EMAILS_FILE
    for path in [USED_EMAILS_FILE, str(Path.home() / "Documents" / "used-tempmailhub-emails.txt"), "/tmp/used-tempmailhub-emails.txt"]:
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "a") as f:
                f.write(f"{email.lower()}\n")
            if path != USED_EMAILS_FILE:
                print(f"⚠️  USED_EMAILS_FILE fallback used: {path}", file=sys.stderr)
                USED_EMAILS_FILE = path
            print(f"💾 Saved {email} to used list", file=sys.stderr)
            return
        except PermissionError as e:
            print(f"⚠️  Cannot write used-emails to {path}: {e} - trying fallback", file=sys.stderr)
            continue
        except Exception as e:
            print(f"⚠️  save_used_email fallback {path}: {e}", file=sys.stderr)
            continue
    print(f"⚠️  Failed to save used email {email} - continuing (non-fatal)", file=sys.stderr)


def is_valid_gmail(email: str) -> bool:
    """Validate Gmail: must be @gmail.com with NO dots or + before @"""
    if not email or '@gmail.com' not in email.lower():
        return False
    local_part = email.split('@')[0]
    if '.' in local_part or '+' in local_part:
        return False
    return True


def api_request(endpoint: str, method: str = "POST", data: dict = None, timeout: int = 15) -> tuple[int, str]:
    """Make API request to TempMailHub - robust socks5/socks4 + direct fallback, isolated."""
    url = f"{TEMPMAIL_API}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "Origin": "https://tempmailhub.org"
    }
    
    # Try proxy list in order: 9050 → 40000 → direct (per proxy_settings for_api)
    # We try up to 2 proxy choices if first fails with IPv6 or timeout
    candidates = []
    primary = proxy_settings(for_api=True)
    if primary:
        candidates.append(primary)
        # add fallback direct as last
        candidates.append(None)
        # also add secondary proxy if primary is 9050, add 40000 as fallback vice versa
        alt_port = 40000 if primary.get("port")==9050 else 9050
        import socket as _sock
        try:
            with _sock.create_connection(("127.0.0.1", alt_port), timeout=1):
                candidates.insert(1, {"server": f"socks5://127.0.0.1:{alt_port}", "port": alt_port, "bypass": "127.0.0.1,localhost"})
        except: pass
    else:
        candidates = [None]

    last_error = None
    for proxy in candidates:
        _ORIGINAL_SOCKET = None
        proxy_desc = proxy["server"] if proxy else "direct"
        try:
            if proxy:
                import socks, socket as _socket
                proxy_port = int(proxy["server"].split(":")[-1])
                # try socks5 first, fallback to socks4 for warp (40000) if IPv6 error
                socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", proxy_port)
                _ORIGINAL_SOCKET = _socket.socket
                _socket.socket = socks.socksocket
                print(f"  🌐 API via {proxy_desc} (isolated)", file=sys.stderr)

            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for attempt in range(2):
                try:
                    req = urllib.request.Request(url, headers=headers, method=method)
                    if method == "POST":
                        req.data = json.dumps(data).encode('utf-8') if data else b'{}'
                    with opener.open(req, timeout=timeout) as response:
                        return response.status, response.read().decode()
                except urllib.error.HTTPError as e:
                    return e.code, e.read().decode(errors="replace")
                except (urllib.error.URLError, TimeoutError, OSError) as error:
                    err_str = str(error)
                    # socks4 fallback for warp IPv6 case
                    if "IPv6" in err_str and proxy and proxy.get("port")==40000 and attempt==0:
                        try:
                            import socks
                            socks.set_default_proxy(socks.SOCKS4, "127.0.0.1", proxy_port)
                            print(f"  ↻ retry socks4 for warp {proxy_port}", file=sys.stderr)
                            continue
                        except: pass
                    last_error = error
                    print(f"  ⚠️  API timeout/error via {proxy_desc} (attempt {attempt + 1}/2): {error}", file=sys.stderr)
                    if attempt < 1:
                        import time, random
                        time.sleep(1 + random.random())
                    else:
                        break
            # if we got here, this proxy failed - try next candidate
            if proxy and "IPv6" in str(last_error):
                print(f"  ⚠️  {proxy_desc} IPv6 fail, trying next", file=sys.stderr)
                continue
            if last_error and proxy is not None:
                continue
            break
        finally:
            if _ORIGINAL_SOCKET is not None:
                import socket as _socket
                _socket.socket = _ORIGINAL_SOCKET
                try:
                    import socks
                    socks.set_default_proxy()
                except: pass

    return 0, f"API failed: {last_error}"


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
        
        # Check if API call failed (status 0 means timeout/error)
        if status == 0:
            print(f"  ❌ API timeout - trying next...", file=sys.stderr)
            continue
        
        # Check for errors (like monitor script)
        if "imap" in msg_response.lower() and "failed" in msg_response.lower():
            print(f"  ❌ IMAP auth error - trying next...", file=sys.stderr)
            continue
        elif "authentication" in msg_response.lower() and "failed" in msg_response.lower():
            print(f"  ❌ Auth failed - trying next...", file=sys.stderr)
            continue
        elif not msg_response or msg_response == "":
            # Empty body = freshly created mailbox with no mail yet. That is a
            # working inbox, not a failure — the verification email arrives after
            # the signup form is submitted, not before.
            if not lovable_email_available(email):
                print(f"  ⚠️  Email already registered on Lovable - trying next...", file=sys.stderr)
                time.sleep(1)
                continue
            print(f"  ✅ Mailbox working (empty, ready for verification mail)", file=sys.stderr)
            return email, email_id
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
    """Click button/link with exact text - wait for clickability first."""
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
    
    # Wait for element to be clickable (visible + enabled)
    try:
        target = locator.last
        # Wait for visible AND stable
        await target.wait_for(state="visible", timeout=10_000)
        await asyncio.sleep(0.5)  # Let animations finish
        # Try normal click first (respects actionability checks)
        await target.click(timeout=10_000)
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
    """Dismiss cookie banner and overlays aggressively."""
    await asyncio.sleep(1)  # Let overlays render
    
    # Try multiple times
    for attempt in range(3):
        dismissed = False
        try:
            # Try common cookie banner buttons
            for label in ("Reject all", "Accept all", "OK", "Accept", "Got it"):
                button = page.get_by_role("button", name=label, exact=False)
                if await button.count():
                    try:
                        await button.first.click(timeout=2_000, force=True)
                        dismissed = True
                        await asyncio.sleep(0.5)
                        break
                    except:
                        pass
            
            # Try closing any dialogs
            close_buttons = page.locator('button[aria-label*="Close"], button[aria-label*="close"]')
            if await close_buttons.count():
                try:
                    await close_buttons.first.click(timeout=1_000, force=True)
                    dismissed = True
                    await asyncio.sleep(0.5)
                except:
                    pass
            
            if dismissed:
                await asyncio.sleep(0.5)
                continue
            else:
                break
        except:
            break


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
    print("  🌐 Navigating to Lovable...", file=sys.stderr)
    await navigate(page, LOVABLE_URL)
    await wait_for_lovable_ready(page)
    print("  🍪 Dismissing overlays...", file=sys.stderr)
    await dismiss_cookie_banner(page)
    await sign_out_if_needed(page)
    
    if "/dashboard" in page.url:
        await navigate(page, LOVABLE_URL)
        await wait_for_lovable_ready(page)
    
    # Wait for any overlays to clear before clicking
    await asyncio.sleep(2)
    
    print("  🖱️  Clicking 'Log in' button (with retry for 15 min)...", file=sys.stderr)
    
    # Retry loop: click login button until email input popup appears (15 min max)
    deadline = asyncio.get_running_loop().time() + 900  # 15 minutes
    email_input = page.locator('input[type="email"]').last
    login_clicked = False
    
    while asyncio.get_running_loop().time() < deadline:
        # Check if popup already visible
        try:
            if await email_input.is_visible(timeout=1_000):
                print("  ✅ Login popup appeared!", file=sys.stderr)
                break
        except:
            pass
        
        # Try to click login button if not clicked recently
        if not login_clicked:
            try:
                await click_exact(page, "Log in")
                login_clicked = True
                print("  ✅ Clicked 'Log in' button", file=sys.stderr)
            except Exception as exc:
                if "closed" in str(exc).lower():
                    raise
                # Button not ready yet, keep trying
                pass
        
        # Wait before next check
        await asyncio.sleep(2)
        login_clicked = False  # Allow clicking again
    
    # Final check - if popup still not visible, fail
    if not await email_input.is_visible():
        raise FlowError("Login popup never appeared after 15 minutes")
    
    # Now fill email and continue
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
    
    # Wait for reset form to appear
    await asyncio.sleep(1)
    
    reset_email = page.locator('input[placeholder*="email"]')
    if await reset_email.count() == 0:
        reset_email = page.locator('input[type="email"]')
    current_email = (await reset_email.last.input_value()).strip().lower()
    if current_email != email.lower():
        await click_exact(page, "Use a different email")
        reset_email = page.locator('input[placeholder*="email"]')
        await reset_email.last.fill(email)
    
    # Use click_exact for consistency (waits for visibility)
    await asyncio.sleep(1)  # Let form settle
    await click_exact(page, "Send reset link")
    await page.wait_for_timeout(3_000)


async def human_type(locator, text: str) -> None:
    """Type text with human-like delays (InvisiblePlaywright already humanizes, but add extra realism)."""
    await locator.click()  # Focus first
    await asyncio.sleep(0.1)
    await locator.type(text, delay=random.randint(50, 150))  # 50-150ms between keystrokes


async def do_signup(page: Page, email: str, password: str) -> str:
    """Attempt signup flow."""
    try:
        passwords = page.locator('input[type="password"]')
        await passwords.nth(0).wait_for(timeout=20_000)
        await human_type(passwords.nth(0), password)
        if await passwords.count() >= 2:
            await human_type(passwords.nth(1), password)
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
    await human_type(new_password, password)
    await human_type(confirm_password, password)
    await click_exact(page, "Reset Password")
    
    # Wait for confirmation and redirect (Firebase is SLOW)
    deadline = asyncio.get_running_loop().time() + 60
    while asyncio.get_running_loop().time() < deadline:
        text = await body_text(page)
        
        # Already on dashboard - success!
        if "/dashboard" in page.url and "Dashboard" in text:
            return
        
        # Password updated - keep waiting for redirect
        if "Your password has been updated" in text:
            await page.wait_for_timeout(2_000)
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
        
        await page.wait_for_timeout(1_000)
    else:
        raise FlowError("Lovable did not confirm password reset or redirect to dashboard")
    
    # Final dashboard wait with account menu check
    await wait_for_dashboard(page, timeout=60)


async def wait_for_dashboard(page: Page, timeout: float = 60) -> None:
    """Wait for dashboard to load with account menu verification."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        current = await body_text(page)
        if "/dashboard" in page.url and "Dashboard" in current:
            # Verify account menu is present
            account_menu = page.locator('button[aria-label="Account menu"]')
            if await account_menu.count():
                return
        await page.wait_for_timeout(1_000)
    
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
        proxy=proxy_settings(for_api=False),
    )


def keep_browser_open() -> bool:
    """Check if we should keep browser open."""
    return os.getenv("KEEP_BROWSER_OPEN", "1").lower() in ("1", "true", "yes")


async def run(cdp_url: str | None, auto_close: bool = False) -> dict[str, object]:
    print("🚀 Starting automation...", file=sys.stderr)
    
    # Configure InvisiblePlaywright properly for bot detection evasion - isolated warp proxy
    proxy_config = proxy_settings(for_api=False)
    playwright_proxy = None
    if proxy_config:
        playwright_proxy = {
            "server": proxy_config["server"],
            "bypass": proxy_config.get("bypass", "127.0.0.1,localhost"),
        }
        print(f"🌐 Browser proxy {playwright_proxy['server']} bypass={playwright_proxy['bypass']} (isolated)", file=sys.stderr)
    else:
        print("🌐 Browser direct (warp=off, isolated)", file=sys.stderr)
    
    # Use InvisiblePlaywright with humanization enabled
    async with InvisiblePlaywright(
        headless=False,
        proxy=playwright_proxy,
        humanize=True,  # Human-like mouse movements and typing
        locale='en-US',
    ) as browser:
        print("✅ Browser launched (InvisiblePlaywright)", file=sys.stderr)
        
        # InvisiblePlaywright returns Browser directly
        if isinstance(browser, BrowserContext):
            context = browser
        else:
            context = browser.contexts[0] if browser.contexts else await browser.new_context(viewport={"width": 1440, "height": 900})
        
        print("✅ Context ready", file=sys.stderr)
        # Create Lovable page (NO TempMail page - TRUE API-ONLY!)
        lovable_page = await context.new_page()
        await install_ad_blocker(lovable_page)
        
        # Check egress IP (skip if times out)
        try:
            egress_ip = await asyncio.wait_for(verify_egress_ip(context), timeout=10)
            print(f"🌐 Browser egress IP: {egress_ip}")
        except asyncio.TimeoutError:
            print("⚠️  Egress IP check timed out, continuing...", file=sys.stderr)
        
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
                            await human_type(lovable_page.locator('input[type="password"]').last, password)
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
        
        # Save session - dynamic default to repo location or home
        _default_sessions = str(Path(__file__).resolve().parents[2] / "scripts" / "sessions")
        if not Path(_default_sessions).exists():
            _default_sessions = str(Path.home() / "Documents" / "repos" / "automation-toolkit" / "scripts" / "sessions")
        sessions_dir = Path(
            os.environ.get(
                "CHIMERA_SESSIONS_DIR",
                _default_sessions,
            )
        )
        try:
            sessions_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            # fallback to home
            sessions_dir = Path.home() / "Documents" / "repos" / "automation-toolkit" / "scripts" / "sessions"
            sessions_dir.mkdir(parents=True, exist_ok=True)
            print(f"⚠️  CHIMERA_SESSIONS_DIR fallback to {sessions_dir}", file=sys.stderr)
        
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
                _default_miner = str(Path(__file__).resolve().parents[2].parent / "chimera-miner")
                if not Path(_default_miner).exists():
                    _default_miner = str(Path.home() / "Documents" / "repos" / "chimera-miner")
                sys.path.insert(
                    0,
                    os.environ.get(
                        "CHIMERA_MINER_DIR", _default_miner
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
    parser.add_argument("--raw", action="store_true", help="Force direct connection (no proxy/WARP)")
    args = parser.parse_args()
    
    cdp = args.cdp_url or os.getenv("BU_CDP_WS")
    
    # Pass --raw flag to run() via environment
    if args.raw:
        os.environ["FORCE_NO_PROXY"] = "1"
    
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
