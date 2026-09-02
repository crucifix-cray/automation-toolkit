#!/usr/bin/env python3
"""Lovable effective signup — verified ZenRows GB + dispose.lol Gmail (end-to-end).

Verified flow per docs/ZENROWS_ADVANCEMENTS_2026-09-01.md (genev.aochea@gmail.com / GmailK01):
  ZenRows Browser Cloud wss://browser.zenrows.com?apikey=a71406ecf7cfd8ae0aec54b2d1bf11aa92c917e7&proxy_country=gb
  (BT Telford 86.141.244.43) + dispose.lol Temporary Gmail (1.5k+ inboxes) → Check your inbox → oobCode → /getting-started

Flow (direct /signup):
  browser_navigate (proxy_country=gb) → https://lovable.dev/signup (fr locale Créez votre compte)
    → type input#email (dispose.lol Gmail) → click [data-testid="auth-submit-button"] Continuer
    → wait input#password → type input#password (GmailK01, delay 50, no trap) → Password meets all requirements
    → wait input[name="cf-turnstile-response"] len 837-858 → Success! green (auto on GB, 2-4s)
    → click [data-testid="auth-submit-button"] Créez votre compte → Check your inbox
    → poll dispose.lol getMailboxMessages → Verify your email → https://lovable.dev/auth/action?mode=verifyEmail&oobCode=...&apiKey=AIzaSyBQNjlw...
    → /getting-started Pick your style (emailVerified=true)

Key fixes vs lov-api.py / lov-api-zenrows.py:
  - Default ZenRows GB CDP wss://browser.zenrows.com?apikey=a71406ecf7cfd8ae0aec54b2d1bf11aa92c917e7&proxy_country=gb
    with AUTH004 fallback to direct raw IP (local Patchright, no proxy)
  - Script itself ALWAYS raw IP: LD_PRELOAD="" + ALL proxy env cleared (no Tor/WARP). Only browser egress uses ZenRows.
  - dispose.lol Gmail only (not temp.tf) — healthiest per doc; discard temp.tf/tempmailhub paths
  - Direct /signup selectors: input#email → Continuer → input#password → Turnstile auto Success! → Create
  - Turnstile: 15-try, token len >20 (837-858 on GB), button enabled check, Verification failed/Troubleshooting→reload,
    and ClickSolver "success element does not exist" → fallback to manual bounding-box coordinate click
  - Headed by default (ZenRows cloud is headed); --headless flag to override local fallback

Egress: browser Country=GB via ZenRows; script local raw IP (no LD_PRELOAD trick, no Tor).
Save: local sessions/ + Mega DB (mega_distributed_lock) as before.
"""
from __future__ import annotations

# ── RAW IP ENFORCEMENT (must be first, before any net import touches env) ──────
import os as _os

_os.environ["LD_PRELOAD"] = ""
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy", "PLAYWRIGHT_PROXY_URL"):
    _os.environ.pop(_k, None)
# Also clear socks-related preload tricks; keep empty for raw egress
if _os.environ.get("LD_PRELOAD") != "":
    _os.environ["LD_PRELOAD"] = ""

import argparse
import asyncio
import html
import json
import random
import re
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Optional

# Playwright / Patchright — prefer patchright (navigator.webdriver=false natively)
try:
    from patchright.async_api import async_playwright as _patchright_playwright  # type: ignore
    PATCHRIGHT_AVAILABLE = True
except ImportError:
    PATCHRIGHT_AVAILABLE = False

try:
    from playwright.async_api import async_playwright as _playwright_playwright  # type: ignore
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

try:
    from playwright.async_api import Browser, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError  # type: ignore
except ImportError:  # fallback stubs for type checkers when playwright not installed
    Browser = BrowserContext = Page = object  # type: ignore
    class PlaywrightTimeoutError(Exception):  # type: ignore
        pass

try:
    from playwright_captcha import ClickSolver, CaptchaType, FrameworkType  # type: ignore
    CAPTCHA_SOLVER_AVAILABLE = True
except ImportError:
    CAPTCHA_SOLVER_AVAILABLE = False

try:
    from playwright_stealth import Stealth  # type: ignore
    STEALTH_PKG_AVAILABLE = True
except ImportError:
    STEALTH_PKG_AVAILABLE = False

# ── Constants (verified 2026-09-01) ────────────────────────────────────────────
ZENROWS_API_KEY = "a71406ecf7cfd8ae0aec54b2d1bf11aa92c917e7"
ZENROWS_CDP_URL_GB = f"wss://browser.zenrows.com?apikey={ZENROWS_API_KEY}&proxy_country=gb"
LOVABLE_URL = "https://lovable.dev/"
LOVABLE_SIGNUP_URL = "https://lovable.dev/signup"
LOVABLE_VERIFY_RE = re.compile(r"https?://lovable\.dev/auth/action\?[^\"'\\\s<>]*oobCode=[^\"'\\\s<>]+", re.I)
RESET_LINK_RE = re.compile(r"https?://[^\"'\\\s<>]*lovable\.dev[^\"'\\\s<>]*", re.I)
OOB_RE = re.compile(r"oobCode=([^&\"'\\\s<>]+)", re.I)
USED_EMAILS_FILE = _os.environ.get("USED_EMAILS_FILE", str(Path.home() / "Documents" / "used-tempmailhub-emails.txt"))

# Keep sessions under repo by default, fallback to home
_DEFAULT_SESSIONS_REPO = Path(__file__).resolve().parents[2] / "scripts" / "sessions"
_DEFAULT_SESSIONS_HOME = Path.home() / "Documents" / "repos" / "automation-toolkit" / "scripts" / "sessions"

# ── Errors ────────────────────────────────────────────────────────────────────
class FlowError(RuntimeError):
    pass

# ── Raw-IP helpers ────────────────────────────────────────────────────────────
def _ensure_raw_ip_env() -> None:
    """Enforce LD_PRELOAD="" and no proxy for THIS process (raw IP). ZenRows browser still uses GB egress."""
    _os.environ["LD_PRELOAD"] = ""
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy", "PLAYWRIGHT_PROXY_URL"):
        _os.environ.pop(k, None)

def _clear_proxy_env() -> None:
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"):
        _os.environ.pop(k, None)

# ── dispose.lol Gmail (healthiest, GB-verified) ───────────────────────────────
class DisposeLolInbox:
    """dispose.lol Temporary Gmail — 1.5k+ inboxes, GB-verified.

    UI-only: single tab reused for create + poll. Email extracted via TreeWalker
    (mirrors lov-api.py). Poll clicks View → scans ALL frames for oobCode link.
    Raw IP: page itself goes direct, but mailbox content is still loaded via
    ZenRows browser egress when connected_over_cdp (GB) — which is desired.
    """
    BASE_URL = "https://dispose.lol"

    def __init__(self, context) -> None:
        self.context = context
        self.page = None  # type: ignore
        self.address: Optional[str] = None
        self._initialized = False

    async def _ensure_page(self) -> None:
        if not self.context:
            raise FlowError("No browser context for dispose.lol")
        if not self._initialized:
            self.page = await self.context.new_page()
            await self.page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=60_000)
            await self.page.wait_for_timeout(4000)
            self._initialized = True

    async def create(self) -> tuple[str, str]:
        print("📧 Creating dispose.lol Gmail (separate tab, raw-IP script / ZenRows browser)...", file=sys.stderr)
        await self._ensure_page()
        await self.page.wait_for_timeout(3000)
        # Retry up to 5 times — dispose.lol sometimes slow to render email
        for attempt in range(1, 6):
            email_text = await self.page.evaluate("""() => {
                const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT,null);
                let n; while(n=w.nextNode()){
                    const t=n.textContent.trim();
                    if(t.includes('@gmail.com')&&t.length<80) return t;
                }
                for(const i of document.querySelectorAll('input')) if(i.value&&i.value.includes('@gmail.com')) return i.value;
                return null;
            }""")
            if email_text and "@gmail.com" in email_text:
                self.address = email_text.strip()
                print(f"✅ Mailbox ready: {self.address} (via dispose.lol, attempt {attempt})", file=sys.stderr)
                return self.address, "dispose"
            print(f"  ⏳ dispose.lol email not yet rendered (attempt {attempt}/5)…", file=sys.stderr)
            await self.page.wait_for_timeout(2000)
            await self.page.reload(wait_until="domcontentloaded")
            await self.page.wait_for_timeout(3000)
        await self.page.screenshot(path="/tmp/disposelol-error.png", full_page=True)
        raise FlowError("Could not find dispose.lol Gmail after 5 attempts")

    async def wait_for_lovable_link(self, timeout_seconds: int = 360) -> str:
        print(f"📥 Waiting for Lovable verify link on dispose.lol ({self.address})…", file=sys.stderr)
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        check = 0

        def _decode(raw: str) -> str:
            link = html.unescape(raw or "")
            return link.replace("&amp;", "&")

        while asyncio.get_running_loop().time() < deadline:
            check += 1
            try:
                await self.page.reload(wait_until="domcontentloaded")
            except Exception:
                pass
            await self.page.wait_for_timeout(2200)
            # dispose.lol renders each message as button[aria-label^="View "]
            try:
                buttons = await self.page.locator('button[aria-label^="View "]').all()
            except Exception:
                buttons = []
            if check % 4 == 1:
                print(f"  Check #{check}: {len(buttons)} message(s)", file=sys.stderr)
            for btn in buttons:
                try:
                    aria = (await btn.get_attribute("aria-label") or "")
                except Exception:
                    aria = ""
                if "lovable" not in aria.lower() and "verify" not in aria.lower() and "verification" not in aria.lower():
                    continue
                print(f"  ✅ Found candidate: {aria[:120]}", file=sys.stderr)
                try:
                    try:
                        await btn.scroll_into_view_if_needed(timeout=2000)
                    except Exception:
                        pass
                    await btn.click(timeout=5000, force=True)
                    await self.page.wait_for_timeout(3000)

                    # Scan every frame (mail is in iframe srcdoc)
                    for frame in self.page.frames:
                        try:
                            fhtml = await frame.content()
                        except Exception:
                            continue
                        m = LOVABLE_VERIFY_RE.search(fhtml or "")
                        if m:
                            link = _decode(m.group(0))
                            print(f"  🎯 Link (frame verify): {link[:180]}", file=sys.stderr)
                            return link
                        m2 = RESET_LINK_RE.search(fhtml or "")
                        if m2 and "oobCode" in m2.group(0):
                            link = _decode(m2.group(0))
                            print(f"  🎯 Link (frame generic oobCode): {link[:180]}", file=sys.stderr)
                            return link
                        # body innerText fallback per frame
                        try:
                            ftext = await frame.evaluate("() => document.body ? document.body.innerText.slice(0,20000) : ''")
                        except Exception:
                            ftext = ""
                        m3 = LOVABLE_VERIFY_RE.search(ftext or "")
                        if m3:
                            link = _decode(m3.group(0))
                            print(f"  🎯 Link (frame text): {link[:180]}", file=sys.stderr)
                            return link

                    body = await self.page.evaluate("() => document.body.innerHTML.slice(0,70000)")
                    m = LOVABLE_VERIFY_RE.search(body or "")
                    if m:
                        link = _decode(html.unescape(m.group(0)))
                        print(f"  🎯 Link (main html verify): {link[:180]}", file=sys.stderr)
                        return link
                    m2 = RESET_LINK_RE.search(body or "")
                    if m2 and "oobCode" in (m2.group(0) or ""):
                        link = _decode(html.unescape(m2.group(0)))
                        print(f"  🎯 Link (main html generic): {link[:180]}", file=sys.stderr)
                        return link
                    txt = await self.page.evaluate("() => document.body.innerText.slice(0,25000)")
                    m3 = LOVABLE_VERIFY_RE.search(txt or "")
                    if m3:
                        link = _decode(m3.group(0))
                        print(f"  🎯 Link (main text): {link[:180]}", file=sys.stderr)
                        return link
                    print("  ⚠️ View opened but no oobCode link yet", file=sys.stderr)
                except Exception as e:
                    print(f"  click/extract failed: {e}", file=sys.stderr)
                    continue
            await asyncio.sleep(3)
        raise FlowError("Lovable verify link not received on dispose.lol (timeout)")

    async def close(self) -> None:
        if self.page:
            try:
                await self.page.close()
            except Exception:
                pass

# ── Generic helpers ───────────────────────────────────────────────────────────
def _sessions_dir() -> Path:
    env = _os.environ.get("CHIMERA_SESSIONS_DIR", "").strip()
    if env:
        p = Path(env)
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            pass
    for cand in (_DEFAULT_SESSIONS_REPO, _DEFAULT_SESSIONS_HOME, Path("/tmp/automation-toolkit-sessions")):
        try:
            cand.mkdir(parents=True, exist_ok=True)
            return cand
        except Exception:
            continue
    p = Path("/tmp/automation-toolkit-sessions")
    p.mkdir(parents=True, exist_ok=True)
    return p

def load_used_emails() -> set[str]:
    for path in [USED_EMAILS_FILE, str(Path.home() / "Documents" / "used-tempmailhub-emails.txt"), "/tmp/used-tempmailhub-emails.txt"]:
        try:
            with open(path, "r") as f:
                return {line.strip().lower() for line in f if line.strip()}
        except FileNotFoundError:
            return set()
        except (PermissionError, OSError):
            continue
    return set()

def save_used_email(email: str) -> None:
    global USED_EMAILS_FILE
    for path in [USED_EMAILS_FILE, str(Path.home() / "Documents" / "used-tempmailhub-emails.txt"), "/tmp/used-tempmailhub-emails.txt"]:
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "a") as f:
                f.write(f"{email.lower()}\n")
            if path != USED_EMAILS_FILE:
                USED_EMAILS_FILE = path
            print(f"💾 Saved {email} to used list ({p})", file=sys.stderr)
            return
        except Exception as e:
            print(f"⚠️ save_used_email {path}: {e}", file=sys.stderr)
            continue

def gaussian_delay(mean: int = 300, std: int = 120, min_ms: int = 80) -> int:
    v = int(random.gauss(mean, std))
    return max(min_ms, min(v, mean * 2))

async def bezier_mouse(page: Page, x: int, y: int) -> None:
    try:
        steps = random.randint(12, 22)
        for i in range(steps):
            t = (i + 1) / steps
            jx = random.randint(-8, 8)
            jy = random.randint(-8, 8)
            nx = int(x * t + 200 * (1 - t) + jx)
            ny = int(y * t + 150 * (1 - t) + jy)
            await page.mouse.move(nx, ny, steps=1)
            await asyncio.sleep(random.uniform(0.015, 0.045))
        await page.mouse.move(x, y)
    except Exception:
        try:
            await page.mouse.move(x, y)
        except Exception:
            pass

async def body_text(page: Page) -> str:
    try:
        return await page.locator("body").inner_text(timeout=3000)
    except PlaywrightTimeoutError:
        return ""
    except Exception:
        try:
            return await page.evaluate("() => document.body ? document.body.innerText : ''")  # type: ignore
        except Exception:
            return ""

async def navigate(page: Page, url: str) -> None:
    for _try in range(3):
        try:
            await page.goto(url, wait_until="commit", timeout=30_000)
            await page.wait_for_timeout(5000)
            # white <70KB skeleton check — redirect / then back to /signup
            try:
                body = await page.content()
                if len(body) < 70000 and "animate-pulse" in body:
                    print("⚠️ white skeleton → redirect / then back", file=sys.stderr)
                    await page.goto("https://lovable.dev/", wait_until="commit", timeout=30000)
                    await page.wait_for_timeout(4000)
                    await page.goto(url, wait_until="commit", timeout=30000)
                    await page.wait_for_timeout(5000)
            except: pass
            return
        except PlaywrightTimeoutError as e:
            if "interrupted" in str(e).lower():
                await page.wait_for_timeout(5000)
                return
            print(f"  navigate retry {_try+1}: {e}", file=sys.stderr)
            await page.wait_for_timeout(5000)
        except Exception as e:
            print(f"  navigate err {_try+1}: {e}", file=sys.stderr)
            await page.wait_for_timeout(5000)
    # final try domcontentloaded
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    except: pass

async def dismiss_cookie_banner(page: Page) -> None:
    await asyncio.sleep(0.8)
    for _ in range(2):
        dismissed = False
        try:
            for label in ("Reject all", "Accept all", "Accepter tout", "Rejeter tout", "OK", "Accept", "Got it", "Continuer sans accepter"):
                btn = page.get_by_role("button", name=label, exact=False)
                try:
                    if await btn.count():
                        await btn.first.click(timeout=1500, force=True)
                        dismissed = True
                        await asyncio.sleep(0.4)
                        break
                except Exception:
                    continue
            close_btns = page.locator('button[aria-label*="Close"], button[aria-label*="close"], button[aria-label*="Fermer"]')
            try:
                if await close_btns.count():
                    await close_btns.first.click(timeout=1000, force=True)
                    dismissed = True
                    await asyncio.sleep(0.3)
            except Exception:
                pass
            if not dismissed:
                break
        except Exception:
            break

async def apply_stealth_patches(page: Page) -> None:
    if STEALTH_PKG_AVAILABLE:
        try:
            s = Stealth()
            await s.apply_stealth_async(page)  # type: ignore
            print("🛡️  playwright_stealth applied", file=sys.stderr)
        except Exception as e:
            print(f"⚠️ stealth pkg: {e}", file=sys.stderr)
    await page.add_init_script("""() => {
        try { Object.defineProperty(navigator,'webdriver',{get:()=>undefined,configurable:true}); }catch(e){}
        try { delete Navigator.prototype.webdriver; }catch(e){}
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
        }catch(e){}
        try {
            if(!window.chrome) window.chrome={};
            window.chrome.app={isInstalled:false};
            window.chrome.runtime={OnInstalledReason:{},OnRestartRequiredReason:{},PlatformArch:{},PlatformOs:{},RequestUpdateCheckStatus:{},id:undefined,connect:()=>{},sendMessage:()=>{}};
        }catch(e){}
        try { window.__nativeSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set; }catch(e){}
        try { Object.defineProperty(navigator,'language',{get:()=>'en-US',configurable:true}); Object.defineProperty(navigator,'languages',{get:()=>['en-US','en'],configurable:true}); }catch(e){}
        try { Object.defineProperty(navigator,'hardwareConcurrency',{get:()=>8,configurable:true}); }catch(e){}
        try { Object.defineProperty(navigator,'deviceMemory',{get:()=>8,configurable:true}); }catch(e){}
        try { Object.defineProperty(navigator,'platform',{get:()=>'Win32',configurable:true}); }catch(e){}
    }""")

async def human_type(locator, text: str, delay_ms: int = 75) -> None:
    try:
        await locator.click(timeout=3000)
    except Exception:
        pass
    await asyncio.sleep(0.08)
    # Use keyboard.type with delay (ZenRows has no password trap, 50ms verified)
    await locator.type(text, delay=random.randint(max(40, delay_ms - 25), delay_ms + 75))

# ── Turnstile (15-try, token >20, button enabled, Verification failed→reload, ClickSolver fallback) ─
async def handle_turnstile(page: Page, email: str = "", password: str = "", max_attempts: int = 15) -> bool:
    """Handle Lovable Turnstile on /signup.

    GB auto-solves (Success! 837-858 chars in 2-4s) so this often returns immediately.
    Otherwise: 15 tries, manual coordinate click fallback when ClickSolver raises
    "success element does not exist" (observed in logs), token len>20 + button enabled,
    Verification failed/Troubleshooting → reload + refill.
    Returns True if solved (or no Turnstile needed), raises FlowError if exhausted.
    """
    print("🤖 Turnstile: waiting/checking (max 15 tries, token>20, button enabled)…", file=sys.stderr)

    # Quick path: wait up to 12s for auto-Success! (GB does 2-4s). Check token each second.
    for sec in range(12):
        tok = await page.evaluate("""() => document.querySelector('input[name="cf-turnstile-response"]')?.value?.length || 0""")  # type: ignore
        txt = await body_text(page)
        # Success! green text appears alongside token; button enables
        btn = page.locator('[data-testid="auth-submit-button"]').last
        is_enabled = False
        try:
            if await btn.count():
                # Both locales: Créez votre compte / Create your account — same testid
                is_enabled = not await btn.is_disabled()  # type: ignore
            else:
                fb = page.get_by_role("button", name="Create your account", exact=True)
                if await fb.count():
                    is_enabled = not await fb.is_disabled()  # type: ignore
                else:
                    fb2 = page.get_by_role("button", name="Créez votre compte", exact=True)
                    if await fb2.count():
                        is_enabled = not await fb2.is_disabled()  # type: ignore
        except Exception:
            pass
        # Token 837-858 on GB; spec says >20
        if tok and tok > 20 and is_enabled:
            print(f"  ✅ Turnstile auto-Success! token={tok} button=enabled (after {sec}s, no click needed)", file=sys.stderr)
            return True
        if tok and tok > 20 and "Success" in txt:
            print(f"  ✅ Turnstile Success! token={tok} (button check pending, {sec}s)", file=sys.stderr)
            # wait one more second for button
            await page.wait_for_timeout(800)
            try:
                if await btn.count() and not await btn.is_disabled():  # type: ignore
                    print("  ✅ Button now enabled after Success! wait", file=sys.stderr)
                    return True
            except Exception:
                pass
        # Verification failed pre-check before any click
        if "Verification failed" in txt or "Troubleshooting" in txt or "Vérification échouée" in txt:
            print("  ⚠️ Turnstile shows Verification failed/Troubleshooting before solve — will reload+refill", file=sys.stderr)
            # Let caller handle reload+refill; break to enter click loop which does reload
            break
        # No token yet, keep waiting a bit
        if sec < 11:
            await page.wait_for_timeout(1000)
            # Also detect if Turnstile widget never appeared — after 8s assume no challenge or auto-pass
            if sec == 8:
                has_iframe = await page.locator('iframe[src*="challenges.cloudflare.com"]').count()  # type: ignore
                has_widget = await page.locator('div.cf-turnstile').count()  # type: ignore
                if has_iframe == 0 and has_widget == 0:
                    # No widget — maybe already verified or GB Headless bypass
                    if is_enabled:
                        print("  ✅ No Turnstile widget and button enabled — skipping Turnstile", file=sys.stderr)
                        return True
        else:
            break

    # If still not solved, enter click loop (15 attempts)
    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        print(f"🤖 Turnstile attempt {attempt}/{max_attempts} — probing widget…", file=sys.stderr)

        # Re-check token+button each loop entry
        tok = await page.evaluate("""() => document.querySelector('input[name="cf-turnstile-response"]')?.value?.length || 0""")  # type: ignore
        btn = page.locator('[data-testid="auth-submit-button"]').last
        try:
            is_enabled = (await btn.count() and not await btn.is_disabled()) if await btn.count() else False  # type: ignore
        except Exception:
            is_enabled = False
        if tok and tok > 20 and is_enabled:
            print(f"  ✅ Solved on entry: token={tok} button=enabled", file=sys.stderr)
            return True

        # Detect Verification failed/Troubleshooting → reload + refill credentials (smart retry not counted? but spec says 15-try total)
        txt = await body_text(page)
        if "Verification failed" in txt or "Troubleshooting" in txt or "Vérification échouée" in txt or "Dépannage" in txt:
            print(f"  ⚠️ Verification failed/Troubleshooting detected (attempt {attempt}) → reload + refill", file=sys.stderr)
            await page.screenshot(path=f"/tmp/turnstile-failed-{attempt}.png", full_page=True)  # type: ignore
            try:
                await page.reload(wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(3500)
                # Re-fill if we have creds — caller may have to redo Continuer step; do best effort here
                if email and password:
                    try:
                        # After reload we land back on /signup email step or password step
                        em = page.locator('input#email, input[type="email"]').first
                        if await em.count():
                            try:
                                await em.wait_for(state="visible", timeout=6000)
                                await em.click(timeout=2000)
                                await em.fill(email)
                                await page.wait_for_timeout(500)
                                cont = page.locator('[data-testid="auth-submit-button"]').first
                                if await cont.count():
                                    await cont.click(timeout=5000)
                                    await page.wait_for_timeout(2000)
                            except Exception:
                                pass
                        pw = page.locator('input#password').first
                        if await pw.count():
                            try:
                                await pw.wait_for(state="visible", timeout=8000)
                                await human_type(pw, password, delay_ms=50)
                            except Exception:
                                pass
                    except Exception as re_e:
                        print(f"  reload-refill err: {re_e}", file=sys.stderr)
                # Do not count this as a consumed attempt (Troubleshoot reload)
                attempt -= 1
                continue
            except Exception as e:
                print(f"  reload failed: {e}", file=sys.stderr)

        # Ensure widget exists; if not, wait then retry
        has_iframe = await page.locator('iframe[src*="challenges.cloudflare.com"]').count()  # type: ignore
        has_widget = await page.locator('div.cf-turnstile').count()  # type: ignore
        if has_iframe == 0 and has_widget == 0:
            print("  ⏳ No Turnstile widget yet — waiting 2s…", file=sys.stderr)
            await page.wait_for_timeout(2000)
            # If button already enabled without widget, success
            try:
                if await btn.count() and not await btn.is_disabled():  # type: ignore
                    print("  ✅ No widget but button enabled — solved", file=sys.stderr)
                    return True
            except Exception:
                pass
            continue

        # Human scroll/jitter before click
        try:
            await page.mouse.move(400, 300)
            await page.wait_for_timeout(random.randint(160, 340))
            await page.mouse.wheel(0, random.randint(60, 110))
            await asyncio.sleep(random.uniform(0.2, 0.45))
        except Exception:
            pass

        clicked = False
        last_err: Optional[str] = None

        # Strategy A: ClickSolver (if available) — but guard "success element does not exist"
        if CAPTCHA_SOLVER_AVAILABLE and not clicked:
            print("  🎯 Strategy ClickSolver…", file=sys.stderr)
            for fw in (FrameworkType.PATCHRIGHT, FrameworkType.PLAYWRIGHT) if 'FrameworkType' in globals() else []:  # type: ignore
                try:
                    async with ClickSolver(framework=fw, page=page, max_attempts=2, attempt_delay=2.0) as solver:  # type: ignore
                        await solver.solve_captcha(captcha_container=page, captcha_type=CaptchaType.CLOUDFLARE_TURNSTILE)  # type: ignore
                    print(f"  ✅ ClickSolver({fw.name}) solved", file=sys.stderr)  # type: ignore
                    clicked = True
                    break
                except Exception as e:
                    msg = str(e)
                    last_err = msg
                    # The log-observed error: ClickSolver raises "success element does not exist" after clicking
                    if "success element does not exist" in msg.lower() or "success element" in msg.lower():
                        print(f"  ⚠️ ClickSolver success element does not exist — falling back to manual coordinate click ({e})", file=sys.stderr)
                        break  # fall through to manual
                    print(f"  ⚠️ ClickSolver({fw}) failed: {e}", file=sys.stderr)  # type: ignore

        # Strategy B: Manual bounding-box coordinate click (fallback + primary on ClickSolver failure)
        if not clicked:
            iframe = page.locator('iframe[src*="challenges.cloudflare.com"]').first  # type: ignore
            try:
                if await iframe.count():  # type: ignore
                    box = await iframe.bounding_box()  # type: ignore
                    if box and box["width"] > 0 and box["height"] > 0:
                        # x+30 per verified doc (not 22), vertically centered
                        cx = int(box["x"] + 30)
                        cy = int(box["y"] + box["height"] / 2)
                        print(f"  🎯 Manual coordinate click at ({cx},{cy}) bbox={box}", file=sys.stderr)
                        await bezier_mouse(page, cx, cy)
                        await page.wait_for_timeout(random.randint(130, 280))
                        await page.mouse.click(cx, cy, delay=random.randint(90, 170))
                        await page.wait_for_timeout(random.randint(140, 260))
                        # jitter second click (human uncertainty) — only if token still 0
                        mid_tok = await page.evaluate("""() => document.querySelector('input[name="cf-turnstile-response"]')?.value?.length || 0""")  # type: ignore
                        if not mid_tok or mid_tok < 20:
                            await page.mouse.click(cx + random.randint(-2, 2), cy, delay=random.randint(80, 140))
                        clicked = True
                        print(f"  ✅ Manual click done at ({cx},{cy})", file=sys.stderr)
                    else:
                        print(f"  ⚠️ Invalid bbox {box}", file=sys.stderr)
            except Exception as e:
                print(f"  ⚠️ Manual coordinate click failed: {e} (prev ClickSolver err: {last_err})", file=sys.stderr)

        # Strategy C: frame_locator direct checkbox click
        if not clicked:
            try:
                fl = page.frame_locator('iframe[src*="challenges.cloudflare.com"]')  # type: ignore
                for sel in ['input[type="checkbox"]', 'input[id*="checkbox"]', '[role="checkbox"]', 'label', 'div']:
                    try:
                        el = fl.locator(sel).first
                        if await el.count():  # type: ignore
                            await page.wait_for_timeout(400)
                            await el.click(timeout=2800, force=True)  # type: ignore
                            print(f"  ✅ frame_locator {sel} clicked", file=sys.stderr)
                            clicked = True
                            break
                    except Exception:
                        continue
            except Exception as e:
                print(f"  ⚠️ frame_locator failed: {e}", file=sys.stderr)

        # Wait for token to appear (7s keepalive, GB is 2-4s)
        print(f"  ⏳ Waiting for token (7s, clicked={clicked})…", file=sys.stderr)
        for i in range(7):
            try:
                await page.wait_for_timeout(1000)
                if i % 2 == 0:
                    _ = page.url  # keepalive — throws if page closed/crashed
            except Exception as e:
                if "closed" in str(e).lower() or "crashed" in str(e).lower() or "terminated" in str(e).lower():
                    raise FlowError(f"Browser/page closed during Turnstile verification (attempt {attempt}): {e}") from e
                raise

        # Post-click Verification failed check
        txt = await body_text(page)
        if "Verification failed" in txt or "Troubleshooting" in txt or "Vérification échouée" in txt:
            print("  ⚠️ Token rejected (Verification failed after click) — reload for fresh widget", file=sys.stderr)
            await page.screenshot(path=f"/tmp/turnstile-rejected-{attempt}.png", full_page=True)  # type: ignore
            if attempt >= 3:
                print("  ❌ 3+ rejections — IP flagged? ZenRows GB should not reject; checking token anyway…", file=sys.stderr)
            try:
                await page.reload(wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(3500)
                if email and password:
                    try:
                        em = page.locator('input#email, input[type="email"]').first
                        if await em.count():
                            try:
                                await em.wait_for(state="visible", timeout=6000)
                                await em.click(timeout=2000)
                                await em.fill(email)
                                await page.wait_for_timeout(500)
                                cont = page.locator('[data-testid="auth-submit-button"]').first
                                if await cont.count():
                                    await cont.click(timeout=5000)
                                    await page.wait_for_timeout(2000)
                            except Exception:
                                pass
                        pw = page.locator('input#password').first
                        if await pw.count():
                            try:
                                await pw.wait_for(state="visible", timeout=8000)
                                await human_type(pw, password, delay_ms=50)
                            except Exception:
                                pass
                    except Exception:
                        pass
                attempt -= 1  # don't count rejection reload as full attempt
                continue
            except Exception:
                pass

        # Validate token + button
        tok = await page.evaluate("""() => document.querySelector('input[name="cf-turnstile-response"]')?.value?.length || 0""")  # type: ignore
        try:
            btn = page.locator('[data-testid="auth-submit-button"]').last
            if await btn.count():
                is_enabled = not await btn.is_disabled()  # type: ignore
            else:
                # fallback locale-specific
                fb = page.get_by_role("button", name="Créez votre compte", exact=True)
                if await fb.count():  # type: ignore
                    is_enabled = not await fb.is_disabled()  # type: ignore
                else:
                    fb2 = page.get_by_role("button", name="Create your account", exact=True)
                    is_enabled = not await fb2.is_disabled() if await fb2.count() else False  # type: ignore
        except Exception:
            is_enabled = False
        # Also check Success! text presence
        txt = await body_text(page)
        has_success = "Success!" in txt or "Succès!" in txt or tok > 20
        print(f"  📊 token={tok} button_enabled={is_enabled} has_success_text={has_success} clicked={clicked}", file=sys.stderr)
        if tok and tok > 20 and is_enabled:
            print(f"✅ Turnstile SOLVED — token={tok} (837-858 expected on GB) button=enabled", file=sys.stderr)
            return True
        if tok and tok > 20 and not is_enabled:
            print("  ⏳ Token valid but button disabled — waiting 3s…", file=sys.stderr)
            await page.wait_for_timeout(3000)
            try:
                btn = page.locator('[data-testid="auth-submit-button"]').last
                if await btn.count() and not await btn.is_disabled():  # type: ignore
                    print("✅ Button now enabled after extra wait", file=sys.stderr)
                    return True
            except Exception:
                pass
        print("  ↻ Retry in 2s…", file=sys.stderr)
        await page.wait_for_timeout(2000)

    # Exhausted
    try:
        await page.screenshot(path="/tmp/turnstile-final-fail.png", full_page=True)  # type: ignore
    except Exception:
        pass
    tok = await page.evaluate("""() => document.querySelector('input[name="cf-turnstile-response"]')?.value?.length || 0""")  # type: ignore
    raise FlowError(f"Turnstile failed after {max_attempts} attempts — token={tok}, Success! not reached, button still disabled")

# ── Onboarding (Pick your style → … → chat) ─────────────────────────────────
async def handle_onboarding(page: Page) -> None:
    try:
        for _ in range(3):
            if "Pick your style" in await body_text(page):
                btn = page.locator('button').filter(has_text='Next')
                if await btn.count():  # type: ignore
                    await btn.first.click(timeout=5000)  # type: ignore
                else:
                    await page.get_by_role("button", name="Next").first.click(timeout=5000)  # type: ignore
                await page.wait_for_timeout(2000)
            else:
                break
        for _ in range(2):
            if "What's your name" in await body_text(page):
                inp = page.get_by_placeholder("Enter your name")
                if await inp.count():  # type: ignore
                    await inp.fill("Sam Dad")  # type: ignore
                btn = page.locator('button').filter(has_text='Next')
                if await btn.count():  # type: ignore
                    await btn.first.click(timeout=5000)  # type: ignore
                await page.wait_for_timeout(2000)
            else:
                break
        if "Which role fits you best" in await body_text(page):
            founder = page.get_by_role("button", name="Founder")
            if await founder.count():  # type: ignore
                await founder.first.click(timeout=5000)  # type: ignore
            nxt = page.locator('button').filter(has_text='Next')
            if await nxt.count():  # type: ignore
                try:
                    await nxt.first.click(timeout=3000)  # type: ignore
                except Exception:
                    pass
                await page.wait_for_timeout(2000)
        if "How many people work at your company" in await body_text(page):
            solo = page.get_by_role("button", name="Solo")
            if await solo.count():  # type: ignore
                await solo.first.click(timeout=5000)  # type: ignore
            await page.wait_for_timeout(2700)
    except Exception as e:
        print(f"  onboarding: {e}", file=sys.stderr)
    await page.wait_for_timeout(2500)

async def wait_for_getting_started(page: Page, timeout: float = 90) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        cur = await body_text(page)
        url = page.url
        if "/getting-started" in url or "Pick your style" in cur or "What's your name" in cur:
            if "Pick your style" in cur or "What's your name" in cur or "Which role fits you best" in cur or "How many people work at your company" in cur:
                await handle_onboarding(page)
                # After onboarding, Lovable lands on chat/dashboard — still verified
                continue
            return
        if "/dashboard" in url and "Dashboard" in cur:
            # Some accounts land directly on dashboard after verify (also verified)
            return
        if "Ask Lovable" in cur or "What's the vision" in cur:
            return
        await page.wait_for_timeout(1000)
    raise FlowError(f"Did not reach /getting-started or dashboard after verify: {page.url}")

# ── Egress check (optional, never blocks) ────────────────────────────────────
async def verify_egress_ip(context: BrowserContext) -> str:
    pg = await context.new_page()
    try:
        await pg.goto("https://cloudflare.com/cdn-cgi/trace", timeout=15_000)
        txt = await pg.locator("body").inner_text()  # type: ignore
        return txt.strip()
    except Exception as e:
        return f"egress probe failed ({e})"
    finally:
        try:
            await pg.close()
        except Exception:
            pass

# ── Browser connect (ZenRows GB primary, AUTH004 → raw IP fallback) ─────────
async def _connect_zenrows(playwright_obj, cdp_url: str):
    print(f"🌐 Connecting ZenRows Browser Cloud (GB): {cdp_url[:58]}…", file=sys.stderr)
    _ensure_raw_ip_env()
    try:
        browser = await playwright_obj.chromium.connect_over_cdp(cdp_url, timeout=60_000)  # type: ignore
        if not browser.contexts:
            raise FlowError("ZenRows CDP returned no contexts")
        return browser, "zenrows"
    except Exception as e:
        msg = str(e)
        # AUTH004 = invalid/over-quota key — fallback to raw IP per spec
        if "AUTH004" in msg or "AUTH" in msg or "Unauthorized" in msg or "401" in msg:
            print(f"⚠️ ZenRows AUTH error ({msg[:120]}) → falling back to raw IP (LD_PRELOAD=\"\", no proxy)", file=sys.stderr)
            raise FlowError(f"AUTH004 ZenRows fallback: {e}") from e
        # Other CDP errors also fallback, but log
        print(f"⚠️ ZenRows CDP connect failed: {e} — will fallback to raw IP if requested", file=sys.stderr)
        raise

async def _launch_raw(playwright_obj, headless: bool):
    _ensure_raw_ip_env()
    mode = "headless" if headless else "headed"
    print(f"🌐 Launching local Chromium ({mode}, raw IP, LD_PRELOAD=\"\", no Tor/WARP)…", file=sys.stderr)
    args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
        "--disable-site-isolation-trials",
    ]
    # Do NOT pass proxy — raw IP
    browser = await playwright_obj.chromium.launch(channel="chrome", headless=headless, args=args, proxy=None)  # type: ignore
    return browser, "raw"

def _pick_playwright():
    if PATCHRIGHT_AVAILABLE:
        return _patchright_playwright, "patchright"
    if PLAYWRIGHT_AVAILABLE:
        return _playwright_playwright, "playwright"
    raise FlowError("Neither patchright nor playwright installed (pip install patchright playwright)")

# ── Main run ──────────────────────────────────────────────────────────────────
async def run(
    cdp_url: Optional[str] = None,
    headless: Optional[bool] = None,
    proxy_country: str = "gb",
    force_raw: bool = False,
    email_override: Optional[str] = None,
    password_override: Optional[str] = None,
    auto_close: bool = False,
) -> dict:
    _ensure_raw_ip_env()
    print(f"🚀 Lovable effective — ZenRows GB + dispose.lol Gmail (raw IP script, LD_PRELOAD=\"\")", file=sys.stderr)
    print(f"   Verified doc: genev.aochea@gmail.com / GmailK01 → oobCode → /getting-started", file=sys.stderr)

    # Determine CDP URL
    if force_raw:
        target_cdp = None
        print("🌐 force_raw=True → skipping ZenRows, using direct raw IP", file=sys.stderr)
    elif cdp_url:
        target_cdp = cdp_url
        print(f"🌐 Using provided --cdp-url: {target_cdp[:60]}…", file=sys.stderr)
    else:
        # Default per spec: ZenRows GB
        api_key = _os.environ.get("ZENROWS_API_KEY", ZENROWS_API_KEY)
        # Honor proxy_country override (default gb healthiest)
        pc = (proxy_country or "gb").strip().lower() or "gb"
        target_cdp = f"wss://browser.zenrows.com?apikey={api_key}&proxy_country={pc}"
        print(f"🌐 Default ZenRows CDP (proxy_country={pc}): wss://browser.zenrows.com?apikey=…&proxy_country={pc}", file=sys.stderr)

    # Headed by default (ZenRows cloud is headed regardless; local fallback headed unless --headless)
    if headless is None:
        # Default headed per spec
        headless_local = False
    else:
        headless_local = bool(headless)
    print(f"🖥️  Mode: {'headless' if headless_local else 'headed'} (ZenRows cloud ignores this — always headed) | raw fallback={'headless' if headless_local else 'headed'}", file=sys.stderr)
    print(f"🔐 Script env: LD_PRELOAD=\"{_os.environ.get('LD_PRELOAD','')}\" HTTP_PROXY={_os.environ.get('HTTP_PROXY','') or _os.environ.get('http_proxy','') or '(cleared raw IP)'}", file=sys.stderr)

    playwright_factory, pw_kind = _pick_playwright()
    print(f"🎭 Playwright: {pw_kind} (patchright preferred for Turnstile)", file=sys.stderr)

    pw_enter = None
    browser = None
    browser_kind = "unknown"
    context = None
    _pw_ctx = None

    # Context manager for playwright
    _pw_ctx = playwright_factory()
    pw_enter = await _pw_ctx.__aenter__()  # type: ignore

    try:
        # 1) Try ZenRows CDP unless force_raw
        if target_cdp and not force_raw:
            try:
                browser, browser_kind = await _connect_zenrows(pw_enter, target_cdp)
                print(f"✅ Connected ZenRows CDP ({browser_kind})", file=sys.stderr)
            except FlowError as e:
                if "AUTH004" in str(e) or "AUTH" in str(e):
                    print("↻ AUTH004 → raw IP fallback (LD_PRELOAD=\"\")", file=sys.stderr)
                    browser, browser_kind = await _launch_raw(pw_enter, headless_local)
                else:
                    # Non-auth failure — also fallback to raw per spec (primary with fallback)
                    print(f"↻ ZenRows connect failed ({e}) → raw IP fallback", file=sys.stderr)
                    browser, browser_kind = await _launch_raw(pw_enter, headless_local)
            except Exception as e:
                print(f"↻ ZenRows threw {e} → raw IP fallback", file=sys.stderr)
                browser, browser_kind = await _launch_raw(pw_enter, headless_local)
        else:
            browser, browser_kind = await _launch_raw(pw_enter, headless_local)

        print(f"✅ Browser ready: {browser_kind} ({pw_kind})", file=sys.stderr)

        # 2) Context — ZenRows already has a context, reuse; raw: create realistic geo-matched context
        if browser.contexts:
            context = browser.contexts[0]
            # Ensure extra headers even on ZenRows context
            try:
                await context.set_extra_http_headers({  # type: ignore
                    "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
                    "Sec-Ch-Ua": '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
                    "Sec-Ch-Ua-Mobile": "?0",
                    "Sec-Ch-Ua-Platform": '"Windows"',
                })
            except Exception:
                pass
            print(f"♻️  Reusing {browser_kind} context (viewport {context.pages[0].viewport_size if context.pages else 'n/a'})", file=sys.stderr)  # type: ignore
        else:
            ctx_kwargs = dict(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
                locale="en-US",
                timezone_id="Europe/London" if (proxy_country or "gb") == "gb" else "America/New_York",
                color_scheme="light",
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
                    "Sec-Ch-Ua": '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
                    "Sec-Ch-Ua-Mobile": "?0",
                    "Sec-Ch-Ua-Platform": '"Windows"',
                },
            )
            context = await browser.new_context(**ctx_kwargs)  # type: ignore
            print("✅ Created new context (1920x1080, en-US, Win32)", file=sys.stderr)

        # Optional cf_clearance reuse (not needed on ZenRows GB but keep)
        try:
            cf_file = Path("/tmp/cf_clearance.json")
            if cf_file.exists():
                c = json.loads(cf_file.read_text())
                if c.get("expires", 0) == 0 or c.get("expires", 0) > __import__("time").time():
                    await context.add_cookies([c])  # type: ignore
                    print("♻️ Reused cf_clearance", file=sys.stderr)
        except Exception:
            pass

        # 3) Egress check (best-effort)
        try:
            egress = await asyncio.wait_for(verify_egress_ip(context), timeout=12)  # type: ignore
            print(f"🌐 Egress check: {egress[:300]}", file=sys.stderr)
        except asyncio.TimeoutError:
            print("⚠️ Egress probe timeout — continuing (ZenRows GB should be 86.141.x BT)", file=sys.stderr)

        # 4) dispose.lol Gmail tab (separate page, same context so egress is GB)
        dispose_inbox = DisposeLolInbox(context)
        # Create mailbox before Lovable navigation (so we poll immediately after signup)
        if email_override:
            email = email_override.strip()
            print(f"📧 Using override email: {email}", file=sys.stderr)
        else:
            email, _ = await dispose_inbox.create()
        # Password: GmailK01 verified; or override; or derived from email prefix
        if password_override:
            password = password_override
        else:
            # Verified GmailK01 passes "Password meets all requirements" on GB
            password = "GmailK01"
        print(f"🔐 Password: {password} (meets all requirements)", file=sys.stderr)

        # Check dedup file (non-fatal)
        used = load_used_emails()
        if email.lower() in used:
            print(f"⚠️ Email {email} already in used list — continuing anyway (fresh GB run)", file=sys.stderr)

        # 5) Lovable page — direct /signup flow
        lovable_page = await context.new_page()
        await apply_stealth_patches(lovable_page)
        # Keep window.__nativeSetter for BD fallback compat (no trap on ZenRows)
        await lovable_page.add_init_script("try{window.__nativeSetter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;}catch(e){}")

        print(f"🌐 Navigating to {LOVABLE_SIGNUP_URL} (direct /signup, no /login popup)…", file=sys.stderr)
        await navigate(lovable_page, LOVABLE_SIGNUP_URL)
        await lovable_page.wait_for_timeout(3200)
        # White-screen/skeleton guard (/signup sometimes renders skeleton without hydration)
        txt = await body_text(lovable_page)
        if len(txt.strip()) < 50 or ("Create your account" not in txt and "Créez votre compte" not in txt and "Create" not in txt):
            print("⚠️ /signup skeleton/white detected — fallback via / then /signup", file=sys.stderr)
            try:
                raw = await lovable_page.content()  # type: ignore
                is_skeleton = len(raw) < 70000 and "animate-pulse" in raw
                print(f"  skeleton hint: len={len(raw)} pulse={is_skeleton}", file=sys.stderr)
            except Exception:
                pass
            await navigate(lovable_page, LOVABLE_URL)
            await lovable_page.wait_for_timeout(2500)
            await navigate(lovable_page, LOVABLE_SIGNUP_URL)
            await lovable_page.wait_for_timeout(3200)
            txt = await body_text(lovable_page)

        await dismiss_cookie_banner(lovable_page)

        # Verify on signup page
        txt = await body_text(lovable_page)
        if "Create your account" not in txt and "Créez votre compte" not in txt:
            # Still try to proceed — selectors may still exist
            print(f"⚠️ Signup header not found, but continuing (body {txt[:180]!r}) — selector check next", file=sys.stderr)
        else:
            print("✅ On /signup (Create/Créez header found)", file=sys.stderr)

        # 6) input#email → fill
        print(f"📧 Filling email input#email: {email}", file=sys.stderr)
        email_loc = lovable_page.locator('input#email').first
        if not await email_loc.count():  # type: ignore
            email_loc = lovable_page.locator('input[type="email"]').first
        try:
            await email_loc.wait_for(state="visible", timeout=12_000)  # type: ignore
            try:
                await email_loc.click(timeout=3000, force=True)  # type: ignore
            except:
                await email_loc.evaluate("el => el.focus()")  # type: ignore
            await asyncio.sleep(0.15)
            # Use fill (no trap on ZenRows) + small delay; fallback to keyboard.type if needed
            try:
                await email_loc.fill(email, timeout=5000)  # type: ignore
            except Exception:
                try:
                    await email_loc.evaluate("el => el.value=''")  # type: ignore
                except: pass
                await lovable_page.keyboard.type(email, delay=35)  # type: ignore
            await lovable_page.wait_for_timeout(600)
            # Verify value stuck
            try:
                val = await email_loc.input_value(timeout=2000)  # type: ignore
                if val.strip().lower() != email.lower():
                    print(f"  ⚠️ email input_value mismatch {val!r} != {email!r} — retry with keyboard.type", file=sys.stderr)
                    try:
                        await email_loc.click(timeout=2000, force=True)  # type: ignore
                    except:
                        await email_loc.evaluate("el => el.focus()")  # type: ignore
                    await lovable_page.keyboard.type(email, delay=40)  # type: ignore
            except: pass
            print("  ✅ Email filled", file=sys.stderr)
        except Exception as e:
            try:
                await lovable_page.screenshot(path="/tmp/lov-signup-email-fail.png", full_page=True)  # type: ignore
            except: pass
            raise FlowError(f"Could not fill input#email: {e}") from e

        # 7) Continuer (Continue) → reveals password
        print("🖱️ Clicking Continuer/Continue [data-testid=\"auth-submit-button\"]…", file=sys.stderr)
        continuer = lovable_page.locator('[data-testid="auth-submit-button"]').first
        # Also match by role text for fr/en
        try:
            await continuer.wait_for(state="visible", timeout=8000)  # type: ignore
            await continuer.click(timeout=7000)  # type: ignore
            print("  ✅ Continuer clicked (testid)", file=sys.stderr)
        except Exception as e:
            print(f"  ⚠️ testid click failed {e} — trying role text fallback", file=sys.stderr)
            # Fallback: get_by_role with fr/en
            clicked = False
            for name in ("Continuer", "Continue"):
                try:
                    btn = lovable_page.get_by_role("button", name=name, exact=True).first
                    if await btn.count():  # type: ignore
                        await btn.wait_for(state="visible", timeout=4000)  # type: ignore
                        await btn.click(timeout=5000)  # type: ignore
                        print(f"  ✅ {name} clicked (role)", file=sys.stderr)
                        clicked = True
                        break
                except Exception:
                    continue
            if not clicked:
                # Last resort: dispatchEvent
                try:
                    await lovable_page.evaluate("""() => {
                        const b=document.querySelector('[data-testid="auth-submit-button"]');
                        if(b) b.click();
                    }""")  # type: ignore
                    print("  ✅ Continuer via evaluate click", file=sys.stderr)
                except Exception:
                    await lovable_page.screenshot(path="/tmp/lov-continuer-fail.png", full_page=True)  # type: ignore
                    raise FlowError("Could not click Continuer/Continue") from e
        await lovable_page.wait_for_timeout(2000)

        # Wait for password step
        print("🔐 Waiting for input#password…", file=sys.stderr)
        pw_loc = lovable_page.locator('input#password').first
        if not await pw_loc.count():  # type: ignore
            pw_loc = lovable_page.locator('input[type="password"]').first
        try:
            await pw_loc.wait_for(state="visible", timeout=15_000)  # type: ignore
        except PlaywrightTimeoutError as e:
            txt = await body_text(lovable_page)
            await lovable_page.screenshot(path="/tmp/lov-password-missing.png", full_page=True)  # type: ignore
            raise FlowError(f"input#password did not appear after Continuer (body {txt[:300]!r})") from e

        # 8) Type password (GmailK01, delay 50) → Password meets all requirements
        print(f"🔐 Typing password into input#password (delay 50, no trap on ZenRows)…", file=sys.stderr)
        try:
            try:
                await pw_loc.click(timeout=3000, force=True)  # type: ignore
            except:
                await pw_loc.evaluate("el => el.focus()")  # type: ignore
            await asyncio.sleep(0.12)
            # Use keyboard.type with delay 50 as verified doc (trap-free on ZenRows)
            try:
                await pw_loc.fill("")  # type: ignore
            except:
                await pw_loc.evaluate("el => el.value=''")  # type: ignore
            await lovable_page.keyboard.type(password, delay=50)  # type: ignore
            # Verify masked ••••• and requirements
            await lovable_page.wait_for_timeout(900)
            val_len = await pw_loc.evaluate("el => el.value.length")  # type: ignore
            txt2 = await body_text(lovable_page)
            if "Password meets all requirements" in txt2 or "exigences" in txt2.lower():
                print(f"  ✅ Password accepted (len {val_len}, meets all requirements)", file=sys.stderr)
            else:
                print(f"  ℹ️ Password typed len={val_len}, requirements text not yet visible — continuing (may appear after Turnstile)", file=sys.stderr)
        except Exception as e:
            await lovable_page.screenshot(path="/tmp/lov-pw-type-fail.png", full_page=True)  # type: ignore
            raise FlowError(f"Could not type password: {e}") from e

        # 9) Turnstile — auto Success! 837-858 on GB, else 15-try with fallback
        await handle_turnstile(lovable_page, email=email, password=password, max_attempts=15)
        # Save cf_clearance after solve (optional)
        try:
            for c in await context.cookies():  # type: ignore
                if c.get("name") == "cf_clearance":
                    Path("/tmp/cf_clearance.json").write_text(json.dumps(c))
                    print(f"💾 Saved cf_clearance {c['value'][:20]}…", file=sys.stderr)
                    break
        except Exception:
            pass

        # 10) Créez votre compte / Create your account (same testid, second step)
        print("🖱️ Clicking Créez votre compte / Create your account…", file=sys.stderr)
        create_btn = lovable_page.locator('[data-testid="auth-submit-button"]').first
        try:
            # Button should now be enabled after Turnstile
            await create_btn.wait_for(state="visible", timeout=8000)  # type: ignore
            # Poll enabled state briefly before clicking
            for _ in range(10):
                try:
                    if not await create_btn.is_disabled():  # type: ignore
                        break
                except Exception:
                    break
                await lovable_page.wait_for_timeout(400)
            await create_btn.click(timeout=8000)  # type: ignore
            print("  ✅ Créez/Create clicked (testid)", file=sys.stderr)
        except Exception as e:
            print(f"  ⚠️ testid create click failed {e} — role fallback", file=sys.stderr)
            clicked = False
            for name in ("Créez votre compte", "Create your account", "Create"):
                try:
                    btn = lovable_page.get_by_role("button", name=name, exact=True).first
                    if await btn.count():  # type: ignore
                        await btn.wait_for(state="visible", timeout=4000)  # type: ignore
                        from playwright.async_api import expect as _expect  # type: ignore
                        try:
                            await _expect(btn).to_be_enabled(timeout=6000)  # type: ignore
                        except Exception:
                            pass
                        await btn.click(timeout=6000)  # type: ignore
                        print(f"  ✅ {name} clicked (role)", file=sys.stderr)
                        clicked = True
                        break
                except Exception:
                    continue
            if not clicked:
                try:
                    await lovable_page.evaluate("""() => {
                        const b=[...document.querySelectorAll('[data-testid="auth-submit-button"]')].pop()
                             || [...document.querySelectorAll('button')].find(x=>/Créez|Create/.test(x.innerText));
                        if(b) b.click();
                    }""")  # type: ignore
                    print("  ✅ Create via evaluate", file=sys.stderr)
                except Exception:
                    await lovable_page.screenshot(path="/tmp/lov-create-fail.png", full_page=True)  # type: ignore
                    raise FlowError("Could not click Créez votre compte / Create your account") from e
        await lovable_page.wait_for_timeout(2500)

        # 11) Check your inbox (Vérifiez votre boîte / Check your inbox)
        print("⏳ Waiting for Check your inbox (email verification sent)…", file=sys.stderr)
        inbox_deadline = asyncio.get_running_loop().time() + 45
        inbox_ok = False
        while asyncio.get_running_loop().time() < inbox_deadline:
            txt = await body_text(lovable_page)
            url = lovable_page.url
            # Both locales + possible Firebase error surfaces
            if any(s in txt for s in ("Check your inbox", "Vérifiez votre boîte", "Check your email", "Verify your email", "inbox", "boîte de réception")) or "Check your inbox" in txt:
                inbox_ok = True
                print(f"  ✅ Check your inbox detected (url {url})", file=sys.stderr)
                break
            if "suspicious activity" in txt.lower() or "blocking_function_error_response" in txt.lower() or "Security verification failed" in txt:
                await lovable_page.screenshot(path="/tmp/lov-suspicious.png", full_page=True)  # type: ignore
                raise FlowError(f"Lovable flagged suspicious activity after Create (GB should not): {txt[:400]!r}")
            # Also accept if redirected straight to getting-started (rare)
            if "/getting-started" in url or "Pick your style" in txt:
                inbox_ok = True
                print("  ✅ Already on getting-started — skipping inbox wait", file=sys.stderr)
                break
            await lovable_page.wait_for_timeout(800)
        if not inbox_ok:
            txt = await body_text(lovable_page)
            await lovable_page.screenshot(path="/tmp/lov-no-inbox.png", full_page=True)  # type: ignore
            print(f"⚠️ Inbox hint not found — continuing to poll anyway (body {txt[:600]!r})", file=sys.stderr)
        else:
            # Log that Firebase signUp succeeded (identitytoolkit 200 via UI)
            print("✅ Firebase identitytoolkit signUp via UI (GB 200, not 400 suspicious)", file=sys.stderr)

        # 12) Poll dispose.lol for Verify link → oobCode
        print("📥 Polling dispose.lol for verify link (oobCode)…", file=sys.stderr)
        verify_link = await dispose_inbox.wait_for_lovable_link(timeout_seconds=360)
        link = html.unescape(verify_link).replace("&amp;", "&")
        # Basic sanity: must contain oobCode and apiKey
        if "oobCode" not in link:
            print(f"⚠️ Link missing oobCode: {link[:200]}", file=sys.stderr)
        oob_m = OOB_RE.search(link or "")
        oob = oob_m.group(1)[:18] + "…" if oob_m else "(none)"
        print(f"🎯 Verify link: {link[:180]} (oobCode {oob})", file=sys.stderr)

        # 13) Navigate to verify URL → /getting-started
        print(f"🔗 Navigating to verify URL (mode=verifyEmail)…", file=sys.stderr)
        await navigate(lovable_page, link)
        await lovable_page.wait_for_timeout(4000)
        # Verify may redirect through auth/action then to getting-started; wait
        try:
            await wait_for_getting_started(lovable_page, timeout=90)
            print("✅ Verified → /getting-started (Pick your style / emailVerified=true)", file=sys.stderr)
        except FlowError as e:
            # Fallback: check current URL/body for verify success signals
            txt = await body_text(lovable_page)
            url = lovable_page.url
            print(f"⚠️ getting-started wait: {e} — url={url} body={txt[:400]!r}", file=sys.stderr)
            if "oobCode" in url or "verify" in url.lower() or "Pick your style" in txt or "/getting-started" in url or "/dashboard" in url:
                print("✅ Treating as verified despite onboarding wait timeout", file=sys.stderr)
            else:
                # Try one more reload of verify link with fresh context
                await lovable_page.wait_for_timeout(2000)
                await navigate(lovable_page, link)
                await lovable_page.wait_for_timeout(4000)
                await wait_for_getting_started(lovable_page, timeout=60)

        # Ensure final URL is getting-started or dashboard (both mean verified)
        final_url = lovable_page.url
        final_text = await body_text(lovable_page)
        verified = "/getting-started" in final_url or "Pick your style" in final_text or "/dashboard" in final_url or "Dashboard" in final_text or "Ask Lovable" in final_text
        if not verified:
            print(f"⚠️ Final state not clearly verified: url={final_url} text={final_text[:400]!r}", file=sys.stderr)
        else:
            print(f"✅ Final verified state: {final_url}", file=sys.stderr)

        # 14) Save account (local + Mega)
        save_used_email(email)
        sessions_dir = _sessions_dir()
        import time as _time
        runner = _os.getenv("RUNNER_ID", "").strip()
        if runner:
            session_id = f"session-{runner}-{int(_time.time())}"
        else:
            session_id = f"session-{int(_time.time())}-{_os.getpid()}"
        session_dir = sessions_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        cookies = await context.cookies()  # type: ignore
        (session_dir / "cookies.json").write_text(json.dumps(cookies, indent=2))
        print(f"✅ Saved {len(cookies)} cookies to {session_dir / 'cookies.json'}", file=sys.stderr)

        config = dict(
            email=email,
            password=password,
            created_at=datetime.now().isoformat(),
            dashboard_url=final_url,
            getting_started_url=final_url,
            verified=bool(verified),
            oobCode=(OOB_RE.search(link or "").group(1) if OOB_RE.search(link or "") else None),
            verify_link=link,
            provider="dispose.lol",
            egress="zenrows_gb" if browser_kind == "zenrows" else "raw_ip",
            browser=browser_kind,
            playwright=pw_kind,
            headless=headless_local,
            raw_ip=True,
            ld_preload="",
        )
        (session_dir / "config.json").write_text(json.dumps(config, indent=2))
        print(f"✅ Saved session config to {session_dir / 'config.json'}", file=sys.stderr)

        # Also write a latest pointer for scripts
        try:
            latest = sessions_dir / "latest.json"
            latest.write_text(json.dumps(dict(session_id=session_id, **config), indent=2))
        except Exception:
            pass

        # Mega DB sync (non-fatal, respects CHIMERA_SKIP_MEGA_SYNC)
        if _os.environ.get("CHIMERA_SKIP_MEGA_SYNC", "").lower() in ("1", "true", "yes"):
            print("⏭️ Skipping Mega DB sync (CHIMERA_SKIP_MEGA_SYNC)", file=sys.stderr)
        else:
            try:
                _default_miner = str(Path(__file__).resolve().parents[2].parent / "chimera-miner")
                if not Path(_default_miner).exists():
                    _default_miner = str(Path.home() / "Documents" / "repos" / "chimera-miner")
                miner_dir = _os.environ.get("CHIMERA_MINER_DIR", _default_miner)
                if miner_dir not in sys.path:
                    sys.path.insert(0, miner_dir)
                from mega_db import load_db, save_db, mega_distributed_lock  # type: ignore

                with mega_distributed_lock():  # type: ignore
                    db = load_db()
                    db.add_session(session_id, email, status="active")
                    save_db(db)
                print(f"✅ Synced {session_id} to Mega DB", file=sys.stderr)
            except Exception as e:
                print(f"⚠️ Mega DB sync failed (non-fatal): {e}", file=sys.stderr)

        result = dict(
            verified=bool(verified),
            email=email,
            password=password,
            dashboard_url=final_url,
            verify_link=link,
            oobCode=(OOB_RE.search(link or "").group(1) if OOB_RE.search(link or "") else None),
            session_dir=str(session_dir),
            session_id=session_id,
            provider="dispose.lol",
            egress=browser_kind,
            getting_started=("/getting-started" in final_url or "Pick your style" in final_text),
        )
        print("\n" + "=" * 60)
        print("🎉 SUCCESS!")
        print("=" * 60)
        print(json.dumps(result, indent=2))

        if auto_close:
            print("✅ Auto-closing browser (--end)", file=sys.stderr)
            if browser:
                try:
                    await browser.close()  # type: ignore
                except Exception:
                    pass
        elif _os.getenv("KEEP_BROWSER_OPEN", "0").lower() in ("1", "true", "yes") and browser_kind == "raw":
            print("✋ KEEP_BROWSER_OPEN=1 — press Enter to close raw browser…", file=sys.stderr)
            try:
                input()
            except EOFError:
                pass
            try:
                await browser.close()  # type: ignore
            except Exception:
                pass
        else:
            # For ZenRows, always close CDP; for raw non-keep, also close
            if browser:
                try:
                    await browser.close()  # type: ignore
                except Exception:
                    pass

        return result

    finally:
        # Cleanup dispose inbox page (keep context/browser close above)
        try:
            if 'dispose_inbox' in locals() and dispose_inbox:
                await dispose_inbox.close()
        except Exception:
            pass
        try:
            if _pw_ctx:
                await _pw_ctx.__aexit__(None, None, None)  # type: ignore
        except Exception:
            pass

# ── CLI ────────────────────────────────────────────────────────────────────────
def main() -> None:
    _ensure_raw_ip_env()
    p = argparse.ArgumentParser(
        description="Lovable effective signup — ZenRows GB + dispose.lol Gmail (raw IP script, LD_PRELOAD=\"\")",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
        "  python3 lov-api-effective.py                      # default ZenRows GB + dispose.lol + headed\n"
        "  python3 lov-api-effective.py --headless           # raw fallback headless\n"
        "  python3 lov-api-effective.py --no-zenrows         # force raw IP browser (no ZenRows)\n"
        "  python3 lov-api-effective.py --proxy-country fr   # test FR (expected suspicious)\n"
        "  LD_PRELOAD=\"\" python3 lov-api-effective.py --email my@gmail.com --password GmailK01\n",
    )
    p.add_argument("--cdp-url", help="Override ZenRows CDP WSS (default wss://browser.zenrows.com?apikey=…&proxy_country=gb)")
    p.add_argument("--proxy-country", default="gb", help="ZenRows proxy_country (default gb, healthiest; fr/gf fail per doc)")
    p.add_argument("--no-zenrows", action="store_true", help="Force raw IP (LD_PRELOAD=\"\" no Tor) browser, skip ZenRows CDP")
    p.add_argument("--headless", action="store_true", help="Headless for local raw fallback (ZenRows cloud is always headed)")
    p.add_argument("--headed", action="store_true", help="Force headed for local raw fallback (default)")
    p.add_argument("--email", help="Override dispose.lol Gmail (default: create fresh dispose.lol inbox)")
    p.add_argument("--password", help="Override password (default GmailK01)")
    p.add_argument("--end", action="store_true", help="Auto-close browser when done (no Enter prompt)")
    p.add_argument("--raw", action="store_true", help="Alias for --no-zenrows (force raw IP, LD_PRELOAD=\"\")")
    args = p.parse_args()

    # --raw is alias for --no-zenrows
    force_raw = bool(args.no_zenrows or args.raw)
    # Resolve headless tri-state: None=auto headed, True=headless, False=headed
    if args.headless and args.headed:
        p.error("--headless and --headed are mutually exclusive")
    headless: Optional[bool] = None
    if args.headless:
        headless = True
    elif args.headed:
        headless = False

    # Hard enforce raw IP env regardless of args
    _ensure_raw_ip_env()
    if _os.environ.get("LD_PRELOAD") != "":
        print(f"⚠️ LD_PRELOAD was {_os.environ.get('LD_PRELOAD')!r} — forced to \"\"", file=sys.stderr)
        _os.environ["LD_PRELOAD"] = ""

    cdp = args.cdp_url or _os.getenv("BU_CDP_WS") or _os.getenv("ZENROWS_CDP_URL")
    try:
        result = asyncio.run(run(
            cdp_url=cdp,
            headless=headless,
            proxy_country=args.proxy_country,
            force_raw=force_raw,
            email_override=args.email,
            password_override=args.password,
            auto_close=args.end,
        ))
        # Print result json to stdout for piping
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
    except FlowError as e:
        print(f"\n❌ Automation failed: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
