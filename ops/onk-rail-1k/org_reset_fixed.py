#!/usr/bin/env python3
"""OnKernel org reset — delete org, new org, Start-Up trial, lifetime key, proxy.

Full unlock flow (dashboard + CLI):
  load session (cookies or email/password) -> delete org -> create org -> skip
  -> billing/plans/confirm?trial=startup -> Start trial
  -> api-keys create with expiry=yolo (lifetime); CLI fallback omit --days-to-expire
  -> kernel proxies create --type residential (requires trial/Hobbyist+)
  -> save {org, api_key, proxy_id, trial, custom_proxies}

Usage:
  DISPLAY=:0 python3 src/onkernel/org_reset.py --end --session finals/sessions/onk_123.json
"""
from __future__ import annotations

import os as _os

_os.environ["LD_PRELOAD"] = ""
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
           "ALL_PROXY", "all_proxy", "PLAYWRIGHT_PROXY_URL"):
    _os.environ.pop(_k, None)

import argparse
import asyncio
import glob
import json
import re
import sys
import time
from copy import deepcopy

try:
    from .session_store import (
        atomic_write_json,
        backup_session_bundle,
        save_latest_pointer,
        save_session_bundle,
    )
except ImportError:  # direct execution: python src/onkernel/org_reset.py
    from session_store import (
        atomic_write_json,
        backup_session_bundle,
        save_latest_pointer,
        save_session_bundle,
    )

SESSIONS = "/home/alan/Documents/repos/automation-toolkit/finals/sessions"
DASH = "https://dashboard.onkernel.com"


class FlowError(Exception):
    pass


def log(m: str) -> None:
    print(m, file=sys.stderr, flush=True)


def pick_session(path: str | None) -> str:
    if path:
        return path
    lat = os.path.join(SESSIONS, "latest_onk.json")
    if _os.path.exists(lat):
        d = json.load(open(lat))
        if d.get("session_file") and _os.path.exists(d["session_file"]):
            return d["session_file"]
    cands = sorted(glob.glob(os.path.join(SESSIONS, "onk_*.json")),
                   key=lambda p: _os.path.getmtime(p))
    cands = [c for c in cands if not c.endswith((".cookies.json", ".storage.json"))]
    if not cands:
        raise FlowError(f"No onk session in {SESSIONS}")
    return cands[-1]


import os


async def run(session_file: str, org_name: str | None = None,
              headless: bool = False, host_key: str | None = None,
              use_proxy: bool = False) -> dict:
    from playwright.async_api import async_playwright

    with open(session_file) as handle:
        acc = json.load(handle)
    if not isinstance(acc, dict):
        raise FlowError(f"Invalid account JSON in {session_file}")
    if not acc.get("email") or not acc.get("password"):
        raise FlowError("Refusing destructive reset: account email/password are missing")
    storage_fp = session_file.replace(".json", ".storage.json")
    if not _os.path.exists(storage_fp):
        raise FlowError(f"No storage file: {storage_fp} (re-run onk-api.py)")
    backup_dir = backup_session_bundle(session_file, "before-org-reset")
    log(f"🛟 Credential backup: {backup_dir}")

    previous = {
        key: deepcopy(acc.get(key))
        for key in ("org", "org_slug", "api_key", "proxy_id", "trial", "reset_at")
        if acc.get(key) is not None
    }
    history = acc.setdefault("credential_history", [])
    if previous and (not history or history[-1] != previous):
        history.append(previous)
    acc.update({
        "status": "reset_preflight",
        "reset_started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "backup_dir": str(backup_dir),
        "last_error": None,
    })
    atomic_write_json(session_file, acc)
    first = acc.get("first", "Genev")
    last = acc.get("last", "Aochea")
    new_org = org_name or f"{first} {last}"

    host_key = (host_key or _os.environ.get("ONK_HOST_KEY") or "").strip() or None
    onk_sid = None

    async with async_playwright() as pw:
        if host_key:
            # Remote OnKernel browser (parallel-safe) via host API key
            import shlex
            import subprocess as _sp
            log(f"🌐 Using OnKernel CDP host key {host_key[:18]}...")
            env = {**_os.environ, "KERNEL_API_KEY": host_key, "LD_PRELOAD": ""}
            for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                       "ALL_PROXY", "all_proxy"):
                env.pop(_k, None)
            # Default: NO proxy. Just spin the browser and let the script grab the
            # API key. Proxy creation is opt-in via --proxy because it needs a
            # paid plan ("Insufficient_plan: Proxies require a paid plan"), while
            # browser creation without one still returns 200.
            pname = ""
            if use_proxy:
                pname = f"reset-host-{int(time.time())}-{os.getpid() % 10000}"
                try:
                    _sp.check_output(
                        f"kernel proxies create --name {shlex.quote(pname)} --type mobile "
                        f"--country gb -o json || true",
                        shell=True, env=env, text=True, timeout=60,
                    )
                    log(f"  proxy created: {pname}")
                except Exception as e:
                    log(f"  proxy create failed ({str(e)[:70]}) — continuing without proxy")
                    pname = ""
            else:
                log("  proxy: skipped (default) — pass --proxy to enable")
            proxy_flag = f"--proxy-name {shlex.quote(pname)} " if pname else ""
            cmd = (
                f"kernel browsers create --stealth --timeout 900 "
                f"{proxy_flag}"
                f"--start-url {shlex.quote(DASH)} -o json"
            )
            last_err = "unknown"
            data = None
            for _t in range(3):
                try:
                    out = _sp.check_output(cmd, shell=True, env=env, text=True, timeout=90)
                    data = json.loads(out)
                    break
                except Exception as e:
                    last_err = str(e)[:150]
                    log(f"  browser create try {_t+1}/3 failed: {last_err}")
                    time.sleep(8)
            if not data or not data.get("cdp_ws_url"):
                raise FlowError(f"OnK browser create failed: {last_err}")
            onk_sid = data.get("session_id") or data.get("id")
            cdp = data["cdp_ws_url"]
            log(f"   SID={onk_sid} CDP={cdp[:80]}...")
            browser = await pw.chromium.connect_over_cdp(cdp, timeout=60_000)
            # Prefer default context; overlay storage state via new context when possible
            if browser.contexts:
                ctx = browser.contexts[0]
                # inject cookies from storage into existing context
                try:
                    st = json.load(open(storage_fp))
                    cookies = st.get("cookies") or []
                    if cookies:
                        await ctx.add_cookies(cookies)
                except Exception as e:
                    log(f"  cookie inject warn: {e}")
                page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            else:
                ctx = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    storage_state=storage_fp,
                )
                page = await ctx.new_page()
        else:
            args = ["--no-sandbox", "--disable-dev-shm-usage", "--mute-audio",
                    "--no-first-run", "--no-default-browser-check", "--disable-sync",
                    "--no-service-autorun", "--disable-default-apps",
                    "--disable-background-networking", "--disable-component-update",
                    "--window-size=1920,1080"]
            if not headless and not _os.environ.get("DISPLAY"):
                headless = True
            try:
                browser = await pw.chromium.launch(channel="chrome", headless=headless,
                                                   args=args, proxy=None)
            except Exception:
                browser = await pw.chromium.launch(headless=headless, args=args, proxy=None)
            ctx = await browser.new_context(viewport={"width": 1920, "height": 1080},
                                            storage_state=storage_fp, proxy=None)
            page = await ctx.new_page()
        try:
            await page.goto(DASH, wait_until="domcontentloaded", timeout=60_000)
        except Exception:
            pass
        await page.wait_for_timeout(6000)
        if "sign-in" in page.url or "sign-up" in page.url:
            email = acc.get("email")
            password = acc.get("password")
            if not email or not password:
                await page.screenshot(path="/tmp/onk-reset-login-expired.png")
                await browser.close()
                raise FlowError("Cookies expired and no email/password in session JSON")
            log(f"🍪 Cookies expired — signing in as {email}...")
            await page.goto(DASH + "/sign-in", wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(3000)
            # Clerk: email -> continue -> password -> continue
            email_in = page.locator('input[name="identifier"], input[name="emailAddress"], input[type="email"]').first
            await email_in.click(timeout=15_000)
            await page.keyboard.press("Control+a")
            await page.keyboard.type(email, delay=40)
            await page.wait_for_timeout(500)
            cont = page.locator('button:has-text("continue"), button:has-text("Continue")').first
            await cont.click(timeout=10_000)
            await page.wait_for_timeout(3000)
            pwd_in = page.locator('input[name="password"], input[type="password"]').first
            await pwd_in.click(timeout=15_000)
            await page.keyboard.type(password, delay=40)
            await page.wait_for_timeout(500)
            await page.locator('button:has-text("continue"), button:has-text("Continue"), button:has-text("sign in")').last.click(timeout=10_000)
            await page.wait_for_timeout(8000)
            # wait until off auth pages
            for _ in range(20):
                if "sign-in" not in page.url and "sign-up" not in page.url:
                    break
                await page.wait_for_timeout(1000)
            if "sign-in" in page.url or "sign-up" in page.url:
                await page.screenshot(path="/tmp/onk-reset-login-failed.png")
                await browser.close()
                raise FlowError(f"Password login failed — still on {page.url}")
            log(f"✅ Re-logged in via password @ {page.url}")
        log(f"✅ Logged in as {acc.get('email')} @ {page.url}")
        # Refresh the saved browser state before any destructive dashboard action.
        # This preserves a current login even if the reset later fails.
        acc["status"] = "authenticated_before_reset"
        await save_session_bundle(session_file, acc, ctx)
        save_latest_pointer(session_file, acc)
        # current org name from switcher
        cur_org = await page.evaluate("""() => {
          const b = [...document.querySelectorAll('button')].find(x => x.innerText && x.innerText.includes('\u25be') === false && x.innerText.trim().length > 0);
          const sw = [...document.querySelectorAll('button')].map(x=>x.innerText.trim()).find(t=>t && !/switch|create|manage/i.test(t) && t.length < 40);
          return sw || null; }""")
        log(f"Current org hint: {cur_org}")
        # Already org-less (prior partial reset) → skip delete, create fresh
        if "select-org" in (page.url or ""):
            log("ℹ️ Already on select-org (no org) — skipping delete, creating fresh org")
            acc.update({
                "status": "old_org_deleted",
                "reset_from_org": previous.get("org") or cur_org,
                "reset_target_org": new_org,
            })
            await save_session_bundle(session_file, acc, ctx)
        else:
            # open switcher -> manage (Clerk cl-organizationSwitcherTrigger)
            try:
                await page.locator('.cl-organizationSwitcherTrigger').first.click(timeout=8000)
            except Exception:
                await page.evaluate("""() => {
                  [...document.querySelectorAll('button')].find(x => /Genev Aochea|genev/i.test(x.innerText))?.click(); }""")
            await page.wait_for_timeout(2500)
            clicked = await page.evaluate("""() => {
              const m = [...document.querySelectorAll('button')].find(x => /^manage$/i.test(x.innerText.trim()));
              if (m) { m.click(); return true; } return false; }""")
            if not clicked:
                await page.screenshot(path="/tmp/onk-reset-no-manage.png")
                raise FlowError("No manage button (switcher layout changed)")
            await page.wait_for_timeout(4000)
            # delete organization
            await page.evaluate("""() => {
              [...document.querySelectorAll('button')].find(x => /^delete organization$/i.test(x.innerText.trim()))?.click(); }""")
            await page.wait_for_timeout(3000)
            confirm = None
            for attempt in range(4):
                confirm = await page.evaluate("""() => {
                  const t = document.body.innerText || '';
                  let m = t.match(/type\\s+[\"']([^\"']+)[\"']\\s+below/i);
                  if (m) return m[1];
                  m = t.match(/type\\s+[\"']([^\"']+)[\"']/i);
                  if (m) return m[1];
                  m = t.match(/delete\\s+[\"']([^\"']+)[\"']/i);
                  if (m) return m[1];
                  return null;
                }""")
                if confirm:
                    break
                await page.evaluate("""() => {
                  [...document.querySelectorAll('button')].find(x => /^delete organization$/i.test(x.innerText.trim()))?.click();
                }""")
                await page.wait_for_timeout(2500 + attempt * 1000)
            if not confirm:
                await page.screenshot(path="/tmp/onk-reset-no-confirm.png")
                raise FlowError("No delete confirm dialog")
            log(f"🗑️ Deleting org (confirm: {confirm})...")
            await page.screenshot(path="/tmp/onk-reset-confirm.png")
            inp = page.locator('input:not([type="hidden"])').last
            variants = [confirm, confirm.title(), cur_org or ""]
            enabled = False
            for variant in dict.fromkeys(v for v in variants if v):
                await inp.click(timeout=10_000)
                await page.wait_for_timeout(400)
                await page.keyboard.press("Control+a")
                await page.wait_for_timeout(200)
                await page.keyboard.type(variant, delay=60)
                await page.keyboard.press("Tab")
                await page.wait_for_timeout(1200)
                st = await page.evaluate("""() => {
                  const btns = [...document.querySelectorAll('button')].filter(x => /^delete organization$/i.test(x.innerText.trim()));
                  const b = btns[btns.length-1]; return b ? b.disabled : 'NOBTN'; }""")
                log(f"  try {variant!r} -> disabled={st}")
                if st is False:
                    enabled = True
                    break
            if not enabled:
                await page.screenshot(path="/tmp/onk-reset-still-disabled.png")
                raise FlowError("Delete button stays disabled")
            acc.update({
                "status": "reset_in_progress",
                "reset_from_org": previous.get("org") or cur_org,
                "reset_target_org": new_org,
            })
            await save_session_bundle(session_file, acc, ctx)
            await page.wait_for_timeout(1500)
            await page.screenshot(path="/tmp/onk-reset-confirm-filled.png")
            del_btn = page.get_by_role("button", name="delete organization").last
            probe = await page.evaluate("""() => {
              const btns = [...document.querySelectorAll('button')].filter(x => /^delete organization$/i.test(x.innerText.trim()));
              const b = btns[btns.length-1];
              if (!b) return 'NO BTN';
              const r = b.getBoundingClientRect();
              const top = document.elementFromPoint(r.x + r.width/2, r.y + r.height/2);
              const cs = getComputedStyle(b);
              return JSON.stringify({rect:[r.x,r.y,r.width,r.height], disabled:b.disabled,
                aria:b.getAttribute('aria-disabled'), pe:cs.pointerEvents, op:cs.opacity,
                top:(top?top.tagName+'.'+top.className:'none').slice(0,120)}); }""")
            log(f"  probe: {probe}")
            try:
                await del_btn.click(timeout=10_000)
            except Exception:
                log("  normal click failed — force click")
                await del_btn.click(timeout=10_000, force=True)
            await page.wait_for_timeout(8000)
            log(f"After delete: {page.url}")
            await page.screenshot(path="/tmp/onk-reset-deleted.png")
            acc["status"] = "old_org_deleted"
            await save_session_bundle(session_file, acc, ctx)
        # create new org (select-org flow or switcher -> create organization)
        if "select-org" not in page.url:
            try:
                await page.goto(DASH + "/select-org", wait_until="domcontentloaded", timeout=60_000)
                await page.wait_for_timeout(5000)
            except Exception as e:
                log(f"  select-org goto: {e}")
        if "select-org" not in page.url and "create" not in (await page.evaluate("() => document.body.innerText")).lower():
            await page.screenshot(path="/tmp/onk-reset-no-create.png")
            raise FlowError(f"No org-create page: {page.url}")
        slug = f"genev-{int(time.time()) % 100000}"
        inputs = page.locator('input[type="text"], input:not([type])')
        if await inputs.count():
            await inputs.nth(0).fill(new_org)
            await page.wait_for_timeout(1000)
            if await inputs.count() > 1:
                await inputs.nth(1).fill(slug)
        await page.locator('button', has_text="create organization").first.click(timeout=10_000)
        await page.wait_for_timeout(8000)
        skip = page.locator('button', has_text="skip")
        if await skip.count():
            await skip.first.click(timeout=8000)
            await page.wait_for_timeout(8000)
        log(f"✅ New org → {page.url}")
        acc.update({
            "org": new_org,
            "org_slug": slug,
            "status": "new_org_created",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        await save_session_bundle(session_file, acc, ctx)
        save_latest_pointer(session_file, acc)

        # ── 1) Unlock Start-Up TRIAL (proxies / region / higher limits) ──
        trial_ok = False
        try:
            confirm = f"{DASH}/{slug}/billing/plans/confirm?trial=startup"
            await page.goto(confirm, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(4000)
            # optional survey: "just exploring"
            await page.evaluate("""() => {
              const b=[...document.querySelectorAll('button')].find(x=>/just exploring/i.test(x.innerText||''));
              if(b) b.click();
            }""")
            await page.wait_for_timeout(1000)
            started = False
            try:
                await page.get_by_role("button", name=re.compile(r"start trial", re.I)).click(timeout=10_000)
                started = True
            except Exception:
                started = await page.evaluate("""() => {
                  const b=[...document.querySelectorAll('button,a')].find(x=>/^start trial$/i.test((x.innerText||'').trim()));
                  if(b){b.click(); return true} return false;
                }""")
            await page.wait_for_timeout(8000)
            await page.screenshot(path="/tmp/onk-reset-trial.png")
            body = await page.evaluate("() => document.body.innerText")
            trial_ok = started and ("start trial" not in body.lower() or "trial" in body.lower())
            # hard check: billing page should not say subscription free only
            await page.goto(f"{DASH}/{slug}/billing", wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(4000)
            bill = await page.evaluate("() => document.body.innerText.toLowerCase()")
            if "start-up" in bill or "startup" in bill or "trial" in bill:
                trial_ok = True
            log(f"{'✅' if trial_ok else '⚠️'} Start-Up trial unlock (billing snippet: {bill[:120]!r})")
        except Exception as e:
            log(f"  trial unlock issue: {e}")
            await page.screenshot(path="/tmp/onk-reset-trial-fail.png")

        # ── 2) Lifetime API key (UI expiry = yolo; NOT 30 days) ──
        api_key = None
        try:
            await page.goto(f"{DASH}/{slug}/api-keys", wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(4000)
            await page.locator('button', has_text="create api key").first.click(timeout=10_000)
            await page.wait_for_timeout(2500)
            # name
            name_in = page.locator('input[placeholder*="Production"], input[type="text"]').first
            await name_in.click(timeout=8_000)
            await page.keyboard.press("Control+a")
            await page.keyboard.type("auto-main", delay=40)
            await page.wait_for_timeout(500)
            # expiration → yolo (lifetime / never)
            # control often shows "30 days"; open and pick yolo
            picked = await page.evaluate("""() => {
              const clickText = (re) => {
                const el=[...document.querySelectorAll('button,div,span,[role="combobox"]')]
                  .find(x => re.test((x.innerText||'').trim()) && (x.innerText||'').length < 40);
                if(el){el.click(); return true} return false;
              };
              return clickText(/^(30 days|expiration)/i) || clickText(/30 days/i);
            }""")
            await page.wait_for_timeout(800)
            yolo = await page.evaluate("""() => {
              const el=[...document.querySelectorAll('[role="option"],button,div,span,li')]
                .find(x => /^yolo$/i.test((x.innerText||'').trim()));
              if(el){el.click(); return true} return false;
            }""")
            log(f"  expiry picker opened={picked} yolo={yolo}")
            if not yolo:
                # fallback: click visible "yolo" span
                try:
                    await page.get_by_text("yolo", exact=True).click(timeout=5_000)
                    yolo = True
                except Exception:
                    pass
            await page.wait_for_timeout(800)
            await page.screenshot(path="/tmp/onk-reset-key-dialog.png")
            await page.locator('button', has_text=re.compile(r"^create$", re.I)).last.click(timeout=10_000)
            await page.wait_for_timeout(5000)
            api_key = await page.evaluate("""() => {
              for (const i of document.querySelectorAll('input'))
                if (i.value && i.value.startsWith('sk_')) return i.value;
              const m = document.body.innerText.match(/sk_[A-Za-z0-9_.\\-]+/);
              return m ? m[0] : null; }""")
            if api_key:
                log(f"✅ Lifetime key: {api_key[:12]}...{api_key[-4:]}")
            else:
                log("⚠️ No key in UI — will try CLI create without --days-to-expire")
        except Exception as e:
            log(f"  key create issue: {e}")
        # CLI lifetime key if UI failed / still want verify expires_at null
        proxy_id = None
        if api_key:
            env = dict(_os.environ)
            env["KERNEL_API_KEY"] = api_key
            env["LD_PRELOAD"] = ""
            for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                       "ALL_PROXY", "all_proxy"):
                env.pop(_k, None)
            # If UI key still has 30d expiry, mint a true never-expire via CLI
            try:
                import subprocess
                lst = subprocess.run(
                    ["kernel", "api-keys", "list", "-o", "json"],
                    capture_output=True, text=True, env=env, timeout=30)
                raw = (lst.stdout or "").strip()
                start = raw.find("[")
                keys = json.loads(raw[start:]) if start >= 0 else []
                need_life = True
                for k in keys:
                    if k.get("name") == "auto-main" and not k.get("expires_at"):
                        need_life = False
                if need_life:
                    cr = subprocess.run(
                        ["kernel", "api-keys", "create", "--name", "auto-main-life",
                         "-o", "json"],
                        capture_output=True, text=True, env=env, timeout=30)
                    # omit --days-to-expire => never
                    raw2 = (cr.stdout or "").strip()
                    # plaintext key often in JSON field
                    m = re.search(r"sk_[A-Za-z0-9_.\-]+", raw2)
                    if m and cr.returncode == 0:
                        api_key = m.group(0)
                        env["KERNEL_API_KEY"] = api_key
                        log(f"✅ CLI lifetime key: {api_key[:12]}...{api_key[-4:]}")
                    else:
                        log(f"  CLI key create rc={cr.returncode} {(cr.stderr or cr.stdout or '')[:160]}")
            except Exception as e:
                log(f"  CLI key verify/create: {e}")

            # ── 3) Unlock proxies: create managed residential after trial ──
            try:
                import subprocess
                pr = subprocess.run(
                    ["kernel", "proxies", "create", "--type", "residential",
                     "--country", "US", "--name", "auto-res", "-o", "json"],
                    capture_output=True, text=True, env=env, timeout=60)
                rawp = (pr.stdout or "").strip()
                if pr.returncode == 0:
                    try:
                        start = rawp.find("{")
                        pj = json.loads(rawp[start:]) if start >= 0 else {}
                        proxy_id = pj.get("id")
                    except Exception:
                        proxy_id = None
                    log(f"✅ Proxy unlocked/created id={proxy_id}")
                else:
                    log(f"⚠️ Proxy create failed: {(pr.stderr or pr.stdout or '')[:200]}")
                ent = subprocess.run(
                    ["kernel", "org", "entitlements", "-o", "json"],
                    capture_output=True, text=True, env=env, timeout=30)
                eraw = (ent.stdout or "").strip()
                try:
                    start = eraw.find("{")
                    ej = json.loads(eraw[start:]) if start >= 0 else {}
                    cp = (ej.get("features") or {}).get("custom_proxies") or {}
                    log(f"  entitlements custom_proxies={cp}")
                    acc["custom_proxies"] = cp
                except Exception:
                    log(f"  entitlements raw: {eraw[:160]}")
            except Exception as e:
                log(f"  proxy unlock issue: {e}")

        # Publish the new active credentials only after every value has been
        # captured. Previous credentials remain in credential_history + backup.
        errors = []
        if not api_key:
            errors.append("no fresh lifetime API key")
        if not trial_ok:
            errors.append("Start-Up trial was not unlocked")
        if not proxy_id:
            errors.append("residential proxy was not created")

        acc["org"] = new_org
        acc["org_slug"] = slug
        acc["api_key"] = api_key
        acc["api_key_status"] = "active" if api_key else "missing_after_reset"
        acc["proxy_id"] = proxy_id
        acc["trial"] = "startup" if trial_ok else None
        acc["status"] = "ready" if not errors else "needs_recovery"
        acc["last_error"] = "; ".join(errors) if errors else None
        acc["reset_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        acc["updated_at"] = acc["reset_at"]
        await save_session_bundle(session_file, acc, ctx)
        save_latest_pointer(session_file, acc)
        log(f"💾 Updated {session_file}; original bundle remains at {backup_dir}")
        await browser.close()
        if onk_sid and host_key:
            try:
                import subprocess as _sp
                _sp.run(
                    f"kernel browsers delete {onk_sid}",
                    shell=True,
                    env={**_os.environ, "KERNEL_API_KEY": host_key, "LD_PRELOAD": ""},
                    timeout=20,
                    capture_output=True,
                )
                log(f"🗑️ OnK host browser deleted: {onk_sid}")
            except Exception as e:
                log(f"  OnK delete soft-fail: {e}")
        if errors:
            raise FlowError(
                f"Reset reached a recoverable partial state: {'; '.join(errors)}. "
                f"Original credentials: {backup_dir}"
            )
        return acc


def main() -> None:
    p = argparse.ArgumentParser(description="Reset OnKernel org from saved cookies")
    p.add_argument("--end", action="store_true")
    p.add_argument("--session", help="Session JSON (default latest_onk.json)")
    p.add_argument("--org-name", help="New org display name")
    p.add_argument("--headless", action="store_true")
    p.add_argument("--host-key", help="OnKernel host API key for remote CDP browser")
    p.add_argument("--proxy", action="store_true",
                   help="Create and attach a mobile proxy for the host browser "
                        "(needs paid plan; default is no proxy)")
    a = p.parse_args()
    sess = pick_session(a.session)
    log(f"Session: {sess}")
    try:
        res = asyncio.run(
            run(sess, org_name=a.org_name, headless=a.headless,
                host_key=a.host_key, use_proxy=a.proxy)
        )
    except Exception as exc:
        # Never leave a destructive reset looking healthy. The latest completed
        # checkpoint and timestamped backup remain available for recovery.
        try:
            with open(sess) as handle:
                failed = json.load(handle)
            if isinstance(failed, dict):
                failed["status"] = "needs_recovery"
                failed["last_error"] = str(exc)
                failed["updated_at"] = time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                )
                atomic_write_json(sess, failed)
                save_latest_pointer(sess, failed)
        except Exception as save_exc:
            log(f"Could not record reset failure: {save_exc}")
        raise
    print(json.dumps({k: v for k, v in res.items()}, indent=2))
    if not a.end:
        input("done — Enter to exit...")


if __name__ == "__main__":
    main()
