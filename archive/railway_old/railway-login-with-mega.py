#!/usr/bin/env python3
"""Sign in to Railway, keep the browser open on the dashboard, register
the browserless Railway CLI session, and sync to Mega.nz."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import secrets
import subprocess
import sys
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from playwright.async_api import async_playwright
from playwright.async_api import expect
import socket


RAILWAY_HOME = "https://railway.com/"
RAILWAY_DASHBOARD = "https://railway.com/dashboard"
TEMP_MAIL_HOME = "https://22.do/"
ACTION_TIMEOUT = 30_000
EMAIL_TIMEOUT = 180_000
CLOUDFLARE_TIMEOUT = 180_000
WARP_PROXY = "socks5://127.0.0.1:40000"

RAILWAY_OAUTH = "https://backboard.railway.com/oauth"
RAILWAY_CLIENT_ID = "rlwy_oaci_onEklvmksh1hRUiCo7E2zX12"
RAILWAY_GRAPHQL = "https://backboard.railway.com/graphql/v2"

# Mega.nz account #4 — rclone config (from rabbyos-dash/rclone-mega4/)
MEGA_RCLONE_CONF = Path("/home/alae/Documents/repos/rabbyos-dash/rclone-mega4/rclone.conf")
MEGA_REMOTE = "mega"
MEGA_REMOTE_PATH = "railway_sessions"  # Remote folder name inside Mega


def proxy_settings() -> dict | None:
    """Return proxy config if WARP is listening, else None (graceful fallback)."""
    try:
        with socket.create_connection(("127.0.0.1", 40000), timeout=2):
            pass
        return {
            "server": WARP_PROXY,
            "bypass": "22.do,127.0.0.1,localhost,railway.com"
        }
    except OSError:
        print(
            "WARP proxy (127.0.0.1:40000) is not running; using a direct connection.",
            file=sys.stderr,
        )
        return None


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
    domain  = page.locator("#mail-choices")
    await expect(account).to_be_visible()
    await expect(account).not_to_have_value("")

    # Use JS click to bypass any ad overlays covering the buttons
    prev = await account.input_value()
    for _ in range(6):
        await page.evaluate("document.getElementById('mail-random')?.click()")
        await page.wait_for_timeout(1_500)
        if await account.input_value() != prev:
            break

    username = await account.input_value()
    domain_val = await domain.input_value()
    # domain_val may already include '@' or not
    if "@" in username:
        email = username
    elif "@" in domain_val:
        email = f"{username}{domain_val}"
    else:
        email = f"{username}@{domain_val}"

    # JS click Open to avoid overlay interception
    await page.evaluate("document.getElementById('into-mailbox')?.click()")
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
    try:
        await page.goto(RAILWAY_DASHBOARD, wait_until="domcontentloaded", timeout=15_000)
        await wait_for_cloudflare(page, "Railway dashboard")
        # Only truly logged in if we stay on dashboard, not redirected to login
        await page.wait_for_timeout(2_000)
        return "/login" not in page.url and "/dashboard" in page.url
    except Exception:
        return False


async def sign_in_to_railway(page, email: str, inbox_page, timeout_ms: int) -> None:
    if await is_logged_in(page):
        print("Already logged in to Railway.")
        return

    # Go directly to login page
    await goto_with_retry(page, "https://railway.com/login")
    await wait_for_cloudflare(page, "Railway login")
    await page.wait_for_timeout(2_000)

    # Page shows "Continue with GitHub" + "Log in using email" link — click email link
    email_login_link = page.get_by_text(re.compile(r"Log in using email", re.I))
    try:
        await expect(email_login_link).to_be_visible(timeout=8_000)
        await email_login_link.click()
        await page.wait_for_timeout(1_500)
    except Exception:
        pass  # Maybe email field is already shown

    # Now fill in the email field
    email_field = page.locator('input[type="email"], input[name="email"]').first
    await expect(email_field).to_be_visible(timeout=ACTION_TIMEOUT)
    await email_field.fill(email)
    print(f"Filled email: {email}")

    # Click Continue / Send code button
    continue_button = page.get_by_role("button", name=re.compile(r"Continue|Send|Next|Sign in", re.I)).first
    await expect(continue_button).to_be_visible(timeout=ACTION_TIMEOUT)
    await continue_button.click()

    await page.bring_to_front()
    await page.wait_for_timeout(2_000)

    code = await wait_for_railway_code(inbox_page, timeout_ms)
    print(f"Railway login code received: {code}")

    await page.bring_to_front()
    # Railway uses individual digit input boxes — try typing digit by digit first
    digit_inputs = page.locator('input[inputmode="numeric"], input[maxlength="1"]')
    digit_count = await digit_inputs.count()
    if digit_count >= 6:
        print("Detected digit-by-digit OTP input")
        for i, digit in enumerate(code):
            await digit_inputs.nth(i).fill(digit)
            await page.wait_for_timeout(100)
    else:
        # Fallback: single input field
        code_field = page.locator('input[type="text"], input[name="code"], input[inputmode="numeric"], input[autocomplete="one-time-code"]').first
        await expect(code_field).to_be_visible(timeout=ACTION_TIMEOUT)
        await code_field.fill(code)

    submit_button = page.get_by_role("button", name=re.compile(r"Verify|Submit|Continue", re.I))
    await expect(submit_button).to_be_visible()
    await submit_button.click()

    await expect(page).to_have_url(
        re.compile(r"railway\.com/(dashboard|account|new|projects)"), timeout=ACTION_TIMEOUT
    )
    print("Successfully logged in to Railway.")


async def accept_railway_policies(page) -> None:
    await wait_for_cloudflare(page, "Railway dashboard")
    await page.wait_for_timeout(2_000)

    dialog = page.get_by_role("dialog", name=re.compile(r"Terms of Service|Fair Use Policy", re.I)).first
    try:
        await dialog.wait_for(state="visible", timeout=5_000)
    except Exception:
        return

    for _ in range(6):
        try:
            agree_button = page.get_by_role("button", name=re.compile(r"I agree|Accept|Continue", re.I)).first
            if await agree_button.count() and await agree_button.is_visible():
                await agree_button.click()
                await page.wait_for_timeout(1_000)
        except Exception:
            break


def start_oauth_server() -> tuple[str, str, asyncio.Task]:
    """Start local OAuth callback server and return (verifier, state, server_task)."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    state = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()

    code_future = asyncio.Future()

    async def handle_callback(reader, writer):
        try:
            request_line = (await reader.readline()).decode()
            match = re.search(r"GET /callback\?(.+) HTTP", request_line)
            if match:
                params = urllib.parse.parse_qs(match.group(1))
                if params.get("code"):
                    code_future.set_result(params["code"][0])
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n<h1>Success! Return to terminal.</h1>")
            await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()

    async def server():
        srv = await asyncio.start_server(handle_callback, "127.0.0.1", 0)
        port = srv.sockets[0].getsockname()[1]
        redirect_uri = f"http://127.0.0.1:{port}/callback"
        
        challenge = base64.urlsafe_b64encode(
            __import__("hashlib").sha256(verifier.encode()).digest()
        ).rstrip(b"=").decode()
        
        auth_url = (
            f"{RAILWAY_OAUTH}/authorize?"
            f"client_id={RAILWAY_CLIENT_ID}&"
            f"response_type=code&"
            f"redirect_uri={quote(redirect_uri)}&"
            f"code_challenge={challenge}&"
            f"code_challenge_method=S256&"
            f"state={state}&"
            f"scope=openid%20profile%20email%20offline_access"
        )
        
        code_future.add_done_callback(lambda _: srv.close())
        async with srv:
            return (redirect_uri, auth_url, await code_future)

    task = asyncio.create_task(server())
    return (verifier, state, task)


async def get_oauth_tokens(page) -> dict:
    """Exchange OAuth code for tokens."""
    verifier, state, server_task = start_oauth_server()
    redirect_uri, auth_url, code = await server_task

    request = urllib.request.Request(
        f"{RAILWAY_OAUTH}/token",
        data=urllib.parse.urlencode({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": RAILWAY_CLIENT_ID,
            "code_verifier": verifier,
        }).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode())


def get_web_user(cookies: list[dict]) -> dict:
    """Extract user info from cookies."""
    for cookie in cookies:
        if cookie.get("name") == "railway.user":
            try:
                return json.loads(urllib.parse.unquote(cookie["value"]))
            except Exception:
                pass
    return {}


def next_session_dir(railway_dir: Path) -> Path:
    """Find next available session-N directory."""
    highest = 0
    for candidate in railway_dir.glob("session-*"):
        try:
            num = int(candidate.name.split("-")[-1])
            highest = max(highest, num)
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
        "user": {
            "id": user.get("id", str(uuid.uuid4())),
            "token": None,
            "accessToken": tokens["access_token"],
            "refreshToken": tokens.get("refresh_token", ""),
            "tokenExpiresAt": expires_at,
        },
        "projects": {},
        "editor": None,
        "linkedFunctions": None,
        "sandboxes": None,
        "activeSandbox": None,
        "sandboxTemplates": None,
        "codeAgents": None,
    }
    
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
    
    # Save browser cookies
    (session_dir / "browser_cookies.json").write_text(json.dumps(cookies, indent=2))


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


def rclone(*args, timeout=60) -> subprocess.CompletedProcess:
    """Run rclone with the mega4 config."""
    cmd = ["rclone", "--config", str(MEGA_RCLONE_CONF), "--transfers", "1", "--timeout", "90s"] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def sync_to_mega(session_dir: Path) -> None:
    """Sync session directory to Mega.nz with merge conflict resolution."""
    if not MEGA_RCLONE_CONF.exists():
        print(f"⚠️  rclone config not found at {MEGA_RCLONE_CONF}. Skipping sync.", file=sys.stderr)
        return

    print(f"📤 Syncing {session_dir.name} to Mega.nz (account #4)...")

    try:
        # 1. Create remote directory if needed
        rclone("mkdir", f"{MEGA_REMOTE}:{MEGA_REMOTE_PATH}", timeout=20)

        # 2. Pull remote changes first — resolve conflicts by keeping both,
        #    remote files land in the parent dir, local session is untouched
        print("📥 Pulling remote changes from Mega...")
        pull = rclone(
            "copy",
            f"{MEGA_REMOTE}:{MEGA_REMOTE_PATH}",
            str(session_dir.parent),
            "--ignore-existing",   # never overwrite local sessions already on disk
            timeout=120,
        )
        if pull.returncode != 0:
            print(f"   Pull warning (non-fatal): {pull.stderr.strip()}", file=sys.stderr)

        # 3. Push local session to Mega (our changes win)
        print(f"📤 Pushing {session_dir.name} to Mega...")
        push = rclone(
            "copy",
            str(session_dir),
            f"{MEGA_REMOTE}:{MEGA_REMOTE_PATH}/{session_dir.name}",
            timeout=120,
        )

        if push.returncode == 0:
            print(f"✅ {session_dir.name} synced to mega:{MEGA_REMOTE_PATH}/{session_dir.name}")
        else:
            print(f"⚠️  Mega push failed: {push.stderr.strip()}", file=sys.stderr)

    except subprocess.TimeoutExpired:
        print("⚠️  Mega sync timed out. Session saved locally only.", file=sys.stderr)
    except FileNotFoundError:
        print("⚠️  rclone not found. Install: https://rclone.org/downloads/", file=sys.stderr)
    except Exception as e:
        print(f"⚠️  Mega sync error: {e}", file=sys.stderr)


async def run(profile_dir: Path, email_timeout_ms: int, railway_dir: Path) -> None:
    profile_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        proxy = proxy_settings()
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            channel="chrome",
            headless=False,
            viewport={"width": 1440, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
            proxy=proxy,
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        async def abort_overlay(route):
            await route.abort()

        await context.route("**luminaire.railway.com/**", abort_overlay)
        # Block ad networks that inject overlays covering buttons on 22.do
        for ad_pattern in [
            "**doubleclick.net/**",
            "**googleadservices.com/**",
            "**googlesyndication.com/**",
            "**adservice.google.com/**",
            "**ads.pubmatic.com/**",
            "**amazon-adsystem.com/**",
        ]:
            await context.route(ad_pattern, abort_overlay)
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
            
            # Sync to Mega.nz
            sync_to_mega(session_dir)
            
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
    railway_dir = Path.home() / "Documents" / "railways"
    railway_dir.mkdir(parents=True, exist_ok=True)
    
    profile_dir = railway_dir / "browser_profile"
    
    print(f"🚀 Railway CLI Session Creator + Mega Sync")
    print(f"📁 Sessions directory: {railway_dir}")
    print(f"🌐 Mega remote path: {MEGA_REMOTE_PATH}")
    print()
    
    try:
        asyncio.run(run(profile_dir, EMAIL_TIMEOUT, railway_dir))
    except Exception as error:
        print(f"❌ {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
