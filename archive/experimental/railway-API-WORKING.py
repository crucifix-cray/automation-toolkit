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
RAILWAY_LOGIN = "https://railway.com/login"
RAILWAY_DASHBOARD = "https://railway.com/dashboard"
ACTION_TIMEOUT = 30_000
EMAIL_TIMEOUT = 180_000
CLOUDFLARE_TIMEOUT = 180_000
WARP_PROXY = "socks4://127.0.0.1:40000"  # SOCKS4 works, SOCKS5 blocks the mail API

RAILWAY_OAUTH = "https://backboard.railway.com/oauth"
RAILWAY_CLIENT_ID = "rlwy_oaci_onEklvmksh1hRUiCo7E2zX12"
RAILWAY_GRAPHQL = "https://backboard.railway.com/graphql/v2"

# Gmail validation regex (no dots, no + before @)
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


class FlowError(Exception):
    """Raised when the temp-mail provider cannot deliver a working mailbox."""


# ============================================================================
# dispose.lol API - SvelteKit remote functions with devalue transport
# Docs: "dispose lol Mail Automation.txt" (repo root)
# The remote prefix (1i1fsx0) is build-specific and may change after deploys.
# ============================================================================
DISPOSE_BASE = "https://dispose.lol"
DISPOSE_PREFIX = "/_app/remote/1i1fsx0"
# Documented payload for the current anonymous mailbox: [{"assignmentId":-1}]
DISPOSE_MESSAGES_PAYLOAD = "W3siYXNzaWdubWVudElkIjotMX1d"


class _Undefined:
    pass


UNDEFINED = _Undefined()


def devalue_encode(value) -> str:
    """Encode a value into a devalue transport string (unpadded base64url).

    table position 0 is the inlined root; every other value becomes a table
    entry referenced by its index. undefined is the -1 sentinel.
    """
    memo: list = []
    seen: dict = {}

    def ref(x):
        if x is UNDEFINED:
            return -1  # undefined is the only value inlined as a sentinel
        # everything else (str/bool/number/object/array) is tableized and
        # referenced by index - matches the documented devalue contract
        key = ("v", type(x).__name__, x) if isinstance(x, (str, int, float)) else ("i", id(x))
        idx = seen.get(key)
        if idx is None:
            idx = len(memo) + 1
            seen[key] = idx
            memo.append(entry(x))
        return idx

    def entry(x):
        if isinstance(x, dict):
            return {k: ref(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [ref(v) for v in x]
        return x

    raw = json.dumps([entry(value), *memo], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def devalue_decode(transport: str):
    """Parse a devalue transport string back into Python objects."""
    table = json.loads(transport)

    def deref(v, chasing=frozenset()):
        if isinstance(v, int) and not isinstance(v, bool):
            if v in (-1, 0):
                return None  # undefined / null sentinels
            if 1 <= v < len(table) and v not in chasing:
                return deref(table[v], chasing | {v})
        if isinstance(v, dict):
            return {k: deref(x, chasing) for k, x in v.items()}
        if isinstance(v, list):
            return [deref(x, chasing) for x in v]
        return v

    return deref(table[0]) if table else None


class DisposeLolMailbox:
    """dispose.lol mailbox via remote-function API.

    Cloudflare's WAF 403s direct HTTP clients on the mailbox routes (verified
    live), so RPC calls ride a hidden page's fetch (Chrome TLS + cookies).
    Zero DOM scraping - all payloads use the documented devalue encoding.
    """

    def __init__(self, context):
        self.context = context
        self.page = None
        self.address = None

    async def _ensure_page(self):
        if self.page is None or self.page.is_closed():
            self.page = await self.context.new_page()
            await self.page.goto(DISPOSE_BASE, wait_until="load", timeout=60000)
            await self.page.wait_for_timeout(3000)
        return self.page

    async def _rpc(self, name: str, method: str = "POST", payload: str = ""):
        """Execute a remote function in the page context, return decoded result."""
        page = await self._ensure_page()
        script = """
        async () => {
            const method = %s;
            const payload = %s;
            const url = %s + (method === "GET" ? "?payload=" + encodeURIComponent(payload) : "");
            const opts = { method, credentials: "include", headers: {"Content-Type": "application/json", "x-sveltekit-pathname": "/", "x-sveltekit-search": ""} };
            if (method === "POST") opts.body = JSON.stringify({ payload, refreshes: [] });
            const resp = await fetch(url, opts);
            const text = await resp.text();
            let env;
            try { env = JSON.parse(text); }
            catch (e) { throw new Error("non-JSON response (HTTP " + resp.status + "): " + text.slice(0, 80)); }
            if (env.type === "error") throw new Error(env.error && env.error.message || "dispose error");
            if (env.type !== "result") throw new Error("unexpected envelope: " + env.type);
            return env.result;
        }
        """ % (json.dumps(method), json.dumps(payload), json.dumps(DISPOSE_BASE + DISPOSE_PREFIX + "/" + name))
        try:
            transport = await page.evaluate(script)
        except Exception as error:
            raise FlowError(f"dispose.lol {name} RPC failed: {error}") from error
        return devalue_decode(transport)

    async def create(self) -> str:
        """Get (or create) the anonymous mailbox. Returns the @gmail.com address."""
        result = await self._rpc("getOrCreateMailbox")
        if not isinstance(result, dict) or not result.get("address"):
            raise FlowError(f"getOrCreateMailbox gave no address: {result!r}")
        if result.get("needsCaptcha"):
            raise FlowError("dispose.lol requires a captcha for mailbox creation")
        if result.get("error"):
            raise FlowError(f"dispose.lol mailbox error: {result['error']}")
        self.address = result["address"]
        print(f"✓ dispose.lol mailbox ready: {self.address}", file=sys.stderr)
        return self.address

    async def list_messages(self) -> list:
        """List messages for the current anonymous mailbox."""
        try:
            result = await self._rpc("getMailboxMessages", method="GET", payload=DISPOSE_MESSAGES_PAYLOAD)
        except FlowError:
            return []
        if not isinstance(result, dict):
            return []
        return result.get("messages") or []

    async def get_message(self, message_id: str) -> dict:
        """Fetch the full message body for one message."""
        payload = devalue_encode({"id": message_id, "refresh": True})
        result = await self._rpc("getMailboxMessage", payload=payload)
        if not isinstance(result, dict):
            return {}
        return result.get("message") or {}

    async def wait_for_railway_code(self, timeout_ms: int) -> str:
        """Poll the API for the Railway 6-digit code (subject or full body)."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_ms / 1000
        railway_re = re.compile(r"\b(\d{6})\s+is your Railway (?:login )?code\b", re.I)

        poll_count = 0
        while loop.time() < deadline:
            poll_count += 1
            messages = await self.list_messages()
            print(f"  Poll #{poll_count}: {len(messages)} messages in inbox", file=sys.stderr)

            for message in messages:
                message_id = str(message.get("id") or "")
                subject = str(message.get("subject") or "")
                match = railway_re.search(subject)
                if not match:
                    detail = await self.get_message(message_id)
                    for text in (subject,
                                 str(detail.get("textBody") or ""),
                                 str(detail.get("htmlBodySrcdoc") or "")):
                        match = railway_re.search(text)
                        if match:
                            break
                if match:
                    code = match.group(1)
                    print(f"✓ Found Railway code: {code}")
                    return code

            await asyncio.sleep(8)

        raise RuntimeError(f"Railway code not found after {poll_count} polls ({timeout_ms/1000}s)")

    async def close(self):
        if self.page is not None and not self.page.is_closed():
            await self.page.close()
        self.page = None


async def is_logged_in(page) -> bool:
    # Always force fresh login to avoid cookie conflicts from previous sessions
    return False


async def sign_in_to_railway(page, mailbox: DisposeLolMailbox, email_timeout_ms: int, profile_dir: Path) -> None:
    if await is_logged_in(page):
        return

    # Navigate directly to login page (homepage doesn't show sign-in button prominently)
    await page.goto(RAILWAY_LOGIN, wait_until="domcontentloaded")
    await wait_for_cloudflare(page, "Railway")
    
    # Wait for page to fully load (JS, etc.)
    await page.wait_for_load_state("networkidle", timeout=15000)

    # Click "Log in using email" button and wait for email form
    email_btn = page.get_by_role("button", name="Log in using email", exact=True)
    await expect(email_btn).to_be_visible(timeout=10000)
    await expect(email_btn).to_be_enabled(timeout=10000)  # Wait for enabled!
    await email_btn.click()
    print("✓ Clicked 'Log in using email'")
    
    # Wait a moment for the form to appear (might be animated)
    await page.wait_for_timeout(3000)
    
    # Debug: Check what's visible after click
    try:
        all_inputs = await page.locator('input[type="email"], input[placeholder*="email" i]').count()
        print(f"🔍 Found {all_inputs} email inputs after click")
    except:
        pass
    
    # Wait for email input to appear
    email_input = page.get_by_placeholder("hello@email.com")
    await expect(email_input).to_be_visible(timeout=15000)
    await email_input.fill(mailbox.address)
    print(f"✓ Filled email: {mailbox.address}")
    
    # FAST POLL BUTTON - Check every 500ms, click immediately when enabled
    print("🔍 Checking for Cloudflare Turnstile...")
    await page.wait_for_timeout(2000)
    
    continue_btn = page.get_by_role("button", name="Continue with Email", exact=True)
    
    # Check for Turnstile
    turnstile_exists = False
    try:
        turnstile_iframe = page.locator('iframe[src*="challenges.cloudflare.com"]')
        if await turnstile_iframe.count() > 0:
            turnstile_exists = True
            print("✓ Turnstile iframe detected")
    except:
        pass
    
    if not turnstile_exists:
        try:
            has_turnstile = await page.evaluate('''() => {
                const input = document.querySelector('input[name="cf-turnstile-response"]');
                const container = input?.parentElement?.parentElement;
                return container && container.offsetHeight > 0;
            }''')
            if has_turnstile:
                turnstile_exists = True
                print("✓ Turnstile widget detected")
        except:
            pass
    
    if turnstile_exists:
        print("✓ Turnstile found - waiting passively (no auto-solve in headless)")
        
        # DON'T use auto-solver in headless - it doesn't work
        # Just wait and let Turnstile solve itself passively
        
        # CRITICAL: Fast poll - check button every 500ms
        print("⏳ Fast polling button (every 0.5s, max 180s for headless Turnstile)...")
        deadline = asyncio.get_running_loop().time() + 180  # 3 minutes for passive solve
        
        while asyncio.get_running_loop().time() < deadline:
            try:
                is_enabled = await continue_btn.is_enabled(timeout=500)
                if is_enabled:
                    print("✅ BUTTON ENABLED! Clicking NOW...")
                    await continue_btn.click(timeout=3000)
                    print("✅ Clicked!")
                    break
            except Exception:
                await page.wait_for_timeout(500)
                continue
        else:
            print(f"❌ Button never enabled after 120s")
            token_len = await page.evaluate('''() => {
                const input = document.querySelector('input[name="cf-turnstile-response"]');
                return input ? input.value.length : 0;
            }''')
            print(f"⚠️  Token length: {token_len}")
            
            # Check if Turnstile is in error state
            error_check = await page.evaluate('''() => {
                const iframe = document.querySelector('iframe[src*="challenges.cloudflare.com"]');
                return iframe ? 'iframe exists' : 'no iframe';
            }''')
            print(f"⚠️  Turnstile state: {error_check}")
            
            screenshot_path = str(profile_dir / "turnstile_timeout.png")
            await page.screenshot(path=screenshot_path, full_page=True)
            print(f"⚠️  Screenshot: {screenshot_path}")
            raise RuntimeError("Turnstile timeout - button still disabled after 120s")
    else:
        print("✓ No Turnstile, clicking immediately")
        await continue_btn.click(timeout=10000)
        print("✅ Clicked!")
    
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

    print("⏳ Polling dispose.lol API for Railway code...")
    # Wait 15 seconds before polling - Railway needs time to send email
    print("⏳ Waiting 15s for Railway to send email...")
    await asyncio.sleep(15)
    
    code = await mailbox.wait_for_railway_code(email_timeout_ms)
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
            headless=False,  # VISIBLE - Turnstile doesn't work in headless
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
            print("📧 Creating dispose.lol Gmail via API...")
            mailbox = DisposeLolMailbox(context)
            email = await mailbox.create()
            print(f"✓ Gmail created: {email}")
            await sign_in_to_railway(dashboard_page, mailbox, email_timeout_ms, profile_dir)
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
            await mailbox.close()
            await context.close()


def self_test() -> int:
    """Verify the devalue codec against the documented dispose.lol contract."""
    # [{"id":1,"refresh":2},"<id>",true] - documented getMailboxMessage payload
    enc = devalue_encode({"id": "<id>", "refresh": True})
    assert enc == "W3siaWQiOjEsInJlZnJlc2giOjJ9LCI8aWQ-Iix0cnVlXQ", enc
    assert devalue_decode(
        base64.urlsafe_b64decode(enc + "==").decode()
    ) == {"id": "<id>", "refresh": True}
    # note: DISPOSE_MESSAGES_PAYLOAD is kept verbatim from captured traffic,
    # even though it contains an observed server-side typo ("assignnentId")
    assert DISPOSE_MESSAGES_PAYLOAD == "W3siYXNzaWdubWVudElkIjotMX1d"
    assert devalue_decode('[{"domains":1},[2,3],"astroai.eu.cc","cdf.dgen.lat"]') == {
        "domains": ["astroai.eu.cc", "cdf.dgen.lat"]
    }
    assert devalue_decode(
        '[{"address":1,"showSet":2,"error":3,"needsCaptcha":2},'
        '"john@gmail.com",false,null]'
    ) == {"address": "john@gmail.com", "showSet": False, "error": None, "needsCaptcha": False}
    tbl = (
        '[{"address":1,"mailboxKey":1,"assignmentId":2,"messages":3,"readOnly":4},'
        '"a@gmail.com",null,[{"id":5,"subject":6,"sender":7}],false,'
        '"m1","652608 is your Railway login code","Railway <noreply@railway.com>"]'
    )
    msgs = devalue_decode(tbl)
    assert msgs["messages"][0]["subject"] == "652608 is your Railway login code"
    assert msgs["readOnly"] is False and msgs["assignmentId"] is None
    print("self-test: devalue codec OK")
    return 0


def main() -> int:
    import argparse
    import time

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run the devalue codec self-test and exit",
    )
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

    if options.self_test:
        return self_test()
    
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