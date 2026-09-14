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
import subprocess

from patchright.async_api import async_playwright
from patchright.async_api import expect
import socket

# Patchright has built-in stealth, no need for extra plugins

# Import playwright-captcha for auto Cloudflare Turnstile solving
try:
    from playwright_captcha import CaptchaType, ClickSolver, FrameworkType
    CAPTCHA_SOLVER_AVAILABLE = True
except ImportError:
    CAPTCHA_SOLVER_AVAILABLE = False
    print("⚠️  playwright-captcha not installed. Install with: pip install playwright-captcha", file=sys.stderr)


RAILWAY_HOME = "https://railway.com/"
RAILWAY_DASHBOARD = "https://railway.com/dashboard"
TEMPMAIL_URL = "https://tempmailhub.org/"
TEMPMAIL_API = "https://api.tempmailhub.org"
ACTION_TIMEOUT = 30_000
EMAIL_TIMEOUT = 180_000
CLOUDFLARE_TIMEOUT = 180_000
WARP_PROXY = "socks5://127.0.0.1:40000"

RAILWAY_OAUTH = "https://backboard.railway.com/oauth"
RAILWAY_CLIENT_ID = "rlwy_oaci_onEklvmksh1hRUiCo7E2zX12"
RAILWAY_GRAPHQL = "https://backboard.railway.com/graphql/v2"

# Email validation
GMAIL_RE = re.compile(r"\b[A-Za-z0-9_]+@gmail\.com\b", re.IGNORECASE)


def rotate_warp_ip():
    """Rotate WARP IP by updating wgcf account and restarting WireGuard."""
    print("🔄 Rotating WARP IP...")
    
    old_ip = check_current_ip()
    
    try:
        # Update wgcf account to get new IP
        result = subprocess.run(
            ["sudo", "wgcf", "update"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            print(f"⚠️  wgcf update failed: {result.stderr}", file=sys.stderr)
            return False
        
        # Regenerate WireGuard profile
        result = subprocess.run(
            ["sudo", "wgcf", "generate"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            print(f"⚠️  wgcf generate failed: {result.stderr}", file=sys.stderr)
            return False
        
        # Restart WireGuard interface
        # First, stop it
        subprocess.run(
            ["sudo", "wg-quick", "down", "wgcf"],
            capture_output=True,
            timeout=10
        )
        
        # Then start it with new config
        result = subprocess.run(
            ["sudo", "wg-quick", "up", "wgcf"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            print(f"⚠️  WireGuard up failed: {result.stderr}", file=sys.stderr)
            return False
        
        # Start SOCKS5 proxy on port 40000 if not already running
        start_warp_proxy()
        
        # Wait for connection to stabilize
        import time
        time.sleep(3)
        
        # Verify IP actually changed
        new_ip = check_current_ip()
        if new_ip == old_ip:
            print(f"⚠️  IP didn't change! Still: {old_ip}", file=sys.stderr)
            return False
        
        print(f"✅ WARP IP rotated: {old_ip} → {new_ip}")
        return True
        
    except subprocess.TimeoutExpired:
        print("⚠️  WARP rotation timeout", file=sys.stderr)
        return False
    except Exception as e:
        print(f"⚠️  WARP rotation error: {e}", file=sys.stderr)
        return False


def start_warp_proxy():
    """Start SOCKS5 proxy on port 40000 using hev-socks5-tunnel or similar."""
    # Check if port 40000 is already in use
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex(('127.0.0.1', 40000))
            if result == 0:
                print("✓ WARP SOCKS5 proxy already running on port 40000")
                return True
    except:
        pass
    
    print("⚠️  WARP SOCKS5 proxy not running on port 40000")
    print("⚠️  Please start it manually or configure hev-socks5-tunnel")
    print("⚠️  Script will continue with direct connection")
    return False


def check_current_ip():
    """Check current IP address via Cloudflare trace."""
    try:
        result = subprocess.run(
            ["curl", "-s", "https://cloudflare.com/cdn-cgi/trace"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if line.startswith('ip='):
                    ip = line.split('=')[1]
                    print(f"🌐 Current IP: {ip}")
                    return ip
    except Exception as e:
        print(f"⚠️  IP check failed: {e}", file=sys.stderr)
    
    return None

# Mega.nz account #4 — rclone config (from rabbyos-dash/rclone-mega4/)
MEGA_RCLONE_CONF = Path("/home/alan/Documents/repos/rabbyos-dash/rclone-mega4/rclone.conf")
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


def api_post(path: str, payload: dict | None = None) -> tuple[int, str]:
    """Talk to TempMailHub API."""
    import urllib.request
    body = json.dumps(payload or {}).encode()
    request = urllib.request.Request(
        f"{TEMPMAIL_API}{path}",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Origin": TEMPMAIL_URL.rstrip("/"),
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        },
    )
    last_error = None
    for attempt in range(1, 4):
        try:
            print(f"  API request (attempt {attempt}/3): {path[:60]}", file=sys.stderr)
            with urllib.request.urlopen(request, timeout=15) as response:
                result = response.status, response.read().decode(errors="replace")
                print(f"  ✓ API response: {result[0]}", file=sys.stderr)
                return result
        except urllib.error.HTTPError as error:
            result = error.code, error.read().decode(errors="replace")
            print(f"  ⚠ API HTTP error: {result[0]}", file=sys.stderr)
            return result
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last_error = error
            print(f"  ✗ API network error (attempt {attempt}/3): {error}", file=sys.stderr)
            import time
            time.sleep(2)
    raise RuntimeError(f"TempMailHub API request failed after 3 attempts: {last_error}")


def is_valid_gmail(email: str) -> bool:
    """Validate Gmail: must be @gmail.com with NO dots or + before @"""
    if not email or '@gmail.com' not in email.lower():
        return False
    local_part = email.split('@')[0]
    if '+' in local_part or '.' in local_part:
        return False
    return True


def create_working_email() -> tuple[str, str]:
    """Create TempMailHub Gmail accounts via API until one works."""
    import time
    deadline = time.monotonic() + 90
    
    while time.monotonic() < deadline:
        status, raw = api_post("/emails")
        if status != 201:
            print(f"⚠ TempMailHub account creation failed: {status} {raw[:120]}", file=sys.stderr)
            time.sleep(2)
            continue
        
        try:
            account = json.loads(raw)
            email, email_id = account["email"], str(account["email_id"])
            
            # ONLY accept valid Gmail (no dots, no +)
            if not is_valid_gmail(email):
                print(f"⚠ Skipping invalid Gmail: {email}", file=sys.stderr)
                time.sleep(1)
                continue
        except (KeyError, ValueError) as exc:
            print(f"⚠ TempMailHub account reply malformed: {raw[:120]}", file=sys.stderr)
            time.sleep(2)
            continue
        
        # Test if mailbox is readable
        status, messages_raw = api_post(f"/emails/messages?email_id={email_id}")
        if status == 200 and "error" not in messages_raw.lower():
            print(f"✓ Working TempMailHub Gmail: {email} (email_id={email_id})")
            return email, email_id
        
        print(f"⚠ Gmail account {email} has broken mailbox, retrying...", file=sys.stderr)
        time.sleep(1)
    
    raise RuntimeError("TempMailHub gave no valid Gmail account in time")


def read_messages(email_id: str) -> list:
    """Read messages from TempMailHub API."""
    try:
        status, raw = api_post(f"/emails/messages?email_id={email_id}")
    except RuntimeError as exc:
        print(f"⚠ TempMail message poll failed: {exc}", file=sys.stderr)
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


async def wait_for_railway_code(email_id: str, timeout_ms: int) -> str:
    """Poll TempMailHub API for Railway 6-digit code."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_ms / 1000
    
    railway_re = re.compile(r"\b(\d{6})\s+is your Railway (?:login )?code\b", re.I)
    
    while loop.time() < deadline:
        for message in read_messages(email_id):
            subject = str(message.get("subject") or message.get("title") or "")
            body_text = json.dumps(message, default=str)
            
            # Check subject and body for Railway code
            for text in [subject, body_text]:
                match = railway_re.search(text)
                if match:
                    code = match.group(1)
                    print(f"✓ Found Railway code: {code}")
                    return code
        
        await asyncio.sleep(8)
    
    raise RuntimeError("Railway sent no 6-digit code to TempMailHub inbox before timeout")


async def is_logged_in(page) -> bool:
    # Always force fresh login to avoid cookie conflicts from previous sessions
    return False


async def sign_in_to_railway(page, email: str, email_id: str, email_timeout_ms: int, profile_dir: Path) -> None:
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
    print(f"✓ Filled email: {email}")
    
    # Check if Cloudflare Turnstile appears and solve it
    print("🔍 Checking for Cloudflare Turnstile...")
    await page.wait_for_timeout(2000)  # Wait for Turnstile to load
    
    # Check if Turnstile iframe exists (indicates visible checkbox mode)
    turnstile_exists = False
    try:
        turnstile_iframe = page.locator('iframe[src*="challenges.cloudflare.com"]')
        count = await turnstile_iframe.count()
        if count > 0:
            turnstile_exists = True
            print(f"✓ Found Cloudflare Turnstile iframe")
    except:
        pass
    
    # Also check for the turnstile container div
    if not turnstile_exists:
        try:
            has_turnstile = await page.evaluate('''() => {
                const input = document.querySelector('input[name="cf-turnstile-response"]');
                const container = input?.parentElement?.parentElement;
                return container && container.offsetHeight > 0;
            }''')
            if has_turnstile:
                turnstile_exists = True
                print(f"✓ Found Cloudflare Turnstile widget")
        except:
            pass
    
    if turnstile_exists and CAPTCHA_SOLVER_AVAILABLE:
        print("🤖 Auto-solving Cloudflare Turnstile checkbox...")
        try:
            async with ClickSolver(
                framework=FrameworkType.PATCHRIGHT,
                page=page,
                max_attempts=1,  # Only try once, then fall back to waiting
                attempt_delay=2
            ) as solver:
                await solver.solve_captcha(
                    captcha_container=page,
                    captcha_type=CaptchaType.CLOUDFLARE_TURNSTILE
                )
            print("✅ Turnstile checkbox clicked and validated!")
            
        except Exception as e:
            # The solver may click the checkbox but fail to detect success
            # This is OK - we'll wait for the button to enable
            print(f"⚠️  ClickSolver error (checkbox may still be clicked): {str(e)[:100]}", file=sys.stderr)
            print("✅ Checkbox likely clicked, continuing...", file=sys.stderr)
        
        # Always wait for Cloudflare to process, even if solver had error
        print("⏳ Waiting for Turnstile to validate...")
        await page.wait_for_timeout(3000)
            
    elif turnstile_exists and not CAPTCHA_SOLVER_AVAILABLE:
        print("⚠️  Turnstile detected but solver not available - waiting for manual click")
    else:
        print("✓ No visible Turnstile - using invisible mode")
    
    # Wait for Continue button to be enabled
    continue_btn = page.get_by_role("button", name="Continue with Email", exact=True)
    
    print("⏳ Waiting for Continue button to enable...")
    button_enabled = False
    try:
        await expect(continue_btn).to_be_enabled(timeout=45000)
        print("✅ Button enabled!")
        button_enabled = True
    except Exception as e:
        print(f"⚠️  Button still disabled after 45s", file=sys.stderr)
        
        # Check if token was populated
        token_val = await page.evaluate('''() => {
            const input = document.querySelector('input[name="cf-turnstile-response"]');
            return input ? input.value : '';
        }''')
        print(f"⚠️  Turnstile token length: {len(token_val)}", file=sys.stderr)
        
        # Check button state
        btn_html = await page.evaluate('''() => {
            const btn = document.querySelector('button[type="submit"]');
            return btn ? btn.outerHTML.substring(0, 300) : 'not found';
        }''')
        print(f"⚠️  Button HTML: {btn_html}", file=sys.stderr)
        
        screenshot_path = str(profile_dir / "turnstile_timeout.png")
        await page.screenshot(path=screenshot_path)
        print(f"⚠️  Saved debug screenshot: {screenshot_path}")
    
    if button_enabled:
        print("🖱️  Clicking Continue button...")
        try:
            await continue_btn.click(timeout=10000)
            print("✅ Clicked Continue button")
        except Exception as e:
            print(f"⚠️  Regular click failed: {e}", file=sys.stderr)
            print("🔧 Trying force click...", file=sys.stderr)
            await continue_btn.click(force=True, timeout=10000)
            print("✅ Force clicked Continue button")
    else:
        raise RuntimeError(f"Cloudflare Turnstile not solved - button still disabled")
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

    print("⏳ Polling TempMailHub API for Railway code...")
    code = await wait_for_railway_code(email_id, email_timeout_ms)
    if len(code) != len(fields):
        raise RuntimeError(f"Railway code wrong length: {code}")
    
    print(f"✓ Filling code: {code}")
    for field, digit in zip(fields, code):
        await field.fill(digit)

    await expect(page).to_have_url(
        re.compile(r"/dashboard(?:/|$)"), timeout=email_timeout_ms
    )
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
    print(f"✓ Filled email: {email}")
    
    # Check if Cloudflare Turnstile appears and solve it
    print("🔍 Checking for Cloudflare Turnstile...")
    await page.wait_for_timeout(2000)  # Wait for Turnstile to load
    
    # Check if Turnstile iframe exists (indicates visible checkbox mode)
    turnstile_exists = False
    try:
        turnstile_iframe = page.locator('iframe[src*="challenges.cloudflare.com"]')
        count = await turnstile_iframe.count()
        if count > 0:
            turnstile_exists = True
            print(f"✓ Found Cloudflare Turnstile iframe")
    except:
        pass
    
    # Also check for the turnstile container div
    if not turnstile_exists:
        try:
            has_turnstile = await page.evaluate('''() => {
                const input = document.querySelector('input[name="cf-turnstile-response"]');
                const container = input?.parentElement?.parentElement;
                return container && container.offsetHeight > 0;
            }''')
            if has_turnstile:
                turnstile_exists = True
                print(f"✓ Found Cloudflare Turnstile widget")
        except:
            pass
    
    if turnstile_exists and CAPTCHA_SOLVER_AVAILABLE:
        print("🤖 Auto-solving Cloudflare Turnstile checkbox...")
        try:
            async with ClickSolver(
                framework=FrameworkType.PATCHRIGHT,
                page=page,
                max_attempts=1,  # Only try once, then fall back to waiting
                attempt_delay=2
            ) as solver:
                await solver.solve_captcha(
                    captcha_container=page,
                    captcha_type=CaptchaType.CLOUDFLARE_TURNSTILE
                )
            print("✅ Turnstile checkbox clicked and validated!")
            
        except Exception as e:
            # The solver may click the checkbox but fail to detect success
            # This is OK - we'll wait for the button to enable
            print(f"⚠️  ClickSolver error (checkbox may still be clicked): {str(e)[:100]}", file=sys.stderr)
            print("✅ Checkbox likely clicked, continuing...", file=sys.stderr)
        
        # Always wait for Cloudflare to process, even if solver had error
        print("⏳ Waiting for Turnstile to validate...")
        await page.wait_for_timeout(3000)
            
    elif turnstile_exists and not CAPTCHA_SOLVER_AVAILABLE:
        print("⚠️  Turnstile detected but solver not available - waiting for manual click")
    else:
        print("✓ No visible Turnstile - using invisible mode")
    
    # Wait for Continue button to be enabled
    continue_btn = page.get_by_role("button", name="Continue with Email", exact=True)
    
    print("⏳ Waiting for Continue button to enable...")
    button_enabled = False
    try:
        await expect(continue_btn).to_be_enabled(timeout=45000)
        print("✅ Button enabled!")
        button_enabled = True
    except Exception as e:
        print(f"⚠️  Button still disabled after 45s", file=sys.stderr)
        
        # Check if token was populated
        token_val = await page.evaluate('''() => {
            const input = document.querySelector('input[name="cf-turnstile-response"]');
            return input ? input.value : '';
        }''')
        print(f"⚠️  Turnstile token length: {len(token_val)}", file=sys.stderr)
        
        # Check button state
        btn_html = await page.evaluate('''() => {
            const btn = document.querySelector('button[type="submit"]');
            return btn ? btn.outerHTML.substring(0, 300) : 'not found';
        }''')
        print(f"⚠️  Button HTML: {btn_html}", file=sys.stderr)
        
        screenshot_path = str(profile_dir / "turnstile_timeout.png")
        await page.screenshot(path=screenshot_path)
        print(f"⚠️  Saved debug screenshot: {screenshot_path}")
    
    if button_enabled:
        print("🖱️  Clicking Continue button...")
        try:
            await continue_btn.click(timeout=10000)
            print("✅ Clicked Continue button")
        except Exception as e:
            print(f"⚠️  Regular click failed: {e}", file=sys.stderr)
            print("🔧 Trying force click...", file=sys.stderr)
            await continue_btn.click(force=True, timeout=10000)
            print("✅ Force clicked Continue button")
    else:
        raise RuntimeError(f"Cloudflare Turnstile not solved - button still disabled")
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

    print("⏳ Polling TempMailHub API for Railway code...")
    code = await wait_for_railway_code(email_id, email_timeout_ms)
    if len(code) != len(fields):
        raise RuntimeError(f"Railway code wrong length: {code}")
    
    print(f"✓ Filling code: {code}")
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
    print("🍪 Checking for cookie banner...")
    
    # Try Osano cookie banner first (appears after email verification)
    try:
        osano_dialog = page.locator('[role="dialog"][aria-label*="Cookie"]').first
        if await osano_dialog.count() > 0 and await osano_dialog.is_visible():
            print(f"  Found Osano cookie banner")
            
            # Click "Reject Non-Essential" button
            reject_btn = osano_dialog.locator('button.osano-cm-denyAll, button:has-text("Reject Non-Essential")').first
            if await reject_btn.count() > 0:
                try:
                    await reject_btn.click(timeout=3_000)
                    print(f"  ✅ Clicked 'Reject Non-Essential'")
                    await page.wait_for_timeout(1000)
                    return
                except Exception as e:
                    print(f"  ⚠️ Failed to click button: {e}")
            
            # Fallback: try close button
            close_btn = osano_dialog.locator('button.osano-cm-dialog__close').first
            if await close_btn.count() > 0:
                try:
                    await close_btn.click(timeout=2_000)
                    print(f"  ✅ Clicked close button")
                    await page.wait_for_timeout(500)
                    return
                except Exception:
                    pass
            
            # Last resort: remove via JS
            await osano_dialog.evaluate("el => el.remove()")
            print(f"  ✅ Removed Osano banner via JS")
            await page.wait_for_timeout(500)
            return
    except Exception as e:
        print(f"  ⚠️ Osano check error: {e}")
    
    # Try other cookie banner selectors
    selectors = [
        ".fc-message-root",
        "#onetrust-banner-sdk",
        "[class*='cookie']",
        "[id*='cookie']",
        "[class*='consent']",
        "[id*='consent']"
    ]
    
    for selector in selectors:
        try:
            banner = page.locator(selector).first
            if await banner.count() > 0 and await banner.is_visible():
                print(f"  Found banner with selector: {selector}")
                
                # Try to click dismiss/accept button
                buttons = banner.locator("button")
                clicked = False
                for index in range(await buttons.count()):
                    button = buttons.nth(index)
                    if not await button.is_visible():
                        continue
                    try:
                        await button.click(timeout=2_000)
                        clicked = True
                        print(f"  ✅ Clicked button in banner")
                        break
                    except Exception:
                        continue
                
                # If no button worked, forcefully remove the banner
                if not clicked:
                    await banner.evaluate("el => el.remove()")
                    print(f"  ✅ Removed banner via JS")
                
                await page.wait_for_timeout(500)
                return
        except Exception:
            continue
    
    print("  ✓ No cookie banner found")


async def accept_railway_policies(page) -> None:
    await wait_for_cloudflare(page, "Railway dashboard")
    await expect(page).to_have_url(re.compile(r"/dashboard(?:/|$)"))
    
    # IMPORTANT: Dismiss Osano cookie banner FIRST before any TOS interaction
    print("📜 Handling Terms of Service...")
    print("🍪 Dismissing Osano cookie banner first...")
    await page.wait_for_timeout(2000)  # Wait for banner to appear
    await dismiss_cookie_banner(page)
    await page.wait_for_timeout(1000)
    
    # Dismiss again to be sure
    await dismiss_cookie_banner(page)
    
    print("🔍 Looking for TOS dialog...")
    dialog = page.get_by_role("dialog", name=re.compile(r"Terms of Service", re.I)).last
    try:
        await dialog.wait_for(state="visible", timeout=ACTION_TIMEOUT)
        print("✓ TOS dialog found")
    except Exception:
        print("✓ No TOS dialog (already accepted)")
        return

    agree_buttons = [
        "I agree with Railway's Terms of Service",
        "I agree to the Fair Use Policy",
    ]
    
    for iteration in range(6):
        print(f"  TOS iteration {iteration + 1}...")
        
        # Remove cookie banner before EVERY action
        await dismiss_cookie_banner(page)
        
        try:
            await scroll_terms_dialog(dialog)
            print(f"    ✓ Scrolled dialog")
        except Exception as e:
            print(f"    ⚠️  Scroll failed: {e}")
            break
        
        # Remove banner again after scroll
        await dismiss_cookie_banner(page)
        
        clicked = False
        for name in agree_buttons:
            # Remove banner RIGHT before clicking
            await dismiss_cookie_banner(page)
            
            button = page.get_by_role("button", name=name, exact=True)
            try:
                await expect(button).to_be_visible(timeout=3_000)
                await expect(button).to_be_enabled(timeout=3_000)
                print(f"    🖱️  Clicking: {name}")
                
                # Try regular click first
                try:
                    await button.click(timeout=5_000)
                except Exception as e:
                    print(f"    ⚠️  Regular click failed, trying force click: {e}")
                    await button.click(force=True)
                
                clicked = True
                print(f"    ✅ Clicked: {name}")
                break
            except AssertionError:
                continue
            except Exception as e:
                print(f"    ⚠️  Click failed: {e}")
                continue
        
        if not clicked:
            print(f"    ⚠️  No button clicked")
            break
        
        await page.wait_for_timeout(1_500)

    try:
        await expect(page.get_by_text("Terms accepted", exact=True)).to_be_visible(
            timeout=15_000
        )
        print("✅ Terms accepted successfully")
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


def test_railway_cli(session_dir: Path) -> None:
    """Test Railway CLI works from the session directory."""
    try:
        result = subprocess.run(
            ["railway", "whoami"],
            cwd=str(session_dir),
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            print(f"✅ Railway CLI test: {result.stdout.strip()}")
        else:
            print(f"⚠️  Railway CLI test failed: {result.stderr.strip()}", file=sys.stderr)
    except FileNotFoundError:
        print("⚠️  Railway CLI not found. Install: curl -fsSL https://railway.app/install.sh | sh", file=sys.stderr)
    except Exception as e:
        print(f"⚠️  Railway CLI test error: {e}", file=sys.stderr)


async def run(profile_dir: Path, email_timeout_ms: int, railway_dir: Path) -> None:
    profile_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        proxy = proxy_settings()
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            channel="chrome",
            headless=False,
            viewport={"width": 1440, "height": 900},
            proxy=proxy,
        )
        
        async def abort_overlay(route):
            await route.abort()

        # The survey widget injects an fc-message-root popup that intercepts clicks.
        await context.route("**luminaire.railway.com/**", abort_overlay)
        context.set_default_timeout(ACTION_TIMEOUT)
        context_closed = asyncio.Event()
        context.on("close", context_closed.set)
        dashboard_page = await context.new_page()

        try:
            print("📧 Creating TempMailHub Gmail via API...")
            email, email_id = create_working_email()
            print(f"✓ Temporary Gmail created: {email}")
            await sign_in_to_railway(dashboard_page, email, email_id, email_timeout_ms, profile_dir)
            await accept_railway_policies(dashboard_page)
            await dashboard_page.bring_to_front()
            session_dir = await register_cli_session(context, dashboard_page, railway_dir)
            print(f"CLI session registered in: {session_dir}")
            
            # Sync to Mega.nz
            sync_to_mega(session_dir)
            
            # Test Railway CLI with the new session
            print(f"\n✅ Testing Railway CLI from session directory...")
            test_railway_cli(session_dir)
            
            print(f"\n✅ SUCCESS! Railway account created and synced to Mega")
            print(f"📁 Session: {session_dir}")
            print(f"☁️  Mega: mega:{MEGA_REMOTE_PATH}/{session_dir.name}")
            print(f"\nTo use this session:")
            print(f"  cd {session_dir}")
            print(f"  railway whoami")
            
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
    import time

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile-dir",
        default=None,  # Will generate unique profile if not provided
        help="Folder for persistent cookies and session data (default: auto-generated unique profile)",
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
    
    # Generate unique browser profile per session to avoid cookie conflicts
    import time
    if not options.profile_dir or options.profile_dir == "railway_profile":
        profile_dir = Path.home() / "Documents" / "railways" / f"browser_profile_{int(time.time())}"
    else:
        profile_dir = Path(options.profile_dir).expanduser().resolve()
    
    railway_dir = options.railway_dir.expanduser().resolve()
    railway_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"🚀 Railway CLI Session Creator + Mega Sync")
    print(f"📁 Sessions directory: {railway_dir}")
    print(f"🌐 Mega remote: mega:{MEGA_REMOTE_PATH}")
    print()
    
    # Rotate WARP IP before creating account
    print("🔄 Rotating WARP IP for new session...")
    old_ip = check_current_ip()
    
    if rotate_warp_ip():
        new_ip = check_current_ip()
        if new_ip and old_ip and new_ip != old_ip:
            print(f"✅ IP changed: {old_ip} → {new_ip}")
        else:
            print(f"⚠️  IP may not have changed (old: {old_ip}, new: {new_ip})")
    else:
        print("⚠️  WARP rotation failed, continuing with current IP")
    
    print()

    try:
        asyncio.run(
            run(
                profile_dir=profile_dir,
                email_timeout_ms=options.email_timeout,
                railway_dir=railway_dir,
            )
        )
    except Exception as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())