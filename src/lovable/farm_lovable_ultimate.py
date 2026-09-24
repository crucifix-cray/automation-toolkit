#!/usr/bin/env python3
"""Ultimate Lovable farm — OnK stealth CDP + mail chain + signup + 2FA + GH push.

Proof / single shot:
  HOLY_SECRET_KEY=… KERNEL_API_KEY=sk_… \\
    python3 src/lovable/farm_lovable_ultimate.py --once

Done = verified + totp_secret + farm/lov-* branch pushed.
Mega skipped (SKIP_MEGA=1).
"""
from __future__ import annotations

import os as _os

_os.environ["LD_PRELOAD"] = ""
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
           "ALL_PROXY", "all_proxy", "PLAYWRIGHT_PROXY_URL"):
    _os.environ.pop(_k, None)
_os.environ.setdefault("SKIP_MEGA", "1")
_os.environ.setdefault("CHIMERA_SKIP_MEGA_SYNC", "1")

import argparse
import asyncio
import fcntl
import html
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SESSIONS = REPO / "scripts" / "sessions"
API = "https://api.onkernel.com"
PASSWORD_DEFAULT = "GmailK01"
LOVABLE_SIGNUP = "https://lovable.dev/signup"
LOVABLE_HOME = "https://lovable.dev/"

sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src" / "lovable"))

from mail_chain import acquire_mailbox, LOVABLE_VERIFY_RE  # noqa: E402
from account_creation import (  # noqa: E402
    FlowError,
    apply_stealth_patches,
    body_text,
    dismiss_cookie_banner,
    handle_turnstile,
    navigate,
    save_used_email,
    wait_for_getting_started,
)


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _load_holy() -> None:
    if _os.environ.get("HOLY_SECRET_KEY", "").strip():
        return
    local = REPO / "finals" / "secrets" / "holy_secret_key.local"
    if local.is_file():
        _os.environ["HOLY_SECRET_KEY"] = local.read_text().strip()


def api(key: str, method: str, path: str, body: dict | None = None) -> tuple[int, str]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        API + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")
    except Exception as e:
        return 0, str(e)


def ensure_mobile_proxy(key: str, name: str, country: str = "gb") -> bool:
    """Mint OnK mobile proxy. Default country=gb — Lovable Firebase rejects US egress."""
    code, body = api(key, "POST", "/proxies", {
        "name": name, "type": "mobile", "config": {"country": country},
    })
    if code in (200, 201):
        return True
    c2, b2 = api(key, "GET", "/proxies")
    if c2 == 200:
        try:
            for p in json.loads(b2):
                if p.get("name") == name and p.get("id"):
                    api(key, "DELETE", f"/proxies/{p['id']}")
        except Exception:
            pass
        code, body = api(key, "POST", "/proxies", {
            "name": name, "type": "mobile", "config": {"country": country},
        })
        if code in (200, 201):
            return True
    log(f"  proxy create fail {code}: {body[:200]}")
    return False


def delete_proxy_named(key: str, name: str) -> None:
    c, b = api(key, "GET", "/proxies")
    if c != 200:
        return
    try:
        for p in json.loads(b):
            if p.get("name") == name and p.get("id"):
                api(key, "DELETE", f"/proxies/{p['id']}")
                log(f"🗑️  proxy {name} deleted")
    except Exception:
        pass


def create_browser(key: str, proxy_name: str) -> dict:
    import shlex
    px = f" --proxy-name {shlex.quote(proxy_name)}" if proxy_name else ""
    # start on / not /signup — first nav to signup hydrates cleaner on mobile-US
    cmd = f"kernel browsers create --stealth --timeout 900{px} --start-url {shlex.quote(LOVABLE_HOME)} -o json"
    env = {**_os.environ, "KERNEL_API_KEY": key, "LD_PRELOAD": ""}
    last = "unknown"
    for t in range(3):
        try:
            out = subprocess.check_output(cmd, shell=True, env=env, text=True, timeout=90)
            data = json.loads(out)
            log(f"🌐 Browser live: {data.get('browser_live_view_url', '')}")
            log(f"   SID: {data['session_id']}")
            return data
        except Exception as e:
            last = str(e)[:150]
            log(f"  browser create try {t+1}/3: {last}")
            time.sleep(15)
    raise FlowError(f"browser create failed: {last}")


def delete_browser(key: str, sid: str) -> None:
    env = {**_os.environ, "KERNEL_API_KEY": key, "LD_PRELOAD": ""}
    try:
        subprocess.run(f"kernel browsers delete {sid}", shell=True, env=env,
                       timeout=20, capture_output=True)
        log(f"🗑️  Browser {sid} deleted")
    except Exception as e:
        log(f"  delete browser err: {e}")


def reserve_session_dir() -> tuple[int, Path]:
    SESSIONS.mkdir(parents=True, exist_ok=True)
    lock = SESSIONS / ".session_num.lock"
    with open(lock, "a+") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        nums = []
        for p in SESSIONS.iterdir():
            if p.is_dir() and p.name.startswith("session-"):
                parts = p.name.split("-")
                if len(parts) == 2 and parts[1].isdigit():
                    nums.append(int(parts[1]))
        n = (max(nums) + 1) if nums else 1
        d = SESSIONS / f"session-{n}"
        d.mkdir(parents=True, exist_ok=False)
        (d / ".reserved").write_text(str(time.time()))
        return n, d


def pick_host_key(explicit: str | None) -> str:
    if explicit:
        return explicit.strip()
    env = _os.environ.get("KERNEL_API_KEY", "").strip()
    if env.startswith("sk_"):
        return env
    hosts = Path("/tmp/onk-host-keys.json")
    if hosts.is_file():
        data = json.loads(hosts.read_text())
        if isinstance(data, list) and data:
            return data[0]["api_key"]
    raise SystemExit("Need KERNEL_API_KEY or --host-key or /tmp/onk-host-keys.json")


async def enable_2fa_live(ctx, email: str, password: str) -> str | None:
    """Enable authenticator 2FA on already-authenticated context. Returns secret or None."""
    import pyotp
    from account_creation import handle_onboarding

    tab = await ctx.new_page()
    try:
        # Finish getting-started if still stuck there (blocks settings / Enable)
        for _obo in range(3):
            await tab.goto("https://lovable.dev/dashboard", timeout=40000,
                           wait_until="domcontentloaded")
            await tab.wait_for_timeout(3000)
            try:
                await handle_onboarding(tab)
            except Exception as e:
                log(f"  onboarding skip: {e}")
            if "getting-started" not in (tab.url or ""):
                break
            await tab.goto("https://lovable.dev/getting-started", timeout=30000,
                           wait_until="domcontentloaded")
            await tab.wait_for_timeout(2000)
            try:
                await handle_onboarding(tab)
            except Exception:
                pass

        async def click_text(*texts):
            for t in texts:
                try:
                    await tab.evaluate(
                        f"""() => {{ const b=[...document.querySelectorAll('button,a,[role=button]')]
                        .find(x=>((x.innerText||'').trim())==={t!r}); if(!b) throw new Error('no'); b.click(); }}""")
                    await tab.wait_for_timeout(2500)
                    return t
                except Exception:
                    continue
            try:
                await tab.evaluate(
                    """(nds) => { const b=[...document.querySelectorAll('button,a,[role=button]')].find(x=>{
                        const t=(x.innerText||'').trim(); return nds.some(n=>t===n||t.includes(n)); });
                        if(!b) throw new Error('no'); b.click(); }""",
                    list(texts),
                )
                await tab.wait_for_timeout(2500)
                return texts[0]
            except Exception:
                raise Exception(f"no {'/'.join(texts)}")

        async def click_includes(*needles):
            await tab.evaluate(
                """(nds) => { const b=[...document.querySelectorAll('button,a,[role=button]')].find(x=>{
                    const t=x.innerText||''; return nds.some(n=>t.includes(n)); });
                    if(!b) throw new Error('no method btn'); b.click(); }""",
                list(needles),
            )
            await tab.wait_for_timeout(4000)

        enable_labels = (
            "Enable", "Activer", "Add method", "Ajouter",
            "Set up", "Turn on", "Add", "Configurer",
        )

        last_enable_err = None
        for attempt in range(1, 4):
            await tab.goto("https://lovable.dev/settings/account#2fa", timeout=40000,
                           wait_until="domcontentloaded")
            await tab.wait_for_timeout(4500)

            # login if needed
            try:
                logged = await tab.evaluate(f"() => document.body.innerText.includes({email!r})")
            except Exception:
                logged = False
            if not logged or "/login" in (tab.url or ""):
                await tab.goto(
                    "https://lovable.dev/login?redirect=%2Fsettings%2Faccount%23%2F2fa",
                    timeout=40000, wait_until="domcontentloaded")
                await tab.wait_for_timeout(3500)
                try:
                    await tab.locator('input[placeholder="Email"]').fill(email, timeout=8000)
                except Exception:
                    await tab.locator('input[type="email"], input#email').first.fill(email)
                await tab.locator('[data-testid="auth-submit-button"]').click()
                await tab.wait_for_timeout(3000)
                try:
                    await tab.locator('input[placeholder="Password"]').fill(password, timeout=8000)
                except Exception:
                    await tab.locator('input[type="password"], input#password').first.fill(password)
                await tab.locator('[data-testid="auth-submit-button"]').click()
                await tab.wait_for_timeout(6000)
                await tab.goto("https://lovable.dev/settings/account#2fa", timeout=40000,
                               wait_until="domcontentloaded")
                await tab.wait_for_timeout(5000)

            snippet = ""
            try:
                snippet = await tab.evaluate("() => document.body.innerText.slice(0,800)")
                log(f"  settings body (try {attempt}): {snippet[:300]!r}")
            except Exception:
                pass

            # still on onboarding? clear and retry
            if "getting-started" in (tab.url or "") or "Pick your style" in snippet:
                try:
                    await handle_onboarding(tab)
                except Exception:
                    pass
                continue

            if await tab.evaluate("() => document.body.innerText.includes('Re-authentication required')"):
                await click_text("Reauthenticate", "Se réauthentifier")
                await tab.wait_for_timeout(3500)
                await tab.locator('input[placeholder="Email"]').fill(email)
                await tab.locator('[data-testid="auth-submit-button"]').click()
                await tab.wait_for_timeout(2500)
                await tab.locator('input[placeholder="Password"]').fill(password)
                await tab.locator('[data-testid="auth-submit-button"]').click()
                await tab.wait_for_timeout(5000)

            if await tab.evaluate(
                "() => { const t=document.body.innerText; "
                "return t.includes('Manage your 2FA methods')||t.includes('Désactiver'); }"):
                log("⚠️ 2FA already enabled — no secret to capture")
                return None

            await tab.evaluate("""() => {
                const el=[...document.querySelectorAll('*')].find(e=>/two-factor|2FA|double authentification/i.test(e.innerText||'') && e.children.length<5);
                if(el) el.scrollIntoView({block:'center'});
                window.scrollBy(0, 400);
            }""")
            await tab.wait_for_timeout(1000)

            try:
                await click_text(*enable_labels)
                last_enable_err = None
                break
            except Exception as e:
                last_enable_err = e
                log(f"  Enable not found try {attempt}/3: {e}")
                try:
                    await handle_onboarding(tab)
                except Exception:
                    pass
                await tab.wait_for_timeout(2000)
        else:
            try:
                await tab.screenshot(path="/tmp/lov-2fa-no-enable.png", full_page=True)
            except Exception:
                pass
            raise Exception(f"no Enable/Activer ({last_enable_err})")

        await click_includes("Authenticator app", "authentification", "Authenticator", "Application")
        if "/login" in tab.url:
            await tab.locator('input[placeholder="Email"]').fill(email)
            await tab.locator('[data-testid="auth-submit-button"]').click()
            await tab.wait_for_timeout(2500)
            await tab.locator('input[placeholder="Password"]').fill(password)
            await tab.locator('[data-testid="auth-submit-button"]').click()
            await tab.wait_for_timeout(5000)
            await click_text(*enable_labels)
            await click_includes("Authenticator app", "authentification", "Authenticator", "Application")

        await tab.evaluate("""() => {
            const s=[...document.querySelectorAll('*')].find(e=>e.children.length===0
              && /manual code|code manuel/i.test(e.innerText||''));
            const b=s?.closest('button'); if(!b) throw new Error('no manual btn'); b.click(); }""")
        await tab.wait_for_timeout(2000)
        secret = await tab.evaluate("""() => {
            const t=document.body.innerText;
            const m=t.match(/Manual entry key\\s*([A-Z2-7]{16,})/) || t.match(/([A-Z2-7]{32})/);
            return m ? m[1] : ''; }""")
        if not secret or len(secret) < 16:
            log(f"❌ no TOTP secret (got {secret!r})")
            try:
                await tab.screenshot(path="/tmp/lov-2fa-no-secret.png", full_page=True)
            except Exception:
                pass
            return None
        code = pyotp.TOTP(secret).now()
        await tab.evaluate("""(code) => {
            const el=document.querySelector('#totp-code');
            const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
            s.call(el,code);
            el.dispatchEvent(new Event('input',{bubbles:true}));
            el.dispatchEvent(new Event('change',{bubbles:true})); }""", code)
        await tab.evaluate("""() => {
            const b=[...document.querySelectorAll('button')].find(x=>{
              const t=x.innerText.trim();
              return t==='Verify & Enable'||t.startsWith('Vérifier')||t.includes('Enable'); });
            if(!b) throw new Error('no verify'); b.click(); }""")
        await tab.wait_for_timeout(5000)
        ok = await tab.evaluate("""() => {
            const t=document.body.innerText;
            return t.includes('Manage your 2FA methods')||t.includes('Désactiver')||t.includes('Disable'); }""")
        if ok:
            log(f"✅ 2FA enabled, secret len={len(secret)}")
            return secret
        log("❌ 2FA verify did not stick")
        try:
            await tab.screenshot(path="/tmp/lov-2fa-verify-fail.png", full_page=True)
        except Exception:
            pass
        return None
    finally:
        try:
            await tab.close()
        except Exception:
            pass


async def _wait_signup_email(page, timeout_ms: int = 75000):
    """Poll until signup email field is visible; reload via / if stuck."""
    deadline = time.time() + timeout_ms / 1000
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        await dismiss_cookie_banner(page)
        for sel in ("input#email", 'input[type="email"]', 'input[name="email"]'):
            loc = page.locator(sel).first
            try:
                if await loc.count():
                    await loc.wait_for(state="visible", timeout=2500)
                    return loc
            except Exception:
                pass
        txt = ""
        try:
            txt = await body_text(page)
        except Exception:
            pass
        url = page.url
        log(f"  signup wait #{attempt}: url={url[:80]} body={(txt or '')[:120]!r}")
        # CF / challenge / blank → hard reload path
        if attempt % 3 == 0:
            log("  signup hydrate retry via / → /signup")
            try:
                await page.goto(LOVABLE_HOME, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3000)
                await page.goto(LOVABLE_SIGNUP, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(5000)
            except Exception as e:
                log(f"  reload err: {e}")
        else:
            await page.wait_for_timeout(2000)
    try:
        await page.screenshot(path="/tmp/lov-signup-no-email.png", full_page=True)
    except Exception:
        pass
    raise FlowError(f"signup email field never appeared (url={page.url})")


async def signup_flow(ctx, email: str, password: str, mailbox) -> dict:
    page = await ctx.new_page()
    # OnK stealth already spoofs navigator — extra playwright_stealth can worsen CF
    # await apply_stealth_patches(page)
    await page.add_init_script(
        "try{window.__nativeSetter=Object.getOwnPropertyDescriptor("
        "HTMLInputElement.prototype,'value').set;}catch(e){}")

    log(f"🌐 Navigating to {LOVABLE_SIGNUP}")
    await navigate(page, LOVABLE_SIGNUP)
    await page.wait_for_timeout(2500)
    txt = await body_text(page)
    if len(txt.strip()) < 50 or ("Create" not in txt and "Créez" not in txt):
        log("⚠️ signup skeleton — reload via /")
        await navigate(page, LOVABLE_HOME)
        await page.wait_for_timeout(2500)
        await navigate(page, LOVABLE_SIGNUP)
        await page.wait_for_timeout(3000)
    await dismiss_cookie_banner(page)

    # email
    log(f"📧 Filling email: {email}")
    email_loc = await _wait_signup_email(page)
    try:
        await email_loc.click(timeout=3000, force=True)
    except Exception:
        await email_loc.evaluate("el => el.focus()")
    await asyncio.sleep(0.12)
    try:
        await email_loc.fill(email, timeout=5000)
    except Exception:
        await page.keyboard.type(email, delay=35)
    await page.wait_for_timeout(500)

    # Continuer
    log("🖱️ Continuer")
    continuer = page.locator('[data-testid="auth-submit-button"]').first
    try:
        await continuer.wait_for(state="visible", timeout=8000)
        await continuer.click(timeout=7000)
    except Exception:
        for name in ("Continuer", "Continue"):
            try:
                btn = page.get_by_role("button", name=name, exact=True).first
                if await btn.count():
                    await btn.click(timeout=5000)
                    break
            except Exception:
                continue

    await page.wait_for_timeout(1200)
    pw_loc = page.locator("input#password").first
    if not await pw_loc.count():
        pw_loc = page.locator('input[type="password"]').first
    await pw_loc.wait_for(state="visible", timeout=15000)
    try:
        await pw_loc.click(timeout=3000, force=True)
    except Exception:
        pass
    await pw_loc.fill(password)
    await page.wait_for_timeout(800)
    val_len = await pw_loc.evaluate("el => el.value.length")
    if val_len != len(password):
        await pw_loc.fill(password)
        await page.wait_for_timeout(800)

    await handle_turnstile(page, email=email, password=password, max_attempts=15)

    log("🖱️ Create account")
    create_btn = page.locator('[data-testid="auth-submit-button"]').first
    await create_btn.wait_for(state="visible", timeout=8000)
    for _ in range(12):
        try:
            if not await create_btn.is_disabled():
                break
        except Exception:
            break
        await page.wait_for_timeout(400)
    try:
        await create_btn.click(timeout=8000)
    except Exception:
        await page.evaluate("""() => {
            const b=[...document.querySelectorAll('[data-testid="auth-submit-button"]')].pop()
                 || [...document.querySelectorAll('button')].find(x=>/Créez|Create/.test(x.innerText));
            if(b) b.click(); }""")
    await page.wait_for_timeout(2500)

    # inbox hint
    inbox_deadline = time.time() + 45
    while time.time() < inbox_deadline:
        txt = await body_text(page)
        url = page.url
        if any(s in txt for s in ("Check your inbox", "Vérifiez", "Check your email", "inbox")):
            log("✅ Check your inbox")
            break
        if "suspicious" in txt.lower() or "blocking_function" in txt.lower():
            raise FlowError(f"suspicious activity: {txt[:300]!r}")
        if "/getting-started" in url or "Pick your style" in txt:
            break
        await page.wait_for_timeout(800)

    log("📥 Polling mailbox for verify link…")
    verify_link = await mailbox.wait_for_lovable_link(timeout_seconds=420)
    link = html.unescape(verify_link).replace("&amp;", "&")
    log(f"🎯 Verify: {link[:160]}")

    await navigate(page, link)
    await page.wait_for_timeout(4000)
    try:
        await wait_for_getting_started(page, timeout=90)
    except FlowError as e:
        txt = await body_text(page)
        url = page.url
        log(f"⚠️ getting-started wait: {e} url={url}")
        if not ("/getting-started" in url or "Pick your style" in txt
                or "/dashboard" in url or "Ask Lovable" in txt):
            await navigate(page, link)
            await page.wait_for_timeout(4000)
            await wait_for_getting_started(page, timeout=60)

    final_url = page.url
    final_text = await body_text(page)
    verified = (
        "/getting-started" in final_url or "Pick your style" in final_text
        or "/dashboard" in final_url or "Ask Lovable" in final_text
        or "Dashboard" in final_text
    )
    if not verified:
        raise FlowError(f"not verified: url={final_url} text={final_text[:300]!r}")
    log(f"✅ Verified: {final_url}")
    # Clear getting-started so settings/2FA is reachable
    try:
        from account_creation import handle_onboarding
        await handle_onboarding(page)
        log(f"  after onboarding: {page.url}")
    except Exception as e:
        log(f"  onboarding non-fatal: {e}")
    return {"page": page, "verify_link": link, "final_url": page.url, "verified": True}


async def run_once(host_key: str, password: str = PASSWORD_DEFAULT,
                   proxy_country: str = "gb", skip_zenvex: bool = False) -> dict:
    proxy_name = f"mobile-{proxy_country}-{uuid.uuid4().hex[:10]}"
    onk_sid = None
    mailbox = None
    browser = None
    pw_cm = None

    if not ensure_mobile_proxy(host_key, proxy_name, country=proxy_country):
        raise FlowError(f"mobile proxy create failed: {proxy_name}")
    log(f"✅ Proxy {proxy_name} (country={proxy_country})")

    try:
        from playwright.async_api import async_playwright
        pw_cm = async_playwright()
        pw = await pw_cm.__aenter__()

        used_emails: set[str] = set()
        signup = None
        email = ""
        bdata: dict = {}
        ctx = None
        max_signup_attempts = 3

        for attempt in range(1, max_signup_attempts + 1):
            if attempt > 1:
                # Fresh mobile IP + rotated zenvex domain after suspicious/Turnstile
                try:
                    if mailbox:
                        await mailbox.close()
                except Exception:
                    pass
                mailbox = None
                try:
                    if browser:
                        await browser.close()
                except Exception:
                    pass
                browser = None
                if onk_sid:
                    delete_browser(host_key, onk_sid)
                    onk_sid = None
                delete_proxy_named(host_key, proxy_name)
                proxy_name = f"mobile-{proxy_country}-{uuid.uuid4().hex[:10]}"
                if not ensure_mobile_proxy(host_key, proxy_name, country=proxy_country):
                    raise FlowError(f"mobile proxy recreate failed: {proxy_name}")
                log(f"♻️  Retry {attempt}/{max_signup_attempts}: new proxy {proxy_name}")

            bdata = create_browser(host_key, proxy_name)
            onk_sid = bdata["session_id"]
            browser = await pw.chromium.connect_over_cdp(bdata["cdp_ws_url"], timeout=45000)
            ctx = browser.contexts[0] if browser.contexts else await browser.new_context()

            log(f"📧 Acquiring mailbox (attempt {attempt}, zenvex_offset={attempt - 1})…")
            mailbox = await acquire_mailbox(
                ctx, used=used_emails, skip_zenvex=skip_zenvex, zenvex_offset=attempt - 1,
            )
            email = mailbox.address
            log(f"📮 Using {email} via {mailbox.provider}")

            try:
                signup = await signup_flow(ctx, email, password, mailbox)
                save_used_email(email)
                break
            except FlowError as e:
                emsg = str(e).lower()
                used_emails.add(email.lower())
                try:
                    save_used_email(email)
                except Exception:
                    pass
                retryable = ("suspicious" in emsg or "turnstile" in emsg) and attempt < max_signup_attempts
                if retryable:
                    log(f"⚠️ signup attempt {attempt} failed ({e}); rotating proxy+mail…")
                    continue
                raise

        if not signup or ctx is None:
            raise FlowError("signup retries exhausted")

        num, session_dir = reserve_session_dir()
        log(f"📁 Reserved {session_dir.name}")

        (session_dir / "email.txt").write_text(email + "\n")
        # Full trio ASAP (cookies + LS + Firebase refresh_token) — optional helper
        _save_full_state = None
        try:
            from src.lovable.session_state import save_full_state as _save_full_state
        except ImportError:
            try:
                from session_state import save_full_state as _save_full_state  # type: ignore
            except ImportError:
                _save_full_state = None
        page0 = ctx.pages[0] if ctx.pages else await ctx.new_page()
        try:
            if _save_full_state is not None:
                if "lovable.dev" not in (page0.url or ""):
                    await page0.goto("https://lovable.dev/dashboard", timeout=45000, wait_until="domcontentloaded")
                ok_refresh = await _save_full_state(ctx, page0, session_dir)
                log(f"💾 Full state saved (refresh_token={'YES' if ok_refresh else 'MISSING'})")
            else:
                cookies = await ctx.cookies()
                (session_dir / "cookies.json").write_text(json.dumps(cookies, indent=2))
                log("💾 cookies-only save (session_state module not present)")
        except Exception as e:
            cookies = await ctx.cookies()
            (session_dir / "cookies.json").write_text(json.dumps(cookies, indent=2))
            log(f"⚠️ Full-state save failed ({e}); cookies-only fallback")
        try:
            state = await ctx.storage_state()
            (session_dir / "storage_state.json").write_text(json.dumps(state, indent=2))
        except Exception:
            pass

        cfg = {
            "email": email,
            "password": password,
            "created_at": datetime.now().isoformat(),
            "dashboard_url": signup["final_url"],
            "verified": True,
            "verify_link": signup["verify_link"],
            "provider": mailbox.provider if mailbox else "",
            "egress": f"onk_mobile_{proxy_country}",
            "onk_session_id": onk_sid,
            "proxy_name": proxy_name,
            "proxy_country": proxy_country,
            "browser_live_url": bdata.get("browser_live_view_url", ""),
        }
        (session_dir / "config.json").write_text(json.dumps(cfg, indent=2))
        (session_dir / "verified.json").write_text(json.dumps({
            "email": email, "verified": True, "at": cfg["created_at"],
        }, indent=2))

        # 2FA preferred but NOT required — always keep verified + refresh_token
        log("🔐 Enabling 2FA…")
        secret = None
        try:
            secret = await enable_2fa_live(ctx, email, password)
        except Exception as e:
            log(f"⚠️ 2FA exception (keeping verified account): {e}")
        if secret:
            cfg["totp_secret"] = secret
            cfg["2fa_done"] = True
            cfg["2fa_pending"] = False
            log(f"✅ 2FA set (secret len={len(secret)})")
        else:
            cfg["2fa_done"] = False
            cfg["2fa_pending"] = True
            cfg.pop("totp_secret", None)
            log("⚠️ 2FA not set — saving verified credentials + refresh_token anyway")
        (session_dir / "config.json").write_text(json.dumps(cfg, indent=2))
        # Re-save full state (tokens may have rotated; critical when 2FA skipped)
        try:
            if _save_full_state is not None:
                page1 = ctx.pages[0] if ctx.pages else await ctx.new_page()
                try:
                    await page1.goto("https://lovable.dev/dashboard", timeout=45000, wait_until="domcontentloaded")
                except Exception:
                    pass
                ok2 = await _save_full_state(ctx, page1, session_dir)
                log(f"💾 Post-auth full state (refresh_token={'YES' if ok2 else 'MISSING'})")
            else:
                (session_dir / "cookies.json").write_text(json.dumps(await ctx.cookies(), indent=2))
        except Exception as e:
            log(f"⚠️ Post-auth full-state save failed: {e}")

        # GH push (verified alone is enough; 2FA optional)
        _load_holy()
        from src.railway.gh_push import sync_lovable_to_github
        sync_lovable_to_github(session_dir)

        result = {
            "ok": True,
            "session": num,
            "session_dir": str(session_dir),
            "email": email,
            "provider": mailbox.provider if mailbox else "",
            "totp_secret": secret,
            "2fa_done": bool(secret),
            "2fa_pending": not bool(secret),
            "verified": True,
        }
        print(json.dumps(result, indent=2))
        return result
    finally:
        try:
            if mailbox:
                await mailbox.close()
        except Exception:
            pass
        try:
            if browser:
                await browser.close()
        except Exception:
            pass
        try:
            if pw_cm:
                await pw_cm.__aexit__(None, None, None)
        except Exception:
            pass
        if onk_sid:
            delete_browser(host_key, onk_sid)
        delete_proxy_named(host_key, proxy_name)


async def finish_session_2fa(host_key: str, session_num: int, proxy_country: str = "gb") -> dict:
    """Resume 2FA + GH push for an already-verified session-*."""
    session_dir = SESSIONS / f"session-{session_num}"
    cfg_path = session_dir / "config.json"
    ck_path = session_dir / "cookies.json"
    if not cfg_path.is_file() or not ck_path.is_file():
        raise FlowError(f"missing session-{session_num}")
    cfg = json.loads(cfg_path.read_text())
    if cfg.get("totp_secret"):
        log("already has totp — pushing only")
        _load_holy()
        from src.railway.gh_push import sync_lovable_to_github
        sync_lovable_to_github(session_dir)
        return {"ok": True, "session": session_num, "email": cfg["email"], "skipped_2fa": True}

    email, password = cfg["email"], cfg["password"]
    proxy_name = f"mobile-{proxy_country}-{uuid.uuid4().hex[:10]}"
    onk_sid = None
    pw_cm = None
    browser = None
    if not ensure_mobile_proxy(host_key, proxy_name, country=proxy_country):
        raise FlowError("proxy create failed")
    try:
        bdata = create_browser(host_key, proxy_name)
        onk_sid = bdata["session_id"]
        from playwright.async_api import async_playwright
        pw_cm = async_playwright()
        pw = await pw_cm.__aenter__()
        browser = await pw.chromium.connect_over_cdp(bdata["cdp_ws_url"], timeout=45000)
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        raw = json.loads(ck_path.read_text())
        cookies = [{
            "name": c["name"], "value": c["value"], "domain": c["domain"],
            "path": c.get("path", "/"),
            "expires": int(c["expires"]) if c.get("expires") else -1,
            "httpOnly": bool(c.get("httpOnly", False)),
            "secure": bool(c.get("secure", False)),
            "sameSite": c.get("sameSite", "Lax") if c.get("sameSite") in ("Lax", "Strict", "None") else "Lax",
        } for c in raw if "lovable" in c.get("domain", "")]
        await ctx.add_cookies(cookies)

        secret = await enable_2fa_live(ctx, email, password)
        if not secret:
            raise FlowError("2FA failed on resume")
        cfg["totp_secret"] = secret
        cfg["2fa_done"] = True
        cfg_path.write_text(json.dumps(cfg, indent=2))
        # refresh cookies
        try:
            (session_dir / "cookies.json").write_text(json.dumps(await ctx.cookies(), indent=2))
        except Exception:
            pass

        _load_holy()
        from src.railway.gh_push import sync_lovable_to_github
        sync_lovable_to_github(session_dir)
        result = {"ok": True, "session": session_num, "email": email, "totp_secret": secret}
        print(json.dumps(result, indent=2))
        return result
    finally:
        try:
            if browser:
                await browser.close()
        except Exception:
            pass
        try:
            if pw_cm:
                await pw_cm.__aexit__(None, None, None)
        except Exception:
            pass
        if onk_sid:
            delete_browser(host_key, onk_sid)
        delete_proxy_named(host_key, proxy_name)


def main() -> None:
    _load_holy()
    ap = argparse.ArgumentParser(description="Ultimate Lovable farm (OnK + mail chain + 2FA + GH)")
    ap.add_argument("--once", action="store_true", help="Run one full create→2FA→GH proof")
    ap.add_argument("--finish-session", type=int, default=None,
                    help="Resume 2FA+GH on existing session-N")
    ap.add_argument("--host-key", default=None, help="OnK API key (else KERNEL_API_KEY / host-keys)")
    ap.add_argument("--password", default=PASSWORD_DEFAULT)
    ap.add_argument("--proxy-country", default="gb",
                    help="OnK mobile proxy country (default gb — US gets Firebase suspicious)")
    ap.add_argument("--skip-zenvex", action="store_true",
                    help="Skip zenvex UI mail (use temp.tf→22.do→dispose→mail.tm) — more reliable on Railway")
    args = ap.parse_args()
    if not args.once and args.finish_session is None:
        ap.error("pass --once or --finish-session N")
    key = pick_host_key(args.host_key)
    log(f"🔑 Using OnK key …{key[-12:]}")
    try:
        if args.finish_session is not None:
            asyncio.run(finish_session_2fa(key, args.finish_session, proxy_country=args.proxy_country))
        else:
            asyncio.run(run_once(
                key, password=args.password, proxy_country=args.proxy_country,
                skip_zenvex=args.skip_zenvex,
            ))
    except Exception as e:
        log(f"❌ FAIL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
