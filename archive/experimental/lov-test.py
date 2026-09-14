#!/usr/bin/env python3
"""Create a TempMailHub address and sign in to Lovable with it.

By default, the script launches a visible, isolated Chromium profile. It keeps
the TempMailHub tab open, opens a Lovable tab, requests a password reset, reads
the reset message, sets the password to the email address, and verifies the
Lovable dashboard. An existing browser can be used with --cdp-url instead.

Install:
    python -m pip install "playwright>=1.45,<2"
    python -m playwright install chromium

Run on a normal computer:
    python lovable_temp_login.py

Keep the launched browser open after success:
    python lovable_temp_login.py

Close the launched browser automatically instead:
    python lovable_temp_login.py --close-browser

Use Browser Use Cloud or another CDP browser:
    BU_CDP_WS="<browser websocket url>" python lovable_temp_login.py
    python lovable_temp_login.py --cdp-url "<browser websocket url>"

The generated password matches the generated email because that was requested
for this workflow. If the generated email has no digit, Lovable's validation
requires a trailing ``1``. This is not a safe password for a real account.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

from playwright.async_api import (
    BrowserContext,
    Error as PlaywrightError,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)
from playwright.async_api import async_playwright


TEMPMAIL_URL = "https://tempmailhub.org/"
LOVABLE_URL = "https://lovable.dev/"
RESET_SUBJECT = "Reset your password for Lovable"
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", re.IGNORECASE)


class FlowError(RuntimeError):
    """Raised when a site does not reach the expected state."""


async def body_text(page: Page) -> str:
    try:
        return await page.locator("body").inner_text(timeout=3_000)
    except PlaywrightTimeoutError:
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
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    except PlaywrightTimeoutError:
        # Cloudflare may keep the initial navigation open while it verifies the browser.
        pass


async def click_exact(page: Page, text: str, timeout: float = 15) -> None:
    locator = page.get_by_role("button", name=text, exact=True)
    if await locator.count() == 0:
        locator = page.get_by_role("menuitem", name=text, exact=True)
    if await locator.count() == 0:
        locator = page.get_by_text(text, exact=True)
    if await locator.count() == 0:
        raise FlowError(f"Could not find clickable text {text!r} on {page.url}")
    await locator.last.click(timeout=timeout * 1_000, force=True)


async def dismiss_cookie_banner(page: Page) -> None:
    for label in ("Accept all", "OK", "Reject all"):
        button = page.get_by_role("button", name=label, exact=True)
        if await button.count() and await button.last.is_visible():
            await button.last.click(force=True)
            return


async def remove_tempmail_popup(page: Page) -> None:
    await page.evaluate(
        """() => {
          document.querySelectorAll('[role="dialog"][aria-modal="true"]')
            .forEach(node => node.remove());
        }"""
    )


async def get_page(context: BrowserContext, host: str) -> Page:
    for page in context.pages:
        if host in page.url:
            return page
    for page in context.pages:
        if page.url in ("", "about:blank"):
            return page
    return await context.new_page()


async def create_temp_email(page: Page) -> str:
    await navigate(page, TEMPMAIL_URL)
    await page.wait_for_selector('button[title="Generate new email"]', timeout=30_000)
    await remove_tempmail_popup(page)

    generate = page.locator('button[title="Generate new email"]')
    await generate.click(force=True)
    await page.wait_for_timeout(1_000)
    await remove_tempmail_popup(page)

    deadline = asyncio.get_running_loop().time() + 20
    while asyncio.get_running_loop().time() < deadline:
        matches = EMAIL_RE.findall(await body_text(page))
        if matches:
            return matches[0]
        await page.wait_for_timeout(500)
    raise FlowError("TempMailHub did not display an email address")


async def create_unused_temp_email(page: Page, used: set[str]) -> str:
    for _ in range(3):
        email = await create_temp_email(page)
        if email not in used:
            return email
        await page.wait_for_timeout(1_000)
    raise FlowError("TempMailHub kept returning the same temporary address")


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
        await account.last.evaluate("node => node.click()")
        await page.wait_for_timeout(500)
    else:
        raise FlowError("Lovable account menu did not show Sign out")
    deadline = asyncio.get_running_loop().time() + 30
    while asyncio.get_running_loop().time() < deadline:
        if "/dashboard" not in page.url and "Log in" in await body_text(page):
            return
        await page.wait_for_timeout(500)
    raise FlowError("Lovable did not finish signing out")


async def request_reset(page: Page, email: str) -> None:
    await navigate(page, LOVABLE_URL)
    await wait_for_lovable_ready(page)
    await dismiss_cookie_banner(page)
    await sign_out_if_needed(page)

    if "/dashboard" in page.url:
        await navigate(page, LOVABLE_URL)
        await wait_for_lovable_ready(page)

    await click_exact(page, "Log in")
    email_input = page.locator('input[type="email"]').last
    for _login_try in range(2):
        try:
            await email_input.wait_for(state="visible", timeout=15_000)
            break
        except PlaywrightTimeoutError:
            if _login_try == 1:
                raise FlowError("Lovable login modal did not render its email field")
            await click_exact(page, "Log in")
    await email_input.fill(email)
    await click_exact(page, "Continue")
    await page.locator('input[type="password"]').wait_for(timeout=20_000)
    await click_exact(page, "Forgot password?")

    reset_email = page.locator('input[placeholder="Enter your email address"]')
    if await reset_email.count() == 0:
        reset_email = page.locator('input[type="email"]')
    current_email = (await reset_email.last.input_value()).strip().lower()
    if current_email != email.lower():
        await click_exact(page, "Use a different email")
        reset_email = page.locator('input[placeholder="Enter your email address"]')
        await reset_email.last.fill(email)
    await click_exact(page, "Send reset link")
    await wait_for_text(page, "Check your email", timeout=20)


async def read_reset_link(
    page: Page,
    timeout: float = 120,
    ignored_items: Optional[set[str]] = None,
) -> str:
    ignored_items = ignored_items or set()
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        await remove_tempmail_popup(page)
        current_text = await body_text(page)
        email_item = page.locator("li.email-item").filter(has_text=RESET_SUBJECT)
        for index in range(await email_item.count()):
            candidate = email_item.nth(index)
            if (await candidate.inner_text()).strip() in ignored_items:
                continue
            await candidate.click(force=True)
            link = page.locator('a[href*="resetPassword"]').first
            if await link.count():
                href = await link.get_attribute("href")
                if href:
                    return href

        retry = page.get_by_text("Try Again", exact=True)
        if await retry.count() and "Try Again" in current_text:
            await retry.last.click(force=True)
        elif "Fetching messages" in current_text:
            await page.wait_for_timeout(6_000)
            continue
        else:
            refresh = page.locator('button[title="Refresh inbox"]')
            if await refresh.count():
                await refresh.click(force=True)
        await page.wait_for_timeout(6_000)

    raise FlowError(f"Timed out waiting for {RESET_SUBJECT!r} in TempMailHub")


async def existing_reset_items(page: Page, timeout: float = 45) -> set[str]:
    """Wait for the current mailbox state before requesting a new message."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        await remove_tempmail_popup(page)
        text = await body_text(page)
        if "Fetching messages" in text:
            await page.wait_for_timeout(4_000)
            continue
        retry = page.get_by_text("Try Again", exact=True)
        if await retry.count() and "Try Again" in text:
            await retry.last.click(force=True)
            await page.wait_for_timeout(6_000)
            continue
        return set(
            await page.locator("li.email-item")
            .filter(has_text=RESET_SUBJECT)
            .all_inner_texts()
        )
    raise FlowError("TempMailHub inbox did not become ready before the reset request")


async def set_password_and_verify(page: Page, reset_url: str, password: str) -> None:
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
            raise FlowError("Lovable rejected the generated password requirements")
        await page.wait_for_timeout(500)
    else:
        raise FlowError("Lovable did not confirm the password reset")
    await wait_for_dashboard(page, timeout=45)


async def run_flow(context: BrowserContext) -> dict[str, object]:
    temp_page = await get_page(context, "tempmailhub.org")
    lovable_page = await get_page(context, "lovable.dev")

    last_error: Optional[Exception] = None
    used_emails: set[str] = set()
    for attempt in range(1, 4):
        try:
            print(f"Attempt {attempt}/3: generating a temporary address", file=sys.stderr)
            email = await create_unused_temp_email(temp_page, used_emails)
            used_emails.add(email)
            password = email if re.search(r"\d", email) else f"{email}1"
            old_reset_items = await existing_reset_items(temp_page)
            print(f"Attempt {attempt}/3: requesting Lovable reset for {email}", file=sys.stderr)
            await request_reset(lovable_page, email)
            reset_url = await read_reset_link(
                temp_page,
                timeout=75,
                ignored_items=old_reset_items,
            )
            print(f"Attempt {attempt}/3: reset email received", file=sys.stderr)
            await set_password_and_verify(lovable_page, reset_url, password)
            print(f"Attempt {attempt}/3: dashboard verified", file=sys.stderr)
            break
        except Exception as exc:
            last_error = exc
            print(f"Attempt {attempt}/3 failed: {exc}", file=sys.stderr)
    else:
        raise FlowError(f"All temporary inbox attempts failed: {last_error}") from last_error

    dashboard_text = await body_text(lovable_page)
    account_menu = lovable_page.locator('button[aria-label="Account menu"]')
    try:
        await account_menu.wait_for(state="visible", timeout=20_000)
    except PlaywrightTimeoutError as exc:
        raise FlowError("Lovable dashboard account menu did not render") from exc
    if "/dashboard" not in lovable_page.url or "Dashboard" not in dashboard_text:
        raise FlowError("Dashboard loaded, but the authenticated account could not be verified")

    return {
        "verified": True,
        "email": email,
        "password": password,
        "dashboard_url": lovable_page.url,
        "tempmail_url": temp_page.url,
    }


async def launch_local_context(playwright, args: argparse.Namespace) -> BrowserContext:
    profile_dir = Path(args.profile_dir).expanduser().resolve()
    options = {"user_data_dir": str(profile_dir), "headless": args.headless}
    if args.browser_path:
        options["executable_path"] = args.browser_path
        return await playwright.chromium.launch_persistent_context(**options)

    try:
        return await playwright.chromium.launch_persistent_context(channel="chrome", **options)
    except PlaywrightError:
        try:
            return await playwright.chromium.launch_persistent_context(**options)
        except PlaywrightError as exc:
            raise FlowError(
                "No usable browser was found. Install Google Chrome, or run "
                "'python -m playwright install chromium', then run this script again."
            ) from exc


async def run(args: argparse.Namespace) -> dict[str, object]:
    async with async_playwright() as playwright:
        owned_context = not args.cdp_url
        if args.cdp_url:
            browser = await playwright.chromium.connect_over_cdp(args.cdp_url, timeout=60_000)
            if not browser.contexts:
                raise FlowError("The connected browser has no browser context")
            context = browser.contexts[0]
        else:
            context = await launch_local_context(playwright, args)

        result = await run_flow(context)
        if owned_context and args.keep_browser_open:
            print(json.dumps(result, indent=2), flush=True)
            print("Browser left open. Press Ctrl+C to close it.", file=sys.stderr)
            try:
                while True:
                    await asyncio.sleep(3_600)
            except asyncio.CancelledError:
                pass
        if owned_context and not args.keep_browser_open:
            await context.close()
        return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cdp-url",
        default=os.environ.get("BU_CDP_WS"),
        help="Optional browser CDP WebSocket URL. Defaults to BU_CDP_WS.",
    )
    parser.add_argument(
        "--profile-dir",
        default=str(Path.home() / ".lovable-temp-login-profile"),
        help="Isolated browser profile directory for local mode.",
    )
    parser.add_argument(
        "--browser-path",
        help="Optional path to a Chrome/Chromium executable for local mode.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run local Chromium without a visible window.",
    )
    browser_lifetime = parser.add_mutually_exclusive_group()
    browser_lifetime.add_argument(
        "--keep-browser-open",
        dest="keep_browser_open",
        action="store_true",
        default=True,
        help="Keep a locally launched browser open after success (default).",
    )
    browser_lifetime.add_argument(
        "--close-browser",
        dest="keep_browser_open",
        action="store_false",
        help="Close a locally launched browser after success.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = asyncio.run(run(args))
    except KeyboardInterrupt:
        print("Browser closed.", file=sys.stderr)
        return 0
    except Exception as exc:
        print(f"Automation failed: {exc}", file=sys.stderr)
        return 1
    if not (not args.cdp_url and args.keep_browser_open):
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
