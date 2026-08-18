#!/usr/bin/env python3
"""Sign in to Railway, keep the browser open on the dashboard, and register
the browserless Railway CLI session under Documents/railways/session-N."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import secrets
import sys
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from playwright.async_api import async_playwright
from playwright.async_api import expect


RAILWAY_HOME = "https://railway.com/"
RAILWAY_DASHBOARD = "https://railway.com/dashboard"
TEMP_MAIL_HOME = "https://22.do/"
ACTION_TIMEOUT = 30_000
EMAIL_TIMEOUT = 180_000
CLOUDFLARE_TIMEOUT = 180_000

RAILWAY_OAUTH = "https://backboard.railway.com/oauth"
RAILWAY_CLIENT_ID = "rlwy_oaci_onEklvmksh1hRUiCo7E2zX12"
RAILWAY_GRAPHQL = "https://backboard.railway.com/graphql/v2"


async def wait_for_cloudflare(page, page_name: str) -> None:
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
    refresh = page.locator("#refresh")
    await expect(refresh).to_be_visible(timeout=ACTION_TIMEOUT)
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


def http_post_form(url: str, fields: dict, headers: dict | None = None) -> dict:
    body = urllib.parse.urlencode(fields).encode()
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "railway-cli/5.35.0",
            **(headers or {}),
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode())


PKCE_CHARSET = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
)
RAILWAY_SCOPES = (
    "openid email profile offline_access workspace:admin project:admin ssh_keys"
)


async def get_oauth_tokens(page) -> dict:
    """Run the CLI's authorization-code (PKCE) OAuth flow inside the
    already-logged-in browser: open the consent page, click Authorize, catch
    the redirect on a local callback server, and exchange the code for tokens.

    The plain device-code flow returns tokens without the OIDC scopes
    (openid/email/profile/offline_access), which Railway rejects when the
    GraphQL API validates them, so the browser (code) flow is required."""
    verifier = "".join(secrets.choice(PKCE_CHARSET) for _ in range(128))
    challenge = _pkce_challenge(verifier)
    state = secrets.token_urlsafe(32)

    loop = asyncio.get_running_loop()
    result_holder = {}

    async def callback_handler(reader, writer):
        request_line = (await reader.read(65536)).decode(errors="replace").split("\r\n")[0]
        path = request_line.split(" ")[1] if " " in request_line else "/"
        if not result_holder:
            result_holder["query"] = urllib.parse.parse_qs(
                urllib.parse.urlparse(path).query
            )
        body = b"<html><body>Railway login approved. You can close this tab.</body></html>"
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
            + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
            + body
        )
        await writer.drain()
        writer.close()

    callback_server = await asyncio.start_server(callback_handler, "127.0.0.1", 0)
    callback_port = callback_server.sockets[0].getsockname()[1]
    redirect_uri = f"http://127.0.0.1:{callback_port}/callback"

    try:
        authorization_url = (
            f"{RAILWAY_OAUTH}/auth?"
            + urllib.parse.urlencode(
                {
                    "response_type": "code",
                    "client_id": RAILWAY_CLIENT_ID,
                    "redirect_uri": redirect_uri,
                    "scope": RAILWAY_SCOPES,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                    "state": state,
                    "prompt": "consent",
                    "cli_caller": "opencode",
                }
            )
        )
        await page.goto(authorization_url, wait_until="domcontentloaded")

        deadline = loop.time() + 120
        while loop.time() < deadline:
            if result_holder:
                break
            await dismiss_cookie_banner(page)
            authorize = page.get_by_role("button", name="Authorize", exact=True)
            if await authorize.count():
                try:
                    await authorize.click(timeout=5_000)
                except Exception:
                    pass
            await page.wait_for_timeout(2_000)

        if not result_holder:
            raise RuntimeError("The Railway consent flow never redirected back.")
        callback_query = result_holder["query"]
        if "error" in callback_query:
            description = callback_query.get("error_description", [""])[0]
            raise RuntimeError(
                f"Railway OAuth rejected the request: "
                f"{callback_query['error'][0]} {description}"
            )
        if "code" not in callback_query or callback_query.get("state", [""])[0] != state:
            raise RuntimeError("Railway OAuth callback was missing or mismatched.")

        return http_post_form(
            f"{RAILWAY_OAUTH}/token",
            {
                "grant_type": "authorization_code",
                "code": callback_query["code"][0],
                "redirect_uri": redirect_uri,
                "client_id": RAILWAY_CLIENT_ID,
                "code_verifier": verifier,
            },
        )
    finally:
        callback_server.close()
        await callback_server.wait_closed()


def _pkce_challenge(verifier: str) -> str:
    import hashlib

    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def get_web_user(cookies: list[dict]) -> dict:
    session = {
        c["name"]: c["value"]
        for c in cookies
        if c["domain"] == "backboard.railway.com"
        and c["name"] in ("rw.session", "rw.session.sig")
    }
    if not session.get("rw.session"):
        raise RuntimeError("No rw.session cookie found for the CLI registration.")
    cookie_header = "; ".join(f"{k}={v}" for k, v in session.items())
    payload = {"query": "query { me { id email } }"}
    request = urllib.request.Request(
        RAILWAY_GRAPHQL,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Cookie": cookie_header,
            "User-Agent": "railway-cli/5.35.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Railway API user lookup failed: {error.code}") from error
    me = (data.get("data") or {}).get("me") or {}
    if not me.get("id"):
        raise RuntimeError("Railway API returned no user identity.")
    return me


def next_session_dir(railway_dir: Path) -> Path:
    highest = 2
    for candidate in railway_dir.glob("session-*"):
        try:
            highest = max(highest, int(candidate.name.split("-")[-1]))
        except ValueError:
            continue
    return railway_dir / f"session-{highest + 1}"


def write_cli_session(session_dir: Path, tokens: dict, user: dict, cookies: list[dict]) -> None:
    session_dir.mkdir(parents=True, exist_ok=True)
    cli_home = session_dir / ".railway"
    (cli_home / "sessions").mkdir(parents=True, exist_ok=True)
    (session_dir / "railway_cli_sessions").mkdir(parents=True, exist_ok=True)
    (cli_home / "config.lock").write_text("")

    now = datetime.now(timezone.utc)
    expires_at = int(now.timestamp()) + int(tokens.get("expires_in", 300))
    config = {
        "activeSandbox": None,
        "codeAgents": None,
        "editor": None,
        "linkedFunctions": None,
        "projects": {},
        "sandboxTemplates": None,
        "sandboxes": None,
        "user": {
            "accessToken": tokens["access_token"],
            "id": user["id"],
            "refreshToken": tokens.get("refresh_token"),
            "token": None,
            "tokenExpiresAt": expires_at,
        },
    }

    (session_dir / "browser_cookies.json").write_text(
        json.dumps({"cookies": cookies}, indent=2)
    )
    for target in (session_dir / "railway_cli_config.json", cli_home / "config.json"):
        target.write_text(json.dumps(config, indent=2))
    (cli_home / "version.json").write_text(
        json.dumps(
            {
                "last_update_check": now.isoformat(),
                "latest_version": None,
                "download_failures": 0,
                "skipped_version": None,
                "last_package_manager_spawn": None,
            },
            indent=2,
        )
    )
    session_payload = {
        "agent_session_id": str(uuid.uuid4()),
        "parent_pid": os.getpid(),
        "parent_btime": 0,
        "created_at": now.isoformat(),
    }
    session_name = f"{secrets.token_hex(8)}.session"
    (cli_home / "sessions" / session_name).write_text(json.dumps(session_payload))
    (session_dir / "railway_cli_sessions" / session_name).write_text(
        json.dumps(session_payload)
    )


def verify_tokens(tokens: dict, user: dict) -> str:
    request = urllib.request.Request(
        RAILWAY_GRAPHQL,
        data=json.dumps({"query": "query { me { id email } }"}).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {tokens['access_token']}",
            "User-Agent": "railway-cli/5.35.0",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        me = ((json.loads(response.read().decode())).get("data") or {}).get("me") or {}
    if not me.get("id") or me["id"] != user["id"]:
        raise RuntimeError("CLI tokens failed verification against the Railway API.")
    return me.get("email") or user.get("email") or me["id"]


async def register_cli_session(context, page, railway_dir: Path) -> Path:
    cookies = await context.cookies()
    tokens = await get_oauth_tokens(page)
    user = get_web_user(cookies)
    session_dir = next_session_dir(railway_dir)
    write_cli_session(session_dir, tokens, user, cookies)
    email = verify_tokens(tokens, user)
    print(f"CLI verification: {email} authenticated via the new session tokens.")
    return session_dir


async def run(profile_dir: Path, email_timeout_ms: int, railway_dir: Path) -> None:
    profile_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            channel="chrome",
            headless=False,
            viewport={"width": 1440, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        async def abort_overlay(route):
            await route.abort()

        # The survey widget injects an fc-message-root popup that intercepts clicks.
        await context.route("**luminaire.railway.com/**", abort_overlay)
        context.set_default_timeout(ACTION_TIMEOUT)
        context_closed = asyncio.Event()
        context.on("close", context_closed.set)
        inbox_page = await context.new_page()
        dashboard_page = await context.new_page()

        try:
            email = await create_temp_inbox(inbox_page)
            print(f"Temporary email created: {email}")
            await sign_in_to_railway(dashboard_page, email, inbox_page, email_timeout_ms)
            await accept_railway_policies(dashboard_page)
            await dashboard_page.bring_to_front()
            session_dir = await register_cli_session(context, dashboard_page, railway_dir)
            print(f"CLI session registered in: {session_dir}")
            await dashboard_page.bring_to_front()
            print(f"Logged in. Dashboard is ready at {dashboard_page.url}")
            print("Keeping the browser open. Close the browser window to exit.")
            await context_closed.wait()
        except Exception as error:
            failure_path = profile_dir / "railway_login_failure.png"
            try:
                await dashboard_page.screenshot(path=str(failure_path), full_page=True)
                print(f"A failure screenshot was saved as {failure_path}.", file=sys.stderr)
            except Exception:
                pass
            raise RuntimeError(f"Railway login failed: {error}") from error
        finally:
            await context.close()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile-dir",
        default="railway_profile",
        help="Folder for persistent cookies and session data (default: railway_profile)",
    )
    parser.add_argument(
        "--email-timeout",
        type=int,
        default=EMAIL_TIMEOUT,
        help="Milliseconds to wait for the Railway email (default: 180000)",
    )
    parser.add_argument(
        "--railway-dir",
        type=Path,
        default=Path.home() / "Documents" / "railways",
        help="Folder that holds the session-N CLI registrations (default: ~/Documents/railways)",
    )
    options = parser.parse_args()

    try:
        asyncio.run(
            run(
                profile_dir=Path(options.profile_dir).expanduser().resolve(),
                email_timeout_ms=options.email_timeout,
                railway_dir=options.railway_dir.expanduser().resolve(),
            )
        )
    except Exception as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())