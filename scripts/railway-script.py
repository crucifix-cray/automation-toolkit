#!/usr/bin/env python3
"""Sign in to Railway, activate a device, and persist the browser session."""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path
from urllib.parse import quote

from playwright.async_api import async_playwright
from playwright.async_api import expect


RAILWAY_HOME = "https://railway.com/"
RAILWAY_DASHBOARD = "https://railway.com/dashboard"
TEMP_MAIL_HOME = "https://22.do/"
ACTION_TIMEOUT = 30_000
EMAIL_TIMEOUT = 120_000
CLOUDFLARE_TIMEOUT = 180_000


async def wait_for_cloudflare(page, page_name: str) -> None:
    """Wait for a human to complete a visible Cloudflare challenge."""
    challenge_widgets = page.locator(
        'iframe[src*="challenges.cloudflare.com"], '
        'input[type="checkbox"][name*="cf-turnstile"], '
        "#challenge-stage, #cf-chl-widget, .cf-turnstile"
    )
    challenge_copy = page.get_by_text(
        re.compile(
            r"Verify you are human|Checking your browser|Just a moment|Attention Required|"
            r"Sorry, you have been blocked|Click to reveal",
            re.I,
        )
    ).first

    challenge = None
    if await challenge_copy.count() and await challenge_copy.is_visible():
        challenge = challenge_copy
    else:
        # Invisible 1x1 Turnstile frames are normal risk checks, not a checkbox.
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
        # Cloudflare owns the checkbox. Do not simulate or bypass it.
        await expect(challenge).to_be_hidden(timeout=CLOUDFLARE_TIMEOUT)
    except AssertionError as error:
        raise RuntimeError(
            f"Cloudflare verification on {page_name} was not completed in time."
        ) from error


async def goto_with_retry(page, url: str, attempts: int = 4) -> None:
    for attempt in range(attempts):
        try:
            await page.goto(url, wait_until="domcontentloaded")
            return
        except Exception:
            if attempt == attempts - 1:
                raise
            await page.wait_for_timeout(5_000 * (attempt + 1))


async def create_temp_inbox(page) -> str:
    await goto_with_retry(page, TEMP_MAIL_HOME)
    await wait_for_cloudflare(page, "22.do")

    account = page.locator("#mail-input")
    domain = page.locator("#mail-choices")
    await expect(account).to_be_visible()
    await expect(account).not_to_have_value("")

    # The Random control prevents a persistent profile from reusing an old inbox.
    # Its AJAX call can fail with 403 right after load, so retry until the value moves.
    previous_address = await account.input_value()
    for _ in range(5):
        await page.locator("#mail-random").click()
        try:
            await expect(account).not_to_have_value(previous_address, timeout=5_000)
            break
        except AssertionError:
            continue
    email = f"{await account.input_value()}{await domain.input_value()}"

    await page.locator("#into-mailbox").click()
    await expect(page).to_have_url(re.compile(r"/inbox/"), timeout=ACTION_TIMEOUT)
    await expect(page.locator("#refresh")).to_be_visible(timeout=ACTION_TIMEOUT)
    return email


async def wait_for_railway_code(page, timeout_ms: int) -> str:
    message = page.get_by_text(
        re.compile(r"\b\d{6}\s+is your Railway login code\b", re.I)
    ).first
    refresh = page.locator("#refresh")
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_ms / 1000

    while loop.time() < deadline:
        await wait_for_cloudflare(page, "22.do inbox")
        remaining = max(100, int((deadline - loop.time()) * 1000))
        try:
            await expect(message).to_be_visible(timeout=min(5_000, remaining))
            text = await message.inner_text()
            match = re.search(r"\b(\d{6})\s+is your Railway login code\b", text, re.I)
            if match:
                return match.group(1)
        except AssertionError:
            if loop.time() >= deadline:
                break
            await expect(refresh).to_be_visible(timeout=min(ACTION_TIMEOUT, remaining))
            await refresh.click()

    raise RuntimeError(
        "Railway sent no six-digit login code to the 22.do inbox before the timeout."
    )


async def is_logged_in(page) -> bool:
    await page.goto(RAILWAY_DASHBOARD, wait_until="domcontentloaded")
    await wait_for_cloudflare(page, "Railway dashboard")
    try:
        await expect(page).to_have_url(
            re.compile(r"/dashboard(?:/|$)"), timeout=15_000
        )
        await expect(
            page.get_by_text("My Projects", exact=True).first
        ).to_be_visible(timeout=10_000)
        return True
    except AssertionError:
        return False


async def sign_in_to_railway(page, email: str, inbox_page, email_timeout_ms: int) -> None:
    if await is_logged_in(page):
        return

    await page.goto(RAILWAY_HOME, wait_until="domcontentloaded")
    await wait_for_cloudflare(page, "Railway")

    sign_in = page.get_by_role("button", name="Sign in", exact=True)
    await expect(sign_in).to_be_visible()
    await sign_in.click()
    await page.get_by_role("button", name="Log in using email", exact=True).click()

    email_input = page.get_by_placeholder("hello@email.com")
    await expect(email_input).to_be_visible()
    await email_input.fill(email)
    await page.get_by_role("button", name="Continue with Email", exact=True).click()
    await wait_for_cloudflare(page, "Railway sign-in")

    # The iframe first loads auth.magic.link/send, then changes to the OTP view.
    magic_frame_selector = 'iframe[src*="auth.magic.link"]'
    await expect(page.locator(magic_frame_selector)).to_be_attached(
        timeout=ACTION_TIMEOUT
    )
    magic = page.frame_locator(magic_frame_selector)
    fields = [
        magic.get_by_role("textbox", name=f"one time password input {number}", exact=True)
        for number in range(1, 7)
    ]
    await expect(fields[0]).to_be_visible(timeout=ACTION_TIMEOUT)

    code = await wait_for_railway_code(inbox_page, email_timeout_ms)
    if len(code) != len(fields):
        raise RuntimeError("Railway returned a verification code with the wrong length.")
    for field, digit in zip(fields, code):
        await field.fill(digit)

    await expect(page).to_have_url(
        re.compile(r"/dashboard(?:/|$)"), timeout=email_timeout_ms
    )


async def scroll_terms_dialog(dialog) -> None:
    """Scroll every scrollable container inside the terms dialog so the
    agreement buttons render."""
    await dialog.evaluate(
        """dialog => {
            for (const el of [dialog, ...dialog.querySelectorAll('*')]) {
                if (el.scrollHeight > el.clientHeight + 10) {
                    el.scrollTop = el.scrollHeight;
                    el.dispatchEvent(new Event('scroll', { bubbles: true }));
                }
            }
        }"""
    )


async def dismiss_cookie_banner(page) -> None:
    """Railway occasionally shows a survey/cookie-consent overlay that can
    intercept clicks; dismiss it if present."""
    for _ in range(4):
        root = page.locator(".fc-message-root").first
        if not await root.count() or not await root.is_visible():
            return
        buttons = root.locator("button")
        clicked = False
        for index in range(await buttons.count()):
            button = buttons.nth(index)
            if not await button.is_visible():
                continue
            try:
                await button.click(timeout=2_000)
                clicked = True
                break
            except Exception:
                continue
        if not clicked:
            await root.evaluate("el => el.remove()")
            return
        await page.wait_for_timeout(500)


async def accept_railway_policies(page) -> None:
    await wait_for_cloudflare(page, "Railway dashboard")
    await expect(page).to_have_url(re.compile(r"/dashboard(?:/|$)"))
    await dismiss_cookie_banner(page)
    dialog = page.get_by_role("dialog", name=re.compile(r"Terms of Service", re.I)).last
    try:
        await dialog.wait_for(state="visible", timeout=ACTION_TIMEOUT)
    except Exception:
        return

    agree_buttons = [
        "I agree with Railway's Terms of Service",
        "I agree to the Fair Use Policy",
    ]
    for _ in range(6):
        try:
            await scroll_terms_dialog(dialog)
        except Exception:
            break
        clicked = False
        for name in agree_buttons:
            await dismiss_cookie_banner(page)
            button = page.get_by_role("button", name=name, exact=True)
            try:
                await expect(button).to_be_visible(timeout=3_000)
                await expect(button).to_be_enabled(timeout=3_000)
            except AssertionError:
                continue
            await button.click()
            clicked = True
            break
        if not clicked:
            break
        await page.wait_for_timeout(1_500)

    try:
        await expect(page.get_by_text("Terms accepted", exact=True)).to_be_visible(
            timeout=15_000
        )
    except AssertionError:
        try:
            await expect(dialog).to_be_hidden(timeout=5_000)
        except AssertionError:
            pass


async def activate_device(page, activation_url: str) -> None:
    await page.goto(activation_url, wait_until="domcontentloaded")
    await wait_for_cloudflare(page, "Railway device activation")

    sign_in_or_create = page.get_by_role(
        "button", name="Sign in or create account", exact=True
    )
    await expect(sign_in_or_create).to_be_visible()
    await sign_in_or_create.click()
    await wait_for_cloudflare(page, "Railway device authorization")

    authorize = page.get_by_role("button", name="Authorize", exact=True)
    await expect(authorize).to_be_visible()
    await authorize.click()

    await expect(page).to_have_url(re.compile(r"/dashboard(?:/|$)"))
    await expect(page.get_by_text("My Projects", exact=True).first).to_be_visible()


async def run(
    activation_url: str,
    profile_dir: Path,
    headless: bool,
    close_when_done: bool,
    email_timeout_ms: int,
) -> None:
    profile_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            channel="chrome",
            headless=headless,
            viewport={"width": 1440, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        context.set_default_timeout(ACTION_TIMEOUT)
        inbox_page = await context.new_page()
        railway_page = await context.new_page()

        try:
            email = await create_temp_inbox(inbox_page)
            print(f"Temporary email created: {email}")
            await sign_in_to_railway(
                railway_page,
                email,
                inbox_page,
                email_timeout_ms,
            )
            await accept_railway_policies(railway_page)
            await activate_device(railway_page, activation_url)
            await railway_page.bring_to_front()
            print(f"Device activated. Railway is ready at {railway_page.url}")
            print(f"Persistent cookies and session data are stored in: {profile_dir}")

            if not close_when_done:
                try:
                    await asyncio.to_thread(input, "Browser is ready. Press Enter to close it. ")
                except EOFError:
                    pass
        except Exception as error:
            failure_path = profile_dir / "railway_activation_failure.png"
            try:
                await railway_page.screenshot(path=str(failure_path), full_page=True)
                print(f"A failure screenshot was saved as {failure_path}.", file=sys.stderr)
            except Exception:
                pass
            raise RuntimeError(f"Railway activation failed: {error}") from error
        finally:
            # Closing a persistent context writes cookies and storage to profile_dir.
            await context.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--user-code", help="One-time Railway code such as SQLB-MKRB")
    source.add_argument("--activation-url", help="Full Railway /activate URL")
    parser.add_argument(
        "--profile-dir",
        default="railway_profile",
        help="Folder for persistent cookies and session data (default: railway_profile)",
    )
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--close", action="store_true")
    parser.add_argument(
        "--email-timeout",
        type=int,
        default=EMAIL_TIMEOUT,
        help="Milliseconds to wait for the Railway email (default: 120000)",
    )
    options = parser.parse_args()

    if options.activation_url:
        activation_url = options.activation_url
    else:
        activation_url = f"https://railway.com/activate?user_code={quote(options.user_code)}"

    try:
        asyncio.run(
            run(
                activation_url=activation_url,
                profile_dir=Path(options.profile_dir).expanduser().resolve(),
                headless=options.headless,
                close_when_done=options.close,
                email_timeout_ms=options.email_timeout,
            )
        )
    except Exception as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
