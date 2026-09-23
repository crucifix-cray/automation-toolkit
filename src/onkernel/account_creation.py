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
from pathlib import Path

try:
    from .session_store import save_latest_pointer, save_session_bundle
except ImportError:  # direct execution: python src/onkernel/account_creation.py
    from session_store import save_latest_pointer, save_session_bundle

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
    current = await current_dispose_email(dpage)
    stale = current if fresh else None
    if fresh:
        # dispose.lol keeps one inbox per cookie jar. Change briefly clears the
        # address (None) then may re-render the SAME one — wait until different,
        # and clear site cookies as a last resort.
        rotated = False
        for rot in range(1, 8):
            try:
                chg = dpage.locator("button", has_text="Change")
                if not await chg.count():
                    break
                await chg.first.click(timeout=8000)
                new = None
                for _ in range(15):
                    await dpage.wait_for_timeout(1200)
                    new = await current_dispose_email(dpage)
                    if new and new != stale:
                        break
                log(f"  🔄 Rotated inbox (try {rot}): {stale} -> {new}")
                if new and new != stale:
                    current = new
                    rotated = True
                    break
            except Exception as e:
                log(f"  change click: {e}")
        if not rotated:
            try:
                await dpage.context.clear_cookies()
                await dpage.goto(DISPOSE_URL, wait_until="domcontentloaded", timeout=60_000)
                await dpage.wait_for_timeout(5000)
                new = await current_dispose_email(dpage)
                log(f"  🔄 Cookie-cleared inbox: {stale} -> {new}")
                if new and new != stale:
                    current = new
                    rotated = True
            except Exception as e:
                log(f"  cookie clear: {e}")
        if not rotated:
            raise FlowError(f"Could not rotate dispose inbox away from {stale}")
    for attempt in range(1, 6):
        email = await dpage.evaluate("""() => {
            const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT,null);
            let n; while(n=w.nextNode()){ const t=n.textContent.trim();
              if(t.includes('@gmail.com')&&t.length<80) return t; }
            for(const i of document.querySelectorAll('input'))
              if(i.value&&i.value.includes('@gmail.com')) return i.value;
            return null; }""")
        if email and "@gmail.com" in email:
            if stale and email.strip() == stale.strip():
                raise FlowError(f"Dispose still on stale inbox {email.strip()}")
            log(f"✅ Mailbox: {email.strip()}")
            return email.strip()
        log(f"  ⏳ not rendered (attempt {attempt}/5)...")
        await dpage.wait_for_timeout(2000)
        await dpage.reload(wait_until="domcontentloaded")
        await dpage.wait_for_timeout(3000)
    await dpage.screenshot(path="/tmp/onk-dispose-error.png")
    raise FlowError("No dispose.lol Gmail after 5 attempts")


async def wait_for_kernel_code(dpage, timeout_seconds: int = 300,
                               resend_page=None) -> str | None:
    """Poll dispose.lol for the Kernel 6-digit code.

    Returns the code, or None after ~5min with no mail (caller rotates to a
    fresh inbox and redoes the run). Optionally clicks Clerk "Resend" once
    mid-wait if resend_page is provided.
    """
    log("📥 Waiting for Kernel code on dispose.lol (~5min budget)...")
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    check = 0
    resent = False
    while asyncio.get_running_loop().time() < deadline:
        check += 1
        # Mid-wait: ask Clerk to resend once if nothing has arrived yet.
        if (not resent and resend_page is not None and check == 12):
            try:
                btn = resend_page.get_by_role("button", name=re.compile(r"resend", re.I))
                if await btn.count():
                    await btn.first.click(timeout=5000)
                    resent = True
                    log("  🔁 Clicked Clerk Resend")
            except Exception as e:
                log(f"  resend click: {e}")
        try:
            await dpage.reload(wait_until="domcontentloaded")
        except Exception:
            pass
        await dpage.wait_for_timeout(2500)
        try:
            buttons = await dpage.locator(VIEW_BTN).all()
        except Exception:
            buttons = []
        # Fallback: any button whose aria-label looks like a mail row.
        if not buttons:
            try:
                buttons = await dpage.locator('button[aria-label*="@"], button[aria-label*="code"], button[aria-label*="verification"]').all()
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
            if "kernel" in aria.lower() or "verif" in aria.lower() or m:
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
              headless: bool = False, max_attempts: int = 3,
              cdp_url: str | None = None,
              provider_name: str | None = None) -> dict:
    from playwright.async_api import async_playwright

    first, last = "Genev", "Aochea"
    sessions_dir = Path(__file__).resolve().parents[2] / "finals" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    session_file = sessions_dir / f"onk_{time.time_ns()}_{_os.getpid()}.json"
    result = {
        "email": None,
        "password": password,
        "first": first,
        "last": last,
        "api_key": None,
        "status": "starting",
        "browser_provider": provider_name or ("onkernel-cdp" if cdp_url else "local"),
        "created_at": datetime.utcnow().isoformat() + "Z",
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    async with async_playwright() as pw:
        args = ["--no-sandbox", "--disable-dev-shm-usage", "--mute-audio",
                "--no-first-run", "--no-default-browser-check", "--disable-sync",
                "--no-service-autorun", "--disable-default-apps",
                "--disable-background-networking", "--disable-component-update",
                "--window-size=1920,1080"]
        if not headless and not _os.environ.get("DISPLAY"):
            log("⚠️ No DISPLAY — falling back to headless")
            headless = True
        if cdp_url:
            log(f"🌐 Connecting to OnKernel CDP provider {provider_name or 'unknown'}...")
            browser = await pw.chromium.connect_over_cdp(cdp_url, timeout=60_000)
            if browser.contexts:
                ctx = browser.contexts[0]
            else:
                ctx = await browser.new_context(
                    viewport={"width": 1920, "height": 1080}
                )
        else:
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
            # Persist the credentials before submitting the signup form. If the
            # browser dies later, the account email/password are still recoverable.
            result.update({
                "email": email,
                "status": "signup_pending",
                "attempt": attempt,
                "updated_at": datetime.utcnow().isoformat() + "Z",
            })
            await save_session_bundle(session_file, result, ctx)
            save_latest_pointer(session_file, result)
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
            code = await wait_for_kernel_code(dpage, resend_page=spage)
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
            result.update({
                "status": "email_verified",
                "updated_at": datetime.utcnow().isoformat() + "Z",
            })
            await save_session_bundle(session_file, result, ctx)
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
        slug = None
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
            result.update({
                "org": f"{first} {last}",
                "org_slug": slug,
                "status": "org_created",
                "updated_at": datetime.utcnow().isoformat() + "Z",
            })
            await save_session_bundle(session_file, result, ctx)
        if not slug:
            match = re.search(r"dashboard\.onkernel\.com/([^/?]+)", spage.url)
            slug = match.group(1) if match else None
            if slug:
                result["org_slug"] = slug

        # 6. Start-Up trial unlock. Save the account first; a UI change here
        # must never erase the already-created login.
        trial_ok = False
        if slug:
            try:
                await spage.goto(
                    f"https://dashboard.onkernel.com/{slug}/billing/plans/confirm?trial=startup",
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )
                await spage.wait_for_timeout(4000)
                await spage.evaluate("""() => {
                  const b=[...document.querySelectorAll('button')]
                    .find(x=>/just exploring/i.test(x.innerText||''));
                  if(b) b.click();
                }""")
                await spage.wait_for_timeout(700)
                start = spage.get_by_role(
                    "button", name=re.compile(r"start trial", re.I)
                )
                await start.click(timeout=10_000)
                await spage.wait_for_timeout(8000)
                await spage.goto(
                    f"https://dashboard.onkernel.com/{slug}/billing",
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )
                await spage.wait_for_timeout(3500)
                billing = await spage.evaluate(
                    "() => document.body.innerText.toLowerCase()"
                )
                trial_ok = (
                    "start-up" in billing
                    or "startup" in billing
                    or "trial" in billing
                )
            except Exception as e:
                log(f"  trial unlock issue: {e}")
        result.update({
            "trial": "startup" if trial_ok else None,
            "status": "trial_started" if trial_ok else "needs_trial",
            "updated_at": datetime.utcnow().isoformat() + "Z",
        })
        await save_session_bundle(session_file, result, ctx)

        # 7. Create a bootstrap dashboard key, then replace it with a verified
        # never-expiring CLI key. The bootstrap remains server-side but is not
        # written as the canonical key unless lifetime creation succeeds.
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
        bootstrap_key = api_key

        proxy_id = None
        custom_proxies = {}
        if bootstrap_key:
            env = dict(_os.environ)
            env["KERNEL_API_KEY"] = bootstrap_key
            env["LD_PRELOAD"] = ""
            for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                        "ALL_PROXY", "all_proxy"):
                env.pop(key, None)
            try:
                created = subprocess.run(
                    ["kernel", "api-keys", "create", "--name", "auto-main-life",
                     "-o", "json"],
                    capture_output=True, text=True, env=env, timeout=30,
                )
                match = re.search(
                    r"sk_[A-Za-z0-9_.\-]+", created.stdout or ""
                )
                if created.returncode == 0 and match:
                    api_key = match.group(0)
                    env["KERNEL_API_KEY"] = api_key
                    log(f"✅ Lifetime API key: {api_key[:12]}...{api_key[-4:]}")
                else:
                    api_key = None
                    log(
                        "  lifetime key create failed: "
                        f"{(created.stderr or created.stdout or '')[:180]}"
                    )
            except Exception as e:
                api_key = None
                log(f"  lifetime key create issue: {e}")

            if api_key:
                try:
                    proxy = subprocess.run(
                        ["kernel", "proxies", "create", "--type", "residential",
                         "--country", "US", "--name", "auto-res", "-o", "json"],
                        capture_output=True, text=True, env=env, timeout=60,
                    )
                    if proxy.returncode == 0:
                        raw = proxy.stdout or ""
                        start = raw.find("{")
                        proxy_data = json.loads(raw[start:]) if start >= 0 else {}
                        proxy_id = proxy_data.get("id")
                    entitlements = subprocess.run(
                        ["kernel", "org", "entitlements", "-o", "json"],
                        capture_output=True, text=True, env=env, timeout=30,
                    )
                    raw = entitlements.stdout or ""
                    start = raw.find("{")
                    if start >= 0:
                        data = json.loads(raw[start:])
                        custom_proxies = (
                            (data.get("features") or {}).get("custom_proxies")
                            or {}
                        )
                except Exception as e:
                    log(f"  proxy unlock issue: {e}")

        errors = []
        if not trial_ok:
            errors.append("Start-Up trial missing")
        if not api_key:
            errors.append("lifetime API key missing")
        if not proxy_id:
            errors.append("residential proxy missing")
        result.update({
            "api_key": api_key,
            "bootstrap_key_created": bool(bootstrap_key),
            "proxy_id": proxy_id,
            "custom_proxies": custom_proxies,
            "status": "ready" if not errors else "needs_unlock",
            "last_error": "; ".join(errors) if errors else None,
            "updated_at": datetime.utcnow().isoformat() + "Z",
        })
        await save_session_bundle(session_file, result, ctx)
        save_latest_pointer(session_file, result)
        log(f"💾 Saved {session_file} (+ cookies + storage)")
        await browser.close()
        if errors:
            raise FlowError(
                f"Account credentials are safely saved at {session_file}, "
                f"but unlock is incomplete: {'; '.join(errors)}"
            )
        return result


def main() -> None:
    p = argparse.ArgumentParser(description="Create OnKernel account (headed, raw IP, dispose Gmail)")
    p.add_argument("--end", action="store_true", help="Exit when done (no prompt)")
    p.add_argument("--email", help="Reuse inbox instead of creating fresh dispose.lol Gmail")
    p.add_argument("--password", default="GmailK01!", help="Account password")
    p.add_argument("--headless", action="store_true", help="Headless (default headed)")
    p.add_argument("--attempts", type=int, default=3, help="Max fresh-mail attempts (default 3)")
    p.add_argument(
        "--cdp-url",
        default=_os.environ.get("ONKERNEL_CDP_URL"),
        help="Use an existing remote Chromium CDP endpoint (or ONKERNEL_CDP_URL)",
    )
    p.add_argument(
        "--provider-name",
        default=_os.environ.get("ONKERNEL_PROVIDER_NAME"),
        help="Non-secret provider label saved in the account record",
    )
    a = p.parse_args()
    res = asyncio.run(run(password=a.password, email_override=a.email,
                          headless=a.headless, max_attempts=a.attempts,
                          cdp_url=a.cdp_url, provider_name=a.provider_name))
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
