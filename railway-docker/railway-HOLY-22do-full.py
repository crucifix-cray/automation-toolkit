#!/usr/bin/env python3
"""
🏆 THE HOLY RAILWAY SCRIPT 🏆
Combines all working parts from previous scripts
- dispose.lol scraping (proven working in test_dispose_inbox.py)
- Railway login flow with Turnstile handling
- Session saving and Mega sync
- WARP IP rotation
"""

import asyncio
import base64
import hashlib
import json
import os
import random
import re
import secrets
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
import uuid
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright, expect, TimeoutError as PlaywrightTimeout
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

# Import playwright-captcha for auto Cloudflare Turnstile solving
try:
    from playwright_captcha import CaptchaType, ClickSolver, FrameworkType
    CAPTCHA_SOLVER_AVAILABLE = True
except ImportError:
    CAPTCHA_SOLVER_AVAILABLE = False
    print("⚠️  playwright-captcha not installed", file=sys.stderr)

# ============================================================================
# CONSTANTS
# ============================================================================
RAILWAY_URL = "https://railway.com"
RAILWAY_LOGIN = "https://railway.com/login"
RAILWAY_OAUTH = "https://backboard.railway.com/oauth"
RAILWAY_CLIENT_ID = "rlwy_oaci_onEklvmksh1hRUiCo7E2zX12"
RAILWAY_GRAPHQL = "https://backboard.railway.com/graphql/v2"
RAILWAY_SCOPES = "openid email profile offline_access workspace:admin project:admin ssh_keys"
PKCE_CHARSET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"

SESSIONS_DIR = Path.home() / "Documents" / "railways"
MEGA_REMOTE = "mega:railway_sessions"

ACTION_TIMEOUT = 30_000
EMAIL_TIMEOUT = 300_000


# ============================================================================
# 22.do PROVIDER POOL — 11 HANDLERS
# ============================================================================
HANDLERS = [
    ("@linshiyou.com", "https://22.do/", "@linshiyou.com"),
    ("@colabeta.com", "https://22.do/", "@colabeta.com"),
    ("@youxiang.dev", "https://22.do/", "@youxiang.dev"),
    ("@colaname.com", "https://22.do/", "@colaname.com"),
    ("@usdtbeta.com", "https://22.do/", "@usdtbeta.com"),
    ("@tnbeta.com", "https://22.do/", "@tnbeta.com"),
    ("@fft.edu.do", "https://22.do/", "@fft.edu.do"),
    ("@gmail.com (Fake Gmail)", "https://22.do/fake-gmail-generator", "@gmail.com"),
    ("@hotmail.com", "https://22.do/temporary-hotmail", "@hotmail.com"),
    ("@outlook.com", "https://22.do/temporary-outlook", "@outlook.com"),
]

class MailTmInbox:
    """mail.tm API-based inbox — no browser needed, works through any proxy"""
    MAIL_TM_API = "https://api.mail.tm"
    _token = None
    _account_id = None

    def __init__(self, context=None, target_domain=None, recovery_email=None):
        self.context = context
        self.address = recovery_email
        self.target_domain = target_domain
        self.recovery_email = recovery_email
        self.handler_used = None

    def _api(self, method, path, data=None, token=None):
        url = f"{self.MAIL_TM_API}{path}"
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, data=json.dumps(data).encode() if data else None, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())

    async def create(self):
        if self.recovery_email:
            self.address = self.recovery_email
            print(f"♻️  Using recovery email: {self.address}")
            return self.address
        print("\n📧 Creating mail.tm mailbox...")
        # get available domains
        domains = self._api("GET", "/domains")
        dom_list = [d["domain"] for d in domains.get("hydra:member", [])]
        if not dom_list:
            raise RuntimeError("No mail.tm domains available")
        dom = random.choice(dom_list)
        local = ''.join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=12))
        addr = f"{local}@{dom}"
        pwd = secrets.token_hex(16)
        # create account
        acct = self._api("POST", "/accounts", {"address": addr, "password": pwd})
        self._account_id = acct.get("id")
        # get token
        tok_data = self._api("POST", "/token", {"address": addr, "password": pwd})
        self._token = tok_data.get("token")
        self.address = addr
        print(f"✅ Mailbox ready: {self.address} (via mail.tm)")
        return self.address

    async def wait_for_railway_code(self, timeout_seconds=300):
        if not self.address:
            raise Exception("No address set")
        print(f"\n📥 Waiting for Railway OTP for {self.address} (timeout: {timeout_seconds}s)...")
        pattern = re.compile(r"\b(\d{6})\s+is your Railway", re.I)
        deadline = time.time() + timeout_seconds
        check_count = 0
        while time.time() < deadline:
            check_count += 1
            try:
                msgs = self._api("GET", "/messages", token=self._token)
                items = msgs.get("hydra:member", [])
                if check_count % 10 == 1:
                    print(f"  Check #{check_count}: {len(items)} message(s)")
                for msg in items:
                    subj = msg.get("subject", "")
                    intro = msg.get("intro", "")
                    if "railway" in subj.lower() or "railway" in intro.lower():
                        # fetch full message
                        full = self._api("GET", f"/messages/{msg['id']}", token=self._token)
                        body = full.get("text", "") or full.get("html", [""])[0] if isinstance(full.get("html"), list) else full.get("html", "")
                        m = pattern.search(subj + " " + intro + " " + body)
                        if m:
                            print(f"  ✅ OTP: {m.group(1)}")
                            return m.group(1)
            except Exception as e:
                if check_count % 10 == 1:
                    print(f"  Check #{check_count}: error {e}")
            await asyncio.sleep(3)
        raise RuntimeError("OTP not received within timeout")


class DisposeLolInbox:
    """Dispose.lol Gmail - browser-based, works through WARP"""
    def __init__(self, context=None, target_domain=None, recovery_email=None):
        self.context = context
        self.page = None
        self.address = recovery_email
        self.target_domain = target_domain
        self.recovery_email = recovery_email
        self.handler_used = None
        self.BASE_URL = "https://dispose.lol"

    async def create(self):
        if self.recovery_email:
            self.address = self.recovery_email
            print(f"♻️  Using recovery email: {self.address}")
            return self.address
        print("\n📧 Creating dispose.lol Gmail...")
        self.page = await self.context.new_page()
        try:
            await self.page.goto(self.BASE_URL, wait_until="load", timeout=60000)
            await self.page.wait_for_timeout(5000)
            email_text = await self.page.evaluate('''() => {
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null);
                let node;
                while (node = walker.nextNode()) {
                    const text = node.textContent.trim();
                    if (text.includes('@gmail.com') && text.length < 100) return text;
                }
                return null;
            }''')
            if email_text and '@gmail.com' in email_text:
                self.address = email_text.strip()
                print(f"✅ Mailbox ready: {self.address} (via dispose.lol)")
                return self.address
            await self.page.screenshot(path="/tmp/disposelol-error.png", full_page=True)
            raise Exception("Could not find dispose.lol email address")
        except Exception:
            if self.page:
                await self.page.close()
            raise

    async def wait_for_railway_code(self, timeout_seconds=300):
        if not self.address:
            raise Exception("No address set")
        print(f"\n📥 Waiting for Railway OTP for {self.address} (timeout: {timeout_seconds}s)...")
        pattern = re.compile(r'\b(\d{6})\b')
        deadline = time.time() + timeout_seconds
        check_count = 0
        while time.time() < deadline:
            check_count += 1
            await self.page.reload(wait_until="load")
            await self.page.wait_for_timeout(2000)
            message_buttons = await self.page.locator('button[aria-label^="View "]').all()
            if check_count % 10 == 1:
                print(f"  Check #{check_count}: {len(message_buttons)} message(s)")
            for button in message_buttons:
                aria_label = await button.get_attribute('aria-label')
                if aria_label and 'railway' in aria_label.lower():
                    subject = aria_label.replace('View ', '')
                    print(f"  ✅ Found Railway message: {subject}")
                    match = pattern.search(subject)
                    if match:
                        otp = match.group(1)
                        print(f"  🎯 OTP: {otp}")
                        return otp
            await asyncio.sleep(3)
        raise RuntimeError("OTP not received within timeout")


class TwoTwoDoInbox:
    """22.do Provider Pool — random handler per run, supports recovery mode"""
    def __init__(self, context, target_domain=None, recovery_email=None):
        self.context = context
        self.address = recovery_email  # if recovery, address known upfront
        self.target_domain = target_domain
        self.recovery_email = recovery_email
        self.handler_used = None

    async def _pick_handler(self):
        if self.recovery_email:
            return None
        if self.target_domain:
            for h in HANDLERS:
                if h[2].lower() == self.target_domain.lower():
                    return h
        # random per run — anti-flag
        chosen = random.choice(HANDLERS)
        print(f"🎲 Random handler: {chosen[0]} → {chosen[1]}")
        return chosen

    async def create(self):
        # Recovery mode — just verify inbox page loads
        if self.recovery_email:
            pg = await self.context.new_page()
            try:
                url = f"https://22.do/inbox/#/{self.recovery_email}"
                print(f"♻️  Recovering existing inbox: {self.recovery_email}")
                await pg.goto(url, wait_until="domcontentloaded", timeout=60000)
                await pg.wait_for_timeout(3000)
                try:
                    inbox = await pg.locator("#email-list-wrap").count()
                    print(f"✅ Recovery inbox ready ({inbox} containers): {url}")
                except: print(f"✅ Recovery: {url}")
                self.address = self.recovery_email
                return self.address
            finally:
                await pg.close()

        # Create new via handler
        self.handler_used = await self._pick_handler()
        name, handler_url, handler_domain = self.handler_used
        print(f"\n📧 Creating 22.do mailbox via {name}...")
        pg = await self.context.new_page()
        try:
            await pg.goto(handler_url, wait_until="domcontentloaded", timeout=60000)
            await pg.wait_for_timeout(3000)

            # close google vignette
            try:
                close = pg.locator('button:has-text("Close ad")').first
                if await close.count() and await close.is_visible():
                    await close.click(timeout=2000)
                    print("  × closed ad overlay")
                    await pg.wait_for_timeout(1000)
            except: pass

            # For main-page domains: select domain from Choices.js dropdown
            if handler_domain not in ("@gmail.com", "@hotmail.com", "@outlook.com"):
                try:
                    await pg.locator(".choices__inner").click(timeout=3000)
                    await pg.wait_for_timeout(500)
                    await pg.locator(f".choices__item--choice >> text={handler_domain}").first.click(timeout=3000)
                    print(f"  → selected domain {handler_domain}")
                    await pg.wait_for_timeout(800)
                except Exception as e:
                    print(f"  ⚠️ domain select {handler_domain}: {e}")

            # Click Random
            await pg.locator("#mail-random").click(timeout=5000)
            await pg.wait_for_timeout(1000)
            local = await pg.locator("#mail-input").input_value(timeout=5000)

            # For fake-gmail: enforce @gmail.com
            if handler_domain == "@gmail.com":
                for _ in range(5):
                    v = (await pg.locator("#mail-input").input_value()).strip()
                    if v.lower().endswith(handler_domain.lower()):
                        local = v
                        break
                    print(f"  got {v} but wanted {handler_domain}, retrying Random…")
                    await pg.locator("#mail-random").click(timeout=3000)
                    await pg.wait_for_timeout(800)
                email = (await pg.locator("#mail-input").input_value()).strip()
                if "@" not in email:
                    email = f"{local.strip()}{handler_domain}"
            else:
                # main page: combine local + selected domain
                try:
                    dom = await pg.locator(".choices__list--single .choices__item").first.inner_text(timeout=2000)
                    email = f"{local.strip()}{dom.strip()}"
                except:
                    email = f"{local.strip()}{handler_domain}"

            await pg.locator("#into-mailbox").click(timeout=5000)
            await pg.wait_for_timeout(4000)
            self.address = email.strip()
            print(f"✅ Mailbox ready: {self.address} (via {name})")
            return self.address
        finally:
            await pg.close()

    async def wait_for_railway_code(self, timeout_seconds=300):
        if not self.address:
            raise Exception("No address set")
        print(f"\n📥 Waiting for Railway OTP for {self.address} (timeout: {timeout_seconds}s)...")
        pattern = re.compile(r"\b(\d{6})\s+is your Railway", re.I)
        deadline = time.time() + timeout_seconds
        check_count = 0
        pg = await self.context.new_page()
        await pg.goto(f"https://22.do/inbox/#/{self.address}", wait_until="domcontentloaded", timeout=60000)
        await pg.wait_for_timeout(3000)
        try:
            while time.time() < deadline:
                check_count += 1
                try:
                    count = await pg.locator("#email-list-wrap .tr").count()
                except:
                    count = 0
                if check_count % 10 == 1:
                    print(f"  Check #{check_count}: {count} message(s)")

                if count > 0:
                    for i in range(count):
                        try:
                            tr = pg.locator("#email-list-wrap .tr").nth(i)
                            subj = await tr.locator(".item.subject").inner_text(timeout=2000)
                            intro = await tr.locator(".item.from").inner_text(timeout=2000)
                            if "railway" in subj.lower() or "railway" in intro.lower():
                                print(f"  ✅ Found Railway email: {subj}")
                                m = pattern.search(subj + " " + intro)
                                if m:
                                    print(f"  ✅ OTP in preview: {m.group(1)}")
                                    return m.group(1)
                                # click subject to open full view, then scan body
                                await tr.locator(".item.subject").click()
                                await pg.wait_for_timeout(2000)
                                body = await pg.locator("body").inner_text(timeout=2000)
                                m = pattern.search(body)
                                if m:
                                    print(f"  ✅ OTP in full message: {m.group(1)}")
                                    return m.group(1)
                        except Exception as e:
                            print(f"    msg check err: {e}")

                await pg.reload(wait_until="domcontentloaded", timeout=30000)
                await pg.wait_for_timeout(3000)
        finally:
            await pg.close()
        raise TimeoutError("❌ Railway OTP email never arrived")

    async def close(self):
        pass


# ============================================================================
# WARP IP ROTATION
# ============================================================================
def _warp_proxy_alive():
    """Check SOCKS5 40000 alive"""
    try:
        import socket
        with socket.create_connection(("127.0.0.1", 40000), timeout=2):
            return True
    except:
        return False
    return False
    return False

def _pick_proxy():
    """Pick best alive proxy for 1GB host: 40000 (wireproxy warp) first - 1080 tunsocks fails for browser (ERR_SOCKS_CONNECTION_FAILED)"""
    import socket
    for port in (40000, 1080):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                return f"socks5://127.0.0.1:{port}"
        except:
            continue
    return None

def rotate_warp_ip():
    """Rotate WARP IP - proxy mode: warp-cli disconnect/connect"""
    print("🔄 Rotating WARP IP (proxy mode)...")
    try:
        if _warp_proxy_alive():
            subprocess.run(["warp-cli", "disconnect"], capture_output=True, timeout=10)
            time.sleep(2)
            subprocess.run(["warp-cli", "connect"], capture_output=True, timeout=10)
            time.sleep(3)
            if _warp_proxy_alive():
                print("✅ WARP IP rotated (proxy mode)")
                return True
        # fallback legacy wgcf
        if not Path("/etc/wireguard/wgcf.conf").exists():
            print("⚠️  WARP not configured (wgcf.conf missing) and proxy not alive")
            return False
        subprocess.run(["sudo", "wgcf", "update"], capture_output=True, timeout=30, check=True)
        subprocess.run(["sudo", "wgcf", "generate"], capture_output=True, timeout=30, check=True)
        subprocess.run(["sudo", "wg-quick", "down", "wgcf"], capture_output=True, timeout=10)
        subprocess.run(["sudo", "wg-quick", "up", "wgcf"], capture_output=True, timeout=30, check=True)
        print("✅ WARP IP rotated (wgcf)")
        return True
    except Exception as e:
        print(f"⚠️  WARP rotation failed: {e}")
        return False


def start_warp():
    """Start WARP - proxy mode preferred (isolated), only browser tunneled"""
    print("🚀 Checking WARP (proxy mode - isolated)...")
    try:
        if _warp_proxy_alive():
            print("✅ WARP already Connected WarpProxy on 127.0.0.1:40000 (isolated, only browser tunneled)")
            return True
        # try to start warp-cli
        r = subprocess.run(["warp-cli", "connect"], capture_output=True, text=True, timeout=30)
        time.sleep(3)
        if _warp_proxy_alive():
            print("✅ WARP started WarpProxy on 127.0.0.1:40000")
            return True
        # legacy wg-quick fallback
        result = subprocess.run(["sudo", "wg-quick", "up", "wgcf"], capture_output=True, text=True, timeout=30)
        if result.returncode == 0 or "already exists" in result.stderr:
            print("✅ WARP started (wg-quick)")
            return True
        print(f"⚠️  WARP start failed: {result.stderr or r.stdout}")
        return False
    except Exception as e:
        print(f"⚠️  WARP start error: {e}")
        return False


def stop_warp():
    """Stop WARP - no-op in proxy mode (keep isolated proxy alive for other apps)"""
    try:
        # In proxy mode we do NOT disconnect - keeps other apps unaffected per user request
        if _warp_proxy_alive():
            print("ℹ️  WARP proxy mode - keeping alive (isolated, not stopping)")
            return
        subprocess.run(["sudo", "wg-quick", "down", "wgcf"], capture_output=True, timeout=10)
        print("✅ WARP stopped")
    except:
        pass


# ============================================================================
# MEGA SYNC
# ============================================================================
def sync_to_mega(session_dir: Path):
    """Upload session to Mega"""
    print(f"\n☁️  Syncing to Mega...")
    try:
        remote_path = f"{MEGA_REMOTE}/{session_dir.name}"
        result = subprocess.run(
            ["rclone", "sync", str(session_dir), remote_path, "-v"],
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode == 0:
            print(f"✅ Synced to {remote_path}")
        else:
            print(f"⚠️  Mega sync failed: {result.stderr}")
    except Exception as e:
        print(f"⚠️  Mega sync error: {e}")


def get_next_session_number():
    """Get next available session number from Mega"""
    try:
        result = subprocess.run(
            ["rclone", "lsd", f"{MEGA_REMOTE}/"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            return 1
        
        session_numbers = []
        for line in result.stdout.split('\n'):
            if 'session-' in line:
                parts = line.split('session-')
                if len(parts) > 1:
                    num_str = parts[1].split()[0].split('-')[0]
                    try:
                        session_numbers.append(int(num_str))
                    except ValueError:
                        continue
        
        if session_numbers:
            next_num = max(session_numbers) + 1
            print(f"  📊 Found {len(session_numbers)} sessions on Mega, next: session-{next_num}")
            return next_num
        else:
            print(f"  📊 No sessions found on Mega, starting from session-1")
            return 1
            
    except Exception as e:
        print(f"  ⚠️  Error checking Mega: {e}, starting from session-1")
        return 1


def next_session_dir(base_dir: Path, session_num: int = None):
    """Get next session directory path"""
    if session_num is None:
        session_num = get_next_session_number()
    return base_dir / f"session-{session_num}"


# ============================================================================
# RAILWAY LOGIN FLOW
# ============================================================================
async def sign_in_to_railway(page, mailbox):
    """
    Complete Railway login flow:
    1. Navigate to login
    2. Fill email
    3. Solve Turnstile
    4. Wait for OTP
    5. Fill OTP
    """
    print("\n🚂 Signing in to Railway...")
    
    # Navigate to Railway login (bypass warp via direct, commit for speed)
    await page.goto(RAILWAY_LOGIN, wait_until="commit", timeout=60000)
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        try:
            await page.wait_for_load_state("load", timeout=15000)
        except: pass
    
    # Click "Log in using email" - robust for flagged IP (Welcome screen may stay, 67% zoom may hide)
    await page.evaluate("document.body.style.zoom='100%'")
    clicked = False
    for locator in [
        page.get_by_role("button", name="Log in using email"),
        page.get_by_text("Log in using email"),
        page.locator('text=Log in using email'),
        page.locator('a:has-text("Log in using email")'),
    ]:
        try:
            await expect(locator.first).to_be_visible(timeout=5000)
            await locator.first.scroll_into_view_if_needed(timeout=3000)
            try:
                await locator.first.click(timeout=5000)
            except:
                await locator.first.evaluate("el => el.click()")
            clicked = True
            break
        except:
            continue
    if not clicked:
        raise Exception("Log in using email not clickable")
    print("✓ Clicked 'Log in using email'")
    
    # Fill email - retry with flexible locators until field actually appears (flagged IP can eat the click)
    email_input = page.locator(
        'input[type="email"], input[inputmode="email"], input[name="email"], '
        'input[autocomplete="email"], input[placeholder*="@"], input[placeholder*="email" i]'
    ).first
    filled = False
    for _ in range(6):
        try:
            await expect(email_input).to_be_visible(timeout=8000)
            await email_input.fill(mailbox.address)
            filled = True
            break
        except Exception:
            for loc in [
                page.get_by_role("button", name="Log in using email"),
                page.get_by_text("Log in using email"),
                page.locator('a:has-text("Log in using email")'),
                page.locator('text=Continue with Email'),
            ]:
                try:
                    await expect(loc.first).to_be_visible(timeout=3000)
                    await loc.first.scroll_into_view_if_needed(timeout=2000)
                    try: await loc.first.click(timeout=3000)
                    except: await loc.first.evaluate("el => el.click()")
                    break
                except: continue
            await page.wait_for_timeout(2000)
    if not filled:
        raise Exception("Email input never appeared (Railway login stuck on Welcome screen)")
    print(f"✓ Filled email: {mailbox.address} (human)")
    # human blur
    try:
        await email_input.evaluate("el => el.blur()")
        await page.mouse.move(random.randint(100,700), random.randint(100,500), steps=random.randint(3,7))
    except:
        pass
    
    # Check for Cloudflare Turnstile - poll up to 10s (sandbox wireproxy late load)
    print("🔍 Checking for Cloudflare Turnstile...")
    await page.wait_for_timeout(2000)
    turnstile_exists = False
    for _ in range(20):
        try:
            turnstile_iframe = page.locator('iframe[src*="challenges.cloudflare.com"]')
            count = await turnstile_iframe.count()
            if count > 0 and await turnstile_iframe.first.is_visible():
                turnstile_exists = True
                print(f"✓ Found Cloudflare Turnstile iframe")
                break
        except:
            pass
        await page.wait_for_timeout(500)
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
    if not turnstile_exists:
        await page.wait_for_timeout(2000)
        try:
            turnstile_iframe = page.locator('iframe[src*="challenges.cloudflare.com"]')
            if await turnstile_iframe.count() > 0:
                turnstile_exists = True
                print(f"✓ Found Cloudflare Turnstile iframe (late)")
        except:
            pass
    
    # Solve Turnstile if present - passive mode for WARP (per RAILWAY_AUTOMATION.md)
    # WARP proxy IPs often auto-validate; ClickSolver fails with "success element does not exist" on this site,
    # so we use passive polling directly - proven working method.
    if turnstile_exists:
        print("🤖 Turnstile detected - using passive wait (WARP proxy auto-validate)...")
        print("  ℹ️  Skipping ClickSolver (fails on this WARP IP), will poll Continue button directly")
        # Optional single manual click attempt on iframe checkbox if present (fast, no solver)
        try:
            iframe = page.locator('iframe[src*="challenges.cloudflare.com"]')
            if await iframe.count() > 0:
                # Try quick click on the Turnstile widget area to trigger validation
                box = await iframe.first.bounding_box()
                if box:
                    await page.mouse.click(box["x"] + box["width"]/2, box["y"] + box["height"]/2)
                    print("  ✅ Clicked Turnstile widget center")
        except:
            pass
        print("⏳ Waiting for Turnstile validation...")
        await page.wait_for_timeout(3000)
        print("⏳ Fast polling Continue button (every 0.5s, max 180s) - per docs...")
    else:
        print("✓ No visible Turnstile")
    
    # Wait for Continue button and click - passive polling 180s via fast poll
    continue_btn = page.get_by_role("button", name="Continue with Email", exact=True)
    print("⏳ Waiting for Continue button to enable...")
    
    try:
        # Use fast polling instead of single expect to handle Turnstile delay
        for poll in range(240):  # 120s /0.5
            try:
                if await continue_btn.is_enabled(timeout=1000):
                    print(f"✅ Button enabled! (poll {poll+1}) Clicking NOW...")
                    await page.wait_for_timeout(500)
                    await continue_btn.click(timeout=5000)
                    print("✅ Clicked 'Continue with Email'")
                    break
            except:
                pass
            await page.wait_for_timeout(500)
            if poll % 10 == 0 and poll > 0:
                print(f"  ... still waiting {poll*0.5:.0f}s")
        else:
            # fallback single expect 60s
            await expect(continue_btn).to_be_enabled(timeout=60000)
            print("✅ Button enabled!")
            await page.wait_for_timeout(1000)
            await continue_btn.click(timeout=5000)
            print("✅ Clicked 'Continue with Email'")
    except Exception as e:
        screenshot_path = f"/tmp/turnstile-timeout-{int(time.time())}.png"
        try:
            await page.screenshot(path=screenshot_path, full_page=True)
            print(f"❌ Screenshot: {screenshot_path}")
            # also dump page text for debug
            txt = await page.locator("body").inner_text()
            print(f"Page text snippet: {txt[:500]}")
        except:
            pass
        raise RuntimeError(f"Turnstile/button timeout: {e}")
    
    # Wait for Railway to send email
    print("⏳ Waiting 15s for Railway email...")
    await asyncio.sleep(15)
    
    # Get OTP from dispose.lol
    code = await mailbox.wait_for_railway_code()
    print(f"✅ Got OTP: {code}")
    
    # Fill OTP - wait for Magic.link modal to appear
    print("  Entering OTP...")
    await page.wait_for_timeout(5000)  # Wait longer for modal to load
    
    # Try direct input method (Magic.link creates 6 inputs)
    try:
        print("  🔍 Looking for OTP inputs...")
        all_inputs = page.locator('input[type="text"]:visible')
        count = await all_inputs.count()
        print(f"  Found {count} visible text inputs")
        
        if count >= 6:
            for i, digit in enumerate(code[:6]):
                await all_inputs.nth(i).fill(digit)
                await asyncio.sleep(0.1)
            print("  ✅ Filled OTP")
        else:
            # Try looking for any input, even if not visible yet
            await page.wait_for_selector('input[type="text"]', timeout=10000)
            all_inputs = page.locator('input[type="text"]')
            count = await all_inputs.count()
            print(f"  Found {count} text inputs (after wait)")
            
            if count >= 6:
                for i, digit in enumerate(code[:6]):
                    await all_inputs.nth(i).fill(digit)
                    await asyncio.sleep(0.1)
                print("  ✅ Filled OTP")
            else:
                raise Exception(f"Only found {count} inputs")
    except Exception as e:
        print(f"  ⚠️  Direct method failed: {e}")
        # Try iframe method
        try:
            print("  🔍 Trying iframe method...")
            magic_frame = page.frame_locator('iframe[src*="auth.magic.link"], iframe[src*="magic"]')
            inputs = magic_frame.locator('input[type="text"]')
            await inputs.first.wait_for(state="visible", timeout=10000)
            
            for i, digit in enumerate(code):
                await inputs.nth(i).fill(digit)
                await asyncio.sleep(0.1)
            print("  ✅ Filled OTP (iframe method)")
        except Exception as e2:
            raise Exception(f"Both OTP methods failed: {e}, {e2}")
    
    # Wait for redirect to dashboard
    print("⏳ Waiting for login to complete...")
    try:
        await page.wait_for_url("**/dashboard**", timeout=30000)
        print("✅ Logged in successfully!")
    except:
        await page.wait_for_timeout(5000)
        if "dashboard" in page.url:
            print("✅ Logged in successfully!")
        else:
            raise Exception(f"Login failed - stuck at: {page.url}")


async def scroll_terms_dialog(dialog) -> None:
    await dialog.evaluate("""dialog => {
        for (const el of [dialog, ...dialog.querySelectorAll('*')]) {
            if (el.scrollHeight > el.clientHeight + 10) {
                el.scrollTop = el.scrollHeight;
                el.dispatchEvent(new Event('scroll', { bubbles: true }));
            }
        }
    }""")

async def dismiss_cookie_banner(page) -> None:
    for _ in range(6):
        removed = False
        for sel in [".osano-cm-window", ".fc-message-root", "[aria-label='Cookie Consent Banner']"]:
            els = page.locator(sel)
            for i in range(await els.count()):
                try:
                    await els.nth(i).evaluate("el => el.remove()")
                    removed = True
                except:
                    pass
        if removed:
            await page.wait_for_timeout(300)
            continue
        root = page.locator(".fc-message-root, .osano-cm-window, [aria-label='Cookie Consent Banner']").first
        if not await root.count() or not await root.is_visible():
            return
        buttons = root.locator("button")
        clicked = False
        for index in range(await buttons.count()):
            button = buttons.nth(index)
            if not await button.is_visible():
                continue
            try:
                await button.click(timeout=2000)
                clicked = True
                break
            except:
                continue
        if not clicked:
            await root.evaluate("el => el.remove()")
            return
        await page.wait_for_timeout(500)

async def accept_railway_policies(page):
    """Accept Railway ToS - correct scroll + I agree buttons per railway-login.py:242"""
    print("\n📜 Accepting Railway policies...")
    try:
        await page.wait_for_timeout(3000)
        await dismiss_cookie_banner(page)
        dialog = page.get_by_role("dialog", name=re.compile(r"Terms of Service", re.I)).last
        try:
            await dialog.wait_for(state="visible", timeout=10000)
        except:
            print("  ✅ No Terms dialog")
            return
        print(f"  📜 Terms dialog found")
        agree_buttons = ["I agree with Railway's Terms of Service", "I agree to the Fair Use Policy"]
        for _ in range(6):
            try:
                await scroll_terms_dialog(dialog)
            except:
                break
            clicked = False
            for name in agree_buttons:
                await dismiss_cookie_banner(page)
                button = page.get_by_role("button", name=name, exact=True)
                try:
                    await expect(button).to_be_visible(timeout=3000)
                    await expect(button).to_be_enabled(timeout=3000)
                except:
                    continue
                try:
                    await button.click(timeout=5000)
                except:
                    await dismiss_cookie_banner(page)
                    await button.click(force=True, timeout=5000)
                print(f"  ✅ Clicked {name}")
                clicked = True
                break
            if not clicked:
                break
            await page.wait_for_timeout(1500)
        try:
            await expect(page.get_by_text("Terms accepted", exact=True)).to_be_visible(timeout=10000)
            print("✅ Terms accepted")
        except:
            try:
                await expect(dialog).to_be_hidden(timeout=5000)
                print("✅ Terms dialog hidden")
            except:
                print("⚠️  Terms dialog may still visible but continuing")
        await page.wait_for_timeout(2000)
    except Exception as e:
        print(f"⚠️  Policy acceptance issue: {e}")
        try:
            await page.get_by_text("Continue").click(timeout=5000)
            print("✅ Clicked Continue fallback")
        except:
            print("⚠️  Could not accept policies")


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

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

async def get_oauth_tokens(page) -> dict:
    """Run CLI PKCE flow inside already-logged-in browser - correct endpoint /oauth/auth"""
    verifier = "".join(secrets.choice(PKCE_CHARSET) for _ in range(128))
    challenge = _pkce_challenge(verifier)
    state = secrets.token_urlsafe(32)
    loop = asyncio.get_running_loop()
    result_holder = {}
    async def callback_handler(reader, writer):
        request_line = (await reader.read(65536)).decode(errors="replace").split("\r\n")[0]
        path = request_line.split(" ")[1] if " " in request_line else "/"
        if not result_holder:
            result_holder["query"] = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)
        body = b"<html><body>Railway login approved. You can close this tab.</body></html>"
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n" + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body)
        await writer.drain()
        writer.close()
    callback_server = await asyncio.start_server(callback_handler, "127.0.0.1", 0)
    callback_port = callback_server.sockets[0].getsockname()[1]
    redirect_uri = f"http://127.0.0.1:{callback_port}/callback"
    try:
        authorization_url = (
            f"{RAILWAY_OAUTH}/auth?"
            + urllib.parse.urlencode({
                "response_type": "code",
                "client_id": RAILWAY_CLIENT_ID,
                "redirect_uri": redirect_uri,
                "scope": RAILWAY_SCOPES,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": state,
                "prompt": "consent",
                "cli_caller": "opencode",
            })
        )
        print(f"  🔗 OAuth URL: {authorization_url[:80]}...")
        await page.goto(authorization_url, wait_until="domcontentloaded")
        deadline = loop.time() + 120
        while loop.time() < deadline:
            if result_holder:
                break
            # dismiss cookie banner if present
            try:
                root = page.locator(".fc-message-root").first
                if await root.count() and await root.is_visible():
                    btns = root.locator("button")
                    for idx in range(await btns.count()):
                        b = btns.nth(idx)
                        if await b.is_visible():
                            try: await b.click(timeout=2000); break
                            except: continue
            except: pass
            authorize = page.get_by_role("button", name="Authorize", exact=True)
            if await authorize.count():
                try: await authorize.click(timeout=5000); print("✓ Clicked Authorize")
                except: pass
            await page.wait_for_timeout(2000)
        if not result_holder:
            raise RuntimeError("Railway consent flow never redirected back.")
        callback_query = result_holder["query"]
        if "error" in callback_query:
            description = callback_query.get("error_description", [""])[0]
            raise RuntimeError(f"Railway OAuth rejected: {callback_query['error'][0]} {description}")
        if "code" not in callback_query or callback_query.get("state", [""])[0] != state:
            raise RuntimeError("Railway OAuth callback missing or mismatched.")
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

def get_web_user(cookies: list[dict]) -> dict:
    session = {c["name"]: c["value"] for c in cookies if c["domain"] == "backboard.railway.com" and c["name"] in ("rw.session", "rw.session.sig")}
    if not session.get("rw.session"):
        raise RuntimeError("No rw.session cookie for CLI registration.")
    cookie_header = "; ".join(f"{k}={v}" for k, v in session.items())
    payload = {"query": "query { me { id email } }"}
    request = urllib.request.Request(
        RAILWAY_GRAPHQL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Cookie": cookie_header, "User-Agent": "railway-cli/5.35.0"},
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
        "user": {"accessToken": tokens["access_token"], "id": user["id"], "refreshToken": tokens.get("refresh_token"), "token": None, "tokenExpiresAt": expires_at},
    }
    (session_dir / "browser_cookies.json").write_text(json.dumps({"cookies": cookies}, indent=2))
    for target in (session_dir / "railway_cli_config.json", cli_home / "config.json"):
        target.write_text(json.dumps(config, indent=2))
    (cli_home / "version.json").write_text(json.dumps({"last_update_check": now.isoformat(), "latest_version": None, "download_failures": 0, "skipped_version": None, "last_package_manager_spawn": None}, indent=2))
    session_payload = {"agent_session_id": str(uuid.uuid4()), "parent_pid": os.getpid(), "parent_btime": 0, "created_at": now.isoformat()}
    session_name = f"{secrets.token_hex(8)}.session"
    (cli_home / "sessions" / session_name).write_text(json.dumps(session_payload))
    (session_dir / "railway_cli_sessions" / session_name).write_text(json.dumps(session_payload))
    # also save simple email/timestamp for compatibility
    (session_dir / "email.txt").write_text(user.get("email",""))
    (session_dir / "created_at.txt").write_text(now.isoformat())
    print(f"✓ Saved CLI session: {session_dir} / .railway/config.json")

def verify_tokens(tokens: dict, user: dict) -> str:
    request = urllib.request.Request(
        RAILWAY_GRAPHQL,
        data=json.dumps({"query": "query { me { id email } }"}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {tokens['access_token']}", "User-Agent": "railway-cli/5.35.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        me = ((json.loads(response.read().decode())).get("data") or {}).get("me") or {}
    if not me.get("id") or me["id"] != user["id"]:
        raise RuntimeError("CLI tokens failed verification.")
    return me.get("email") or user.get("email") or me["id"]

async def register_cli_session(context, page, sessions_dir: Path) -> Path:
    print("\n🔧 Registering Railway CLI session (PKCE /auth)...")
    cookies = await context.cookies()
    tokens = await get_oauth_tokens(page)
    print("✓ Got access and refresh tokens")
    user = get_web_user(cookies)
    print(f"✓ User: {user.get('email')} (ID: {user.get('id')})")
    # find next session dir like railway-login.py but reuse next_session_dir helper that checks Mega
    # Use next_session_dir that already exists in file (checks Mega)
    session_dir = next_session_dir(sessions_dir)
    write_cli_session(session_dir, tokens, user, cookies)
    email = verify_tokens(tokens, user)
    print(f"✅ CLI verification: {email} authenticated")
    return session_dir


# ============================================================================
# MAIN EXECUTION
# ============================================================================
async def run(use_warp=False):
    """Run single account creation"""
    warp_started = False
    browser = None
    mailbox = None
    
    try:
        # Start WARP if requested - warp-cli proxy mode (isolated)
        if use_warp:
            print("\n🌐 Setting up WARP (proxy mode - isolated)...")
            warp_started = start_warp()
            if not warp_started:
                print("⚠️  WARP proxy not available, continuing direct (isolated check failed)")
                use_warp = False
            else:
                # verify isolation: warp=on via proxy, warp=off direct
                import urllib.request, json as _j
                try:
                    import socket
                    with socket.create_connection(("127.0.0.1", 40000), timeout=2):
                        print("✅ WARP proxy 127.0.0.1:40000 alive (browser-only, other apps not affected)")
                except:
                    print("⚠️  Proxy port 40000 not reachable, continuing direct")
                    use_warp = False
        
        print("\n🚀 Launching browser...")
        # WARP route interception: browser goes direct, page.route does WARP via httpx (fixes gVisor SOCKS hang)
        async with async_playwright() as p:
            picked = _pick_proxy() if use_warp else None
            # If WARP route will be used, browser itself stays direct (route handles WARP)
            if use_warp and HTTPX_AVAILABLE and picked:
                proxy_settings = None
                print(f"🌐 Browser direct, WARP route via httpx socks5://127.0.0.1:40000 (gVisor SOCKS fix)")
            else:
                proxy_settings = {"server": picked, "bypass": "127.0.0.1,localhost,dispose.lol,*.dispose.lol,22.do,*.22.do,railway.com,*.railway.com,*.railway.app,backboard.railway.com"} if picked else None
                if proxy_settings:
                    print(f"🌐 Browser proxy: {proxy_settings['server']} bypass={proxy_settings['bypass']} (isolated, wireproxy socks5)")
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-software-rasterizer',
                    '--disable-extensions',
                    '--no-first-run',
                    '--window-size=800,600',
                    '--single-process',
                    '--no-zygote',
                    '--disable-site-isolation-trials',
                    '--disable-features=IsolateOrigins,site-per-process,Translate,AutomationControlled',
                    '--js-flags=--max-old-space-size=96',
                    '--memory-pressure-off',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-background-networking',
                    '--disable-background-timer-throttling',
                    '--disable-renderer-backgrounding',
                    '--disable-ipc-flooding-protection',
                    '--aggressive-cache-discard'
                ]
            )
            context = await browser.new_context(proxy=proxy_settings, viewport={"width": 800, "height": 600})
            # WARP route interception — headed Chromium egress via WARP without browser SOCKS (fixes gVisor SOCKS hang)
            if use_warp and HTTPX_AVAILABLE:
                try:
                    HOP = {"host","connection","proxy-connection","proxy-authorization","keep-alive","transfer-encoding","content-length","upgrade"}
                    async def warp_handler(route):
                        url = route.request.url
                        if url.startswith(("data:","about:")):
                            return await route.continue_()
                        # bypass 22.do / dispose / railway direct (warp 403), keep warp for Turnstile/cloudflare
                        if any(d in url for d in ["22.do", "dispose.lol", "mail.tm", "api.mail.tm", "railway.com", "railway.app", "backboard.railway.com"]):
                            return await route.continue_()
                        try:
                            headers = {k:v for k,v in route.request.headers.items() if k.lower() not in HOP}
                            body = route.request.post_data.encode() if route.request.post_data else None
                            async with httpx.AsyncClient(proxy="socks5://127.0.0.1:40000", timeout=25, follow_redirects=True, verify=False) as c:
                                r = await c.request(route.request.method, url, headers=headers, content=body)
                            resp = {k:v for k,v in r.headers.items() if k.lower() not in (HOP|{"content-encoding","content-length"})}
                            await route.fulfill(status=r.status_code, headers=resp, body=r.content)
                        except Exception:
                            try: await route.continue_()
                            except: pass
                    await context.route("**/*", warp_handler)
                    print("🌐 WARP route interception active (httpx via socks5://127.0.0.1:40000)")
                except Exception as e:
                    print(f"⚠️ WARP route failed: {e}")
            else:
                # 1GB: abort heavy resources — headed (VNC) keeps CSS/JS for visibility, headless saves more
                try:
                    if headless:
                        await context.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image","media","font","stylesheet","other","websocket"] else route.continue_())
                    else:
                        await context.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image","media","font"] else route.continue_())
                except Exception:
                    pass
            context.set_default_timeout(ACTION_TIMEOUT)
            page = await context.new_page()
            # --- crash safe: detect tab/browser crash and retry ---
            def _on_crash(p):
                try:
                    print(f"💥 tab crashed at {p.url if not p.is_closed() else 'closed'} — safe will retry")
                except Exception:
                    print("💥 tab crashed — safe will retry")
            try:
                page.on("crash", _on_crash)
                page.on("close", lambda _: print("❌ tab closed — safe will retry"))
                context.on("close", lambda _: print("❌ context closed"))
            except Exception:
                pass
            # verify egress inside browser (bypass warp for this check, direct)
            try:
                await page.goto("https://cloudflare.com/cdn-cgi/trace", timeout=15000, wait_until="domcontentloaded")
                body = await page.content()
                if "warp=on" in body:
                    print("✅ Browser egress warp=on verified (isolated tunnel)")
                    for l in body.splitlines():
                        if l.startswith("ip=") or l.startswith("warp="):
                            print(f"  {l.strip()}")
                else:
                    print("⚠️  Browser egress not via WARP (direct)")
                await page.goto("about:blank")
            except Exception as e:
                print(f"⚠️  Egress check failed: {e}")
            
            print("✅ Browser ready")
            
            # Create 22.do mailbox — random handler per run (or enforced target_domain / recovery)
            target_domain = globals().get("CLI_TARGET_DOMAIN")  # set from CLI --domain
            recovery_email = globals().get("CLI_RECOVERY_EMAIL")  # set from CLI --recov
            _handler_desc = recovery_email or target_domain or "random pool"
            print(f"📧 22.do handler: {_handler_desc} (pool {len(HANDLERS)} handlers)")
            # --- retry wrapper: don't exit on tab crash, retry fresh tab/handler (minimal) ---
            mailbox = None
            for _crash_attempt in range(3):
                try:
                    mailbox = TwoTwoDoInbox(context=context, target_domain=target_domain, recovery_email=recovery_email)
                    mailbox.railway_page = page  # keep compat with close()
                    await mailbox.create()
                    break
                except Exception as _e:
                    _msg = str(_e)
                    _is_22do_fail = ("ERR_CONNECTION_CLOSED" in _msg or "ERR_PROXY_CONNECTION_FAILED" in _msg or "403" in _msg or "Timeout" in _msg)
                    _is_crash = ("Target crashed" in _msg or "TargetClosed" in _msg or "Page crashed" in _msg or "has been closed" in _msg or page.is_closed())
                    if _is_22do_fail:
                        print(f"⚠️  22.do blocked ({_msg[:80]}), trying dispose.lol...")
                        try:
                            if not page.is_closed():
                                await page.close()
                        except Exception:
                            pass
                        try:
                            dispose_mailbox = DisposeLolInbox(context=context)
                            await dispose_mailbox.create()
                            mailbox = dispose_mailbox
                            break
                        except Exception as _de:
                            print(f"⚠️  dispose.lol also failed ({str(_de)[:60]}), falling back to mail.tm API...")
                            mailbox = MailTmInbox(context=context, target_domain=target_domain, recovery_email=recovery_email)
                            await mailbox.create()
                            break
                    if _is_crash:
                        print(f"💥 crash detected (attempt {_crash_attempt+1}/3): {_msg[:180]} — retrying fresh tab/handler")
                        try:
                            if not page.is_closed():
                                await page.close()
                        except Exception:
                            pass
                        try:
                            page = await context.new_page()
                            page.on("crash", _on_crash)
                            page.on("close", lambda _: print("❌ tab closed — safe will retry"))
                        except Exception:
                            pass
                        if not target_domain and not recovery_email:
                            print("🔄 retrying with new random handler")
                        continue
                    raise
            else:
                raise RuntimeError("tab crashed 3x — aborting run")
            
            # Recreate page if it was closed during fallback
            if page.is_closed():
                page = await context.new_page()
                page.on("crash", _on_crash)
                page.on("close", lambda _: print("❌ tab closed"))
            
            # Sign in to Railway
            await sign_in_to_railway(page, mailbox)
            
            # Accept policies
            await accept_railway_policies(page)
            
            # Register CLI session
            try:
                session_dir = await register_cli_session(context, page, SESSIONS_DIR)
                
                # Sync to Mega
                sync_to_mega(session_dir)
                
                print(f"\n{'='*60}")
                print(f"✅ SUCCESS! Account created: {mailbox.address}")
                print(f"📁 Session: {session_dir}")
                print(f"{'='*60}\n")
            except Exception as e:
                print(f"\n⚠️  OAuth/Session registration failed: {e}")
                print(f"✅ But account IS created! Email: {mailbox.address}")
                print(f"   You can manually log in using this email.")
            
            # Keep browser open for inspection
            print("🔍 Browser will stay open for 30s. Press Ctrl+C to exit now...")
            try:
                await asyncio.sleep(30)
            except KeyboardInterrupt:
                print("\n⏹️  Closing browser...")
            
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        
        # Save debug info
        if mailbox and mailbox.address:
            print(f"\n📧 Email created: {mailbox.address}")
            debug_file = Path("/tmp") / f"railway-debug-{int(time.time())}.txt"
            debug_file.write_text(f"Email: {mailbox.address}\nError: {str(e)}\n{traceback.format_exc()}")
            print(f"💾 Debug info saved: {debug_file}")
    finally:
        # Cleanup
        if mailbox:
            try:
                await mailbox.close()
            except:
                pass
        
        if warp_started:
            stop_warp()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Railway account creator — 22.do pool edition")
    parser.add_argument("--no-warp", action="store_true", help="Disable WARP proxy")
    parser.add_argument("--domain", type=str, default=None, help="Enforce 22.do handler domain, e.g. @linshiyou.com, @gmail.com, @hotmail.com, @outlook.com (default: random) — @googlemail.com banned")
    parser.add_argument("--recov", type=str, default=None, help="Recover existing 22.do inbox, e.g. g92w@colabeta.com (skips creation, opens https://22.do/inbox/#/<mail>)")
    args = parser.parse_args()

    # expose to run() via globals (used inside)
    CLI_TARGET_DOMAIN = args.domain
    CLI_RECOVERY_EMAIL = args.recov

    use_warp = not args.no_warp

    print("="*60)
    print("🏆 THE HOLY RAILWAY ACCOUNT CREATOR — 22.do Pool 🏆")
    print("="*60)
    print(f"📁 Sessions directory: {SESSIONS_DIR}")
    print(f"☁️  Mega remote: {MEGA_REMOTE}")
    print(f"🔁 WARP: {'ENABLED' if use_warp else 'DISABLED'}")
    print(f"📧 22.do handlers: {len(HANDLERS)} (random/pool)" + (f" — enforced: {args.domain or args.recov}" if (args.domain or args.recov) else ""))
    if args.recov:
        print(f"♻️  Recovery mode: {args.recov} → https://22.do/inbox/#/{args.recov}")
    print("="*60)

    asyncio.run(run(use_warp=use_warp))
