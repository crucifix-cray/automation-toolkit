#!/usr/bin/env python3
"""Create a TempMailHub address and sign in to Lovable with it.

The script either attaches to an already-running browser over CDP
(``--cdp-url``/``BU_CDP_WS``) or launches its own hardened Chrome. The
self-launched browser:

* runs on Cloudflare WARP through its local SOCKS proxy (default port 40000)
  so only this browser's traffic gets the WARP IP -- nothing on the host is
  changed. The TempMailHub API (api.tempmailhub.org) is bypassed to DIRECT
  because it does not tolerate the WARP route;
* blocks ads/trackers in-process (Playwright route interception), so no
  extension install is required while still removing ad/tracker noise.

TempMailHub's mailbox API is flaky: some generated accounts fail their IMAP
login server-side. The script therefore generates accounts through the site's
own public API (api.tempmailhub.org) and retries until it finds one whose
mailbox can be read. The TempMailHub tab stays open in the browser.

Flow: generate a working TempMailHub Gmail address, request a Lovable
password reset to it, read the reset link from the mailbox, set the password
(the email address), and verify the dashboard.

The generated password matches the generated email because that was requested
for this workflow. If the generated email has no digit, Lovable's validation
requires a trailing ``1``. This is not a safe password for a real account.
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
    Error as PlaywrightError,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)
from playwright.async_api import async_playwright


TEMPMAIL_URL = "https://tempmailhub.org/"
TEMPLAIL_API_BYPASS = "api.tempmailhub.org"
TEMPLAIL_API = "https://api.tempmailhub.org"
LOVABLE_URL = "https://lovable.dev/"
RESET_SUBJECT = "Reset your password for Lovable"
GMAIL_RE = re.compile(r"\b[A-Za-z0-9_]+@gmail\.com\b", re.IGNORECASE)
RESET_LINK_RE = re.compile(r"https?://[^\"'\\\s<>]*lovable\.dev[^\"'\\\s<>]*", re.I)
WARP_PROXY = "socks5://127.0.0.1:40000"

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


class PasswordRecoveryRequired(FlowError):
    """Raised when Lovable asks for a different password."""


def page_is_open(page: Page | None) -> bool:
    try:
        return page is not None and not page.is_closed()
    except Exception:
        return False


async def close_page_safely(page: Page | None) -> None:
    if not page_is_open(page):
        return
    try:
        await page.close(run_before_unload=False)
    except Exception as exc:
        if "closed" not in str(exc).lower():
            print(f"Page close warning: {exc}", file=sys.stderr)


def proxy_settings() -> dict | None:
    """WARP SOCKS proxy config for the self-launched browser only.

    Returns None when the WARP proxy is not listening, so the browser falls
    back to a direct connection instead of losing all connectivity.

    The site API backends (api.tempmailhub.org, api.lovable.dev) fail through
    the WARP route, so they are sent DIRECT while everything else keeps the
    WARP IP."""
    import socket

    try:
        with socket.create_connection(("127.0.0.1", 40000), timeout=2):
            return {
                "server": WARP_PROXY,
                "bypass": f"{TEMPLAIL_API_BYPASS},api.lovable.dev,127.0.0.1,localhost",
            }
    except OSError:
        print(
            "WARP proxy (127.0.0.1:40000) is not running; using a direct connection.",
            file=sys.stderr,
        )
        return None


async def install_ad_blocker(page: Page) -> None:
    """Block known ad/tracker requests in-process (no extension needed)."""

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
        "() => { "
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined}); "
        "}"
    )


def api_post(path: str, payload: dict | None = None) -> tuple[int, str]:
    """Talk to the TempMailHub API from the host (avoids the browser's proxy).

    Retries transient network stalls (the environment proxy can be slow)."""
    body = json.dumps(payload or {}).encode()
    request = urllib.request.Request(
        f"{TEMPLAIL_API}{path}",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Origin": TEMPMAIL_URL.rstrip("/"),
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        },
    )
    last_error = None
    for _attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return response.status, response.read().decode(errors="replace")
        except urllib.error.HTTPError as error:
            # Account gone / upstream error: surface it, the caller retries.
            return error.code, error.read().decode(errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last_error = error
            import time

            time.sleep(2)
    raise FlowError(f"TempMailHub API request failed: {last_error}")


def create_working_email() -> tuple[str, str]:
    """Create TempMailHub accounts until one has a readable GMAIL mailbox.

    Returns (email, email_id). Some pooled accounts fail IMAP auth server-side
    (or HMAC checks), so keep retrying until the messages call returns cleanly.
    
    GMAIL ONLY: This will keep retrying until it gets a valid @gmail.com address
    (no dots or + before @)."""
    import time

    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        status, raw = api_post("/emails")
        if status != 201:
            print(f"TempMailHub account creation failed: {status} {raw[:120]}", file=sys.stderr)
            time.sleep(2)
            continue
        try:
            account = json.loads(raw)
            email, email_id = account["email"], str(account["email_id"])
            
            # ENFORCE VALID GMAIL (no dots or +)
            if not is_valid_gmail(email):
                print(f"Skipping invalid Gmail: {email}", file=sys.stderr)
                time.sleep(1)
                continue
                
        except (KeyError, ValueError) as exc:
            print(f"TempMailHub account reply was malformed: {raw[:120]}", file=sys.stderr)
            time.sleep(2)
            continue
        status, messages_raw = api_post(f"/emails/messages?email_id={email_id}")
        if status == 200 and "error" not in messages_raw.lower():
            print(f"Working TempMailHub Gmail mailbox (API): {email} (email_id={email_id})")
            return email, email_id
        print(f"TempMailHub Gmail account {email} has a broken mailbox; retrying...")
        time.sleep(1)
    raise FlowError("TempMailHub gave no valid Gmail account with a readable mailbox in time.")


def is_valid_gmail(email: str) -> bool:
    """Validate Gmail address: must be @gmail.com with NO dots or + before @"""
    if not email or '@gmail.com' not in email.lower():
        return False
    
    local_part = email.split('@')[0]
    
    # Reject if has + or . in local part
    if '+' in local_part or '.' in local_part:
        return False
    
    return True


async def extract_email_from_page(page: Page, timeout: float = 30) -> str:
    """Extract the displayed GMAIL email from TempMail page DOM.
    
    This ensures we get the email that's actually visible on the page,
    not something from ads or other noise above/below it.
    
    Strategy:
    1. Try specific email display elements first
    2. Filter out common ad domains
    3. ONLY ACCEPT @gmail.com addresses WITHOUT dots or + before @
    
    Valid format: [a-zA-Z0-9_]+@gmail.com (no dots, no +)
    """
    # GMAIL ONLY: Letters, numbers, underscores ONLY (no dots, no +)
    EMAIL_RE = re.compile(r"\b[A-Za-z0-9_]+@gmail\.com\b", re.IGNORECASE)
    AD_DOMAINS = ['ads', 'adservice', 'doubleclick', 'example.com', 'test.com']
    
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            # Strategy 1: Try specific email display selectors
            for selector in [
                '[class*="email-display"]',
                '[class*="generated-email"]', 
                '[class*="email"]',
                '[id*="email"]',
                'input[type="text"][readonly]',
                'input[value*="@gmail"]',
                '[data-email]'
            ]:
                elem = page.locator(selector)
                if await elem.count() > 0:
                    try:
                        value = await elem.first.input_value(timeout=2000) if 'input' in selector else await elem.first.inner_text(timeout=2000)
                        matches = EMAIL_RE.findall(value)
                        if matches:
                            email = matches[0]
                            if is_valid_gmail(email):
                                print(f"✓ Extracted valid Gmail from selector {selector}: {email}", file=sys.stderr)
                                return email
                            else:
                                print(f"⚠️  Rejected Gmail (has dots or +): {email}", file=sys.stderr)
                    except (PlaywrightTimeoutError, PlaywrightError, AttributeError):
                        continue
            
            # Strategy 2: Get all text, find Gmail addresses only
            text = await body_text(page)
            gmail_emails = EMAIL_RE.findall(text)
            
            if gmail_emails:
                # Filter out ad domains and invalid formats (dots, +)
                clean_emails = [e for e in gmail_emails 
                               if not any(ad in e.lower() for ad in AD_DOMAINS)
                               and is_valid_gmail(e)]
                
                if clean_emails:
                    email = clean_emails[0]
                    print(f"✓ Extracted valid Gmail from page (filtered): {email}", file=sys.stderr)
                    if len(gmail_emails) > 1:
                        print(f"   All Gmail found: {gmail_emails[:3]}, using: {email}", file=sys.stderr)
                    return email
        except PlaywrightTimeoutError:
            pass
        
        await page.wait_for_timeout(1_000)
    
    raise FlowError("Could not extract Gmail address from TempMail page DOM")


def read_messages(email_id: str) -> list:
    try:
        status, raw = api_post(f"/emails/messages?email_id={email_id}")
    except FlowError as exc:
        print(f"TempMail message poll failed; will retry: {exc}", file=sys.stderr)
        return []
    if status != 200:
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("emails", "messages", "mails", "items", "data"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


async def connect_browser(playwright_support, cdp_url: str | None) -> Browser:
    """Attach to an external CDP browser, or launch our own hardened Chrome."""
    if cdp_url:
        browser = await playwright_support.chromium.connect_over_cdp(cdp_url, timeout=60_000)
        if not browser.contexts:
            raise FlowError("The connected browser has no browser context")
        return browser
    return await playwright_support.chromium.launch(
        channel="chrome",
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
        proxy=proxy_settings(),
    )


async def reconnect_browser_context(playwright_support, cdp_url: str) -> tuple[Browser, BrowserContext]:
    """Reconnect to the same external browser after its CDP context dies."""
    browser = await connect_browser(playwright_support, cdp_url)
    return browser, browser.contexts[0]


def keep_browser_open() -> bool:
    """Stay attached to the self-launched browser after the run finishes.

    Set KEEP_BROWSER_OPEN=0 to restore the old close-on-exit behaviour."""
    return os.environ.get("KEEP_BROWSER_OPEN", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


async def verify_egress_ip(context) -> str:
    """Probe the browser's public IP and report whether it runs through WARP."""
    try:
        probe = await context.new_page()
        await probe.goto(
            "https://www.cloudflare.com/cdn-cgi/trace",
            wait_until="domcontentloaded",
            timeout=30_000,
        )
        await probe.wait_for_timeout(2_000)
        text = await probe.locator("body").inner_text(timeout=5_000)
        info = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
        await probe.close()
        return (
            f"ip={info.get('ip', '?')} warp={info.get('warp', '?')} "
            f"colo={info.get('colo', '?')}"
        )
    except Exception as exc:
        return f"egress probe failed ({exc})"


async def body_text(page: Page) -> str:
    if not page_is_open(page):
        return ""
    try:
        return await page.locator("body").inner_text(timeout=3_000)
    except (PlaywrightTimeoutError, PlaywrightError):
        return ""


async def wait_for_text(page: Page, text: str, timeout: float = 60) -> str:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        current = await body_text(page)
        if text.lower() in current.lower():
            return current
        await page.wait_for_timeout(500)
    raise FlowError(f"Timed out waiting for {text!r} on {page.url}")


async def wait_for_dashboard(page: Page, timeout: float = 45) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        current = await body_text(page)
        if "/dashboard" in page.url and "Dashboard" in current:
            return
        await page.wait_for_timeout(1_000)
    raise FlowError(f"Lovable did not reach the dashboard: {page.url}")


async def navigate(page: Page, url: str) -> None:
    if not page_is_open(page):
        raise FlowError(f"Cannot navigate a closed page to {url}")
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    except PlaywrightTimeoutError:
        # Cloudflare may keep the initial navigation open while it verifies the browser.
        pass
    except PlaywrightError as exc:
        if "closed" in str(exc).lower() or "target page" in str(exc).lower():
            raise FlowError(f"Page closed while navigating to {url}") from exc
        raise


async def click_exact(page: Page, text: str, timeout: float = 15) -> None:
    if not page_is_open(page):
        raise FlowError(f"Cannot click {text!r} on a closed page")
    locator = page.get_by_role("button", name=text, exact=True)
    if await locator.count() == 0:
        locator = page.get_by_role("menuitem", name=text, exact=True)
    if await locator.count() == 0:
        locator = page.get_by_text(text, exact=True)
    if await locator.count() == 0:
        raise FlowError(f"Could not find clickable text {text!r} on {page.url}")
    try:
        await locator.last.click(timeout=timeout * 1_000, force=True)
    except (PlaywrightTimeoutError, PlaywrightError) as exc:
        if "closed" in str(exc).lower() or "target page" in str(exc).lower():
            raise FlowError(f"Page closed while clicking {text!r}") from exc
        raise


async def dismiss_cookie_banner(page: Page) -> None:
    for label in ("Accept all", "OK", "Reject all"):
        button = page.get_by_role("button", name=label, exact=True)
        if await button.count() and await button.last.is_visible():
            try:
                await button.last.click(force=True)
            except (PlaywrightTimeoutError, PlaywrightError):
                pass
            return


async def open_tempmail_tab(context: BrowserContext) -> Page:
    """Open (or reuse) the TempMailHub tab so the browser keeps it visible.
    
    If the tab has an error, close it and open a fresh one."""
    for page in context.pages:
        if not page_is_open(page):
            continue
        if "tempmailhub.org" in page.url:
            # Check for errors on the page
            try:
                text = await page.locator("body").inner_text(timeout=2000)
                error_keywords = ["failed to fetch", "imap", "authentication failed",
                                  "invalid credentials", "network error", "oops",
                                  "something went wrong", "unable to load"]
                if any(err in text.lower() for err in error_keywords):
                    print(f"⚠️  TempMail tab has error, closing and reopening...", file=sys.stderr)
                    await close_page_safely(page)
                    break
                else:
                    return page
            except (PlaywrightTimeoutError, PlaywrightError):
                return page
    
    # Open fresh tab
    try:
        page = await context.new_page()
    except PlaywrightError as exc:
        raise FlowError("Browser context closed while opening TempMail") from exc
    await navigate(page, TEMPMAIL_URL)
    return page


async def wait_for_tempmail_ready(page: Page, max_refreshes: int = 3) -> bool:
    """Return only after the mailbox has settled without an IMAP error.

    Refreshes are deliberately limited to the inbox-refresh control. The
    generate-new-email control must never be clicked as an error recovery
    action, otherwise the caller loses the email id it is polling.
    """
    error_keywords = (
        "failed to fetch", "imap", "authentication failed", "invalid credentials",
        "authenticationfailed", "can not authenticate", "connection failed",
    )

    async def state() -> tuple[str, bool, bool]:
        if not page_is_open(page):
            return "", False, True
        text = await body_text(page)
        lowered = text.lower()
        try:
            loading = await page.evaluate(
                """() => [...document.querySelectorAll('[aria-busy="true"], .spinner, .loader, [class*="loading"]')]
                  .some(el => { const s = getComputedStyle(el); return s.display !== 'none' && s.visibility !== 'hidden'; })"""
            )
        except (PlaywrightTimeoutError, PlaywrightError):
            return "", False, True
        has_email = any(is_valid_gmail(value) for value in GMAIL_RE.findall(text))
        return text, has_email, loading or "fetching messages" in lowered

    async def settle(timeout: float = 30) -> tuple[str, bool]:
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            text, has_email, loading = await state()
            if not loading:
                return text, has_email
            await page.wait_for_timeout(500)
        text, has_email, _ = await state()
        return text, has_email

    print("Waiting for TempMail mailbox to settle...", file=sys.stderr)
    text, has_email = await settle()
    for refresh_attempt in range(max_refreshes + 1):
        lowered = text.lower()
        has_error = any(keyword in lowered for keyword in error_keywords)
        if has_email and not has_error:
            print("TempMail ready with a valid Gmail and no IMAP error", file=sys.stderr)
            return True
        if refresh_attempt >= max_refreshes:
            print(f"TempMail still unhealthy after {max_refreshes} refreshes", file=sys.stderr)
            return False
        if not page_is_open(page):
            return False

        refresh = page.locator(
            'button[title="Refresh inbox"], button[title*="Refresh"], [aria-label="Refresh inbox"]'
        ).first
        try:
            if await refresh.count():
                print(f"TempMail refresh {refresh_attempt + 1}/{max_refreshes}", file=sys.stderr)
                await refresh.click(force=True)
            else:
                print("TempMail refresh control missing; reloading tab", file=sys.stderr)
                await page.reload(wait_until="domcontentloaded", timeout=30_000)
        except (PlaywrightTimeoutError, PlaywrightError) as exc:
            if "closed" in str(exc).lower() or "target page" in str(exc).lower():
                return False
            print(f"TempMail refresh failed: {exc}", file=sys.stderr)
        text, has_email = await settle()

    return False


async def get_lovable_page(context: BrowserContext) -> Page:
    for page in context.pages:
        if page_is_open(page) and "lovable.dev" in page.url:
            return page
    return await context.new_page()


async def wait_for_lovable_ready(page: Page, timeout: float = 75) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        text = await body_text(page)
        if "Performing security verification" in text:
            await page.wait_for_timeout(2_500)
            continue
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


async def sign_out_if_needed(page: Page) -> None:
    if not page_is_open(page):
        raise FlowError("Lovable page closed before sign-out")
    account = page.locator('button[aria-label="Account menu"]')
    if "/dashboard" in page.url and await account.count() == 0:
        try:
            await page.reload(wait_until="domcontentloaded", timeout=30_000)
        except PlaywrightTimeoutError:
            pass
        await page.wait_for_timeout(2_500)
    if "/dashboard" in page.url:
        try:
            await account.last.wait_for(state="visible", timeout=20_000)
        except PlaywrightTimeoutError as exc:
            raise FlowError("Lovable dashboard did not render its account menu") from exc
    if await account.count() == 0 or not await account.last.is_visible():
        return

    sign_out = page.get_by_role("menuitem", name="Sign out", exact=True)
    for _menu_try in range(3):
        if await sign_out.count() and await sign_out.last.is_visible():
            await sign_out.last.click(force=True)
            break
        try:
            await account.last.evaluate("node => node.click()")
            await page.wait_for_timeout(500)
        except (PlaywrightTimeoutError, PlaywrightError) as exc:
            raise FlowError("Lovable account menu closed before sign-out") from exc
    else:
        raise FlowError("Lovable account menu did not show Sign out")
    deadline = asyncio.get_running_loop().time() + 30
    while asyncio.get_running_loop().time() < deadline:
        if "/dashboard" not in page.url and "Log in" in await body_text(page):
            return
        await page.wait_for_timeout(500)
    raise FlowError("Lovable did not finish signing out")


async def request_login(page: Page, email: str) -> str:
    """Open Lovable, submit the email, and say which path we landed on.

    Returns "reset" when the account already exists (password form on
    /login), or "signup" when Lovable proposes account creation."""
    await navigate(page, LOVABLE_URL)
    await wait_for_lovable_ready(page)
    await dismiss_cookie_banner(page)
    await sign_out_if_needed(page)

    if "/dashboard" in page.url:
        await navigate(page, LOVABLE_URL)
        await wait_for_lovable_ready(page)

    await click_exact(page, "Log in")
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
        if (
            page.url.startswith("https://lovable.dev/login")
            and await page.locator('input[type="password"]').count()
            and await forgot_password.count()
        ):
            return "reset"
        if "No account found" in text or "Create your account" in text:
            return "signup"
        await page.wait_for_timeout(500)
    raise FlowError(f"Lovable did not react to the email on {page.url}")


async def do_password_reset(page: Page, email: str) -> None:
    """Existing account: request the password-reset email.

    Lovable validates the login form when the Forgot link is clicked, so a
    placeholder password is filled first; the site then shows the reset form."""
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
    """New account: create it with the given password.

    Returns "dashboard" when already signed in, or "verify" when Lovable
    asks for email verification."""
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
        try:
            await page.screenshot(path="/tmp/opencode/lovable_signup_debug.png")
            print(f"A signup debug screenshot was saved as /tmp/opencode/lovable_signup_debug.png", file=sys.stderr)
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


def message_key(message: dict) -> str:
    for key in ("id", "message_id", "email_id", "uid"):
        if message.get(key) is not None:
            return f"{key}:{message[key]}"
    return json.dumps(message, sort_keys=True, default=str)


PASSWORD_RE = re.compile(
    r"(?:new|temporary|one[- ]time|updated)?\s*password\s*[:=\-]\s*([A-Za-z0-9!@#$%^&*_+=.?-]{8,})",
    re.I,
)


def extract_password_from_message(message: dict) -> str | None:
    """Extract a password only from explicit password-labelled mail text."""
    content = html.unescape(json.dumps(message, default=str))
    match = PASSWORD_RE.search(re.sub(r"<[^>]+>", " ", content))
    return match.group(1).strip() if match else None


async def read_reset_link(
    email_id: str,
    timeout: float = 180,
    ignored_keys: set[str] | None = None,
) -> str:
    ignored_keys = ignored_keys or set()
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        for message in read_messages(email_id):
            if message_key(message) in ignored_keys:
                continue
            subject = str(message.get("subject") or message.get("title") or "")
            if "lovable" not in subject.lower():
                continue
            body = json.dumps(message, default=str)
            match = RESET_LINK_RE.search(body)
            if match:
                return html.unescape(match.group(0))
        await asyncio.sleep(8)
    raise FlowError(f"Timed out waiting for the Lovable reset email in the TempMailHub mailbox")


async def read_password_from_mail(
    email_id: str,
    timeout: float = 120,
    ignored_keys: set[str] | None = None,
) -> str:
    ignored_keys = ignored_keys or set()
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        for message in read_messages(email_id):
            if message_key(message) in ignored_keys:
                continue
            password = extract_password_from_message(message)
            if password:
                return password
        await asyncio.sleep(8)
    raise PasswordRecoveryRequired("No explicit replacement password arrived in TempMail")


async def set_password_and_verify(page: Page, reset_url: str, password: str) -> None:
    await navigate(page, reset_url)
    if "invalid verification code" in (await body_text(page)).lower():
        raise FlowError("Lovable reset link is invalid or stale")
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
        lowered = text.lower()
        if any(
            hint in lowered
            for hint in (
                "password must contain", "password is too weak", "change your password",
                "choose a new password", "password was rejected",
            )
        ):
            raise PasswordRecoveryRequired("Lovable rejected or changed the password")
        await page.wait_for_timeout(500)
    else:
        raise FlowError("Lovable did not confirm the password reset")
    await wait_for_dashboard(page, timeout=45)


async def login_with_password(page: Page, password: str) -> None:
    password_input = page.locator('input[type="password"]').last
    await password_input.wait_for(timeout=20_000)
    await password_input.fill(password)
    await click_exact(page, "Log in")
    deadline = asyncio.get_running_loop().time() + 45
    while asyncio.get_running_loop().time() < deadline:
        text = await body_text(page)
        if "/dashboard" in page.url and "Dashboard" in text:
            return
        lowered = text.lower()
        if any(
            hint in lowered
            for hint in (
                "incorrect password", "wrong password", "password rejected",
                "change your password", "update your password", "password expired",
            )
        ):
            raise PasswordRecoveryRequired("Lovable rejected the login password")
        await page.wait_for_timeout(500)
    raise FlowError("Lovable did not finish the password login")


async def recover_password_and_finish(
    page: Page,
    email: str,
    email_id: str,
    ignored_keys: set[str],
) -> str:
    """Use an explicit replacement password from TempMail and finish login."""
    replacement = await read_password_from_mail(
        email_id, timeout=120, ignored_keys=ignored_keys
    )
    await navigate(page, f"{LOVABLE_URL}login")
    mode = await request_login(page, email)
    if mode == "signup":
        await login_with_password(page, replacement)
    else:
        await do_password_reset(page, email)
        reset_url = await read_reset_link(
            email_id, timeout=180, ignored_keys=ignored_keys
        )
        await set_password_and_verify(page, reset_url, replacement)
    return replacement


async def run(cdp_url: str | None) -> dict[str, object]:
    async with async_playwright() as playwright:
        browser = await connect_browser(playwright, cdp_url)
        if browser.contexts:
            context = browser.contexts[0]
        else:
            context = await browser.new_context(viewport={"width": 1440, "height": 900})
        
        # CRITICAL FIX: Install ad-blocker on ALL new pages automatically
        # This prevents ad redirects during page navigation
        async def auto_install_ad_blocker(page: Page):
            """Auto-install ad-blocker on every new page"""
            try:
                await install_ad_blocker(page)
                print(f"✓ Ad-blocker installed on: {page.url[:60]}", file=sys.stderr)
            except Exception as e:
                print(f"⚠️  Ad-blocker install failed: {e}", file=sys.stderr)
        
        context.on("page", auto_install_ad_blocker)
        
        try:
            temp_page = await open_tempmail_tab(context)
            lovable_page = await get_lovable_page(context)
        except Exception:
            if not cdp_url:
                raise
            print("Browser context closed during setup; reconnecting to the existing CDP browser...", file=sys.stderr)
            browser, context = await reconnect_browser_context(playwright, cdp_url)
            context.on("page", auto_install_ad_blocker)  # Re-attach after reconnect
            temp_page = await open_tempmail_tab(context)
            lovable_page = await get_lovable_page(context)
        
        # Install on existing pages too
        await install_ad_blocker(temp_page)
        await install_ad_blocker(lovable_page)
        print(f"Browser egress IP: {await verify_egress_ip(context)}")

        last_error: Optional[Exception] = None
        for _attempt in range(1, 4):
            try:
                if not page_is_open(temp_page):
                    temp_page = await open_tempmail_tab(context)
                    # No need to install ad-blocker - context.on("page") handles it
                if not page_is_open(lovable_page):
                    lovable_page = await get_lovable_page(context)
                    # No need to install ad-blocker - context.on("page") handles it
                # Ensure TempMail is ready and working (retry up to 3 times if errors)
                tempmail_retry = 0
                while tempmail_retry < 3:
                    tempmail_ready = await wait_for_tempmail_ready(temp_page, max_refreshes=3)
                    
                    if not tempmail_ready:
                        # IMAP errors persist after 3 refreshes - close and reopen tab
                        tempmail_retry += 1
                        print(f"⚠️  TempMail errors persist, closing tab (retry {tempmail_retry}/3)", file=sys.stderr)
                        await close_page_safely(temp_page)
                        temp_page = await open_tempmail_tab(context)
                        await install_ad_blocker(temp_page)
                        await temp_page.wait_for_timeout(2000)
                        continue
                    else:
                        # TempMail is ready!
                        print(f"✓ TempMail ready, proceeding with email extraction", file=sys.stderr)
                        break
                
                if tempmail_retry >= 3:
                    raise FlowError("TempMail failed after 3 tab reopens - IMAP errors persist")
                
                email_api, email_id = create_working_email()  # GMAIL ONLY from API
                known_message_ids = {message_key(message) for message in read_messages(email_id)}
                
                # NOW extract and verify the Gmail email from the page DOM
                # This ensures we use what's actually displayed, not API noise
                # If extraction fails or email is invalid, RETRY everything - don't use old email!
                try:
                    email_page = await extract_email_from_page(temp_page, timeout=15)
                    
                    # Validate the page email
                    if not is_valid_gmail(email_page):
                        print(f"⚠️  Page email invalid (has dots or +): {email_page}", file=sys.stderr)
                        print(f"   Closing TempMail tab and retrying...", file=sys.stderr)
                        await close_page_safely(temp_page)
                        temp_page = await open_tempmail_tab(context)
                        await install_ad_blocker(temp_page)
                        continue  # RETRY from beginning
                    
                    if email_page.lower() != email_api.lower():
                        print(f"⚠️  Gmail mismatch! API says: {email_api}, Page shows: {email_page}", file=sys.stderr)
                        print(f"   Keeping API Gmail because email_id belongs to: {email_api}", file=sys.stderr)
                        email = email_api
                    else:
                        print(f"✓ Gmail verified (API and page match): {email_api}", file=sys.stderr)
                        email = email_api
                        
                except Exception as exc:
                    print(f"⚠️  Could not extract valid Gmail from page ({exc})", file=sys.stderr)
                    print(f"   Closing TempMail tab and retrying...", file=sys.stderr)
                    await close_page_safely(temp_page)
                    temp_page = await open_tempmail_tab(context)
                    await install_ad_blocker(temp_page)
                    continue  # RETRY from beginning - DON'T use API email!
                
                # Double-check it's a valid Gmail (no dots or +)
                if not is_valid_gmail(email):
                    print(f"✗ Final validation failed: {email} (has dots or +)", file=sys.stderr)
                    print(f"   Closing TempMail tab and retrying...", file=sys.stderr)
                    await close_page_safely(temp_page)
                    temp_page = await open_tempmail_tab(context)
                    await install_ad_blocker(temp_page)
                    continue  # RETRY from beginning
                
                password = email if re.search(r"\d", email) else f"{email}1"

                mode = await request_login(lovable_page, email)
                if mode == "signup":
                    print("Lovable has no account for this email; creating one...")
                    try:
                        signup_result = await do_signup(lovable_page, email, password)
                    except Exception as exc:
                        print(f"Signup path failed ({exc}); falling back to the reset path.", file=sys.stderr)
                        await navigate(lovable_page, f"{LOVABLE_URL}login")
                        await request_login(lovable_page, email)
                        await do_password_reset(lovable_page, email)
                        reset_url = await read_reset_link(
                            email_id, timeout=180, ignored_keys=known_message_ids
                        )
                        try:
                            await set_password_and_verify(lovable_page, reset_url, password)
                        except PasswordRecoveryRequired:
                            password = await recover_password_and_finish(
                                lovable_page, email, email_id, known_message_ids
                            )
                    else:
                        if signup_result == "verify":
                            print("Lovable wants email verification; watching the mailbox...")
                            reset_url = await read_reset_link(
                                email_id, timeout=180, ignored_keys=known_message_ids
                            )
                            await navigate(lovable_page, reset_url)
                            await wait_for_dashboard(lovable_page, timeout=60)
                        elif signup_result == "login":
                            print("Account created; signing in with the new password...")
                            try:
                                await login_with_password(lovable_page, password)
                            except PasswordRecoveryRequired:
                                print("Lovable requested a replacement password; reading TempMail...", file=sys.stderr)
                                replacement = await read_password_from_mail(
                                    email_id, timeout=120, ignored_keys=known_message_ids
                                )
                                await navigate(lovable_page, f"{LOVABLE_URL}login")
                                await request_login(lovable_page, email)
                                await login_with_password(lovable_page, replacement)
                else:
                    print("Lovable account exists; requesting a password reset...")
                    await do_password_reset(lovable_page, email)
                    reset_url = await read_reset_link(
                        email_id, timeout=180, ignored_keys=known_message_ids
                    )
                    try:
                        await set_password_and_verify(lovable_page, reset_url, password)
                    except PasswordRecoveryRequired:
                        password = await recover_password_and_finish(
                            lovable_page, email, email_id, known_message_ids
                        )
                break
            except Exception as exc:
                last_error = exc
                if cdp_url and any(
                    marker in str(exc).lower()
                    for marker in ("browser context", "target page", "target closed")
                ):
                    try:
                        print("Browser context closed; reconnecting to the existing CDP browser...", file=sys.stderr)
                        browser, context = await reconnect_browser_context(playwright, cdp_url)
                        context.on("page", auto_install_ad_blocker)  # Re-attach after reconnect
                        temp_page = await open_tempmail_tab(context)
                        lovable_page = await get_lovable_page(context)
                        await install_ad_blocker(temp_page)
                        await install_ad_blocker(lovable_page)
                    except Exception as reconnect_error:
                        last_error = reconnect_error
                        print(f"CDP browser reconnect failed: {reconnect_error}", file=sys.stderr)
        else:
            raise FlowError(f"All attempts failed: {last_error}") from last_error

        dashboard_text = await body_text(lovable_page)
        account_menu = lovable_page.locator('button[aria-label="Account menu"]')
        try:
            await account_menu.wait_for(state="visible", timeout=20_000)
        except PlaywrightTimeoutError as exc:
            raise FlowError("Lovable dashboard account menu did not render") from exc
        if (
            "/dashboard" not in lovable_page.url
            or "Dashboard" not in dashboard_text
        ):
            raise FlowError("Dashboard loaded, but the authenticated account could not be verified")

        # Save session: cookies + credentials
        from datetime import datetime
        import pathlib
        
        sessions_dir = pathlib.Path(__file__).parent / "sessions"
        sessions_dir.mkdir(exist_ok=True)
        
        # Find next session number
        existing_sessions = sorted(sessions_dir.glob("session-*"))
        if existing_sessions:
            last_num = int(existing_sessions[-1].name.split("-")[1])
            session_num = last_num + 1
        else:
            session_num = 1
        
        session_dir = sessions_dir / f"session-{session_num}"
        session_dir.mkdir(exist_ok=True)
        
        # Save cookies
        cookies = await context.cookies()
        cookies_file = session_dir / "cookies.json"
        with open(cookies_file, "w") as f:
            json.dump(cookies, f, indent=2)
        print(f"✓ Saved {len(cookies)} cookies to {cookies_file}", file=sys.stderr)
        
        # Save credentials and metadata
        config = {
            "email": email,
            "password": password,
            "created_at": datetime.now().isoformat(),
            "dashboard_url": lovable_page.url,
            "tempmail_url": temp_page.url,
            "verified": True,
        }
        config_file = session_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)
        print(f"✓ Saved session config to {config_file}", file=sys.stderr)
        
        result = {
            "verified": True,
            "email": email,
            "password": password,
            "dashboard_url": lovable_page.url,
            "tempmail_url": temp_page.url,
            "session_dir": str(session_dir),
            "session_number": session_num,
        }
        print(json.dumps(result, indent=2))
        if keep_browser_open() and not cdp_url:
            print(
                "Browser is staying open. Press Enter to close it and exit...",
                file=sys.stderr,
            )
            try:
                await asyncio.get_running_loop().run_in_executor(None, input)
            except EOFError:
                print(
                    "stdin closed; waiting 1 hour before closing the browser...",
                    file=sys.stderr,
                )
                await asyncio.sleep(3600)
            except KeyboardInterrupt:
                pass
        return result

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cdp-url",
        default=os.environ.get("BU_CDP_WS"),
        help="Browser CDP WebSocket URL. Defaults to BU_CDP_WS. When omitted, "
        "the script launches its own hardened Chrome (ad blocker + WARP proxy).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        asyncio.run(run(args.cdp_url))
    except Exception as exc:
        import traceback

        traceback.print_exc()
        print(f"Automation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
