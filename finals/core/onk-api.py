#!/usr/bin/env python3
"""OnKernel account creator — headed local Chromium + dispose.lol Gmail (end-to-end).

Verified flow (2026-09-09, raw IP, headed):
  dispose.lol -> Gmail -> dashboard.onkernel.com/sign-up
  (first/last/email/password + legalAccepted -> continue)
  -> /sign-up/verify-email-address (6-digit code, single input autocomplete=one-time-code)
  -> poll dispose.lol: button[aria-label^="View "] "View 351817 is your verification code"
  -> fill code -> continue -> /onboarding/survey ("other" -> "Please specify..." -> "friend" -> submit)
  -> /select-org (name + slug -> create organization -> skip invites)
  -> /onboarding (generate api key -> api-keys page -> create api key "auto-main" -> full sk_... shown once)
  -> save sessions/onk_<ts>.json {email, password, api_key} + verify via `kernel auth`.

Egress: raw IP only. Script enforces LD_PRELOAD="" + clears ALL proxy env
(tor wraps this box on 127.0.0.1:9251). Headed by default (DISPLAY=:0);
--headless to override. Muted + no-first-run + no-sign-in flags so the
browser never prompts for Chrome sign-in and never plays audio.

Usage:
  DISPLAY=:0 python3 finals/core/onk-api.py --end
  DISPLAY=:0 python3 finals/core/onk-api.py --end --password 'GmailK01!'
"""
from __future__ import annotations

# ── RAW IP ENFORCEMENT (must be first) ──────────────────────────────────────
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
from datetime import datetime

SIGNUP_URL = "https://dashboard.onkernel.com/sign-up"
DISPOSE_URL = "https://dispose.lol"
CODE_RE = re.compile(r"\b\d{6}\b")
VIEW_BTN = 'button[aria-label^="View "]'


class FlowError(Exception):
    pass


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


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
        # dispose.lol reuses the same inbox per session — click "Change" for a NEW address
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


async def wait_for_kernel_code(dpage, timeout_seconds: int = 300) -> str | None:
    """Poll dispose.lol for the Kernel 6-digit code.

    Returns the code, or None after ~5min with no mail (caller rotates to a
    fresh inbox and redoes the run).
    """
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


async def run(password: str = "GmailK01!", email_override=None,
              headless: bool = False, max_attempts: int = 3) -> dict:
    from playwright.async_api import async_playwright

    first, last = "Genev", "Aochea"
    async with async_playwright() as pw:
        args = ["--no-sandbox", "--disable-dev-shm-usage", "--mute-audio",
                "--no-first-run", "--no-default-browser-check", "--disable-sync",
                "--no-service-autorun", "--disable-default-apps",
                "--disable-background-networking", "--disable-component-update",
                "--window-size=1920,1080"]
        if not headless and not _os.environ.get("DISPLAY"):
            log("⚠️ No DISPLAY — falling back to headless")
            headless = True
        log(f"🖥️ Launching {'headless' if headless else 'headed'} Chromium (raw IP)...")
        try:
            browser = await pw.chromium.launch(channel="chrome", headless=headless,
                                               args=args, proxy=None)
        except Exception:
            browser = await pw.chromium.launch(headless=headless, args=args, proxy=None)
        ctx = await browser.new_context(viewport={"width": 1920, "height": 1080},
                                        proxy=None)
        dpage = await ctx.new_page()
        email = None
        spage = None
        # ── attempt loop: fresh dispose Gmail per attempt, ~5min mail budget ──
        for attempt in range(1, max_attempts + 1):
            if email_override and attempt == 1:
                email = email_override
            else:
                email = await create_dispose_email(dpage, fresh=(attempt > 1))
            if spage is not None:
                try:
                    await spage.close()
                except Exception:
                    pass
            # 2. signup
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
                log(f"  ⚠️ No verify page ({spage.url}) — rotating inbox and redoing...")
                email_override = None
                continue
            log("✅ On verify-email-address page")
            # 3. code (~5min budget, then new mail + redo)
            code = await wait_for_kernel_code(dpage)
            if not code:
                log(f"  🔄 Rotating to fresh mail (attempt {attempt}/{max_attempts})...")
                email_override = None
                continue
            await spage.locator('input[autocomplete="one-time-code"]').fill(code)
            await spage.wait_for_timeout(1500)
            await spage.screenshot(path="/tmp/onk-code-filled.png")
            # Clerk often auto-submits on full OTP — click only if still here
            if "verify-email-address" in spage.url:
                try:
                    await spage.get_by_role("button", name="continue").click(timeout=10_000)
                except Exception as e:
                    log(f"  continue click: {e}")
            await spage.wait_for_timeout(8000)
            if "verify-email-address" in spage.url:
                await spage.screenshot(path=f"/tmp/onk-code-rejected-a{attempt}.png")
                log(f"  ⚠️ Code rejected — rotating inbox and redoing...")
                email_override = None
                continue
            log(f"✅ Verified → {spage.url}")
            break
        else:
            await browser.close()
            raise FlowError(f"No verified account after {max_attempts} attempts")
        # 4. survey: other -> specify -> submit
        if "survey" in spage.url:
            await spage.locator('button', has_text="other").first.click(timeout=10_000)
            await spage.wait_for_timeout(2000)
            await spage.fill('input[placeholder*="specify"]', "friend")
            await spage.wait_for_timeout(1000)
            await spage.locator('input[placeholder*="specify"]').evaluate(
                "el => el.parentElement.querySelector('button').click()")
            await spage.wait_for_timeout(8000)
            log(f"✅ Survey done → {spage.url}")
        # 5. org: name + slug -> create -> skip
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
        # 6. onboarding: generate key (optional, one-time) then api-keys page -> create
        api_key = None
        try:
            gen = spage.locator('button', has_text="generate api key")
            if await gen.count():
                await gen.first.click(timeout=8000)
                await spage.wait_for_timeout(4000)
        except Exception as e:
            log(f"  onboarding gen skipped: {e}")
        # api-keys page -> create named key -> full plaintext shown once
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
            # dialog create button (last "create" on page is the dialog one)
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
        result = {"email": email, "password": password, "first": first, "last": last,
                  "api_key": api_key, "created_at": datetime.utcnow().isoformat() + "Z"}
        # save: mail + pwd + cookies + api (repo sessions/ convention)
        repo = "/home/alan/Documents/repos/automation-toolkit/finals/core"
        sdir = _os.path.join(_os.path.dirname(repo), "sessions")
        _os.makedirs(sdir, exist_ok=True)
        fp = _os.path.join(sdir, f"onk_{int(time.time())}.json")
        cookies = await ctx.cookies()
        try:
            state = await ctx.storage_state()
        except Exception:
            state = {}
        open(fp, "w").write(json.dumps(result, indent=2))
        open(fp.replace(".json", ".cookies.json"), "w").write(json.dumps(cookies, indent=2))
        open(fp.replace(".json", ".storage.json"), "w").write(json.dumps(state, indent=2))
        log(f"💾 Saved {fp} (+ .cookies.json + .storage.json, {len(cookies)} cookies)")
        try:
            open(_os.path.join(sdir, "latest_onk.json"), "w").write(
                json.dumps(dict(session_file=fp, **result), indent=2))
        except Exception:
            pass
        await browser.close()
        return result


def main() -> None:
    p = argparse.ArgumentParser(description="Create OnKernel account (headed, raw IP, dispose Gmail)")
    p.add_argument("--end", action="store_true", help="Exit when done (no prompt)")
    p.add_argument("--email", help="Reuse inbox instead of creating fresh dispose.lol Gmail")
    p.add_argument("--password", default="GmailK01!", help="Account password")
    p.add_argument("--headless", action="store_true", help="Headless (default headed)")
    p.add_argument("--attempts", type=int, default=3, help="Max fresh-mail attempts (default 3)")
    a = p.parse_args()
    res = asyncio.run(run(password=a.password, email_override=a.email,
                          headless=a.headless, max_attempts=a.attempts))
    print(json.dumps(res, indent=2))
    if res.get("api_key"):
        # verify key works
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
