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

ORIG_HOME = os.environ.get("HOME", "/home/alan")
from pathlib import Path as _P
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_P(ORIG_HOME) / ".cache" / "ms-playwright")
os.environ["HOME"] = ORIG_HOME  # ensure rclone/playwright use orig home, railway uses session_dir via env override

def ensure_deps():
    """Auto-install missing deps (rclone, playwright) if not found - for cancer cells"""
    import shutil, subprocess as _sp
    # ensure HOME is ORIG for rclone/playwright cache lookup
    os.environ["HOME"] = ORIG_HOME
    # rclone
    if not shutil.which("rclone"):
        print("📥 rclone not found, installing...")
        try:
            _sp.run(["apt", "update", "-q"], capture_output=True, timeout=60)
            _sp.run(["apt", "install", "-y", "unzip"], capture_output=True, timeout=60)
            _sp.run(["bash", "-c", "curl https://rclone.org/install.sh | bash"], capture_output=True, timeout=60)
            print(f"  rclone: {shutil.which('rclone') or 'still missing'}")
        except Exception as e:
            print(f"  rclone install failed: {e}")
    # playwright - ensure browsers installed to ORIG_HOME
    try:
        import playwright
    except ImportError:
        print("📥 playwright not found, installing...")
        try:
            _sp.run([sys.executable, "-m", "pip", "install", "playwright", "--break-system-packages", "-q"], capture_output=True, timeout=60)
            _sp.run([sys.executable, "-m", "playwright", "install", "chromium"], capture_output=True, timeout=120)
            print("  playwright installed")
        except Exception as e:
            print(f"  playwright install failed: {e}")
    # ensure chromium exists
    import pathlib as _pl
    cpath = _pl.Path(ORIG_HOME) / ".cache" / "ms-playwright"
    if not cpath.exists():
        try:
            _sp.run([sys.executable, "-m", "playwright", "install", "chromium"], capture_output=True, timeout=120)
        except: pass
    # railway CLI check
    if not shutil.which("railway"):
        print("⚠️  railway CLI not found")

try:
    ensure_deps()
except: pass
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
RAILWAY_OAUTH_SAME_DOMAIN = "https://railway.com/oauth"
RAILWAY_CLIENT_ID = "rlwy_oaci_onEklvmksh1hRUiCo7E2zX12"
RAILWAY_GRAPHQL = "https://backboard.railway.com/graphql/v2"
RAILWAY_SCOPES = "openid email profile offline_access workspace:admin project:admin ssh_keys"
PKCE_CHARSET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"

SESSIONS_DIR = Path(ORIG_HOME) / "Documents" / "railways"
MEGA_REMOTE = "mega:railway_sessions"
# ponytail: BD Browser API pool for ASN rotation (free tier per-run fresh IP + new ASN)
BRD_WSS_POOL = [
    # hl_709648b2 suspended - removed
    f"wss://brd-customer-hl_834743cb-zone-scraping_browser1:q7k1y7ug1v69@brd.superproxy.io:9222",
    f"wss://brd-customer-hl_3496e863-zone-scraping_browser1:9glc7ho0mx9w@brd.superproxy.io:9222",
    f"wss://brd-customer-hl_faaefe91-zone-scraping_browser1:1e6cx8umg6ax@brd.superproxy.io:9222",
    f"wss://brd-customer-hl_caa3da41-zone-scraping_browser1:ur2v4xcy072v@brd.superproxy.io:9222",
    f"wss://brd-customer-hl_93561405-zone-scraping_browser1:g3jqlqtsjtkc@brd.superproxy.io:9222",
    f"wss://brd-customer-hl_9a778bf1-zone-scraping_browser1:ft5y6mo4jngz@brd.superproxy.io:9222",
    f"wss://brd-customer-hl_19c80b8e-zone-scraping_browser1:o3o5s908y9sh@brd.superproxy.io:9222",
    f"wss://brd-customer-hl_6b1ebf5c-zone-scraping_browser1:fkfbdid0zyi4@brd.superproxy.io:9222",
    f"wss://brd-customer-hl_e895b201-zone-scraping_browser1:b65xwy1jycfq@brd.superproxy.io:9222",
    f"wss://brd-customer-hl_7e8d5d40-zone-scraping_browser1:to0nqcophe4h@brd.superproxy.io:9222",
    # Zenrows Browser Sessions (fallback, uses same API key 3a6a9ee9... - add WSS when available)
]
BRD_WSS = os.environ.get("BRD_WSS") or BRD_WSS_POOL[0]

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

    async def wait_for_railway_code(self, timeout_seconds=750):
        if not self.address:
            raise Exception("No address set")
        print(f"\n📥 Waiting for Railway OTP for {self.address} (timeout: {timeout_seconds}s, max 150 checks)...")
        pattern = re.compile(r'\b(\d{6})\b')
        deadline = time.time() + timeout_seconds
        check_count = 0
        while time.time() < deadline and check_count < 150:
            check_count += 1
            try:
                await self.page.reload(wait_until="domcontentloaded", timeout=15000)
            except: pass
            # ponytail: wait until Loading inbox gone — short poll, not 10s block
            try:
                loading = self.page.locator('.mt-2.inline-flex.items-center.gap-2.text-sm.font-semibold.text-foreground\\/70')
                await loading.wait_for(state="hidden", timeout=3000)
            except:
                await self.page.wait_for_timeout(800)
            message_buttons = await self.page.locator('button[aria-label^="View "]').all()
            if check_count % 10 == 1 or check_count <= 3:
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
async def _click_turnstile_checkbox(page, log=True):
    """Try to click Turnstile checkbox - must hit actual input inside iframe."""
    clicked = False
    # 1) frame_locator on actual checkbox input (most reliable)
    try:
        fl = page.frame_locator('iframe[src*="challenges.cloudflare.com"]')
        # Turnstile's actual checkbox
        for sel in ['input[type="checkbox"]', '[role="checkbox"]', 'label', '#challenge-stage', 'body']:
            try:
                el = fl.locator(sel).first
                if await el.count():
                    box = await el.bounding_box()
                    if box and box["width"] > 0:
                        await el.click(timeout=1500)
                        if log: print(f"  🔘 Clicked Turnstile via {sel}")
                        clicked = True
                        break
            except: continue
    except: pass
    # 2) precise left-side coord click (22px from left edge of iframe)
    if not clicked:
        try:
            iframe = page.locator('iframe[src*="challenges.cloudflare.com"]')
            if await iframe.count() > 0 and await iframe.first.is_visible():
                box = await iframe.first.bounding_box()
                if box and box["width"] > 0:
                    await page.mouse.click(box["x"] + 22, box["y"] + box["height"] / 2, delay=100)
                    await page.wait_for_timeout(500)
                    # click again slightly offset if first didn't trigger
                    await page.mouse.click(box["x"] + 30, box["y"] + box["height"] / 2, delay=100)
                    if log: print("  🔘 Clicked Turnstile iframe left coord")
                    clicked = True
        except: pass
    # 3) fallback: click via JS evaluate on cf-turnstile
    if not clicked:
        try:
            hit = await page.evaluate('''() => {
                const el = document.querySelector('.cf-turnstile, [data-sitekey]');
                if (el) { el.click(); el.dispatchEvent(new MouseEvent('click',{bubbles:true})); return true; }
                return false;
            }''')
            if hit:
                clicked = True
        except: pass
    return clicked


async def _handle_turnstile(page, until_solved_fn, total_seconds=80):
    """Actively handle Cloudflare Turnstile every 0.5s while also running until_solved_fn().

    On every loop: click the checkbox if present, look for an interactive challenge
    and click it, and check if the continue button is now enabled (until_solved_fn).

    If no CF widget is present at all, still continues polling until_solved_fn.
    Returns True if solved (button enabled), else False on timeout.
    """
    deadline = time.time() + total_seconds
    printed_widget = False
    while time.time() < deadline:
        done = await until_solved_fn()
        if done:
            return True
        # actively handle any visible Turnstile widget
        has_widget = False
        try:
            iframe = page.locator('iframe[src*="challenges.cloudflare.com"]')
            cnt = await iframe.count()
            has_widget = cnt > 0
            if cnt > 0 and await iframe.first.is_visible():
                if not printed_widget:
                    print("  🤖 Active Turnstile handling...")
                    printed_widget = True
                await _click_turnstile_checkbox(page, log=False)
        except Exception:
            pass
        # if interactive challenge appeared, click its continue/checkbox too
        try:
            if has_widget:
                chall = page.frame_locator('iframe[src*="challenges.cloudflare.com"]')
                for label in ("I\'m not a robot", "Verify", "Continue", "checkbox"):
                    b = chall.get_by_role("button", name=label)
                    if await b.count():
                        await b.first.click(timeout=1500)
                        break
        except Exception:
            pass
        await page.wait_for_timeout(500)
    return False


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
    
    # Wait for Continue button to enable — active Turnstile handling every 0.5s
    continue_btn = page.get_by_role("button", name="Continue with Email", exact=True)
    print("⏳ Waiting for Continue button to enable (active CF handling)...")

    async def cont_enabled():
        try:
            if await continue_btn.is_enabled(timeout=800):
                return True
        except Exception:
            pass
        return False

    try:
        solved = await _handle_turnstile(page, cont_enabled, total_seconds=80)
        if solved:
            print("✅ Continue button enabled — clicking NOW...")
            await page.wait_for_timeout(500)
            await continue_btn.click(timeout=5000)
            print("✅ Clicked 'Continue with Email'")
        else:
            # put a debug screenshot before breaker rotates
            screenshot_path = f"/tmp/turnstile-timeout-{int(time.time())}.png"
            try:
                await page.screenshot(path=screenshot_path, full_page=True)
                print(f"❌ Screenshot: {screenshot_path}")
                txt = await page.locator("body").inner_text()
                print(f"Page text snippet: {txt[:400]}")
            except: pass
            raise RuntimeError("Turnstile/button timeout")
    except Exception as e:
        raise RuntimeError(f"Turnstile/button timeout: {e}")
    
    # Wait for Railway to send email
    print("⏳ Waiting 15s for Railway email...")
    await asyncio.sleep(15)
    
    # Get OTP from dispose.lol — short 80s wait; if nothing arrives, breaker rotates mail+browser+ASN
    code = await mailbox.wait_for_railway_code(timeout_seconds=80)
    print(f"✅ Got OTP: {code}")
    
    # Fill OTP - wait for Magic.link modal to appear
    print("  Entering OTP...")
    await page.wait_for_timeout(7000)
    filled = False
    # Try iframe method first (most reliable for Magic)
    try:
        print("  🔍 Trying iframe method...")
        magic_frame = page.frame_locator('iframe[src*="auth.magic.link"], iframe[src*="magic"]')
        inputs = magic_frame.locator('input[type="text"], input[type="tel"], input[inputmode="numeric"]')
        await inputs.first.wait_for(state="visible", timeout=15000)
        for i, digit in enumerate(code[:6]):
            await inputs.nth(i).fill(digit)
            await asyncio.sleep(0.15)
        print("  ✅ Filled OTP (iframe method)")
        filled = True
    except Exception as e:
        print(f"  ⚠️  iframe method failed: {e}")
    if not filled:
        try:
            print("  🔍 Trying direct method...")
            all_inputs = page.locator('input[type="text"]:visible, input[inputmode="numeric"]:visible')
            count = await all_inputs.count()
            print(f"  Found {count} visible text inputs")
            if count >= 6:
                for i, digit in enumerate(code[:6]):
                    await all_inputs.nth(i).fill(digit)
                    await asyncio.sleep(0.15)
                print("  ✅ Filled OTP (direct)")
                filled = True
            else:
                await page.wait_for_selector('input', timeout=10000)
                all_inputs = page.locator('input')
                count = await all_inputs.count()
                print(f"  Found {count} inputs (after wait)")
                if count >= 6:
                    for i, digit in enumerate(code[:6]):
                        await all_inputs.nth(i).fill(digit)
                        await asyncio.sleep(0.15)
                    print("  ✅ Filled OTP")
                    filled = True
        except Exception as e2:
            print(f"  ⚠️  Direct method failed: {e2}")
    if not filled:
        # fallback: type code and press Enter on page
        try:
            await page.keyboard.type(code)
            await page.keyboard.press("Enter")
            print(f"  ✅ Typed OTP {code} + Enter (fallback)")
            filled = True
        except Exception as e3:
            print(f"  ⚠️  Fallback failed: {e3}")
        except Exception as e2:
            raise Exception(f"Both OTP methods failed: {e}, {e2}")
    
    # Wait for redirect to dashboard — poll for 60s
    print("⏳ Waiting for login to complete...")
    logged = False
    for _ in range(12):
        await page.wait_for_timeout(5000)
        url = page.url
        txt = ""
        try: txt = await page.evaluate("() => document.body.innerText.slice(0,1000)")
        except: pass
        if "dashboard" in url or "My Projects" in txt or "Create a New Project" in txt:
            print(f"✅ Logged in successfully! url={url[:80]}")
            logged = True
            break
        # also try pressing Enter again if stuck
        try: await page.keyboard.press("Enter")
        except: pass
    if not logged:
        # final check via URL
        try:
            await page.wait_for_url("**/dashboard**", timeout=10000)
            print("✅ Logged in successfully! (via wait_for_url)")
            logged = True
        except: pass
    if not logged:
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

async def get_oauth_tokens_raw(cookies: list[dict]) -> dict:
    """PKCE via raw IP (bypass BD 1-domain) — uses rw.session cookies + local 127.0.0.1 callback"""
    verifier = "".join(secrets.choice(PKCE_CHARSET) for _ in range(128))
    challenge = _pkce_challenge(verifier)
    state = secrets.token_urlsafe(32)
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
    session = {c["name"]: c["value"] for c in cookies if c["domain"] == "backboard.railway.com" and c["name"] in ("rw.session", "rw.session.sig")}
    if not session.get("rw.session"):
        callback_server.close()
        await callback_server.wait_closed()
        raise RuntimeError("No rw.session cookie for raw PKCE.")
    cookie_header = "; ".join(f"{k}={v}" for k, v in session.items())
    all_cookie = "; ".join(f"{c['name']}={c['value']}" for c in cookies if c["domain"].endswith("railway.com") or c["domain"].endswith("magic.link"))
    headers = {"Cookie": all_cookie, "User-Agent": "railway-cli/5.35.0"}
    def fetch_auth():
        import http.client, ssl, urllib.parse
        req = urllib.request.Request(authorization_url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode(errors="replace")
                if "Authorize" in body and not result_holder:
                    try:
                        req2 = urllib.request.Request(authorization_url, headers={**headers, "Content-Type": "application/x-www-form-urlencoded"}, data=b"authorize=Authorize", method="POST")
                        with urllib.request.urlopen(req2, timeout=30) as resp2:
                            body2 = resp2.read().decode(errors="replace")
                            pass
                    except Exception:
                        pass
                return body
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308):
                loc = e.headers.get("Location", "")
                if "127.0.0.1" in loc and "code=" in loc:
                    qs = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query)
                    result_holder["query"] = qs
                    return ""
            raise
        except Exception as e:
            raise
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, fetch_auth)
        for _ in range(30):
            if result_holder:
                break
            await asyncio.sleep(0.5)
        if not result_holder:
            raise RuntimeError("Raw IP PKCE never redirected to callback (no code).")
        callback_query = result_holder["query"]
        if "error" in callback_query:
            raise RuntimeError(f"Railway OAuth rejected: {callback_query['error'][0]}")
        if "code" not in callback_query or callback_query.get("state", [""])[0] != state:
            raise RuntimeError("Raw PKCE callback missing code/state.")
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

async def get_oauth_tokens_local_chrome(cookies: list[dict]) -> dict:
    """PKCE via LOCAL headless chrome on raw IP with the BD session cookie.

    BD's 1-domain / brul policy blocks /oauth/auth inside the BD browser, and the
    rw.session cookie is IP-bound (only valid from a real browser w/ Cloudflare
    clearance). The local chrome here runs on the host's raw egress (NOT Tor: we
    clear LD_PRELOAD) so Cloudflare clears the cookie and the consent redirect to
    127.0.0.1 works. This is the working cloud PKCE path.
    """
    verifier = "".join(secrets.choice(PKCE_CHARSET) for _ in range(128))
    challenge = _pkce_challenge(verifier)
    state = secrets.token_urlsafe(32)
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
    # raw IP egress for chrome (bypass Tor LD_PRELOAD so the cookie's CF clearance works)
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-blink-features=AutomationControlled"],
            env={"LD_PRELOAD": "", "PATH": os.environ.get("PATH", ""), "HOME": ORIG_HOME},
        )
        context = await browser.new_context()
        # inject railway cookies (filter to valid playwright cookie shape)
        valid = []
        for c in cookies:
            try:
                valid.append({"name": c["name"], "value": c["value"], "domain": c["domain"], "path": c.get("path", "/")})
            except: pass
        rail_only = [c for c in valid if c["domain"].endswith("railway.com")]
        # inject osano consent so banner never shows (was blocking Authorize)
        osano_extra = [
            {"name": "osano_consentmanager_uuid", "value": "1ee2898a-8b48-484c-8551-4e17c2fed221", "domain": ".railway.com", "path": "/"},
            {"name": "osano_consentmanager", "value": "1YWwPBXVXTUh5zCJjTwMRChvFRErfkURooORdKhBcflwA0sG3sarvZ3kAoxC", "domain": ".railway.com", "path": "/"},
        ]
        for oc in osano_extra:
            if not any(c["name"] == oc["name"] for c in rail_only):
                rail_only.append(oc)
        if rail_only:
            await context.add_cookies(rail_only)
        page = await context.new_page()
        try:
            print(f"  🔗 local chrome PKCE (raw IP): {authorization_url[:70]}...")
            await page.goto(authorization_url, wait_until="domcontentloaded", timeout=30000)
            print(f"  🔗 after goto url={page.url[:90]} title={await page.title()}")
            # dismiss cookie/consent banner (Osano/OneTrust) that can cover the Authorize button
            for ctxt in ("Accept", "Allow", "Agree", "Accept All", "Allow All", "Got it", "Accept Cookies"):
                try:
                    b = page.get_by_role("button", name=ctxt)
                    if await b.count():
                        await b.first.click(timeout=2000)
                        print(f"  🍪 dismissed cookie banner via '{ctxt}'")
                        await page.wait_for_timeout(800)
                except: pass
            # close Cookie Preferences dialog if open
            try:
                cp = page.get_by_role("button", name="Cookie Preferences")
                if await cp.count() and await cp.first.is_visible():
                    # press Escape to close it
                    await page.keyboard.press("Escape")
                    await page.wait_for_timeout(800)
                    print(f"  🍪 closed Cookie Preferences")
            except: pass
            # scroll consent dialog (Authorize may be below fold)
            try:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(500)
                dlg = page.get_by_role("dialog").first
                if await dlg.count():
                    await dlg.evaluate("el => { el.scrollTop = el.scrollHeight; el.dispatchEvent(new Event('scroll', {bubbles:true})); }")
                    await page.wait_for_timeout(500)
                # also scroll any scrollable container
                await page.evaluate("document.querySelectorAll('[role=dialog], .modal, [class*=consent]').forEach(el=>el.scrollTop=el.scrollHeight)")
                await page.wait_for_timeout(500)
            except: pass
            # click Authorize deep scan 5min, each sec scroll + check whole DOM
            for _ in range(300):
                if result_holder:
                    break
                # scroll and check whole DOM each sec
                try:
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight); document.documentElement.scrollTop=document.documentElement.scrollHeight")
                    await page.evaluate("document.querySelectorAll('*').forEach(el=>{try{if(el.scrollHeight>el.clientHeight) el.scrollTop=el.scrollHeight}catch(e){}})")
                except: pass
                try:
                    btn = None
                    for name in ["Accept and Connect CLI", "Authorize", "Authorize App", "Allow", "Confirm"]:
                        b = page.get_by_role("button", name=name)
                        if await b.count() and await b.first.is_visible():
                            btn = b.first
                            break
                    if not btn:
                        b = page.locator('button:has-text("Authorize"), button:has-text("Accept and Connect CLI")')
                        if await b.count():
                            # check visible
                            try:
                                if await b.first.is_visible():
                                    btn = b.first
                            except:
                                btn = b.first
                    if btn:
                        lbl = await btn.inner_text()
                        # scroll into view
                        try: await btn.scroll_into_view_if_needed(timeout=2000)
                        except: pass
                        try:
                            await btn.click(timeout=3000)
                        except:
                            await btn.evaluate("el => el.click()")
                        print(f"  ✓ Clicked Authorize (local chrome) [btn='{lbl.strip()[:30]}'], url now={page.url[:90]}")
                    elif _ % 30 == 0:
                        try:
                            btns = await page.locator("button").all_inner_texts()
                            print(f"  🔍 consent buttons ({_}s): {[b.strip()[:25] for b in btns if b.strip()]}")
                            hit = await page.evaluate('''() => {
                                const bs = Array.from(document.querySelectorAll('button, [role=button], a'));
                                for (const b of bs) if (b.textContent && (b.textContent.includes('Authorize') || b.textContent.includes('Accept and Connect'))) { b.scrollIntoView(); b.click(); return b.textContent; }
                                return null;
                            }''')
                            if hit:
                                print(f"  ✓ JS clicked Authorize {hit[:20]}")
                        except: pass
                except Exception as ce:
                    if _ % 30 == 0: print(f"  ⚠️  Authorize click err: {str(ce)[:120]}")
                if "127.0.0.1" in page.url and "code=" in page.url:
                    result_holder["query"] = urllib.parse.parse_qs(urllib.parse.urlparse(page.url).query)
                    print("  ✓ Captured code via page.url")
                    break
                await page.wait_for_timeout(1000)
            for _ in range(30):
                if result_holder:
                    break
                await asyncio.sleep(0.5)
            if not result_holder:
                raise RuntimeError("Local chrome PKCE never hit callback")
            q = result_holder["query"]
            if "error" in q:
                raise RuntimeError(f"OAuth rejected {q['error'][0]}")
            if "code" not in q or q.get("state", [""])[0] != state:
                raise RuntimeError("Local chrome PKCE missing code/state")
            return http_post_form(
                f"{RAILWAY_OAUTH}/token",
                {
                    "grant_type": "authorization_code",
                    "code": q["code"][0],
                    "redirect_uri": redirect_uri,
                    "client_id": RAILWAY_CLIENT_ID,
                    "code_verifier": verifier,
                },
            )
        finally:
            await context.close()
            await browser.close()
            callback_server.close()
            try:
                await callback_server.wait_closed()
            except: pass

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

async def register_cli_session(context, page, sessions_dir: Path, cloud_mode=False) -> Path:
    print("\n🔧 Registering Railway CLI session (PKCE /auth)...")
    cookies = await context.cookies()
    # cloud free = 1 domain, PKCE via BD browser blocked → do PKCE via raw IP with cookies
    if cloud_mode:
        user = get_web_user(cookies)
        print(f"✓ User (cloud direct): {user.get('email')} (ID: {user.get('id')})")
        # local chrome on raw IP (works: cookie is IP-bound but CF clears it in a real browser)
        try:
            tokens = await get_oauth_tokens_local_chrome(cookies)
            print("✓ Got access and refresh tokens (cloud local chrome PKCE)")
        except Exception as e:
            print(f"⚠️  Cloud local chrome PKCE failed ({e}), trying raw IP PKCE")
            try:
                tokens = await get_oauth_tokens_raw(cookies)
                print("✓ Got access and refresh tokens (cloud raw IP PKCE)")
            except Exception as e2:
                print(f"⚠️  Cloud raw IP PKCE failed ({e2}), trying browser PKCE fallback")
                try:
                    tokens = await get_oauth_tokens(page)
                    print("✓ Got access and refresh tokens (cloud browser PKCE)")
                except Exception as e3:
                    print(f"⚠️  Cloud PKCE blocked ({e3}), creating web-only session")
                session_dir = next_session_dir(sessions_dir)
                session_dir.mkdir(parents=True, exist_ok=True)
                (session_dir / "email.txt").write_text(user.get("email",""))
                (session_dir / "browser_cookies.json").write_text(json.dumps({"cookies": cookies}, indent=2))
                print(f"✓ Saved web session: {session_dir} (use raw IP cookies for CLI)")
                return session_dir
    else:
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

async def register_cli_session_local_chrome(bd_cookies: list[dict], sessions_dir: Path) -> Path:
    """Cloud: local headless chrome on raw IP with BD cookies — no BD browser needed"""
    print("\n🔧 Registering CLI via local headless chrome (raw IP)...")
    tokens = await get_oauth_tokens_local_chrome(bd_cookies)
    print("✓ Got access and refresh tokens (local chrome)")
    user = get_web_user(bd_cookies)
    print(f"✓ User: {user.get('email')} (ID: {user.get('id')})")
    session_dir = next_session_dir(sessions_dir)
    write_cli_session(session_dir, tokens, user, bd_cookies)
    email = verify_tokens(tokens, user)
    print(f"✅ CLI verification: {email} authenticated")
    return session_dir


# ============================================================================
# MAIN EXECUTION
# ============================================================================
async def run(use_warp=False, cloud_mode=False):
    """Run single account creation — cloud uses Bright Data Browser API"""
    warp_started = False
    browser = None
    mailbox = None
    # cloud: force no warp, use BD WSS pool + fresh browser per run, ASN rotation
    headless = True
    if cloud_mode:
        use_warp = False
        import subprocess as _sp, uuid as _uuid
        from pathlib import Path as _Path
        try: _sp.run(["pkill", "-9", "chrome", "chromium", "firefox"], capture_output=True, timeout=5)
        except: pass
        # ponytail: rotate ASN per run via pool file + API lock (so parallel cells don't clash)
        # if BRD_WSS was passed via env for 1:1, use only that one (don't rotate)
        global BRD_WSS
        passed_wss = os.environ.get("BRD_WSS")
        if passed_wss and passed_wss in BRD_WSS_POOL:
            # 1:1 mode - use only the passed one
            BRD_WSS_POOL = [passed_wss]
        elif passed_wss:
            BRD_WSS_POOL = [passed_wss] + [w for w in BRD_WSS_POOL if w != passed_wss]
        pool_file = _Path("/tmp/bd_pool_index")
        lock_dir = _Path("/tmp/bd_api_locks")
        lock_dir.mkdir(exist_ok=True)
        try:
            idx = int(pool_file.read_text().strip() or 0)
        except:
            idx = 0
        # find free API (not locked) - try pool in order from idx
        orig_idx = idx
        found_lock = None
        for try_i in range(len(BRD_WSS_POOL)):
            cand_idx = (orig_idx + try_i) % len(BRD_WSS_POOL)
            wss_cand = BRD_WSS_POOL[cand_idx]
            # extract customer hl_xxxx
            import re as _re
            m = _re.search(r'hl_[0-9a-f]+', wss_cand)
            cust = m.group(0) if m else f"idx{cand_idx}"
            lock_file = lock_dir / f"{cust}.lock"
            # stale lock >10min is considered free
            is_locked = False
            if lock_file.exists():
                try:
                    age = __import__('time').time() - lock_file.stat().st_mtime
                    if age < 600:
                        is_locked = True
                    else:
                        lock_file.unlink()
                except: pass
            if not is_locked:
                idx = cand_idx
                found_lock = lock_file
                try: lock_file.write_text(str(__import__('os').getpid()))
                except: pass
                break
        if found_lock is None:
            # wait 1min and check again till free, also check credit drain
            while found_lock is None:
                print(f"⚠️  All {len(BRD_WSS_POOL)} BD APIs locked, waiting 60s...")
                __import__('time').sleep(60)
                # try again
                for try_i in range(len(BRD_WSS_POOL)):
                    cand_idx = (orig_idx + try_i) % len(BRD_WSS_POOL)
                    wss_cand = BRD_WSS_POOL[cand_idx]
                    import re as _re2
                    m = _re2.search(r'hl_[0-9a-f]+', wss_cand)
                    cust = m.group(0) if m else f"idx{cand_idx}"
                    lock_file = lock_dir / f"{cust}.lock"
                    is_locked = False
                    if lock_file.exists():
                        try:
                            age = __import__('time').time() - lock_file.stat().st_mtime
                            if age < 600:
                                is_locked = True
                            else:
                                lock_file.unlink()
                        except: pass
                    if not is_locked:
                        idx = cand_idx
                        found_lock = lock_file
                        try: lock_file.write_text(str(__import__('os').getpid()))
                        except: pass
                        print(f"✅ Found free BD API {cust} after wait")
                        break
                # credit drain check: if all APIs cost near 0, stop
                # (handled in main loop, here just continue waiting)
        pool_pick = BRD_WSS_POOL[idx % len(BRD_WSS_POOL)]
        pool_file.write_text(str((idx + 1) % len(BRD_WSS_POOL)))
        base_wss = pool_pick.split("?")[0]
        BRD_WSS = base_wss + f"?sessionId={_uuid.uuid4()}"
        print("☁️  Cloud mode: BD Browser API (ASN rotation), no local WARP")
        print(f"☁️  Fresh BD session: {BRD_WSS[:55]}*** (pool {idx % len(BRD_WSS_POOL) + 1}/{len(BRD_WSS_POOL)} ASN rotation)")
    
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
        async with async_playwright() as p:
            if cloud_mode:
                # ponytail: cloud = BD remote browser, 1 domain per session (free tier limit)
                print(f"☁️  Connecting to BD Browser API: {BRD_WSS[:45]}***")
                browser = await p.chromium.connect_over_cdp(BRD_WSS)
                # BD gives a pre-made context; use it if exists
                if browser.contexts:
                    context = browser.contexts[0]
                    print(f"☁️  Using BD browser context ({len(browser.contexts)} ctx)")
                else:
                    context = await browser.new_context(viewport={"width": 1280, "height": 800})
                # no WARP route in cloud
                use_warp = False
            else:
                # WARP route interception: browser goes direct, page.route does WARP via httpx (fixes gVisor SOCKS hang)
                picked = _pick_proxy() if use_warp else None
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
            
            # Create mailbox — cloud uses mail.tm API to avoid 2-domain limit (free tier)
            target_domain = globals().get("CLI_TARGET_DOMAIN")
            recovery_email = globals().get("CLI_RECOVERY_EMAIL")
            _handler_desc = recovery_email or target_domain or "random pool"
            print(f"📧 22.do handler: {_handler_desc} (pool {len(HANDLERS)} handlers)")
            mailbox = None
            if cloud_mode:
                # ponytail: Gmail first — dispose.lol Gmail (separate BD) per user, then 22.do, then mail.tm
                print("☁️  Cloud mailbox fallback: dispose Gmail -> 22.do -> mail.tm")
                tried = False
                # 1. dispose.lol Gmail via separate BD (keep open)
                try:
                    print("☁️  Trying dispose.lol Gmail (separate BD, keep open)...")
                    from playwright.async_api import async_playwright as _p
                    import uuid as _uuid2
                    dispose_wss = BRD_WSS.split("?")[0] + f"?sessionId={_uuid2.uuid4()}"
                    p2 = await _p().start()
                    b_dispose = await p2.chromium.connect_over_cdp(dispose_wss)
                    ctx_dispose = b_dispose.contexts[0] if b_dispose.contexts else await b_dispose.new_context()
                    pg = await ctx_dispose.new_page()
                    await pg.goto("https://dispose.lol", wait_until="load", timeout=60000)
                    await pg.wait_for_timeout(5000)
                    email_text = await pg.evaluate('''() => {
                        const w=document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null); let n;
                        while(n=w.nextNode()){ const t=n.textContent.trim(); if(t.includes('@gmail.com') && t.length<100) return t; }
                        return null;
                    }''')
                    if email_text and '@gmail.com' in email_text:
                        mailbox = DisposeLolInbox(context=context)
                        mailbox.page = pg
                        mailbox._dispose_browser = b_dispose
                        mailbox._dispose_context = ctx_dispose
                        mailbox._dispose_playwright = p2
                        mailbox.address = email_text.strip()
                        print(f"✅ Mailbox ready: {mailbox.address} (via dispose.lol separate BD, keep for polling)")
                        tried = True
                    else:
                        await b_dispose.close()
                        await p2.stop()
                        raise Exception("dispose Gmail not found")
                except Exception as e:
                    print(f"⚠️  dispose.lol failed ({e}), trying 22.do...")
                if not tried:
                    for dom in ["@gmail.com", "@outlook.com", "@hotmail.com", "@linshiyou.com", "@colabeta.com", "@youxiang.dev"]:
                        try:
                            print(f"☁️  Trying 22.do {dom} (separate BD)...")
                            from playwright.async_api import async_playwright as _p2
                            import uuid as _uuid3
                            wss_22 = BRD_WSS.split("?")[0] + f"?sessionId={_uuid3.uuid4()}"
                            p22 = await _p2().start()
                            b22 = await p22.chromium.connect_over_cdp(wss_22)
                            ctx22 = b22.contexts[0] if b22.contexts else await b22.new_context()
                            tmp_mb = TwoTwoDoInbox(context=ctx22, target_domain=dom)
                            await tmp_mb.create()
                            mailbox = tmp_mb
                            mailbox._22_browser = b22
                            mailbox._22_playwright = p22
                            mailbox._22_context = ctx22
                            print(f"✅ Mailbox ready: {mailbox.address} (via 22.do {dom} separate BD)")
                            tried = True
                            break
                        except Exception as ex:
                            print(f"  22.do {dom} failed: {str(ex)[:80]}")
                            try:
                                await b22.close()
                                await p22.stop()
                            except: pass
                            continue
                if not tried:
                    print("☁️  Cloud mailbox: mail.tm API (fallback)")
                    mailbox = MailTmInbox(context=context, target_domain=target_domain, recovery_email=recovery_email)
                    await mailbox.create()
            else:
                for _crash_attempt in range(3):
                    try:
                        mailbox = TwoTwoDoInbox(context=context, target_domain=target_domain, recovery_email=recovery_email)
                        mailbox.railway_page = page
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
            
            # Sign in to Railway — breaker: whatever err, restart till 8 tries
            tried_mails = []
            for attempt in range(8):
                try:
                    await sign_in_to_railway(page, mailbox)
                    break
                except Exception as e:
                    msg = str(e)
                    # auto-detect suspended/credit done -> mark API as drained and try next
                    if "customer_suspended" in msg or "403" in msg or "Auth Failed" in msg:
                        print(f"🛑 BD API {pool_pick[:30]}*** suspended/drained, marking done and trying next")
                        # mark lock as drained (write drained file)
                        try:
                            drain_file = lock_dir / f"{cust}.drained"
                            drain_file.write_text("suspended")
                            if found_lock and found_lock.exists():
                                found_lock.unlink()
                        except: pass
                        # try next API immediately
                        is_breaker = True
                        is_domlimit = False
                        # force next iteration to pick next free API
                        # continue will go to next attempt with new API
                    else:
                        # whatever err, restart till 8 tries
                        is_breaker = True
                        # keep specific checks for logging, but all errs are breaker
                        is_domlimit = ("navigate_domains_limit" in msg or "domain limit" in msg)
                    if is_domlimit:
                        print(f"⚠️  BD domain-limit hit — cooling down 120s, then fresh session")
                        import asyncio as _as
                        await _as.sleep(120)
                        msg = msg.replace("\n", " ")[:60]
                        # fall through to breaker with fresh IP
                        is_breaker = True
                    if is_breaker and attempt < 7:
                        print(f"⚠️  Breaker {attempt+1}/3: {msg[:80]} — fresh IP + next mailbox")
                        # fresh IP
                        import uuid as _uuid4
                        from pathlib import Path as _Path2
                        pool_file = _Path2("/tmp/bd_pool_index")
                        try: idx = int(pool_file.read_text().strip() or 0)
                        except: idx = 0
                        pool_pick = BRD_WSS_POOL[idx % len(BRD_WSS_POOL)]
                        pool_file.write_text(str((idx + 1) % len(BRD_WSS_POOL)))
                        # update WSS for next try (new ASN + sessionId)
                        import os as _os2
                        new_wss = pool_pick.split("?")[0] + f"?sessionId={_uuid4.uuid4()}"
                        _os2.environ["BRD_WSS"] = new_wss
                        print(f"🔄 New BD session {pool_pick[:45]}*** -> {new_wss[:50]}***")
                        tried_mails.append(mailbox.address if mailbox else "unknown")
                        # kill old BD browsers before new one (ensure fresh IP)
                        import subprocess as _sp2
                        try: _sp2.run(["pkill", "-9", "chrome", "chromium", "firefox"], capture_output=True, timeout=5)
                        except: pass
                        try: await page.close()
                        except: pass
                        try: await context.close()
                        except: pass
                        try: await browser.close()
                        except: pass
                        # new BD browser/context/page with new WSS
                        if cloud_mode:
                            from playwright.async_api import async_playwright as _p3
                            p3 = await _p3().start()
                            browser = await p3.chromium.connect_over_cdp(new_wss)
                            context = browser.contexts[0] if browser.contexts else await browser.new_context()
                            page = await context.new_page()
                        # next mailbox: 5x dispose -> mail.tm -> repeat till 8
                        is_dispose = (attempt % 6) < 5
                        if is_dispose:
                            try:
                                print(f"🔄 Trying dispose Gmail (breaker {attempt+1}/8, dispose {(attempt%6)+1}/5)...")
                                from playwright.async_api import async_playwright as _p4
                                import uuid as _uuid4b
                                disp_wss = new_wss.split("?")[0] + f"?sessionId={_uuid4b.uuid4()}"
                                p4 = await _p4().start()
                                b4 = await p4.chromium.connect_over_cdp(disp_wss)
                                ctx4 = b4.contexts[0] if b4.contexts else await b4.new_context()
                                pg4 = await ctx4.new_page()
                                await pg4.goto("https://dispose.lol", wait_until="load", timeout=60000)
                                await pg4.wait_for_timeout(5000)
                                email_text = await pg4.evaluate('''() => {
                                    const w=document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null); let n;
                                    while(n=w.nextNode()){ const t=n.textContent.trim(); if(t.includes('@gmail.com') && t.length<100) return t; }
                                    return null;
                                }''')
                                if email_text and '@gmail.com' in email_text:
                                    mailbox = DisposeLolInbox(context=context)
                                    mailbox.page = pg4
                                    mailbox._dispose_browser = b4
                                    mailbox._dispose_context = ctx4
                                    mailbox._dispose_playwright = p4
                                    mailbox.address = email_text.strip()
                                    print(f"🔄 Dispose Gmail -> {mailbox.address}")
                                else:
                                    await b4.close()
                                    await p4.stop()
                                    raise Exception("dispose not found")
                            except Exception as e2:
                                print(f"  dispose failed {str(e2)[:60]}, trying mail.tm")
                                mailbox = MailTmInbox(context=context)
                                await mailbox.create()
                                print(f"🔄 Fallback mail.tm -> {mailbox.address}")
                        else:
                            print(f"🔄 Trying mail.tm (breaker {attempt+1}/8, loop {(attempt//6)+1})...")
                            mailbox = MailTmInbox(context=context)
                            await mailbox.create()
                            print(f"🔄 mail.tm -> {mailbox.address}")
                        continue
                    else:
                        print(f"❌ All 8 attempts failed, killing script and releasing lock")
                        raise
            
            # PERSIST cookies right after login, BEFORE policies (tab may close during policies)
            try:
                _early = await context.cookies()
                Path("/tmp/railway_pending_cookies.json").write_text(json.dumps({"cookies": _early}, indent=2))
                print(f"💾 Persisted pending cookies (pre-policy) → /tmp/railway_pending_cookies.json")
            except Exception as _pe:
                print(f"  pre-policy persist failed: {_pe}")

            # Accept policies
            await accept_railway_policies(page)
            
            # Register CLI session — cloud must use local headless chrome (BD brul blocks backboard)
            try:
                if cloud_mode:
                    # keep BD cookies for local chrome, close BD browser before local chrome to avoid 2 concurrent
                    try:
                        bd_cookies = await context.cookies()
                    except Exception:
                        # context closed during policies - load from early persist
                        print(f"⚠️  context closed, loading pending cookies")
                        bd_cookies = json.loads(Path("/tmp/railway_pending_cookies.json").read_text())["cookies"]
                    # PERSIST cookies again so a crash/kill never loses them → --cli can resume
                    try:
                        _pend = Path("/tmp/railway_pending_cookies.json")
                        _pend.write_text(json.dumps({"cookies": bd_cookies}, indent=2))
                        print(f"💾 Persisted pending cookies → {_pend}")
                    except Exception as _pe:
                        print(f"  pending cookies save failed: {_pe}")
                    # close BD browser now, local chrome will run on raw IP
                    try: await browser.close()
                    except: pass
                    # release BD API lock BEFORE local PKCE (raw IP doesn't need BD)
                    try:
                        if 'found_lock' in locals() and found_lock is not None and found_lock.exists():
                            found_lock.unlink()
                            print(f"🔓 Released BD API lock {found_lock.name} before PKCE")
                            found_lock = None
                    except: pass
                    # rclone/mega check - auto-install if missing and verify config
                    try:
                        import shutil as _sh
                        if not _sh.which("rclone"):
                            print("📥 rclone missing, installing for Mega check...")
                            _sp = __import__('subprocess')
                            _sp.run(["apt", "update", "-q"], capture_output=True, timeout=60)
                            _sp.run(["apt", "install", "-y", "unzip"], capture_output=True, timeout=60)
                            _sp.run(["bash", "-c", "curl https://rclone.org/install.sh | bash"], capture_output=True, timeout=60)
                        # verify mega config (use ORIG_HOME)
                        _sp2 = __import__('subprocess')
                        env_m = os.environ.copy()
                        env_m["HOME"] = ORIG_HOME
                        env_m["LD_PRELOAD"] = ""
                        rm = _sp2.run(["rclone", "lsd", "mega:railway_sessions", "--mega-use-https"], env=env_m, capture_output=True, text=True, timeout=15)
                        if rm.returncode != 0:
                            print(f"⚠️  Mega not configured: {rm.stderr.strip()[:200]}")
                        else:
                            print(f"☁️  Mega OK: {len(rm.stdout.splitlines())} sessions")
                    except: pass
                    # retry CLI until success (keep working)
                    session_dir = None
                    for cli_try in range(5):
                        try:
                            session_dir = await register_cli_session_local_chrome(bd_cookies, SESSIONS_DIR)
                            break
                        except Exception as ce:
                            print(f"⚠️  CLI try {cli_try+1}/5 failed: {str(ce)[:200]}")
                            if cli_try < 4:
                                print(f"  retrying CLI in 5s...")
                                await asyncio.sleep(5)
                            else:
                                raise
                else:
                    session_dir = await register_cli_session(context, page, SESSIONS_DIR, cloud_mode=cloud_mode)
                
                # Sync to Mega
                sync_to_mega(session_dir)
                
                print(f"\n{'='*60}")
                print(f"✅ SUCCESS! Account created: {mailbox.address}")
                print(f"📁 Session: {session_dir}")
                print(f"{'='*60}\n")
                # ponytail: cloud — verify via raw IP isolated HOME (not RAILWAY_CONFIG_DIR)
                if cloud_mode:
                    try:
                        env = os.environ.copy()
                        env["HOME"] = str(session_dir)
                        env["LD_PRELOAD"] = ""
                        # raw IP verify (no BD proxy, uses sandbox egress)
                        r = subprocess.run(["railway", "whoami"], env=env, capture_output=True, text=True, timeout=15)
                        print(f"🔧 CLI whoami (raw IP, HOME={session_dir}): {r.stdout.strip() or r.stderr.strip()}")
                        r2 = subprocess.run(["railway", "status"], env=env, capture_output=True, text=True, timeout=15)
                        print(f"🔧 CLI status: {r2.stdout.strip()[:400] or r2.stderr.strip()[:400]}")
                        # sandbox ban check - init project then create sandbox then destroy
                        try:
                            print(f"🧪 Testing sandbox (ban check)...")
                            import uuid as _su
                            pname = f"holy-{_su.uuid4().hex[:6]}"
                            r_init = subprocess.run(["railway", "init", "--name", pname, "--json"], env=env, capture_output=True, text=True, timeout=30)
                            print(f"🧪 init {pname}: {r_init.stdout.strip()[:300] or r_init.stderr.strip()[:300]}")
                            if r_init.returncode == 0:
                                r4 = subprocess.run(["railway", "sandbox", "create"], env=env, capture_output=True, text=True, timeout=60)
                                out4 = (r4.stdout + r4.stderr).strip()[:600]
                                print(f"🧪 sandbox create: {out4}")
                                if "banned" in out4.lower() or "suspended" in out4.lower():
                                    print(f"⚠️  Possible ban/limit detected")
                                else:
                                    try:
                                        subprocess.run(["railway", "sandbox", "destroy", "--yes"], env=env, capture_output=True, text=True, timeout=30)
                                        print(f"🧹 sandbox destroyed (test ok)")
                                    except: pass
                                # cleanup project
                                try:
                                    subprocess.run(["railway", "project", "delete", "--yes"], env=env, capture_output=True, text=True, timeout=30)
                                except: pass
                            else:
                                print(f"⚠️  init failed - possible ban: {r_init.stderr.strip()[:300]}")
                        except Exception as e3:
                            print(f"⚠️  sandbox test skipped: {e3}")
                        # also push to mega via raw IP (use ORIG_HOME for rclone config)
                        env2 = os.environ.copy()
                        env2["HOME"] = ORIG_HOME
                        env2["LD_PRELOAD"] = ""
                        env2["LD_LIBRARY_PATH"] = ""
                        subprocess.run(["rclone", "copy", str(session_dir), f"mega:railway_sessions/{session_dir.name}", "--mega-use-https", "-v"], env=env2, capture_output=True, timeout=60)
                        print(f"☁️  Pushed {session_dir.name} to mega:railway_sessions via raw IP")
                        # cancer cells: persistent - reuse project from ban check to avoid 1 per 30s limit
                        if 'CLI_CELLS' in globals() and CLI_CELLS > 0:
                            for ci in range(CLI_CELLS):
                                try:
                                    print(f"🧬 Spawning persistent cancer cell {ci+1}/{CLI_CELLS}...")
                                    # wait for project rate limit (1 per 30s) - ban check just created one
                                    await asyncio.sleep(35)
                                    # create persistent service in new acc
                                    import tempfile, pathlib as _pl
                                    tmpd = tempfile.mkdtemp()
                                    df = _pl.Path(tmpd) / "Dockerfile"
                                    wss_val = BRD_WSS if 'BRD_WSS' in globals() else os.environ.get("BRD_WSS","")
                                    depth_arg = f" --depth {CLI_DEPTH-1}" if 'CLI_DEPTH' in globals() and CLI_DEPTH > 0 else ""
                                    df.write_text(f'''FROM ubuntu:22.04
RUN apt update && apt install -y python3 python3-pip git curl unzip
RUN pip install playwright || pip install playwright --break-system-packages
RUN playwright install --with-deps chromium
RUN curl https://rclone.org/install.sh | bash
RUN curl -fsSL https://railway.app/install.sh | sh
RUN mkdir -p /root/.config/rclone && printf "[mega]\\ntype = mega\\nuser = emilypeterson30@mail.findmeghana.org\\npass = AIjpeMEdPQWNTQHR6YYDYjcEoGFSOGHASO5DjwkHcXUW7iDLFg\\nsession_id = YHpE8zZFzThFIYjGGm44xFcyUGl1YWtCWlE4_HnRwxFodO1IlI4aFoyFUg\\nmaster_key = s6SFGB0f4UZk7VYPwK/k3A==\\n" > /root/.config/rclone/rclone.conf
WORKDIR /app
RUN git clone https://github.com/crucifix-cray/automation-toolkit.git /app/toolkit
CMD bash -c "LD_PRELOAD='' BRD_WSS='{wss_val}' python3 -u /app/toolkit/railway-docker/railway-HOLY-cloud.py --cloud --cells {CLI_CELLS}{depth_arg}"
''')
                                    # deploy as new service via railway up (reuse project) - fully backgrounded
                                    try:
                                        subprocess.Popen(["railway", "up", "--service", f"cancer-{ci}", "-y", "--detach"], cwd=tmpd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                        print(f"  🧬 Persistent cell {ci+1} deploy: backgrounded")
                                    except Exception as e:
                                        print(f"  🧬 Persistent cell {ci+1} deploy err: {e}")
                                    # parent cooloff 5s then rerun itself (don't block)
                                    print(f"  ❄️  Cooloff 5s then parent reruns...")
                                    await asyncio.sleep(5)
                                except Exception as ce:
                                    print(f"  cell spawn failed: {ce}")
                    except Exception as e:
                        print(f"⚠️  CLI verify failed: {e}")
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
        # Cleanup: release BD API lock so next cell finds it free
        try:
            if cloud_mode and 'found_lock' in locals() and found_lock is not None:
                try: found_lock.unlink()
                except: pass
                print(f"🔓 Released BD API lock {found_lock.name}")
        except: pass
        # push logs to mega logs folder (use ORIG_HOME)
        try:
            import subprocess as _sp3, os as _os3, glob as _glob
            env3 = _os3.environ.copy()
            env3["HOME"] = ORIG_HOME
            env3["LD_PRELOAD"] = ""
            env3["LD_LIBRARY_PATH"] = ""
            for pat in ["/tmp/run_*.log", "/tmp/railway-debug-*.txt", "/tmp/turnstile-*.png", "/tmp/railway_pending_cookies.json"]:
                for f in _glob.glob(pat):
                    try: _sp3.run(["rclone", "copy", f, "mega:railway_sessions/logs/", "--mega-use-https", "-v"], env=env3, capture_output=True, timeout=30)
                    except: pass
            print(f"📤 Pushed logs to mega:railway_sessions/logs/")
        except: pass
        # close BD browser if still open
        try:
            if browser:
                await browser.close()
        except: pass
        # Cleanup
        if mailbox:
            try:
                await mailbox.close()
            except:
                pass
        
        if warp_started:
            stop_warp()


async def cli_only_register(web_dir: str, sessions_dir: Path) -> int:
    """--cli PATH: load a web session's browser_cookies.json and register CLI PKCE only.

    No re-login — uses the saved raw-IP-bound cookies so Cloudflare clears them and
    the local headless chrome completes the consent + callback. Writes the next free
    session dir (after web_dir) and pushes to Mega.
    """
    import json as _json
    web_dir = web_dir.rstrip("/")
    src = Path(web_dir)
    cookies_path = src / "browser_cookies.json"
    if not cookies_path.exists():
        # maybe itself is the cookies file path
        cookies_path = src if src.suffix == ".json" else None
    if not cookies_path or not cookies_path.exists():
        print(f"❌ --cli: no browser_cookies.json found in {src}")
        return 1
    try:
        data = _json.loads(cookies_path.read_text())
    except Exception as e:
        print(f"❌ --cli: bad cookies json: {e}")
        return 1
    cookies = data.get("cookies", []) if isinstance(data, dict) else data
    if not cookies:
        print("❌ --cli: no cookies entries")
        return 1
    print(f"🔧 CLI-only: loaded {len(cookies)} cookies from {cookies_path}")
    session_dir = await register_cli_session_local_chrome(cookies, sessions_dir)
    sync_to_mega(session_dir)
    return 0


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Railway account creator — 22.do pool edition")
    parser.add_argument("--no-warp", action="store_true", help="Disable WARP proxy")
    parser.add_argument("--cloud", action="store_true", help="Use Bright Data Browser API (WSS) instead of local Chromium")
    parser.add_argument("--cloud-no-c", action="store_true", help="Cloud without cancer/sandbox spawn, just create acc + Mega loop")
    parser.add_argument("--domain", type=str, default=None, help="Enforce 22.do handler domain, e.g. @linshiyou.com, @gmail.com, @hotmail.com, @outlook.com (default: random) — @googlemail.com banned")
    parser.add_argument("--recov", type=str, default=None, help="Recover existing 22.do inbox, e.g. g92w@colabeta.com (skips creation, opens https://22.do/inbox/#/<mail>)")
    parser.add_argument("--cli", type=str, default=None, metavar="PATH", help="CLI-only: resume a web session dir (loads browser_cookies.json) and register Railway CLI PKCE only, no re-login. Writes next free session dir.")
    parser.add_argument("--cells", type=int, default=0, metavar="N", help="Cancer mode: after success, spawn N new sandboxes each running Holy --cloud --cells N (exponential)")
    parser.add_argument("--depth", type=int, default=0, metavar="D", help="Demo depth: stop after current Mega sessions + D (0=unlimited till 500)")
    args = parser.parse_args()

    # expose to run() via globals (used inside)
    CLI_TARGET_DOMAIN = args.domain
    CLI_RECOVERY_EMAIL = args.recov
    CLOUD_MODE = args.cloud or args.cloud_no_c or os.environ.get("BRD_WSS") is not None
    CLOUD_NO_C = args.cloud_no_c
    CLI_CELLS = 0 if args.cloud_no_c else args.cells
    CLI_DEPTH = args.depth

    if args.cli:
        print("="*60)
        print("🔧 CLI-ONLY MODE — register Railway CLI PKCE from saved cookies")
        print("="*60)
        code = asyncio.run(cli_only_register(args.cli, SESSIONS_DIR))
        sys.exit(code)

    use_warp = (not args.no_warp) and not CLOUD_MODE

    print("="*60)
    print("🏆 THE HOLY RAILWAY ACCOUNT CREATOR — 22.do Pool 🏆")
    if CLOUD_MODE:
        print("☁️  CLOUD MODE — Bright Data Browser API")
    print("="*60)
    print(f"📁 Sessions directory: {SESSIONS_DIR}")
    print(f"☁️  Mega remote: {MEGA_REMOTE}")
    print(f"🔁 WARP: {'ENABLED' if use_warp else 'DISABLED'}")
    if CLOUD_MODE:
        print(f"🌐 Cloud WSS: {BRD_WSS[:40]}***")
    print(f"📧 22.do handlers: {len(HANDLERS)} (random/pool)" + (f" — enforced: {args.domain or args.recov}" if (args.domain or args.recov) else ""))
    if args.recov:
        print(f"♻️  Recovery mode: {args.recov} → https://22.do/inbox/#/{args.recov}")
    print("="*60)

    if CLI_CELLS > 0:
        # demo depth: record initial Mega sessions
        init_sess = 0
        if CLI_DEPTH > 0:
            try:
                import subprocess as _sp0
                env0 = os.environ.copy()
                env0["LD_PRELOAD"] = ""
                r0 = _sp0.run(["rclone", "lsd", "mega:railway_sessions", "--mega-use-https"], env=env0, capture_output=True, text=True, timeout=30)
                init_sess = len([l for l in r0.stdout.splitlines() if "session-" in l])
                print(f"🧬 CANCER DEMO: start {init_sess} sessions, target +{CLI_DEPTH} => {init_sess+CLI_DEPTH}")
            except: pass
        print(f"🧬 CANCER MODE: {CLI_CELLS} cell(s) loop nonstop till credit limit")
        while True:
            # depth check
            if CLI_DEPTH > 0:
                try:
                    import subprocess as _spd
                    envd = os.environ.copy()
                    envd["LD_PRELOAD"] = ""
                    rd = _spd.run(["rclone", "lsd", "mega:railway_sessions", "--mega-use-https"], env=envd, capture_output=True, text=True, timeout=30)
                    cur = len([l for l in rd.stdout.splitlines() if "session-" in l])
                    if cur >= init_sess + CLI_DEPTH:
                        print(f"✅ Demo depth reached {cur} >= {init_sess+CLI_DEPTH}, stopping")
                        break
                except: pass
            try:
                asyncio.run(run(use_warp=use_warp, cloud_mode=CLOUD_MODE))
            except Exception as e:
                print(f"⚠️  Run error: {e}")
            # check credit drain: if all 11 APIs cost > $45 (near $50 limit), stop
            try:
                import subprocess as _spc, glob as _gl, json as _js
                drained = 0
                for acc in ["acc1","acc2","acc3","acc4","acc5","acc6","acc7","acc8","acc9","acc10","acc11"]:
                    try:
                        jf = f"/tmp/{acc}.json"
                        if not __import__('pathlib').Path(jf).exists():
                            continue
                        key = _js.load(open(jf))["api_key"]
                        out = _spc.run(["curl","-s","-H",f"Authorization: Bearer {key}","https://api.brightdata.com/zone/cost?zone=scraping_browser1"], capture_output=True, text=True, timeout=10)
                        d = _js.loads(out.stdout)
                        cust = list(d.keys())[0]
                        cost = d[cust].get("back_m0",{}).get("cost",0)
                        if cost > 45:
                            drained += 1
                    except: pass
                if drained >= len(BRD_WSS_POOL):
                    print(f"🛑 All {drained} BD APIs credit drained, stopping")
                    break
                for f in _gl.glob("/tmp/bd_api_locks/*.lock"):
                    try: _spc.run(["rm", "-f", f], timeout=5)
                    except: pass
                print(f"🔄 Loop again in 2s...")
                __import__('time').sleep(2)
            except: pass
    else:
        asyncio.run(run(use_warp=use_warp, cloud_mode=CLOUD_MODE))
