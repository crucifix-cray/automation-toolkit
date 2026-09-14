#!/usr/bin/env python3
"""Lovable automation with TRUE API-ONLY mode (no TempMail page).

This version uses ONLY the TempMailHub API - NO page scraping, NO TempMail tab.
Based on the working monitor_inbox.sh approach.

Features:
- ✅ TRUE API-ONLY (no TempMail page)
- ✅ Ad blocking (Lovable page only)
- ✅ WARP proxy support (optional)
- ✅ Gmail validation (no dots/+)
- ✅ Mailbox testing before use
- ✅ Email deduplication
- ✅ Password reset flow
- ✅ Session saving
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import os
import random
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add core path for InvisiblePlaywright
TOOLKIT_CORE = Path(__file__).parent
sys.path.insert(0, str(TOOLKIT_CORE))

from invisible_playwright.async_api import InvisiblePlaywright
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)
try:
    from playwright_captcha import ClickSolver, CaptchaType, FrameworkType
    CAPTCHA_SOLVER_AVAILABLE = True
except ImportError:
    CAPTCHA_SOLVER_AVAILABLE = False
try:
    from playwright_stealth import Stealth
    STEALTH_PKG_AVAILABLE = True
except ImportError:
    STEALTH_PKG_AVAILABLE = False


TEMPMAIL_API = "https://api.tempmailhub.org"
TEMP_TF_API = "https://temp.tf/api"
LOVABLE_URL = "https://lovable.dev/"
RESET_LINK_RE = re.compile(r"https?://[^\"'\\\s<>]*lovable\.dev[^\"'\\\s<>]*", re.I)
WARP_PROXY = "socks5://10.200.1.2:40001"
TOR_PROXY = "socks5://127.0.0.1:9050"
USED_EMAILS_FILE = os.environ.get(
    "USED_EMAILS_FILE", str(Path.home() / "Documents" / "used-tempmailhub-emails.txt")
)

AD_BLOCK_PATTERNS = (
    "doubleclick.net", "googlesyndication.com", "googleadservices.com",
    "google-analytics.com", "googletagmanager.com/gtag", "analytics.google.com",
    "adservice.google", "adroll.com", "outbrain.com", "taboola.com",
    "amazon-adsystem.com", "moatads.com", "scorecardresearch.com", "criteo.com",
    "teads.tv", "doubleverify.com", "yieldmo.com", "adnxs.com", "adsafeprotected.com",
    "adzerk.net", "pubmatic.com", "casalemedia.com", "openx.net", "rubiconproject.com",
)

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


class TempTfInbox:
    """temp.tf API — free Gmail dot/plus aliases, no browser needed"""
    def __init__(self, context=None):
        self.context = context
        self.address = None

    def _get(self, path, data=None):
        url = f"{TEMP_TF_API}{path}"
        if data:
            req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={"Content-Type": "application/json"}, method="POST")
        else:
            req = urllib.request.Request(url)
        # bypass any proxy — temp.tf blocks Tor exits
        old_env = {k: os.environ.pop(k, None) for k in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy", "ALL_PROXY", "all_proxy")}
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        finally:
            for k, v in old_env.items():
                if v is not None:
                    os.environ[k] = v

    async def create(self):
        print("\n📧 Creating temp.tf Gmail (dots only)...", file=sys.stderr)
        for attempt in range(10):
            try:
                acct = self._get("/account?dot=1&providers=gmail")
                self.address = acct["email"]
                # pre-check inbox
                self._get("/check", {"email": self.address})
                print(f"✅ Mailbox ready: {self.address} (via temp.tf)", file=sys.stderr)
                return self.address, None
            except urllib.error.HTTPError as e:
                if e.code == 500:
                    print(f"  ⚠️ {self.address} inbox not ready (500), retrying...", file=sys.stderr)
                    await asyncio.sleep(2)
                    continue
                raise
            except Exception as e:
                print(f"  ⚠️ temp.tf error: {e}", file=sys.stderr)
                await asyncio.sleep(2)
        raise FlowError("temp.tf email creation failed after 10 attempts")

    async def wait_for_lovable_link(self, timeout_seconds=300):
        if not self.address:
            raise Exception("No address set")
        print(f"\n📥 Waiting for Lovable link on temp.tf ({self.address})...", file=sys.stderr)
        import time as _time
        deadline = _time.time() + timeout_seconds
        check = 0
        while _time.time() < deadline:
            check += 1
            try:
                resp = self._get("/check", {"email": self.address})
                items = resp.get("data", [])
                if check % 5 == 1:
                    print(f"  Check #{check}: {len(items)} msg(s)", file=sys.stderr)
                for msg in items:
                    body = msg.get("body", "")
                    subject = msg.get("subject", "")
                    m = RESET_LINK_RE.search(subject + " " + body)
                    if m:
                        link = html.unescape(m.group(0)).replace("&amp;", "&")
                        print(f"  🎯 Link: {link[:160]}", file=sys.stderr)
                        return link
            except urllib.error.HTTPError as e:
                if e.code == 500:
                    print(f"  Check #{check}: inbox initializing (500)...", file=sys.stderr)
                elif e.code == 429:
                    print(f"  Check #{check}: rate limited, waiting 10s...", file=sys.stderr)
                    await asyncio.sleep(10)
            except Exception as e:
                print(f"  Check #{check}: error {str(e)[:60]}", file=sys.stderr)
            await asyncio.sleep(5)
        raise FlowError("Lovable link not received on temp.tf")


class TwoTwoDoInbox:
    """22.do Provider Pool — random handler per run"""
    def __init__(self, context, target_domain=None):
        self.context = context
        self.address = None
        self.target_domain = target_domain
        self.handler_used = None

    async def _pick_handler(self):
        if self.target_domain:
            for h in HANDLERS:
                if h[2].lower() == self.target_domain.lower():
                    return h
        chosen = random.choice(HANDLERS)
        print(f"🎲 Random handler: {chosen[0]}", file=sys.stderr)
        return chosen

    async def create(self):
        self.handler_used = await self._pick_handler()
        name, handler_url, handler_domain = self.handler_used
        print(f"\n📧 Creating 22.do mailbox via {name}...", file=sys.stderr)
        pg = await self.context.new_page()
        try:
            await pg.goto(handler_url, wait_until="domcontentloaded", timeout=60000)
            await pg.wait_for_timeout(3000)

            # close google vignette
            try:
                close = pg.locator('button:has-text("Close ad")').first
                if await close.count() and await close.is_visible():
                    await close.click(timeout=2000)
                    print("  × closed ad overlay", file=sys.stderr)
                    await pg.wait_for_timeout(1000)
            except: pass

            # For main-page domains: select domain from Choices.js dropdown
            if handler_domain not in ("@gmail.com", "@hotmail.com", "@outlook.com"):
                try:
                    await pg.wait_for_timeout(1000)
                    choices = pg.locator(".choices__inner")
                    if await choices.count():
                        await choices.click(timeout=5000)
                        await pg.wait_for_timeout(800)
                        # try multiple selector patterns
                        item = pg.locator(f".choices__item--choice:has-text('{handler_domain}')").first
                        if not await item.count():
                            item = pg.locator(f".choices__list--dropdown .choices__item:has-text('{handler_domain}')").first
                        if await item.count():
                            await item.click(timeout=5000)
                            print(f"  → selected domain {handler_domain}", file=sys.stderr)
                        else:
                            print(f"  ⚠️ domain {handler_domain} not found in dropdown", file=sys.stderr)
                        await pg.wait_for_timeout(800)
                except Exception as e:
                    print(f"  ⚠️ domain select {handler_domain}: {e}", file=sys.stderr)

            # Click Random
            await pg.locator("#mail-random").click(timeout=5000)
            await pg.wait_for_timeout(1000)
            local = await pg.locator("#mail-input").input_value(timeout=5000)

            # For fake-gmail: accept @gmail.com or @googlemail.com
            if handler_domain == "@gmail.com":
                for _ in range(3):
                    v = (await pg.locator("#mail-input").input_value()).strip()
                    if v.lower().endswith(("@gmail.com", "@googlemail.com")):
                        local = v
                        break
                    print(f"  got {v}, retrying Random…", file=sys.stderr)
                    await pg.locator("#mail-random").click(timeout=3000)
                    await pg.wait_for_timeout(800)
                email = (await pg.locator("#mail-input").input_value()).strip()
                if "@" not in email:
                    email = f"{local.strip()}{handler_domain}"
            else:
                try:
                    dom = await pg.locator(".choices__list--single .choices__item").first.inner_text(timeout=2000)
                    email = f"{local.strip()}{dom.strip()}"
                except:
                    email = f"{local.strip()}{handler_domain}"

            await pg.locator("#into-mailbox").click(timeout=5000)
            await pg.wait_for_timeout(4000)
            self.address = email.strip()
            print(f"✅ Mailbox ready: {self.address} (via {name})", file=sys.stderr)
            return self.address, None
        finally:
            await pg.close()

    async def wait_for_lovable_link(self, timeout_seconds=300):
        if not self.address:
            raise Exception("No address set")
        print(f"\n📥 Waiting for Lovable link on 22.do ({self.address})...", file=sys.stderr)
        import time as _time
        deadline = _time.time() + timeout_seconds
        check = 0
        pg = await self.context.new_page()
        await pg.goto(f"https://22.do/inbox/#/{self.address}", wait_until="domcontentloaded", timeout=60000)
        await pg.wait_for_timeout(3000)
        try:
            while _time.time() < deadline:
                check += 1
                await pg.reload(wait_until="domcontentloaded")
                await pg.wait_for_timeout(2000)
                # look for Lovable email in inbox
                rows = await pg.locator("#email-list-wrap .mail-item, #email-list-wrap tr, .inbox-item").all()
                if check % 5 == 1:
                    print(f"  Check #{check}: {len(rows)} message(s)", file=sys.stderr)
                for row in rows:
                    try:
                        txt = await row.inner_text()
                        if "lovable" in txt.lower() or "verification" in txt.lower() or "verify" in txt.lower():
                            print(f"  ✅ Found Lovable email: {txt[:80]}", file=sys.stderr)
                            await row.click(timeout=5000)
                            await pg.wait_for_timeout(3000)
                            # extract link from email body
                            body = await pg.evaluate("() => document.body.innerHTML")
                            m = RESET_LINK_RE.search(body or "")
                            if m:
                                link = html.unescape(m.group(0)).replace("&amp;", "&")
                                print(f"  🎯 Link: {link[:160]}", file=sys.stderr)
                                return link
                            # try frames
                            for frame in pg.frames:
                                try:
                                    fhtml = await frame.content()
                                    m2 = RESET_LINK_RE.search(fhtml or "")
                                    if m2:
                                        link = html.unescape(m2.group(0)).replace("&amp;", "&")
                                        print(f"  🎯 Link (frame): {link[:160]}", file=sys.stderr)
                                        return link
                                except: continue
                    except: continue
                await asyncio.sleep(3)
        finally:
            await pg.close()
        raise FlowError("Lovable link not received on 22.do")


class DisposeLolLovable:
    BASE_URL = "https://dispose.lol"
    def __init__(self, context=None):
        self.context = context
        self.page = None
        self.address = None
        self.session_initialized = False
    async def _ensure_page(self):
        if not self.context: raise Exception("No browser context")
        if not self.session_initialized:
            self.page = await self.context.new_page()
            await self.page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=60000)
            await self.page.wait_for_timeout(5000)
            self.session_initialized = True
    async def create(self):
        print("📧 Creating dispose.lol Gmail (separate tab)...", file=sys.stderr)
        await self._ensure_page()
        await self.page.wait_for_timeout(4000)
        email_text = await self.page.evaluate("""() => {
            const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT,null);
            let n; while(n=w.nextNode()){ const t=n.textContent.trim(); if(t.includes('@gmail.com')&&t.length<80) return t;}
            for(const i of document.querySelectorAll('input')) if(i.value.includes('@gmail.com')) return i.value;
            return null;}""")
        if email_text and '@gmail.com' in email_text:
            self.address = email_text.strip()
            print(f"✅ Mailbox ready: {self.address}", file=sys.stderr)
            return self.address, "dispose"
        await self.page.screenshot(path="/tmp/disposelol-error.png", full_page=True)
        raise FlowError("Could not find dispose.lol email")
    async def wait_for_lovable_link(self, timeout_seconds=300):
        print("📥 Waiting for Lovable link on dispose.lol...", file=sys.stderr)
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        check=0
        def _decode(raw: str) -> str:
            # Link lives inside an iframe srcdoc. Reading the FRAME content gives
            # single-level HTML; decode once, then catch any residual &amp;.
            link = html.unescape(raw or "")
            link = link.replace("&amp;", "&")
            return link

        while asyncio.get_running_loop().time() < deadline:
            check+=1
            await self.page.reload(wait_until="domcontentloaded")
            await self.page.wait_for_timeout(2000)
            buttons = await self.page.locator('button[aria-label^="View "]').all()
            if check%5==1: print(f"  Check #{check}: {len(buttons)} message(s)", file=sys.stderr)
            for btn in buttons:
                aria = await btn.get_attribute('aria-label') or ""
                if 'lovable' not in aria.lower(): continue
                print(f"  ✅ Found Lovable: {aria[:120]}", file=sys.stderr)
                try:
                    # 1) Click "View" to open the email iframe (srcdoc)
                    try: await btn.scroll_into_view_if_needed(timeout=2000)
                    except: pass
                    await btn.click(timeout=5000, force=True)
                    await self.page.wait_for_timeout(3000)

                    # 2) Search EVERY frame (main + iframes) for the link
                    frames = self.page.frames
                    for frame in frames:
                        try:
                            fhtml = await frame.content()
                        except Exception:
                            continue
                        m = RESET_LINK_RE.search(fhtml or "")
                        if m:
                            link = _decode(m.group(0))
                            print(f"  🎯 Link (frame): {link[:160]}", file=sys.stderr)
                            return link
                        # also try innerText of the frame
                        try:
                            ftext = await frame.inner_text("html")
                        except Exception:
                            ftext = ""
                        m2 = RESET_LINK_RE.search(ftext or "")
                        if m2:
                            link = _decode(m2.group(0))
                            print(f"  🎯 Link (frame text): {link[:160]}", file=sys.stderr)
                            return link

                    # 3) Fallback: main-page innerHTML / innerText (triple-escaped)
                    body = await self.page.evaluate("""() => document.body.innerHTML.slice(0, 60000)""")
                    m = RESET_LINK_RE.search(body)
                    if m:
                        link = _decode(html.unescape(m.group(0)))
                        print(f"  🎯 Link (main html): {link[:160]}", file=sys.stderr)
                        return link
                    txt = await self.page.evaluate("""() => document.body.innerText.slice(0, 20000)""")
                    m2 = RESET_LINK_RE.search(txt)
                    if m2:
                        link = _decode(m2.group(0))
                        print(f"  🎯 Link (main text): {link[:160]}", file=sys.stderr)
                        return link
                except Exception as e:
                    print(f"  click/extract failed: {e}", file=sys.stderr)
                    continue
            await asyncio.sleep(3)
        raise FlowError("Lovable link not received")
    async def close(self):
        if self.page:
            try: await self.page.close()
            except: pass


class FlowError(RuntimeError):
    """Raised when a site does not reach the expected state."""


def proxy_settings(for_api: bool = False) -> dict | None:
    """Check proxies in order - enhanced for isolation.
    Browser: 40000 (warp=on fastest 0.5s) → 9050 (tor 3/3 valid) → chain 9051-9054 → direct
    API: 9050 (tor 3/3 valid) → 40000 (warp) → chain → direct (direct gives 3/3 but shares IP, so proxy preferred for GH 429)
    Excludes 9251 (IPv6 PySocks error) and handles socks5/socks4 fallback."""
    import socket

    if os.environ.get("FORCE_NO_PROXY") == "1":
        print("🌐 --raw flag: forcing direct connection (no proxy)", file=sys.stderr)
        return None

    candidates = []
    forced = os.environ.get("PROXY_PORT") or os.environ.get("LOV_PROXY_PORT")
    if forced:
        try:
            candidates.append(int(forced))
        except: pass
    else:
        if for_api:
            # ponytail: tempmailhub direct works; no Tor (prohibited) — keep direct
            candidates = []
        else:
            # ponytail: warp 40002 (warp-cli proxy mode) → 40000 (old wireproxy) → direct
            candidates = [40002, 40000]

    for port in candidates:
        try:
            host, pport = "127.0.0.1", port
            with socket.create_connection((host, pport), timeout=2):
                server = f"socks5://{host}:{pport}"
                # extra check: warp port 40000 alive test via socks5 already passed, but verify socks4 fallback later in api_request if needed
                print(f"✅ Using proxy 127.0.0.1:{port} ({'API' if for_api else 'browser'})", file=sys.stderr)
                return {
                    "server": server,
                    "bypass": "127.0.0.1,localhost,api.lovable.dev,api.tempmailhub.org",
                    "port": port,
                }
        except OSError:
            continue

    if for_api:
        # API can work direct (3/3 valid) but loses unique IP - warn but allow
        print("⚠️  No API proxy found; using direct (may 429 on parallel runs)", file=sys.stderr)
    else:
        print("⚠️  No browser proxy found; using direct (warp=off)", file=sys.stderr)
    return None


def load_used_emails() -> set:
    """Load already-used emails - handles permission/path errors."""
    for path in [USED_EMAILS_FILE, str(Path.home() / "Documents" / "used-tempmailhub-emails.txt"), "/tmp/used-tempmailhub-emails.txt"]:
        try:
            with open(path, "r") as f:
                return set(line.strip().lower() for line in f if line.strip())
        except FileNotFoundError:
            return set()
        except (PermissionError, OSError) as e:
            print(f"⚠️  Cannot read used-emails from {path}: {e} - trying fallback", file=sys.stderr)
            continue
    return set()


def save_used_email(email: str) -> None:
    """Save email to used list - never crashes on permission/path errors."""
    global USED_EMAILS_FILE
    for path in [USED_EMAILS_FILE, str(Path.home() / "Documents" / "used-tempmailhub-emails.txt"), "/tmp/used-tempmailhub-emails.txt"]:
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "a") as f:
                f.write(f"{email.lower()}\n")
            if path != USED_EMAILS_FILE:
                print(f"⚠️  USED_EMAILS_FILE fallback used: {path}", file=sys.stderr)
                USED_EMAILS_FILE = path
            print(f"💾 Saved {email} to used list", file=sys.stderr)
            return
        except PermissionError as e:
            print(f"⚠️  Cannot write used-emails to {path}: {e} - trying fallback", file=sys.stderr)
            continue
        except Exception as e:
            print(f"⚠️  save_used_email fallback {path}: {e}", file=sys.stderr)
            continue
    print(f"⚠️  Failed to save used email {email} - continuing (non-fatal)", file=sys.stderr)


def is_valid_gmail(email: str) -> bool:
    """Validate Gmail: must be @gmail.com with NO dots or + before @"""
    if not email or '@gmail.com' not in email.lower():
        return False
    local_part = email.split('@')[0]
    if '.' in local_part or '+' in local_part:
        return False
    return True


def api_request(endpoint: str, method: str = "POST", data: dict = None, timeout: int = 15) -> tuple[int, str]:
    """Make API request to TempMailHub - robust socks5/socks4 + direct fallback, isolated."""
    url = f"{TEMPMAIL_API}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "Origin": "https://tempmailhub.org"
    }
    
    # API candidate list comes straight from proxy_settings(for_api=True).
    # TempmailHub's API host is IPv6-only and ONLY reachable via Tor; do NOT inject
    # the WARP (40000) or direct fallbacks here or we burn ~40s/attempt on dead paths.
    candidates = []
    primary = proxy_settings(for_api=True)
    if primary:
        candidates.append(primary)
        # add a second Tor port as backup if available (9251), else direct as last resort
        if primary.get("port") == 9050:
            import socket as _sock
            try:
                with _sock.create_connection(("127.0.0.1", 9251), timeout=1):
                    candidates.append({"server": "socks5://127.0.0.1:9251", "port": 9251, "bypass": "127.0.0.1,localhost,api.lovable.dev,api.tempmailhub.org"})
            except: pass
        candidates.append(None)
    else:
        candidates = [None]

    last_error = None
    for proxy in candidates:
        _ORIGINAL_SOCKET = None
        proxy_desc = proxy["server"] if proxy else "direct"
        try:
            if proxy:
                import socks, socket as _socket
                proxy_port = int(proxy["server"].split(":")[-1])
                # Tor exits (9050/9251) resolve DNS remotely (rdns) because TempmailHub
                # API host is IPv6-only and unreachable via the WARP chain.
                # WARP (40000) routes through the netns which handles its own DNS.
                rdns = proxy_port in (9050, 9251)
                socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", proxy_port, rdns=rdns)
                _ORIGINAL_SOCKET = _socket.socket
                _socket.socket = socks.socksocket
                print(f"  🌐 API via {proxy_desc} (rdns={rdns}, isolated)", file=sys.stderr)

            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for attempt in range(2):
                try:
                    req = urllib.request.Request(url, headers=headers, method=method)
                    if method == "POST":
                        req.data = json.dumps(data).encode('utf-8') if data else b'{}'
                    with opener.open(req, timeout=timeout) as response:
                        return response.status, response.read().decode()
                except urllib.error.HTTPError as e:
                    return e.code, e.read().decode(errors="replace")
                except (urllib.error.URLError, TimeoutError, OSError) as error:
                    err_str = str(error)
                    # socks4 fallback for warp IPv6 case
                    if "IPv6" in err_str and proxy and proxy.get("port")==40000 and attempt==0:
                        try:
                            import socks
                            socks.set_default_proxy(socks.SOCKS4, "127.0.0.1", proxy_port)
                            print(f"  ↻ retry socks4 for warp {proxy_port}", file=sys.stderr)
                            continue
                        except: pass
                    last_error = error
                    print(f"  ⚠️  API timeout/error via {proxy_desc} (attempt {attempt + 1}/2): {error}", file=sys.stderr)
                    if attempt < 1:
                        import time, random
                        time.sleep(1 + random.random())
                    else:
                        break
            # if we got here, this proxy failed - try next candidate
            if proxy and "IPv6" in str(last_error):
                print(f"  ⚠️  {proxy_desc} IPv6 fail, trying next", file=sys.stderr)
                continue
            if last_error and proxy is not None:
                continue
            break
        finally:
            if _ORIGINAL_SOCKET is not None:
                import socket as _socket
                _socket.socket = _ORIGINAL_SOCKET
                try:
                    import socks
                    socks.set_default_proxy()
                except: pass

    return 0, f"API failed: {last_error}"


def lovable_email_available(email: str) -> bool:
    """Fast pre-check: does this email already have a Lovable account?
    On any error, be optimistic - let the browser flow decide."""
    import json as _json
    import urllib.request as _urllib

    req = _urllib.Request(
        "https://api.lovable.dev/auth/check-auth-provider",
        data=_json.dumps({"email": email}).encode(),
        headers={
            "Content-Type": "application/json",
            "Origin": "https://lovable.dev",
            "Referer": "https://lovable.dev/",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        },
        method="POST",
    )
    try:
        with _urllib.request.urlopen(req, timeout=15) as response:
            data = _json.loads(response.read().decode())
            return not data.get("user_exists", True)
    except Exception:
        return True


def create_working_email() -> tuple[str, str]:
    """Create valid Gmail via API with mailbox validation (like monitor script)."""
    import time
    
    used_emails = load_used_emails()
    print(f"📋 Loaded {len(used_emails)} used emails", file=sys.stderr)
    
    max_attempts = 30
    for attempt in range(1, max_attempts + 1):
        print(f"🔄 Attempt {attempt}/{max_attempts}: Creating email via API...", file=sys.stderr)
        
        # Create email via API - REQUEST GMAIL EXPLICITLY
        status, raw = api_request("/emails", data={"domain": "gmail.com"})
        if status != 201:
            print(f"  ❌ Failed to create (status {status})", file=sys.stderr)
            time.sleep(2)
            continue
        
        try:
            account = json.loads(raw)
            email = account["email"]
            email_id = str(account["email_id"])
        except (KeyError, ValueError) as exc:
            print(f"  ❌ Malformed response", file=sys.stderr)
            time.sleep(2)
            continue
        
        print(f"  📧 Created: {email} (ID: {email_id})", file=sys.stderr)
        
        # Skip already-used emails
        if email.lower() in used_emails:
            print(f"  ⚠️  Already used - skipping", file=sys.stderr)
            time.sleep(1)
            continue
        
        # Validate Gmail format
        if not is_valid_gmail(email):
            print(f"  ❌ Invalid Gmail format (has dots/+ or not @gmail.com)", file=sys.stderr)
            time.sleep(1)
            continue
        
        print(f"  ✅ Valid Gmail format", file=sys.stderr)
        print(f"  🔍 Testing mailbox via API...", file=sys.stderr)
        
        # Wait for mailbox initialization
        time.sleep(2)
        
        # Test mailbox (like monitor script does)
        status, msg_response = api_request(f"/emails/messages?email_id={email_id}")
        
        # Check if API call failed (status 0 means timeout/error)
        if status == 0:
            print(f"  ❌ API timeout - trying next...", file=sys.stderr)
            continue
        
        # Check for errors (like monitor script)
        if "imap" in msg_response.lower() and "failed" in msg_response.lower():
            print(f"  ❌ IMAP auth error - trying next...", file=sys.stderr)
            continue
        elif "authentication" in msg_response.lower() and "failed" in msg_response.lower():
            print(f"  ❌ Auth failed - trying next...", file=sys.stderr)
            continue
        elif not msg_response or msg_response == "":
            # Empty body = freshly created mailbox with no mail yet. That is a
            # working inbox, not a failure — the verification email arrives after
            # the signup form is submitted, not before.
            if not lovable_email_available(email):
                print(f"  ⚠️  Email already registered on Lovable - trying next...", file=sys.stderr)
                time.sleep(1)
                continue
            print(f"  ✅ Mailbox working (empty, ready for verification mail)", file=sys.stderr)
            return email, email_id
        elif status == 200:
            # Check if mailbox is working
            if "norecentemails" in msg_response.lower() or '"emails":[' in msg_response:
                if not lovable_email_available(email):
                    print(f"  ⚠️  Email already registered on Lovable - trying next...", file=sys.stderr)
                    time.sleep(1)
                    continue
                print(f"  ✅ Mailbox working!", file=sys.stderr)
                print(f"🎉 FOUND WORKING GMAIL: {email} (ID: {email_id})", file=sys.stderr)
                return email, email_id
        
        print(f"  ❓ Unknown response - trying next...", file=sys.stderr)
        time.sleep(1)
    
    raise FlowError(f"Could not find working Gmail mailbox after {max_attempts} attempts")


def read_messages(email_id: str) -> list:
    """Read messages from mailbox via API."""
    status, raw = api_request(f"/emails/messages?email_id={email_id}", timeout=15)
    if status != 200:
        return []
    
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    
    # Extract emails list
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("emails", "messages", "mails", "items", "data"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


async def read_reset_link(email_id: str, timeout: float = 180, page: Page | None = None) -> str:
    """Poll API for Lovable reset email (with optional browser health check)."""
    import time
    deadline = time.time() + timeout
    check_count = 0
    
    while time.time() < deadline:
        check_count += 1
        if check_count % 5 == 1:
            print(f"  📥 Check #{check_count}: Polling API for emails...", file=sys.stderr)
        
        # Check if browser is still alive (if page provided)
        if page:
            try:
                await page.evaluate("1 + 1", timeout=2_000)
            except Exception as exc:
                if "closed" in str(exc).lower() or "crashed" in str(exc).lower() or "terminated" in str(exc).lower():
                    raise FlowError(f"Browser died during email polling: {exc}") from exc
        
        messages = read_messages(email_id)
        
        for message in messages:
            subject = str(message.get("subject") or message.get("title") or "")
            if "lovable" not in subject.lower():
                continue
            
            # Extract link from message body
            body = json.dumps(message, default=str)
            match = RESET_LINK_RE.search(body)
            if match:
                link = html.unescape(match.group(0))
                print(f"✅ Found Lovable reset link!", file=sys.stderr)
                return link
        
        await asyncio.sleep(8)
    
    raise FlowError("Timed out waiting for Lovable reset email")


def gaussian_delay(mean=300, std=120, min_ms=80):
    import random as _r
    v=int(_r.gauss(mean, std))
    return max(min_ms, min(v, mean*2))

async def bezier_mouse(page: Page, x: int, y: int):
    try:
        box = await page.evaluate("() => ({w: window.innerWidth, h: window.innerHeight})")
        # random control points for bezier
        import random as _r
        steps=_r.randint(12,22)
        cur = await page.evaluate("() => ({x: 400, y: 300})")  # fallback
        for i in range(steps):
            t=(i+1)/steps
            # quadratic bezier jitter
            jx=_r.randint(-8,8); jy=_r.randint(-8,8)
            nx=int(x*t + 200*(1-t) + jx); ny=int(y*t + 150*(1-t) + jy)
            await page.mouse.move(nx, ny, steps=1)
            await asyncio.sleep(_r.uniform(0.015,0.045))
        await page.mouse.move(x, y)
    except: 
        try: await page.mouse.move(x, y)
        except: pass

CF_CLEARANCE_FILE = Path("/tmp/cf_clearance.json")

_last_cf_save = 0
async def save_cf_clearance(context: BrowserContext) -> None:
    global _last_cf_save
    import time as _t
    if _t.time() - _last_cf_save < 30: return
    try:
        for c in await context.cookies():
            if c.get("name")=="cf_clearance":
                try:
                    old=json.loads(CF_CLEARANCE_FILE.read_text()) if CF_CLEARANCE_FILE.exists() else {}
                    if old.get("value")==c.get("value"): return
                except: pass
                CF_CLEARANCE_FILE.write_text(json.dumps(c))
                _last_cf_save=_t.time()
                print(f"💾 Saved cf_clearance {c['value'][:20]}...", file=sys.stderr)
                return
    except: pass

async def load_cf_clearance(context: BrowserContext) -> bool:
    try:
        if CF_CLEARANCE_FILE.exists():
            c=json.loads(CF_CLEARANCE_FILE.read_text())
            # check expiry
            if c.get("expires",0) > 0 and c["expires"] < __import__("time").time():
                return False
            await context.add_cookies([c])
            print(f"♻️  Reused cf_clearance", file=sys.stderr)
            return True
    except: pass
    return False

async def apply_stealth_patches(page: Page) -> None:
    """2026 7-patch stealth + behavioral hardening + cf_clearance + playwright_stealth pkg."""
    if STEALTH_PKG_AVAILABLE:
        try:
            s=Stealth()
            await s.apply_stealth_async(page)
            print("🛡️  Applied playwright_stealth pkg", file=sys.stderr)
        except Exception as e:
            print(f"⚠️  stealth pkg failed: {e}", file=sys.stderr)
    await page.add_init_script("""() => {
        // 1 webdriver undefined not false
        try { Object.defineProperty(navigator,'webdriver',{get:()=>undefined,configurable:true}); } catch(e){}
        // delete webdriver from prototype
        try { delete Navigator.prototype.webdriver; } catch(e){}
        // 2 plugins/mimeTypes with realistic lengths
        try {
            const plugins=[
                {name:'PDF Viewer',description:'Portable Document Format',filename:'internal-pdf-viewer'},
                {name:'Chrome PDF Viewer',filename:'internal-pdf-viewer'},
                {name:'Chromium PDF Viewer',filename:'internal-pdf-viewer'},
                {name:'Microsoft Edge PDF Viewer',filename:'internal-pdf-viewer'},
                {name:'WebKit built-in PDF',filename:'internal-pdf-viewer'}
            ];
            Object.defineProperty(navigator,'plugins',{get:()=>Object.assign(plugins,{length:5,item:i=>plugins[i],namedItem:n=>plugins.find(p=>p.name===n),refresh:()=>{}}),configurable:true});
            const mimes=[{type:'application/pdf',suffixes:'pdf',description:''},{type:'text/pdf',suffixes:'pdf',description:''}];
            Object.defineProperty(navigator,'mimeTypes',{get:()=>Object.assign(mimes,{length:2,item:i=>mimes[i],namedItem:n=>mimes.find(m=>m.type===n)}),configurable:true});
        } catch(e){}
        // 3 window.chrome complete
        try {
            if(!window.chrome) window.chrome={};
            window.chrome.app={isInstalled:false,InstallState:{DISABLED:'disabled',INSTALLED:'installed',NOT_INSTALLED:'not_installed'},RunningState:{CANNOT_RUN:'cannot_run',READY_TO_RUN:'ready_to_run',RUNNING:'running'}};
            window.chrome.runtime={OnInstalledReason:{CHROME_UPDATE:'chrome_update',INSTALL:'install',SHARED_MODULE_UPDATE:'shared_module_update',UPDATE:'update'},OnRestartRequiredReason:{APP_UPDATE:'app_update',OS_UPDATE:'os_update',PERIODIC:'periodic'},PlatformArch:{ARM:'arm',ARM64:'arm64',MIPS:'mips',MIPS64:'mips64',X86_32:'x86-32',X86_64:'x86-64'},PlatformOs:{ANDROID:'android',CROS:'cros',LINUX:'linux',MAC:'mac',OPENBSD:'openbsd',WIN:'win'},RequestUpdateCheckStatus:{NO_UPDATE:'no_update',THROTTLED:'throttled',UPDATE_AVAILABLE:'update_available'},id:undefined,connect:()=>{},sendMessage:()=>{}};
            window.chrome.loadTimes=()=>({requestTime:Date.now()/1000,startLoadTime:Date.now()/1000,commitLoadTime:Date.now()/1000,finishDocumentLoadTime:Date.now()/1000 - Math.random()*0.01,finishLoadTime:Date.now()/1000 - Math.random()*0.01,firstPaintTime:Date.now()/1000 - 0.5,firstPaintAfterLoadTime:0,navigationType:'Other',wasFetchedViaSpdy:false,wasNpnNegotiated:false,npnNegotiatedProtocol:'unknown',wasAlternateProtocolAvailable:false,connectionInfo:'http/1.1'});
            window.chrome.csi=()=>({startE:Date.now(),onloadT:Date.now(),pageT:3000+Math.random()*1000,tran:15});
        } catch(e){}
        // 4 permissions
        try { const q=navigator.permissions.query; navigator.permissions.query=p=>p.name==='notifications'?Promise.resolve({state:Notification.permission}):q.call(navigator.permissions,p); } catch(e){}
        try { const q2=navigator.permissions.query; navigator.permissions.query=p=>p.name==='clipboard-read'?Promise.resolve({state:'granted'}):q2.call(navigator.permissions,p); } catch(e){}
        // 5 WebGL vendor/renderer Intel + WebGL2 + canvas fingerprint noise
        try { const gp=WebGLRenderingContext.prototype.getParameter; WebGLRenderingContext.prototype.getParameter=function(p){ if(p===37445) return 'Intel Inc.'; if(p===37446) return 'Intel(R) Iris(TM) Graphics 6100'; return gp.call(this,p); }; } catch(e){}
        try { const gp2=WebGL2RenderingContext.prototype.getParameter; WebGL2RenderingContext.prototype.getParameter=function(p){ if(p===37445) return 'Intel Inc.'; if(p===37446) return 'Intel(R) Iris(TM) Graphics 6100'; return gp2.call(this,p); }; } catch(e){}
        // 6 languages + timezone matching proxy
        try { Object.defineProperty(navigator,'language',{get:()=>'en-US',configurable:true}); Object.defineProperty(navigator,'languages',{get:()=>['en-US','en'],configurable:true}); } catch(e){}
        // 7 iframe isolation + extra
        try { const ce=document.createElement.bind(document); document.createElement=function(...a){ const el=ce(...a); if(a[0].toLowerCase()==='iframe'){ Object.defineProperty(el,'contentWindow',{get:function(){ const w=Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype,'contentWindow').get.call(this); if(w){ try{ Object.defineProperty(w.navigator,'webdriver',{get:()=>undefined,configurable:true}); }catch(e){}} return w; },configurable:true}); } return el; }; } catch(e){}
        try { Object.defineProperty(navigator,'hardwareConcurrency',{get:()=>8,configurable:true}); } catch(e){}
        try { Object.defineProperty(navigator,'deviceMemory',{get:()=>8,configurable:true}); } catch(e){}
        try { Object.defineProperty(navigator,'platform',{get:()=>'Win32',configurable:true}); } catch(e){}
        try { Object.defineProperty(navigator,'maxTouchPoints',{get:()=>0,configurable:true}); } catch(e){}
        try { window.outerWidth=1920; window.outerHeight=1080; window.innerWidth=1920; window.innerHeight=947; } catch(e){}
        // hide automation: chrome.runtime, permissions, etc.
        try { window.navigator.chrome={runtime:{}}; } catch(e){}
        // canvas: don't add noise on lovable (breaks white screen), only return orig
        try { /* no canvas noise — lovable uses canvas for rendering */ } catch(e){}
    }""")


async def install_ad_blocker(page: Page) -> None:
    """Block ads/trackers + stealth."""
    def should_block(url: str) -> bool:
        lowered = url.lower()
        return any(needle in lowered for needle in AD_BLOCK_PATTERNS)
    async def handler(route):
        if should_block(route.request.url):
            await route.abort()
        else:
            await route.continue_()
    await page.route("**/*", handler)
    await apply_stealth_patches(page)


async def navigate(page: Page, url: str) -> None:
    """Navigate with timeout and Cloudflare handling."""
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    except PlaywrightTimeoutError:
        # Cloudflare may keep the initial navigation open while it verifies the browser
        pass


async def body_text(page: Page) -> str:
    """Get page body text."""
    try:
        return await page.locator("body").inner_text(timeout=3_000)
    except PlaywrightTimeoutError:
        return ""


async def click_exact(page: Page, text: str) -> None:
    """Click button/link with exact text - wait for clickability first."""
    # Try button first
    locator = page.get_by_role("button", name=text, exact=True)
    if await locator.count() == 0:
        # Try menuitem
        locator = page.get_by_role("menuitem", name=text, exact=True)
    if await locator.count() == 0:
        # Try any text
        locator = page.get_by_text(text, exact=True)
    if await locator.count() == 0:
        raise FlowError(f"Could not find clickable text {text!r}")
    
    # Wait for element to be clickable (visible + enabled)
    try:
        target = locator.last
        # Wait for visible AND stable
        await target.wait_for(state="visible", timeout=10_000)
        await asyncio.sleep(0.5)  # Let animations finish
        # Try normal click first (respects actionability checks)
        await target.click(timeout=10_000)
    except Exception as exc:
        if "closed" in str(exc).lower() or "target page" in str(exc).lower():
            raise FlowError(f"Page closed while clicking {text!r}") from exc
        raise


async def _is_white(page: Page) -> bool:
    try:
        txt=await page.locator("body").inner_text(timeout=1000)
        if len(txt.strip()) < 30:
            raw=await page.content()
            return len(raw) < 2000 or "Failed to fetch" in raw
        return False
    except: return False

async def wait_for_lovable_ready(page: Page) -> None:
    """Wait for Lovable page to be ready + white-screen fix + live watcher."""
    # live watcher: if blank at any time, reload
    async def _watcher():
        for _ in range(35):
            await asyncio.sleep(2)
            if await _is_white(page):
                try:
                    print("⚠️  Blank detected (watcher) → reload /", file=sys.stderr)
                    await page.goto(LOVABLE_URL, wait_until="domcontentloaded", timeout=30_000)
                except: pass
    watcher_task=asyncio.create_task(_watcher())
    deadline = asyncio.get_running_loop().time() + 75
    white_retries=0
    while asyncio.get_running_loop().time() < deadline:
        text = await body_text(page)
        # white screen: empty body or tiny html (lovable failed fetch) — /signup direct is always white, redirect to /
        if "/signup" in page.url and len(text.strip()) < 50:
            if white_retries < 2:
                print(f"⚠️  /signup white → redirect to /", file=sys.stderr)
                await page.goto(LOVABLE_URL, wait_until="domcontentloaded", timeout=30_000)
                white_retries+=1
                await page.wait_for_timeout(3000)
                continue
        html_len = len(text.strip())
        if html_len < 30 and white_retries < 3:
            # also check raw html length
            try:
                raw = await page.content()
                if len(raw) < 800 or "Failed to fetch" in raw or "api.lovable.dev" in raw:
                    print(f"⚠️  White screen detected (html {len(raw)}), reload {white_retries+1}/3", file=sys.stderr)
                    await page.reload(wait_until="domcontentloaded", timeout=30_000)
                    white_retries+=1
                    await page.wait_for_timeout(3000)
                    continue
            except: pass
            if html_len == 0:
                white_retries+=1
                await page.reload(wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(2500)
                continue
        
        # Wait for Cloudflare security check
        if "Performing security verification" in text:
            await page.wait_for_timeout(2_500)
            continue
        
        # Retry on error
        if "We hit a snag" in text:
            try:
                await page.reload(wait_until="domcontentloaded", timeout=30_000)
            except PlaywrightTimeoutError:
                pass
            await page.wait_for_timeout(2_500)
            continue
        
        if "Log in" in text or ("/dashboard" in page.url and "Dashboard" in text):
            try: watcher_task.cancel()
            except: pass
            return
        
        await page.wait_for_timeout(1_000)
    
    try: watcher_task.cancel()
    except: pass
    raise FlowError("Lovable did not finish loading or its security check")


async def dismiss_cookie_banner(page: Page) -> None:
    """Dismiss cookie banner and overlays aggressively."""
    await asyncio.sleep(1)  # Let overlays render
    
    # Try multiple times
    for attempt in range(3):
        dismissed = False
        try:
            # Try common cookie banner buttons
            for label in ("Reject all", "Accept all", "OK", "Accept", "Got it"):
                button = page.get_by_role("button", name=label, exact=False)
                if await button.count():
                    try:
                        await button.first.click(timeout=2_000, force=True)
                        dismissed = True
                        await asyncio.sleep(0.5)
                        break
                    except:
                        pass
            
            # Try closing any dialogs
            close_buttons = page.locator('button[aria-label*="Close"], button[aria-label*="close"]')
            if await close_buttons.count():
                try:
                    await close_buttons.first.click(timeout=1_000, force=True)
                    dismissed = True
                    await asyncio.sleep(0.5)
                except:
                    pass
            
            if dismissed:
                await asyncio.sleep(0.5)
                continue
            else:
                break
        except:
            break


async def sign_out_if_needed(page: Page) -> None:
    """Sign out if already logged in."""
    account = page.locator('button[aria-label="Account menu"]')
    
    # If on dashboard but account menu not visible, try reload
    if "/dashboard" in page.url and await account.count() == 0:
        try:
            await page.reload(wait_until="domcontentloaded", timeout=30_000)
        except PlaywrightTimeoutError:
            pass
        await page.wait_for_timeout(2_500)
    
    # Check if on dashboard
    if "/dashboard" in page.url:
        try:
            await account.last.wait_for(state="visible", timeout=20_000)
        except PlaywrightTimeoutError:
            # Account menu didn't appear, might be logged out already
            return
    
    if await account.count() == 0 or not await account.last.is_visible():
        return
    
    # Try to open menu and click sign out (with retry)
    sign_out = page.get_by_role("menuitem", name="Sign out", exact=True)
    for _menu_try in range(3):
        if await sign_out.count() and await sign_out.last.is_visible():
            await sign_out.last.click(force=True)
            break
        try:
            await account.last.evaluate("node => node.click()")
            await page.wait_for_timeout(500)
        except Exception:
            pass
    else:
        # Menu didn't open after 3 tries
        return
    
    # Wait for sign out to complete
    deadline = asyncio.get_running_loop().time() + 30
    while asyncio.get_running_loop().time() < deadline:
        if "/dashboard" not in page.url and "Log in" in await body_text(page):
            return
        await page.wait_for_timeout(500)


async def request_login(page: Page, email: str) -> str:
    """Submit email and determine signup vs reset path."""
    print("  🌐 Navigating to Lovable...", file=sys.stderr)
    await navigate(page, LOVABLE_URL)
    await wait_for_lovable_ready(page)
    print("  🍪 Dismissing overlays...", file=sys.stderr)
    await dismiss_cookie_banner(page)
    await sign_out_if_needed(page)
    
    if "/dashboard" in page.url:
        await navigate(page, LOVABLE_URL)
        await wait_for_lovable_ready(page)
    
    # Wait for any overlays to clear before clicking
    await asyncio.sleep(2)
    
    print("  🖱️  Clicking 'Log in' button (with retry for 15 min)...", file=sys.stderr)
    
    # Retry loop: click login button until email input popup appears (15 min max)
    deadline = asyncio.get_running_loop().time() + 900  # 15 minutes
    email_input = page.locator('input#auth-dialog-email').last
    login_clicked = False
    
    while asyncio.get_running_loop().time() < deadline:
        # Check if popup already visible
        try:
            if await email_input.is_visible(timeout=3_000):
                print("  ✅ Login popup appeared!", file=sys.stderr)
                break
        except:
            pass
        
        # Try to click login button if not clicked recently
        if not login_clicked:
            try:
                await click_exact(page, "Log in")
                login_clicked = True
                print("  ✅ Clicked 'Log in' button", file=sys.stderr)
            except Exception as exc:
                if "closed" in str(exc).lower():
                    raise
                # Button not ready yet, keep trying
                pass
        
        # Wait before next check
        await asyncio.sleep(2)
        login_clicked = False  # Allow clicking again
    
    # Final check - if popup still not visible, fail
    if not await email_input.is_visible():
        raise FlowError("Login popup never appeared after 15 minutes")
    
    # Now fill email and continue — robust for lovable's disabled→enabled transition
    await email_input.fill(email)
    await page.wait_for_timeout(800)
    # Try force click on the submit button (id=email-login-button) — handles stable check flakiness.
    # Final fallback dispatches a raw DOM click event to bypass Playwright visibility quirks
    # (popup submit button sometimes reports "not visible" despite being in the DOM).
    submitted = False
    for _ in range(10):
        try:
            btn = page.locator('#email-login-button')
            if await btn.count():
                try:
                    await btn.click(timeout=5000, force=True)
                except Exception:
                    await btn.dispatch_event("click")
                submitted = True
                break
            btn2 = page.get_by_role("button", name="Continue", exact=True).last
            if await btn2.count():
                try:
                    await btn2.click(timeout=5000, force=True)
                except Exception:
                    await btn2.dispatch_event("click")
                submitted = True
                break
        except Exception:
            pass
        await page.wait_for_timeout(700)
    if not submitted:
        # Last resort: dispatch a raw DOM click on whatever Continue control exists
        try:
            await page.get_by_role("button", name="Continue", exact=True).last.dispatch_event("click")
        except Exception:
            await click_exact(page, "Continue")
    
    deadline = asyncio.get_running_loop().time() + 25
    while asyncio.get_running_loop().time() < deadline:
        text = await body_text(page)
        forgot_password = page.get_by_text("Forgot password?", exact=True)
        
        # Check for existing account (password input + forgot password button)
        if (
            page.url.startswith("https://lovable.dev/login")
            and await page.locator('input[type="password"]').count()
            and await forgot_password.count()
        ):
            return "reset"
        
        # Check for new account
        if "No account found" in text or "Create your account" in text:
            return "signup"
        
        await page.wait_for_timeout(500)
    
    raise FlowError(f"Lovable did not react to the email on {page.url}")


async def do_password_reset(page: Page, email: str) -> None:
    """Request password reset."""
    password_input = page.locator('input[type="password"]')
    await password_input.wait_for(timeout=20_000)
    if not (await password_input.input_value()).strip():
        await password_input.fill("dummy1234")
    await click_exact(page, "Forgot password?")
    
    # Wait for reset form to appear
    await asyncio.sleep(1)
    
    reset_email = page.locator('input#auth-dialog-email')
    if await reset_email.count() == 0:
        reset_email = page.locator('input#auth-dialog-email')
    current_email = (await reset_email.last.input_value()).strip().lower()
    if current_email != email.lower():
        await click_exact(page, "Use a different email")
        reset_email = page.locator('input#auth-dialog-email')
        await reset_email.last.fill(email)
    
    # Use click_exact for consistency (waits for visibility)
    await asyncio.sleep(1)  # Let form settle
    await click_exact(page, "Send reset link")
    await page.wait_for_timeout(3_000)


async def human_type(locator, text: str) -> None:
    """Type text with human-like delays (InvisiblePlaywright already humanizes, but add extra realism)."""
    await locator.click()  # Focus first
    await asyncio.sleep(0.1)
    await locator.type(text, delay=random.randint(50, 150))  # 50-150ms between keystrokes


async def do_signup(page: Page, email: str, password: str) -> str:
    """Attempt signup flow."""
    try:
        # Lovable shows the email as a chip ("Edit") on the signup page; the
        # underlying <input type=email> may be empty, which keeps the submit
        # button disabled. Reveal + fill it explicitly so the form validates.
        edit_loc = page.get_by_text("Edit", exact=True)
        if await edit_loc.count():
            try:
                await edit_loc.first.click(timeout=3_000)
                await page.wait_for_timeout(400)
            except Exception:
                pass
        email_input = page.locator('input#auth-dialog-email').last
        if await email_input.count():
            cur = (await email_input.input_value()).strip().lower()
            if cur != email.lower():
                try:
                    await email_input.click(timeout=2_000)
                except Exception:
                    pass
                await email_input.fill(email)
                await page.wait_for_timeout(200)

        passwords = page.locator('input[type="password"]')
        await passwords.nth(0).wait_for(timeout=20_000)
        await human_type(passwords.nth(0), password)
        if await passwords.count() >= 2:
            await human_type(passwords.nth(1), password)
        # --- Turnstile handling — click checkbox + ClickSolver ---
        for _ts_try in range(5):
            try:
                # wait for Turnstile iframe
                try:
                    await page.wait_for_selector('iframe[src*="challenges.cloudflare.com"]', timeout=8000)
                except: pass
                turnstile_iframe = page.locator('iframe[src*="challenges.cloudflare.com"]')
                if await turnstile_iframe.count() > 0 and await turnstile_iframe.first.is_visible():
                    print(f"🤖 Turnstile detected (try {_ts_try+1}/5)", file=sys.stderr)
                    # human scroll before solve
                    try:
                        await page.mouse.wheel(0, 80); await asyncio.sleep(0.4)
                        await page.mouse.wheel(0, -40); await asyncio.sleep(0.3)
                    except: pass
                    # click checkbox: frame_locator selectors first
                    clicked = False
                    try:
                        fl = page.frame_locator('iframe[src*="challenges.cloudflare.com"]')
                        for sel in ['input[type="checkbox"]', '[role="checkbox"]', 'label', '#challenge-stage', 'body']:
                            try:
                                el = fl.locator(sel).first
                                if await el.count():
                                    box = await el.bounding_box()
                                    if box and box["width"] > 0:
                                        await el.click(timeout=1500)
                                        print(f"  🔘 Clicked via {sel}")
                                        clicked = True
                                        break
                            except: continue
                    except: pass
                    # coord click: 22px from left edge
                    if not clicked:
                        try:
                            box = await turnstile_iframe.first.bounding_box()
                            if box and box["width"] > 0:
                                await page.mouse.click(box["x"] + 22, box["y"] + box["height"] / 2, delay=100)
                                await page.wait_for_timeout(500)
                                await page.mouse.click(box["x"] + 30, box["y"] + box["height"] / 2, delay=100)
                                print("  🔘 Clicked via coords")
                                clicked = True
                        except: pass
                    # ClickSolver fallback
                    if CAPTCHA_SOLVER_AVAILABLE and not clicked:
                        try:
                            async with ClickSolver(framework=FrameworkType.PATCHRIGHT, page=page, max_attempts=2, attempt_delay=2) as solver:
                                await solver.solve_captcha(captcha_container=page, captcha_type=CaptchaType.CLOUDFLARE_TURNSTILE)
                            print("  ✅ Solved via ClickSolver")
                        except Exception as e:
                            print(f"  ⚠️ ClickSolver failed: {e}", file=sys.stderr)
                    await page.wait_for_timeout(4000)
                # check if Create button enabled
                create_btn = page.get_by_role("button", name="Create your account", exact=True)
                try:
                    from playwright.async_api import expect
                    await expect(create_btn).to_be_enabled(timeout=10000)
                    print("✅ Create button enabled — Turnstile solved", file=sys.stderr)
                    try: await save_cf_clearance(page.context)
                    except: pass
                    break
                except:
                    token_len = await page.evaluate('''() => document.querySelector('input[name="cf-turnstile-response"]')?.value?.length || 0''')
                    is_disabled = await create_btn.is_disabled() if await create_btn.count() else True
                    print(f"⚠️ Token len {token_len}, disabled={is_disabled} — retry...", file=sys.stderr)
                    if token_len > 20 and not is_disabled:
                        break
                    await page.wait_for_timeout(2000)
                    continue
            except Exception as e:
                print(f"turnstile try {_ts_try}: {e}", file=sys.stderr)
                await page.wait_for_timeout(1000)
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
        # Debug screenshot on failure
        try:
            screenshot_path = "/tmp/lovable_signup_debug.png"
            await page.screenshot(path=screenshot_path)
            print(f"📸 Signup debug screenshot saved: {screenshot_path}", file=sys.stderr)
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


async def set_password_and_verify(page: Page, reset_url: str, password: str) -> None:
    """Set password via reset link."""
    await navigate(page, reset_url)
    
    # Check for invalid link
    if "invalid verification code" in (await body_text(page)).lower():
        raise FlowError("Lovable reset link is invalid or stale")
    
    new_password = page.locator('input[name="newPassword"]')
    confirm_password = page.locator('input[name="confirmPassword"]')
    await new_password.wait_for(timeout=30_000)
    await human_type(new_password, password)
    await human_type(confirm_password, password)
    await click_exact(page, "Reset Password")
    
    # Wait for confirmation and redirect (Firebase is SLOW)
    deadline = asyncio.get_running_loop().time() + 60
    while asyncio.get_running_loop().time() < deadline:
        text = await body_text(page)
        
        # Already on dashboard - success!
        if "/dashboard" in page.url and "Dashboard" in text:
            return
        
        # Password updated - keep waiting for redirect
        if "Your password has been updated" in text:
            await page.wait_for_timeout(2_000)
            continue
        
        # Check for password rejection
        lowered = text.lower()
        if any(
            hint in lowered
            for hint in (
                "password must contain", "password is too weak", "change your password",
                "choose a new password", "password was rejected",
            )
        ):
            raise FlowError("Lovable rejected the password")
        
        await page.wait_for_timeout(1_000)
    else:
        raise FlowError("Lovable did not confirm password reset or redirect to dashboard")
    
    # Final dashboard wait with account menu check
    await wait_for_dashboard(page, timeout=60)


async def handle_lovable_onboarding(page: Page) -> None:
    """4-step onboarding after verify: Pick style → Name → Role → Company → chat."""
    try:
        for _ in range(3):
            if "Pick your style" in await body_text(page):
                btn = page.locator('button').filter(has_text='Next')
                if await btn.count(): await btn.first.click(timeout=5000)
                else: await page.get_by_role("button", name="Next").first.click(timeout=5000)
                await page.wait_for_timeout(2000)
            else: break
        for _ in range(2):
            if "What's your name" in await body_text(page):
                inp = page.get_by_placeholder("Enter your name")
                if await inp.count(): await inp.fill("Sam Dad")
                btn = page.locator('button').filter(has_text='Next')
                if await btn.count(): await btn.first.click(timeout=5000)
                else: await page.get_by_role("button", name="Next").first.click(timeout=5000)
                await page.wait_for_timeout(2000)
            else: break
        if "Which role fits you best" in await body_text(page):
            founder = page.get_by_role("button", name="Founder")
            if await founder.count(): await founder.first.click(timeout=5000)
            else: await page.locator('button').filter(has_text='Founder').first.click(timeout=5000)
            await page.wait_for_timeout(1500)
            nxt = page.locator('button').filter(has_text='Next')
            if await nxt.count():
                try: await nxt.first.click(timeout=3000)
                except: pass
                await page.wait_for_timeout(2000)
        if "How many people work at your company" in await body_text(page):
            solo = page.get_by_role("button", name="Solo")
            if await solo.count(): await solo.first.click(timeout=5000)
            else: await page.locator('button').filter(has_text='Solo').first.click(timeout=5000)
            await page.wait_for_timeout(3000)
    except Exception as e:
        print(f"  onboarding helper: {e}", file=sys.stderr)
    await page.wait_for_timeout(3000)

async def wait_for_dashboard(page: Page, timeout: float = 60) -> None:
    """Wait for dashboard/chat — handles /dashboard and onboarding /getting-started."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        current = await body_text(page)
        if "/dashboard" in page.url and "Dashboard" in current:
            account_menu = page.locator('button[aria-label="Account menu"]')
            if await account_menu.count():
                return
        if any(s in current for s in ("Pick your style", "What's your name", "Which role fits you best", "How many people work at your company")):
            await handle_lovable_onboarding(page)
            continue
        if "Ask Lovable" in current or "What's the vision" in current:
            chat = page.locator('textarea[placeholder*="Ask"], div[contenteditable="true"], input[placeholder*="Ask"]')
            if await chat.count():
                return
            if "Ask Lovable to make a document" in current or "What's the vision" in current:
                return
        await page.wait_for_timeout(1_000)
    
    raise FlowError(f"Lovable did not reach the dashboard: {page.url}")


async def verify_egress_ip(context: BrowserContext) -> str:
    """Check browser egress IP."""
    page = await context.new_page()
    try:
        await page.goto("https://cloudflare.com/cdn-cgi/trace", timeout=15_000)
        text = await page.locator("body").inner_text()
        return text.strip()
    except Exception as e:
        return f"egress probe failed ({e})"
    finally:
        await page.close()


async def connect_browser(playwright_support, cdp_url: str | None) -> Browser:
    """Connect to external CDP browser or launch our own."""
    if cdp_url:
        browser = await playwright_support.chromium.connect_over_cdp(cdp_url, timeout=60_000)
        if not browser.contexts:
            raise FlowError("Connected browser has no context")
        return browser
    
    return await playwright_support.chromium.launch(
        channel="chrome",
        headless=False,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
        ],
        proxy=proxy_settings(for_api=False),
    )


def keep_browser_open() -> bool:
    """Check if we should keep browser open."""
    return os.getenv("KEEP_BROWSER_OPEN", "1").lower() in ("1", "true", "yes")


async def run(cdp_url: str | None, auto_close: bool = False, use_dispose: bool = False) -> dict[str, object]:
    print(f"🚀 Starting automation... (provider={'22.do' if use_dispose else 'tempmailhub'})", file=sys.stderr)
    
    # Configure proxy - isolated warp proxy
    proxy_config = proxy_settings(for_api=False)
    playwright_proxy = None
    if proxy_config:
        playwright_proxy = {
            "server": proxy_config["server"],
            "bypass": proxy_config.get("bypass", "127.0.0.1,localhost"),
        }
        print(f"🌐 Browser proxy {playwright_proxy['server']} bypass={playwright_proxy['bypass']} (isolated)", file=sys.stderr)
    else:
        print("🌐 Browser direct (warp=off, isolated)", file=sys.stderr)
    
    # Launch browser — Patchright (navigator.webdriver=false natively, Turnstile bypass)
    _browser_ctx = None
    _pw_ctx = None
    if use_dispose:
        print("🦊 Dispose mode: Patchright Chromium headed (Turnstile native bypass)", file=sys.stderr)
        from patchright.async_api import async_playwright as _pw
        _pw_ctx = _pw()
        _pw_enter = await _pw_ctx.__aenter__()
        browser = await _pw_enter.chromium.launch(headless=False, proxy=playwright_proxy, args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
        _browser_ctx = _pw_enter
    else:
        try:
            _browser_ctx = InvisiblePlaywright(headless=False, proxy=playwright_proxy, humanize=True, locale='en-US')
            browser = await _browser_ctx.__aenter__()
        except Exception as e:
            if "GeoTimezone" in type(e).__name__ or "egress IP discovery" in str(e):
                print(f"⚠️  Invisible geo failed ({e}) — fallback Patchright", file=sys.stderr)
                from patchright.async_api import async_playwright as _pw
                _pw_ctx = _pw()
                _pw_enter = await _pw_ctx.__aenter__()
                browser = await _pw_enter.chromium.launch(headless=True, proxy=playwright_proxy, args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
                _browser_ctx = _pw_enter
            else:
                raise
    try:
        # Browser launched — context with correct viewport per mode
        print(f"✅ Browser launched ({'Firefox' if use_dispose else 'Chromium'} {'Invisible' if 'Invisible' in type(_browser_ctx).__name__ else 'plain'})", file=sys.stderr)
        
        # InvisiblePlaywright returns Browser directly
        if isinstance(browser, BrowserContext):
            context = browser
        else:
            # realistic geo-matched context: US IP, en-US, Win32, 1920x1080
            vp = {"width": 1920, "height": 1080} if use_dispose else {"width": 1920, "height": 1080}
            ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ctx_kwargs = {
                "viewport": vp,
                "user_agent": ua,
                "locale": "en-US",
                "timezone_id": "America/New_York",
                "color_scheme": "light",
                "extra_http_headers": {
                    "Accept-Language": "en-US,en;q=0.9",
                    "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
                    "Sec-Ch-Ua-Mobile": "?0",
                    "Sec-Ch-Ua-Platform": '"Windows"',
                },
            }
            if browser.contexts:
                context = browser.contexts[0]
                # patch existing context headers
                try: await context.set_extra_http_headers(ctx_kwargs["extra_http_headers"])
                except: pass
            else:
                context = await browser.new_context(**ctx_kwargs)
            # NO stealth init_script — Patchright handles navigator.webdriver=false natively
            # reuse cf_clearance
            try: await load_cf_clearance(context)
            except: pass
        
        print("✅ Context ready", file=sys.stderr)
        # Create Lovable page
        lovable_page = await context.new_page()
        # NO ad-blocker — Lovable needs googletagmanager for consent/SPA hydration
        # cf_clearance saved ONLY after Turnstile solve (not on every response)
        
        # Check egress IP (skip if times out)
        try:
            egress_ip = await asyncio.wait_for(verify_egress_ip(context), timeout=10)
            print(f"🌐 Browser egress IP: {egress_ip}")
        except asyncio.TimeoutError:
            print("⚠️  Egress IP check timed out, continuing...", file=sys.stderr)
        
        dispose_inbox = None
        if use_dispose:
            # Try temp.tf first (API, no browser), fallback to 22.do
            try:
                _tf = TempTfInbox(context)
                await _tf.create()
                dispose_inbox = _tf
                print(f"📧 Using temp.tf as email provider", file=sys.stderr)
            except Exception as e:
                print(f"⚠️ temp.tf failed ({e}), falling back to 22.do", file=sys.stderr)
                dispose_inbox = TwoTwoDoInbox(context)

        last_error: Optional[Exception] = None
        for attempt in range(1, 4):
            try:
                if use_dispose:
                    print(f"\n🔄 Attempt {attempt}/3: Creating account via 22.do...", file=sys.stderr)
                    email, email_id = await dispose_inbox.create()
                else:
                    print(f"\n🔄 Attempt {attempt}/3: Creating account via TRUE API-ONLY mode...", file=sys.stderr)
                    email, email_id = create_working_email()
                password = f"{email}K0"
                
                mode = await request_login(lovable_page, email)
                
                if mode == "signup":
                    print("📝 Lovable: No account found, creating one...")
                    try:
                        signup_result = await do_signup(lovable_page, email, password)
                    except Exception as exc:
                        if use_dispose:
                            print(f"⚠️  Signup failed ({exc}), retry via verify link...", file=sys.stderr)
                            reset_url = await dispose_inbox.wait_for_lovable_link(timeout_seconds=300)
                            await navigate(lovable_page, reset_url)
                            await wait_for_dashboard(lovable_page, timeout=60)
                        else:
                            print(f"⚠️  Signup failed ({exc}), using reset path...", file=sys.stderr)
                            await navigate(lovable_page, f"{LOVABLE_URL}login")
                            await request_login(lovable_page, email)
                            await do_password_reset(lovable_page, email)
                            reset_url = await read_reset_link(email_id, timeout=180, page=lovable_page)
                            await set_password_and_verify(lovable_page, reset_url, password)
                    else:
                        if signup_result == "verify":
                            print("📧 Lovable: Email verification required...")
                            if use_dispose:
                                reset_url = await dispose_inbox.wait_for_lovable_link(timeout_seconds=300)
                            else:
                                reset_url = await read_reset_link(email_id, timeout=180, page=lovable_page)
                            await navigate(lovable_page, reset_url)
                            await wait_for_dashboard(lovable_page, timeout=60)
                        elif signup_result == "login":
                            print("🔐 Account created, logging in...")
                            await human_type(lovable_page.locator('input[type="password"]').last, password)
                            await click_exact(lovable_page, "Log in")
                            await wait_for_dashboard(lovable_page, timeout=45)
                else:
                    if use_dispose:
                        print("📝 Lovable: exists in 22.do mode — setting pwd then verify link...", file=sys.stderr)
                        try:
                            await do_signup(lovable_page, email, password)
                            reset_url = await dispose_inbox.wait_for_lovable_link(timeout_seconds=300)
                            await navigate(lovable_page, reset_url)
                            await wait_for_dashboard(lovable_page, timeout=60)
                        except:
                            await do_password_reset(lovable_page, email)
                            reset_url = await dispose_inbox.wait_for_lovable_link(timeout_seconds=300)
                            await set_password_and_verify(lovable_page, reset_url, password)
                    else:
                        print("🔄 Lovable: Account exists, requesting password reset...")
                        await do_password_reset(lovable_page, email)
                        reset_url = await read_reset_link(email_id, timeout=180, page=lovable_page)
                        await set_password_and_verify(lovable_page, reset_url, password)
                
                break
            except Exception as exc:
                last_error = exc
                print(f"❌ Attempt {attempt} failed: {exc}", file=sys.stderr)
        else:
            raise FlowError(f"All attempts failed: {last_error}") from last_error
        
        # Verify dashboard
        dashboard_text = await body_text(lovable_page)
        account_menu = lovable_page.locator('button[aria-label="Account menu"]')
        try:
            await account_menu.wait_for(state="visible", timeout=20_000)
        except PlaywrightTimeoutError as exc:
            raise FlowError("Dashboard account menu did not render") from exc
        
        if "/dashboard" not in lovable_page.url or "Dashboard" not in dashboard_text:
            raise FlowError("Dashboard loaded but account not verified")
        
        # Save email to used list
        save_used_email(email)
        
        # Save session - dynamic default to repo location or home
        _default_sessions = str(Path(__file__).resolve().parents[2] / "scripts" / "sessions")
        if not Path(_default_sessions).exists():
            _default_sessions = str(Path.home() / "Documents" / "repos" / "automation-toolkit" / "scripts" / "sessions")
        sessions_dir = Path(
            os.environ.get(
                "CHIMERA_SESSIONS_DIR",
                _default_sessions,
            )
        )
        try:
            sessions_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            # fallback to home
            sessions_dir = Path.home() / "Documents" / "repos" / "automation-toolkit" / "scripts" / "sessions"
            sessions_dir.mkdir(parents=True, exist_ok=True)
            print(f"⚠️  CHIMERA_SESSIONS_DIR fallback to {sessions_dir}", file=sys.stderr)
        
        # Generate unique session ID (collision-proof across machines)
        import time as _time
        runner = os.getenv("RUNNER_ID", "").strip()
        if runner:
            session_id = f"session-{runner}-{int(_time.time())}"
        else:
            session_id = f"session-{int(_time.time())}-{os.getpid()}"
        
        session_dir = sessions_dir / session_id
        session_dir.mkdir(exist_ok=True)
        session_num = session_id
        
        # Save cookies
        cookies = await context.cookies()
        cookies_file = session_dir / "cookies.json"
        with open(cookies_file, "w") as f:
            json.dump(cookies, f, indent=2)
        print(f"✅ Saved {len(cookies)} cookies to {cookies_file}", file=sys.stderr)
        
        # Save credentials
        config = {
            "email": email,
            "password": password,
            "created_at": datetime.now().isoformat(),
            "dashboard_url": lovable_page.url,
            "verified": True,
            "api_only": True,
        }
        config_file = session_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)
        print(f"✅ Saved session config to {config_file}", file=sys.stderr)
        
        # Sync session to Chimera Mega DB (with distributed lock for GH runners)
        if os.environ.get("CHIMERA_SKIP_MEGA_SYNC", "").lower() in ("1", "true", "yes"):
            print("⏭️  Skipping Mega DB sync (CHIMERA_SKIP_MEGA_SYNC set)", file=sys.stderr)
        else:
            try:
                _default_miner = str(Path(__file__).resolve().parents[2].parent / "chimera-miner")
                if not Path(_default_miner).exists():
                    _default_miner = str(Path.home() / "Documents" / "repos" / "chimera-miner")
                sys.path.insert(
                    0,
                    os.environ.get(
                        "CHIMERA_MINER_DIR", _default_miner
                    ),
                )
                from mega_db import load_db, save_db, mega_distributed_lock
                with mega_distributed_lock():
                    db = load_db()
                    db.add_session(session_id, email, status="active")
                    save_db(db)
                print(f"✅ Synced {session_id} to Mega DB", file=sys.stderr)
            except Exception as e:
                print(f"⚠️  Mega DB sync failed (non-fatal): {e}", file=sys.stderr)
        
        result = {
            "verified": True,
            "email": email,
            "password": password,
            "dashboard_url": lovable_page.url,
            "session_dir": str(session_dir),
            "session_number": session_num,
        }
        
        print("\n" + "="*60)
        print("🎉 SUCCESS!")
        print("="*60)
        print(json.dumps(result, indent=2))
        
        # Close browser based on --end flag
        if auto_close:
            print("\n✅ Auto-closing browser (--end flag set)", file=sys.stderr)
            if not cdp_url:
                try: await browser.close()
                except: pass
        elif keep_browser_open() and not cdp_url:
            print("\n✋ Browser staying open. Press Enter to close...", file=sys.stderr)
            input()
            try: await browser.close()
            except: pass
        elif not cdp_url:
            try: await browser.close()
            except: pass
        
        return result
    finally:
        # close the InvisiblePlaywright / playwright context manager
        try:
            if '_browser_ctx' in locals() and _browser_ctx:
                await _browser_ctx.__aexit__(None, None, None)
        except: pass
        try:
            if '_pw_ctx' in locals() and _pw_ctx:
                await _pw_ctx.__aexit__(None, None, None)
        except: pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Lovable account via TempMailHub / 22.do")
    parser.add_argument("--cdp-url", help="Connect to existing browser via CDP")
    parser.add_argument("--end", action="store_true", help="Close browser when done (don't wait for Enter)")
    parser.add_argument("--raw", action="store_true", help="Force direct connection (no proxy/WARP)")
    parser.add_argument("--dispose", action="store_true", help="Use 22.do disposable email (random handler, verify link + onboarding)")
    args = parser.parse_args()
    
    cdp = args.cdp_url or os.getenv("BU_CDP_WS")
    
    # Pass --raw flag to run() via environment
    if args.raw:
        os.environ["FORCE_NO_PROXY"] = "1"
    
    try:
        result = asyncio.run(run(cdp, auto_close=args.end, use_dispose=args.dispose))
    except FlowError as e:
        print(f"\n❌ Automation failed: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
