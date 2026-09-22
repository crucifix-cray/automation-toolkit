#!/usr/bin/env python3
"""OnKernel account creator via CDP — uses OnKernel browser cloud, not local Chromium.

Flow (same as account_creation.py but CDP remote browser):
  kernel browsers create --stealth -> CDP WS -> dispose.lol Gmail
  -> dashboard.onkernel.com/sign-up -> Clerk OTP -> survey/org/api-key
  -> save session JSON + kill browser.

Usage:
  KERNEL_API_KEY=sk_73b4... python3 src/onkernel/account_creation_cdp.py --end
  KERNEL_API_KEY=sk_73b4... python3 src/onkernel/account_creation_cdp.py --end --attempts 2
  KERNEL_API_KEY=sk_73b4... python3 src/onkernel/account_creation_cdp.py --end --22do
  KERNEL_API_KEY=sk_73b4... python3 src/onkernel/account_creation_cdp.py --end --22do --proxy-name mobile-us
"""
from __future__ import annotations

import os as _os
_os.environ["LD_PRELOAD"] = ""
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
           "ALL_PROXY", "all_proxy", "PLAYWRIGHT_PROXY_URL"):
    _os.environ.pop(_k, None)

import argparse
import asyncio
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

SIGNUP_URL = "https://dashboard.onkernel.com/sign-up"
DISPOSE_URL = "https://dispose.lol"
TWODO_GMAIL_API = "https://22.do/action/mailbox/gmail"
TWODO_APPLY = "https://22.do/action/mailbox/applyToken"
TWODO_MSG = "https://22.do/action/mailbox/message"
TWODO_CONTENT = "https://22.do/content/"
CODE_RE = re.compile(r"\b\d{6}\b")
VIEW_BTN = 'button[aria-label^="View "]'

KERNEL_API_KEY = _os.environ.get("KERNEL_API_KEY", "")

SESSIONS_DIR = "/home/alae/Documents/repos/automation-toolkit/finals/sessions"
Password = "GmailK01!"


class FlowError(Exception):
    pass


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def create_browser(proxy_name: str = "", start_url: str = "") -> dict:
    """Create OnKernel browser via CLI, return JSON."""
    import shlex
    px = f" --proxy-name {shlex.quote(proxy_name)}" if proxy_name else ""
    start = start_url or DISPOSE_URL
    cmd = f"kernel browsers create --stealth --timeout 900{px} --start-url {shlex.quote(start)} -o json"
    env = {**_os.environ, "KERNEL_API_KEY": KERNEL_API_KEY}
    last_err = "unknown"
    for _t in range(3):
        try:
            out = subprocess.check_output(cmd, shell=True, env=env, text=True, timeout=90)
            break
        except Exception as _e:
            last_err = str(_e)[:150]
            log(f"  browser create try {_t + 1}/3 failed: {last_err}")
            time.sleep(20)
    else:
        raise FlowError(f"browser create failed x3: {last_err}")
    data = json.loads(out)
    log(f"🌐 Browser live: {data['browser_live_view_url']}")
    log(f"   SID: {data['session_id']} | CDP: {data['cdp_ws_url'][:80]}...")
    return data


def delete_browser(session_id: str):
    env = {**_os.environ, "KERNEL_API_KEY": KERNEL_API_KEY}
    try:
        subprocess.run(f"kernel browsers delete {session_id}", shell=True,
                       env=env, timeout=15, capture_output=True)
        log(f"🗑️  Browser {session_id} deleted")
    except Exception as e:
        log(f"  delete err: {e}")


async def current_dispose_email(dpage):
    return await dpage.evaluate("""() => {
        const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT,null);
        let n; while(n=w.nextNode()){ const t=n.textContent.trim();
          if(t.includes('@gmail.com')&&t.length<80) return t; }
        for(const i of document.querySelectorAll('input'))
          if(i.value&&i.value.includes('@gmail.com')) return i.value;
        return null; }""")


async def create_dispose_email(dpage, fresh: bool = False) -> str:
    log("📧 Creating dispose.lol Gmail...")
    await dpage.goto(DISPOSE_URL, wait_until="domcontentloaded", timeout=60_000)
    await dpage.wait_for_timeout(5000)
    if fresh:
        try:
            chg = dpage.locator('button', has_text="Change")
            if await chg.count():
                old = await current_dispose_email(dpage)
                await chg.first.click(timeout=8000)
                await dpage.wait_for_timeout(4000)
                new = await current_dispose_email(dpage)
                log(f"  🔄 Rotated inbox: {old} -> {new}")
        except Exception as e:
            log(f"  change click: {e}")
    for attempt in range(1, 6):
        email = await dpage.evaluate("""() => {
            const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT,null);
            let n; while(n=w.nextNode()){ const t=n.textContent.trim();
              if(t.includes('@gmail.com')&&t.length<80) return t; }
            for(const i of document.querySelectorAll('input'))
              if(i.value&&i.value.includes('@gmail.com')) return i.value;
            return null; }""")
        if email and "@gmail.com" in email:
            log(f"✅ Mailbox: {email.strip()}")
            return email.strip()
        log(f"  ⏳ not rendered (attempt {attempt}/5)...")
        await dpage.wait_for_timeout(2000)
        await dpage.reload(wait_until="domcontentloaded")
        await dpage.wait_for_timeout(3000)
    await dpage.screenshot(path="/tmp/onk-dispose-error.png")
    raise FlowError("No dispose.lol Gmail after 5 attempts")


def create_22do_email(tries: int = 80) -> str:
    """22.do fake-gmail API (pure HTTP). Returns one-dot @gmail.com or raises."""
    import urllib.request as _u
    for _t in range(tries):
        try:
            _d = json.dumps({"type": "random"}).encode()
            _rq = _u.Request(TWODO_GMAIL_API, data=_d,
                headers={"Content-Type": "application/json",
                         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"},
                method="POST")
            with _u.urlopen(_rq, timeout=15) as _r:
                _res = json.loads(_r.read())
            _em = ((_res.get("data") or {}).get("email") or "").strip()
            _local = _em.split("@")[0] if "@" in _em else ""
            if _em.lower().endswith("@gmail.com") and _local.count(".") == 1 and "+" not in _em:
                log(f"✅ Mailbox: {_em} (via 22.do)")
                return _em
            log(f"  22.do skip {_em}, retry {_t + 1}/{tries}")
        except Exception as _e:
            log(f"  22.do API try {_t + 1} err {str(_e)[:100]}")
    raise FlowError("No 22.do one-dot Gmail after tries")


async def wait_for_kernel_code_22do(email: str, timeout_seconds: int = 300) -> str | None:
    """Poll 22.do API for Kernel 6-digit code (pure HTTP, no browser tab)."""
    import random as _r22
    import urllib.request as _u

    def _post(url, payload, token=None):
        _d = json.dumps(payload).encode()
        _h = {"Content-Type": "application/json",
              "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"}
        if token:
            _h["Authorization"] = f"Bearer {token}"
        _rq = _u.Request(url, data=_d, headers=_h, method="POST")
        with _u.urlopen(_rq, timeout=15) as _r:
            return json.loads(_r.read())

    def _get(url):
        _rq = _u.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
            "Referer": "https://22.do/"}, method="GET")
        with _u.urlopen(_rq, timeout=15) as _r:
            return _r.read().decode("utf-8", "ignore")

    log(f"📥 Waiting for Kernel code on 22.do for {email} (~5min budget)...")
    _uuid = "".join(_r22.choices("0123456789abcdef", k=32))
    try:
        _tj = _post(TWODO_APPLY, {"email": email, "uuid": _uuid})
        _tok = (_tj.get("data") or {}).get("token") if _tj.get("status") else None
    except Exception as _e:
        log(f"  22.do applyToken fail: {str(_e)[:80]}")
        return None
    if not _tok:
        log("  22.do applyToken: no token")
        return None
    deadline = time.time() + timeout_seconds
    check = 0
    while time.time() < deadline:
        check += 1
        try:
            _mj = _post(TWODO_MSG, {"email": email, "lastime": 0}, token=_tok)
            _items = (_mj.get("data") or []) if _mj.get("status") else []
        except Exception as _e:
            _items = []
            if check % 4 == 1:
                log(f"  22.do poll err {str(_e)[:80]}")
        if check % 4 == 1:
            log(f"  Check #{check}: {len(_items)} message(s)")
        for _m in _items:
            _s = str(_m.get("subject", ""))
            _f = str(_m.get("from", _m.get("sender", "")))
            _blob = f"{_s} {_f}"
            if "kernel" not in _blob.lower() and "verif" not in _blob.lower():
                continue
            m = CODE_RE.search(_blob)
            if m:
                log(f"  ✅ Code from subject: {m.group(0)}")
                return m.group(0)
            _mid = str(_m.get("messageId", _m.get("id", "")))
            if _mid:
                try:
                    _html = _get(f"{TWODO_CONTENT}{_mid}")
                    m2 = CODE_RE.search(_html or "")
                    if m2 and ("kernel" in (_html or "").lower() or "verif" in (_html or "").lower()):
                        log(f"  ✅ Code from body: {m2.group(0)}")
                        return m2.group(0)
                except Exception as _e:
                    if check % 4 == 1:
                        log(f"  content fetch err {str(_e)[:80]}")
            log(f"  verif-like mail without code yet, keep polling: {_s[:80]}")
        await asyncio.sleep(5)
    log("⏰ No Kernel mail on 22.do in ~5min")
    return None


async def wait_for_kernel_code(dpage, timeout_seconds: int = 300) -> str | None:
    log("📥 Waiting for Kernel code on dispose.lol (~5min budget)...")
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    check = 0
    while asyncio.get_running_loop().time() < deadline:
        check += 1
        try:
            await dpage.reload(wait_until="domcontentloaded")
        except Exception:
            pass
        await dpage.wait_for_timeout(2500)
        try:
            buttons = await dpage.locator(VIEW_BTN).all()
        except Exception:
            buttons = []
        if check % 4 == 1:
            log(f"  Check #{check}: {len(buttons)} message(s)")
        for btn in buttons:
            try:
                aria = (await btn.get_attribute("aria-label") or "")
            except Exception:
                continue
            m = CODE_RE.search(aria)
            if ("kernel" in aria.lower() or "verification" in aria.lower()) and m:
                log(f"  ✅ Code from subject: {m.group(0)}")
                return m.group(0)
            if "kernel" in aria.lower() or "verif" in aria.lower():
                try:
                    await btn.scroll_into_view_if_needed(timeout=2000)
                except Exception:
                    pass
                try:
                    await btn.click(timeout=5000, force=True)
                    await dpage.wait_for_timeout(3000)
                except Exception as e:
                    log(f"  click failed: {e}")
                    continue
                for frame in dpage.frames:
                    try:
                        t = await frame.evaluate(
                            "() => document.body ? document.body.innerText.slice(0,8000) : ''")
                    except Exception:
                        continue
                    m2 = CODE_RE.search(t or "")
                    if m2 and ("kernel" in (t or "").lower() or "verif" in (t or "").lower()):
                        log(f"  ✅ Code from body: {m2.group(0)}")
                        return m2.group(0)
        await asyncio.sleep(3)
    log("⏰ No Kernel mail in ~5min — caller should rotate inbox and redo")
    return None


async def run(password: str = "GmailK01!", email_override: str | None = None,
              max_attempts: int = 3, proxy_name: str = "", use_22do: bool = False) -> dict:
    from playwright.async_api import async_playwright

    first, last = "Genev", "Aochea"
    # Create browser via OnKernel CDP
    browser_data = create_browser(proxy_name, start_url=SIGNUP_URL if use_22do else DISPOSE_URL)
    cdp_ws = browser_data["cdp_ws_url"]
    onk_sid = browser_data["session_id"]

    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.connect_over_cdp(cdp_ws, timeout=30000)
        except Exception as e:
            delete_browser(onk_sid)
            raise FlowError(f"CDP connect failed: {e}")

        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        dpage = ctx.pages[0] if ctx.pages else await ctx.new_page()
        email = None
        spage = None

        for attempt in range(1, max_attempts + 1):
            if email_override and attempt == 1:
                email = email_override
            elif use_22do:
                try:
                    email = await asyncio.to_thread(create_22do_email)
                except FlowError:
                    try:
                        await browser.close()
                    except Exception:
                        pass
                    delete_browser(onk_sid)
                    raise
            else:
                email = await create_dispose_email(dpage, fresh=(attempt > 1))

            if spage is not None:
                try:
                    await spage.close()
                except Exception:
                    pass

            spage = await ctx.new_page()
            await spage.goto(SIGNUP_URL, wait_until="domcontentloaded", timeout=60_000)
            await spage.wait_for_timeout(5000)
            await spage.fill('input[name="firstName"]', first)
            await spage.fill('input[name="lastName"]', last)
            await spage.fill('input[name="emailAddress"]', email)
            await spage.fill('input[name="password"]', password)
            await spage.check('input[name="legalAccepted"]')
            log(f"📝 Attempt {attempt}/{max_attempts}: signup for {email}...")
            await spage.locator('button', has_text="continue").first.click(timeout=10_000)
            await spage.wait_for_timeout(8000)

            if "verify-email-address" not in spage.url:
                await spage.screenshot(path=f"/tmp/onk-signup-fail-a{attempt}.png")
                log(f"  ⚠️ No verify page ({spage.url}) — rotating inbox...")
                email_override = None
                continue

            log("✅ On verify-email-address page")
            if use_22do:
                code = await wait_for_kernel_code_22do(email)
            else:
                code = await wait_for_kernel_code(dpage)
            if not code:
                log(f"  🔄 Rotating to fresh mail (attempt {attempt}/{max_attempts})...")
                email_override = None
                continue

            await spage.locator('input[autocomplete="one-time-code"]').fill(code)
            await spage.wait_for_timeout(1500)
            if "verify-email-address" in spage.url:
                try:
                    await spage.get_by_role("button", name="continue").click(timeout=10_000)
                except Exception as e:
                    log(f"  continue click: {e}")
            await spage.wait_for_timeout(8000)

            if "verify-email-address" in spage.url:
                await spage.screenshot(path=f"/tmp/onk-code-rejected-a{attempt}.png")
                log(f"  ⚠️ Code rejected — rotating inbox...")
                email_override = None
                continue

            log(f"✅ Verified → {spage.url}")
            break
        else:
            try:
                await browser.close()
            except Exception:
                pass
            delete_browser(onk_sid)
            raise FlowError(f"No verified account after {max_attempts} attempts")

        # 4. survey
        if "survey" in spage.url:
            await spage.locator('button', has_text="other").first.click(timeout=10_000)
            await spage.wait_for_timeout(2000)
            await spage.fill('input[placeholder*="specify"]', "friend")
            await spage.wait_for_timeout(1000)
            await spage.locator('input[placeholder*="specify"]').evaluate(
                "el => el.parentElement.querySelector('button').click()")
            await spage.wait_for_timeout(8000)
            log(f"✅ Survey done → {spage.url}")

        # 5. org
        if "select-org" in spage.url:
            slug = f"genev-{int(time.time()) % 100000}"
            inputs = spage.locator('input[type="text"], input:not([type])')
            await inputs.nth(0).fill(f"{first} {last}")
            await spage.wait_for_timeout(1000)
            if await inputs.count() > 1:
                await inputs.nth(1).fill(slug)
            await spage.locator('button', has_text="create organization").first.click(timeout=10_000)
            await spage.wait_for_timeout(8000)
            skip = spage.locator('button', has_text="skip")
            if await skip.count():
                await skip.first.click(timeout=8000)
                await spage.wait_for_timeout(8000)
            log(f"✅ Org done → {spage.url}")

        # 6. api key
        api_key = None
        try:
            gen = spage.locator('button', has_text="generate api key")
            if await gen.count():
                await gen.first.click(timeout=8000)
                await spage.wait_for_timeout(4000)
        except Exception as e:
            log(f"  onboarding gen skipped: {e}")

        try:
            await spage.evaluate("""() => {
              const a=[...document.querySelectorAll('a')].find(x=>/api.keys/i.test(x.innerText));
              if(a) a.click(); }""")
            await spage.wait_for_timeout(6000)
            if "api-keys" not in spage.url:
                await spage.goto("https://dashboard.onkernel.com/api-keys",
                                  wait_until="domcontentloaded", timeout=60_000)
                await spage.wait_for_timeout(5000)
            await spage.locator('button', has_text="create api key").first.click(timeout=10_000)
            await spage.wait_for_timeout(4000)
            name_in = spage.locator('input[placeholder*="Production"]')
            if await name_in.count():
                await name_in.fill("auto-main")
                await spage.wait_for_timeout(1000)
            create_btns = spage.locator('button', has_text="create")
            await create_btns.last.click(timeout=8000)
            await spage.wait_for_timeout(5000)
            api_key = await spage.evaluate("""() => {
              for (const i of document.querySelectorAll('input'))
                if (i.value && i.value.startsWith('sk_')) return i.value;
              return null; }""")
            if api_key:
                log(f"✅ API key: {api_key[:12]}...{api_key[-4:]}")
            await spage.screenshot(path="/tmp/onk-key-created.png")
        except Exception as e:
            log(f"  api-keys create skipped: {e}")
            await spage.screenshot(path="/tmp/onk-key-fail.png")

        # 7. unlock full potential: proxies → start trial → just exploring → start trial
        result_unlock = False
        try:
            try:
                from unlock_trial import unlock_full_potential
            except ImportError:
                from onkernel.unlock_trial import unlock_full_potential
            result_unlock = bool(await unlock_full_potential(spage, log=log))
        except Exception as e:
            log(f"  unlock trial soft-fail: {e}")
            try:
                await spage.screenshot(path="/tmp/onk-unlock-fail.png")
            except Exception:
                pass

        result = {
            "email": email,
            "password": password,
            "first": first,
            "last": last,
            "api_key": api_key,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "onk_session_id": onk_sid,
            "browser_live_url": browser_data.get("browser_live_view_url", ""),
            "trial_unlocked": result_unlock,
        }

        # save
        _os.makedirs(SESSIONS_DIR, exist_ok=True)
        fp = _os.path.join(SESSIONS_DIR, f"onk_{int(time.time())}_{_os.getpid()}.json")
        cookies = await ctx.cookies()
        try:
            state = await ctx.storage_state()
        except Exception:
            state = {}
        open(fp, "w").write(json.dumps(result, indent=2))
        open(fp.replace(".json", ".cookies.json"), "w").write(json.dumps(cookies, indent=2))
        open(fp.replace(".json", ".storage.json"), "w").write(json.dumps(state, indent=2))
        log(f"💾 Saved {fp} ({len(cookies)} cookies)")

        try:
            open(_os.path.join(SESSIONS_DIR, "latest_onk.json"), "w").write(
                json.dumps(dict(session_file=fp, **result), indent=2))
        except Exception:
            pass

        try:
            await browser.close()
        except Exception:
            pass
        delete_browser(onk_sid)
        return result


def main():
    p = argparse.ArgumentParser(description="Create OnKernel account via CDP browser cloud")
    p.add_argument("--end", action="store_true")
    p.add_argument("--email", help="Reuse inbox")
    p.add_argument("--password", default="GmailK01!")
    p.add_argument("--attempts", type=int, default=3)
    p.add_argument("--proxy-name", default="", help="OnKernel proxy name")
    p.add_argument("--22do", dest="use_22do", action="store_true",
                   help="Use 22.do one-dot Gmail API instead of dispose.lol")
    a = p.parse_args()
    if not KERNEL_API_KEY:
        print("❌ Set KERNEL_API_KEY env var", file=sys.stderr)
        sys.exit(1)
    res = asyncio.run(run(password=a.password, email_override=a.email,
                          max_attempts=a.attempts, proxy_name=a.proxy_name,
                          use_22do=a.use_22do))
    print(json.dumps(res, indent=2))
    if res.get("api_key"):
        env = {**_os.environ, "KERNEL_API_KEY": res["api_key"]}
        try:
            out = subprocess.run(["kernel", "auth"], env=env, capture_output=True,
                                 text=True, timeout=30)
            print(out.stdout.strip() or out.stderr.strip())
        except Exception as e:
            print(f"key verify skipped: {e}")
    if not a.end:
        input("done — Enter to exit...")


if __name__ == "__main__":
    main()
