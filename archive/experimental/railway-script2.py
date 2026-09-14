#!/usr/bin/env python3
"""Sign in to Railway with CleanTempMail and activate a device persistently."""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from playwright.async_api import async_playwright
from playwright.async_api import expect


RAILWAY_HOME = "https://railway.com/"
RAILWAY_DASHBOARD = "https://railway.com/dashboard"
CLEAN_TEMP_MAIL_HOME = "https://cleantempmail.com/"
ACTION_TIMEOUT = 30_000
EMAIL_TIMEOUT = 120_000
CLOUDFLARE_TIMEOUT = 180_000


async def wait_for_cloudflare(page, page_name: str) -> None:
    """Wait for a human to complete a visible Cloudflare challenge."""
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
        await expect(challenge).to_be_hidden(timeout=CLOUDFLARE_TIMEOUT)
    except AssertionError as error:
        raise RuntimeError(
            f"Cloudflare verification on {page_name} was not completed in time."
        ) from error


async def create_temp_inbox(page) -> str:
    await page.goto(CLEAN_TEMP_MAIL_HOME, wait_until="domcontentloaded")
    await wait_for_cloudflare(page, "CleanTempMail")

    # CleanTempMail exposes the generated address in this visible display.
    address = page.locator("#emailDisplay")
    await expect(address).to_be_visible()
    await expect(address).not_to_have_text(re.compile(r"Generating|\.\.\.", re.I))

    previous_address = await address.inner_text()
    await page.get_by_role("button", name="Random", exact=True).click()
    await expect(address).not_to_have_text(previous_address)
    email = (await address.inner_text()).strip()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise RuntimeError(f"CleanTempMail returned an invalid address: {email!r}")

    await expect(page.get_by_role("button", name="Refresh", exact=True)).to_be_visible()
    return email


async def wait_for_railway_code(page, timeout_ms: int) -> str:
    message = page.get_by_text(
        re.compile(r"\b\d{6}\s+is your Railway login code\b", re.I)
    ).first
    refresh = page.get_by_role("button", name="Refresh", exact=True)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_ms / 1000

    while loop.time() < deadline:
        await wait_for_cloudflare(page, "CleanTempMail inbox")
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
        "Railway sent no six-digit login code to the CleanTempMail inbox before the timeout."
    )


async def is_logged_in(page) -> bool:
    await page.goto(RAILWAY_DASHBOARD, wait_until="domcontentloaded")
    await wait_for_cloudflare(page, "Railway dashboard")
    try:
        await expect(
            page.get_by_text("My Projects", exact=True).first
        ).to_be_visible(timeout=5_000)
        return True
    except AssertionError:
        return False


async def sign_in_to_railway(page, email: str, inbox_page, email_timeout_ms: int) -> None:
    if await is_logged_in(page):
        return

    await page.goto(RAILWAY_HOME, wait_until="domcontentloaded")
    await wait_for_cloudflare(page, "Railway")
    await expect(page.get_by_role("button", name="Sign in", exact=True)).to_be_visible()
    await page.get_by_role("button", name="Sign in", exact=True).click()
    await page.get_by_role("button", name="Log in using email", exact=True).click()

    email_input = page.get_by_placeholder("hello@email.com")
    await expect(email_input).to_be_visible()
    await email_input.fill(email)
    await page.get_by_role("button", name="Continue with Email", exact=True).click()
    await wait_for_cloudflare(page, "Railway sign-in")

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


async def accept_railway_policies(page) -> None:
    await wait_for_cloudflare(page, "Railway dashboard")
    await expect(page).to_have_url(re.compile(r"/dashboard(?:/|$)"))

    dialog = page.get_by_role("dialog", name=re.compile(r"Terms of Service", re.I)).last
    try:
        await expect(dialog).to_be_visible(timeout=ACTION_TIMEOUT)
    except AssertionError:
        return

    scroll_hint = dialog.get_by_role(
        "button", name="Scroll to read all terms", exact=True
    )
    await expect(scroll_hint).to_be_visible()
    await scroll_hint.evaluate(
        """button => {
            let element = button.parentElement;
            while (element && element.scrollHeight <= element.clientHeight) {
                element = element.parentElement;
            }
            if (!element) throw new Error('Terms scroll panel was not found');
            element.scrollTop = element.scrollHeight;
            element.dispatchEvent(new Event('scroll', { bubbles: true }));
        }"""
    )

    privacy = dialog.get_by_role(
        "button", name="I agree with Railway's Terms of Service", exact=True
    )
    await expect(privacy).to_be_enabled()
    await privacy.click()

    fair_use = dialog.get_by_role(
        "button", name="I agree to the Fair Use Policy", exact=True
    )
    await expect(fair_use).to_be_visible()
    await fair_use.click()
    await expect(page.get_by_text("Terms accepted", exact=True)).to_be_visible()


async def activate_device(page, activation_url: str, user_code: str) -> None:
    await page.goto(activation_url, wait_until="domcontentloaded")
    await wait_for_cloudflare(page, "Railway device activation")
    await expect(
        page.get_by_role("button", name="Sign in or create account", exact=True)
    ).to_be_visible()
    await page.get_by_role(
        "button", name="Sign in or create account", exact=True
    ).click()
    await wait_for_cloudflare(page, "Railway device authorization")

    authorize = page.get_by_role("button", name="Authorize", exact=True)
    try:
        await expect(authorize).to_be_visible(timeout=5_000)
    except AssertionError:
        # Some Railway sessions show a second device-code form after sign-in.
        device_code = page.get_by_label("Device Code")
        if not await device_code.count():
            device_code = page.get_by_placeholder("XXXX-XXXX")
        await expect(device_code).to_be_visible()
        if not user_code:
            raise RuntimeError("Railway requested a device code, but none was provided.")
        await device_code.fill(user_code)
        await page.get_by_role("button", name="Continue", exact=True).click()
        await wait_for_cloudflare(page, "Railway device authorization")
        await expect(authorize).to_be_visible()

    await authorize.click()
    await expect(page).to_have_url(re.compile(r"/dashboard(?:/|$)"))
    await expect(page.get_by_text("My Projects", exact=True).first).to_be_visible()


async def run(
    activation_url: str,
    user_code: str,
    profile_dir: Path,
    headless: bool,
    close_when_done: bool,
    email_timeout_ms: int,
) -> None:
    profile_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=headless,
            viewport={"width": 1440, "height": 900},
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
            await activate_device(railway_page, activation_url, user_code)
            await railway_page.bring_to_front()
            print(f"Device activated. Railway is ready at {railway_page.url}")
            print(f"Persistent cookies and session data are stored in: {profile_dir}")

            if not close_when_done:
                try:
                    await asyncio.to_thread(input, "Browser is ready. Press Enter to close it. ")
                except EOFError:
                    pass
        except Exception as error:
            failure_path = profile_dir / "railway_clean_temp_mail_failure.png"
            try:
                await railway_page.screenshot(path=str(failure_path), full_page=True)
                print(f"A failure screenshot was saved as {failure_path}.", file=sys.stderr)
            except Exception:
                pass
            raise RuntimeError(f"CleanTempMail Railway automation failed: {error}") from error
        finally:
            await context.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--user-code", help="One-time Railway code such as SQLB-MKRB")
    source.add_argument("--activation-url", help="Full Railway /activate URL")
    parser.add_argument(
        "--profile-dir",
        default="railway_clean_temp_mail_profile",
        help="Folder for persistent cookies and session data",
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
        user_code = unquote(parse_qs(urlparse(activation_url).query).get("user_code", [""])[0])
    else:
        user_code = options.user_code
        activation_url = f"https://railway.com/activate?user_code={quote(user_code)}"
    if not user_code:
        parser.error("The activation URL must contain user_code, or pass --user-code.")
    try:
        asyncio.run(
            run(
                activation_url=activation_url,
                user_code=user_code,
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
