#!/usr/bin/env python3
"""OnKernel org reset — load saved cookies, kill org, new org, fresh API key.

Flow (verified selectors, 2026-09-09, headed raw IP):
  load <session>.storage.json -> dashboard.onkernel.com (logged in via Clerk cookies)
  -> org switcher -> manage -> delete organization -> type "<org>" -> delete
  -> create organization (name + slug) -> skip invites
  -> api-keys -> create api key "auto-main" -> full sk_... shown once
  -> update session JSON {org, api_key} + refresh cookies/storage files.

Usage:
  DISPLAY=:0 python3 finals/core/onk-org-reset.py --end
  DISPLAY=:0 python3 finals/core/onk-org-reset.py --end --session finals/sessions/onk_123.json
  DISPLAY=:0 python3 finals/core/onk-org-reset.py --end --org-name "Genev X"
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
              headless: bool = False) -> dict:
    from playwright.async_api import async_playwright

    acc = json.load(open(session_file))
    storage_fp = session_file.replace(".json", ".storage.json")
    if not _os.path.exists(storage_fp):
        raise FlowError(f"No storage file: {storage_fp} (re-run onk-api.py)")
    first = acc.get("first", "Genev")
    last = acc.get("last", "Aochea")
    new_org = org_name or f"{first} {last}"

    async with async_playwright() as pw:
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
        await page.goto(DASH, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(6000)
        if "sign-in" in page.url or "sign-up" in page.url:
            await page.screenshot(path="/tmp/onk-reset-login-expired.png")
            await browser.close()
            raise FlowError("Cookies expired (on login page) — re-run onk-api.py")
        log(f"✅ Logged in as {acc.get('email')} @ {page.url}")
        # current org name from switcher
        cur_org = await page.evaluate("""() => {
          const b = [...document.querySelectorAll('button')].find(x => x.innerText && x.innerText.includes('\u25be') === false && x.innerText.trim().length > 0);
          const sw = [...document.querySelectorAll('button')].map(x=>x.innerText.trim()).find(t=>t && !/switch|create|manage/i.test(t) && t.length < 40);
          return sw || null; }""")
        log(f"Current org hint: {cur_org}")
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
        confirm = await page.evaluate("""() => {
          const t = document.body.innerText;
          const m = t.match(/type "([^"]+)" below to continue/);
          return m ? m[1] : null; }""")
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
        # fresh api key
        api_key = None
        try:
            await page.evaluate("""() => {
              const a=[...document.querySelectorAll('a')].find(x=>/api.keys/i.test(x.innerText));
              if(a) a.click(); }""")
            await page.wait_for_timeout(6000)
            await page.locator('button', has_text="create api key").first.click(timeout=10_000)
            await page.wait_for_timeout(4000)
            name_in = page.locator('input[placeholder*="Production"]')
            if await name_in.count():
                await name_in.fill("auto-main")
                await page.wait_for_timeout(1000)
            await page.locator('button', has_text="create").last.click(timeout=8000)
            await page.wait_for_timeout(5000)
            api_key = await page.evaluate("""() => {
              for (const i of document.querySelectorAll('input'))
                if (i.value && i.value.startsWith('sk_')) return i.value;
              const m = document.body.innerText.match(/sk_[A-Za-z0-9_.\\-]+/);
              return m ? m[0] : null; }""")
            if api_key:
                log(f"✅ Fresh key: {api_key[:12]}...{api_key[-4:]}")
        except Exception as e:
            log(f"  key create issue: {e}")
        # update session files (mail + pwd + cookies + api)
        acc["org"] = new_org
        acc["org_slug"] = slug
        acc["api_key"] = api_key
        acc["reset_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        open(session_file, "w").write(json.dumps(acc, indent=2))
        cookies = await ctx.cookies()
        open(session_file.replace(".json", ".cookies.json"), "w").write(json.dumps(cookies, indent=2))
        try:
            state = await ctx.storage_state()
            open(session_file.replace(".json", ".storage.json"), "w").write(json.dumps(state, indent=2))
        except Exception as e:
            log(f"  storage refresh skipped: {e}")
        log(f"💾 Updated {session_file} ({len(cookies)} cookies)")
        await browser.close()
        if not api_key:
            raise FlowError("No fresh API key captured")
        return acc


def main() -> None:
    p = argparse.ArgumentParser(description="Reset OnKernel org from saved cookies")
    p.add_argument("--end", action="store_true")
    p.add_argument("--session", help="Session JSON (default latest_onk.json)")
    p.add_argument("--org-name", help="New org display name")
    p.add_argument("--headless", action="store_true")
    a = p.parse_args()
    sess = pick_session(a.session)
    log(f"Session: {sess}")
    res = asyncio.run(run(sess, org_name=a.org_name, headless=a.headless))
    print(json.dumps({k: v for k, v in res.items()}, indent=2))
    if not a.end:
        input("done — Enter to exit...")


if __name__ == "__main__":
    main()
