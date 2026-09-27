#!/usr/bin/env python3
"""ZenRows dispose-only farmer with SMTP probe loop.

ONE OnK browser per attempt:
  Phase 1 (loop): fresh context per address (up to --max-addrs): dispose.lol
    Gmail -> Gmail-SMTP marker probe -> poll --wait s. First address where
    the marker lands is LIVE (winner context kept open).
  Phase 2: fresh context in SAME browser -> app.zenrows.com/register
    (CF solve, human fill, submit) -> email/verify.
  Phase 3: poll winner inbox for the ZenRows verify mail -> TRY url4722
    candidates in the farm tab until overview -> eye-click -> 40-hex key.

Dead dispose addresses never cost a signup; only proven-live ones do.

Usage:
  python3 src/farming/farm_zenrows_dispose.py --key-index 70 --max-addrs 10 --wait 40 --attempts 3
"""
from __future__ import annotations

import argparse
import asyncio
import fcntl
import glob
import json
import os
import random
import re
import string
import subprocess
import sys
import time
from pathlib import Path

REPO = Path("/home/alan/Documents/railways")
REG = REPO / "finals" / "zenrows_onkernel_farmed.json"
JSONL = REPO / "finals" / "zenrows_farmed.jsonl"
SMTP_CFG = os.path.expanduser("~/.config/lovfarm/smtp.json")
PASSWORD = "Test1234!AbcZ2026"
GMAIL_RE = re.compile(r"[a-z0-9._%+-]+@gmail\.com", re.I)
LINK_RE = re.compile(r"https?://[^\s'\"<>]+(?:zenrows\.com|url4722)[^\s'\"<>]*", re.I)
KEY_RE = re.compile(r"\b([a-f0-9]{40})\b")

_ZEN_TAG = os.environ.get("ZEN_TAG", "")
_ZT = ("_" + _ZEN_TAG) if _ZEN_TAG else ""


def _zp(p: str) -> str:
    return p.replace("/tmp/zen_", f"/tmp/zen{_ZT}_") if _ZT else p


def log(m: str) -> None:
    print(m, file=sys.stderr, flush=True)


def pick_key(idx: int) -> dict:
    fps = sorted(glob.glob(str(REPO / "finals" / "sessions" / "onk-*" / "session.json")))
    d = json.load(open(fps[idx % len(fps)]))
    return {"email": d.get("email"), "api_key": d["api_key"], "dir": fps[idx % len(fps)].split("/")[-2]}


def kn_create(key: str) -> dict:
    out = subprocess.check_output(
        "kernel browsers create --stealth --timeout 2400 --start-url https://dispose.lol -o json",
        shell=True, env={**os.environ, "KERNEL_API_KEY": key}, text=True, timeout=120)
    return json.loads(out)


def kn_delete(key: str, sid: str) -> None:
    subprocess.run(f"kernel browsers delete {sid}", shell=True,
                   env={**os.environ, "KERNEL_API_KEY": key},
                   timeout=20, capture_output=True)


def smtp_send(to_addr: str, marker: str) -> None:
    import smtplib, ssl
    from email.message import EmailMessage
    cfg = json.load(open(SMTP_CFG))
    user, pwd = cfg.get("gmail_user", ""), cfg.get("gmail_app_pwd", "")
    if not user or not pwd:
        raise RuntimeError("no SMTP creds")
    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = to_addr
    msg["Subject"] = marker
    msg.set_content(f"deliverability probe {marker}")
    ctx = ssl.create_default_context()
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as s:
        s.starttls(context=ctx)
        s.login(user, pwd.replace(" ", ""))
        s.send_message(msg)


async def inbox_marked(page, marker: str) -> bool:
    try:
        labels = await page.evaluate(
            """() => [...document.querySelectorAll('button[aria-label^="View "]')]
                 .map(b => b.getAttribute('aria-label') || '')""")
    except Exception:
        return False
    return any(marker in (a or "") for a in labels)


async def phase_probe(browser, max_addrs: int, wait_s: int):
    """Cycle dispose inboxes; return (email, inbox_page, inbox_ctx) for first LIVE one."""
    for i in range(1, max_addrs + 1):
        marker = "lovprobe-" + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        ctx = await browser.new_context()
        page = await ctx.new_page()
        try:
            await page.goto("https://dispose.lol", wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(4000)
            body = await page.evaluate("() => document.body.innerText") or ""
            gmails = GMAIL_RE.findall(body)
            if not gmails:
                log(f"[probe {i}] no Gmail on page")
                continue
            addr = gmails[0]
            log(f"[probe {i}] target {addr} [{marker}]")
            try:
                await asyncio.to_thread(smtp_send, addr, marker)
            except Exception as e:
                log(f"[probe {i}] send fail {str(e)[:100]}")
                continue
            deadline = time.time() + wait_s
            check = 0
            live = False
            while time.time() < deadline:
                check += 1
                try:
                    await page.reload(wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    pass
                await page.wait_for_timeout(3000)
                if await inbox_marked(page, marker):
                    live = True
                    break
                if check % 4 == 1:
                    log(f"[probe {i}] poll #{check}: waiting...")
                await asyncio.sleep(2)
            if live:
                log(f"[probe {i}] LIVE -> {addr}")
                return addr, page, ctx
            log(f"[probe {i}] miss after {wait_s}s")
        except Exception as e:
            log(f"[probe {i}] err {str(e)[:100]}")
        try:
            await ctx.close()
        except Exception:
            pass
    return None, None, None


async def cf_solve(page) -> bool:
    await page.goto("https://app.zenrows.com/register", wait_until="domcontentloaded", timeout=60000)
    for i in range(36):
        await page.wait_for_timeout(5000)
        try:
            title = await page.title()
            snip = await page.evaluate("() => document.body.innerText.substring(0,1200)")
        except Exception:
            continue
        if "Sign Up" in title and "Create a ZenRows account" in snip:
            log(f"CF solved at {i*5}s")
            return True
        if "ERROR_CAPTCHA_UNSOLVABLE" in snip or "Performing security verification" in snip:
            try:
                await page.reload(wait_until="domcontentloaded")
            except Exception:
                pass
        elif i % 6 == 5 and "Just a moment" in title and i // 6 < 5:
            try:
                await page.reload(wait_until="domcontentloaded")
            except Exception:
                pass
    return False


async def human_fill(page, sel: str, text: str) -> None:
    try:
        el = await page.wait_for_selector(sel, timeout=15000)
        await el.click()
        await page.wait_for_timeout(300)
        for ch in text:
            await el.type(ch, delay=random.randint(60, 180))
            if random.random() < 0.1:
                await page.wait_for_timeout(random.randint(200, 500))
    except Exception:
        await page.fill(sel, text)


async def phase_register(browser, email: str):
    """Fresh context -> register with the LIVE address. Returns (page, ctx)."""
    ctx = await browser.new_context()
    page = await ctx.new_page()
    if not await cf_solve(page):
        raise RuntimeError("CF unsolved")
    await human_fill(page, "#email", email)
    await human_fill(page, "#password", PASSWORD)
    btn = None
    try:
        btn = await page.wait_for_selector('button:has-text("Create account")', timeout=10000)
    except Exception:
        pass
    if btn:
        try:
            bb = await btn.bounding_box()
            if bb:
                await page.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2)
                await page.wait_for_timeout(300)
                await page.mouse.click(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2,
                                       delay=random.randint(80, 160))
            else:
                await btn.click(timeout=8000)
        except Exception:
            await page.evaluate("""() => {
                const b=[...document.querySelectorAll('button')].find(x=>x.innerText.includes('Create account'));
                if(b) b.click(); }""")
    else:
        await page.evaluate("""() => {
            const b=[...document.querySelectorAll('button')].find(x=>x.innerText.includes('Create account'));
            if(b) b.click(); }""")
    await page.wait_for_timeout(9000)
    url = page.url
    try:
        content = await page.content()
    except Exception:
        content = ""
    if "Too many accounts detected from your IP" in content:
        raise RuntimeError("IP-FLAGGED")
    if "Email domain not allowed" in content or "Invalid email address" in content:
        raise RuntimeError("EMAIL-REJECTED")
    if "email/verify" not in url and "verify" not in content.lower():
        raise RuntimeError(f"REGISTER-STUCK at {url}")
    log(f"Registered {email} -> {url}")
    return page, ctx


async def phase_verify(farm_page, inbox_page, timeout_s: int = 300):
    """Poll winner inbox for the ZenRows verify mail; TRY candidates till overview."""
    deadline = time.time() + timeout_s
    check = 0
    while time.time() < deadline:
        check += 1
        try:
            await inbox_page.reload(wait_until="domcontentloaded", timeout=30000)
        except Exception:
            pass
        await inbox_page.wait_for_timeout(3000)
        try:
            body = await inbox_page.evaluate("() => document.body.innerText") or ""
        except Exception:
            body = ""
        if "verify@e.zenrows.com" in body or "Verify your email to activate" in body:
            try:
                await inbox_page.evaluate("""() => {
                    const b=[...document.querySelectorAll('button')]
                      .find(x=>(x.getAttribute('aria-label')||'').includes('Verify your email'));
                    if(b) b.click(); }""")
            except Exception:
                pass
            await inbox_page.wait_for_timeout(3000)
            try:
                html = await inbox_page.content()
            except Exception:
                html = ""
            cands = [m.group(0) for m in LINK_RE.finditer(html)]
            cands = [c for c in cands if "url4722" in c]
            seen = set()
            uniq = [c for c in cands if not (c in seen or seen.add(c))]
            log(f"verify candidates: {len(uniq)}")
            for cand in uniq:
                try:
                    await farm_page.goto(cand, wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    continue
                await farm_page.wait_for_timeout(8000)
                if "overview" in farm_page.url:
                    return True
            log("candidates missed overview, keep polling")
        else:
            try:
                await inbox_page.evaluate("""() => {
                    const r=[...document.querySelectorAll('button')]
                      .find(x=>x.innerText.includes('Refresh')); if(r) r.click(); }""")
            except Exception:
                pass
            if check % 5 == 1:
                log(f"verify poll #{check}: waiting for ZenRows mail...")
            # resend at ~40s if nothing
            if check == 8:
                try:
                    r = await farm_page.evaluate("""() => {
                        const b=[...document.querySelectorAll('button')]
                          .find(x=>x.innerText.includes('Resend'));
                        if(b){ b.click(); return 'resend-clicked'; } return 'none'; }""")
                    log(f"resend: {r}")
                except Exception as e:
                    log(f"resend err {str(e)[:80]}")
        await asyncio.sleep(3)
    return False


async def phase_key(farm_page) -> str:
    url = farm_page.url
    if "overview" not in url:
        await farm_page.goto("https://app.zenrows.com/overview", wait_until="domcontentloaded", timeout=30000)
        await farm_page.wait_for_timeout(5000)
        url = farm_page.url
    try:
        await farm_page.wait_for_selector('input[aria-label="API key"]', timeout=15000)
        await farm_page.wait_for_timeout(1000)
        masked = await farm_page.evaluate("() => document.querySelector('input[aria-label=\"API key\"]')?.value || ''")
        if masked and "•" in masked:
            log(f"key masked {masked[:12]}... revealing")
            try:
                await farm_page.click('button[aria-label="Show API key"]', timeout=5000)
            except Exception:
                await farm_page.evaluate("""() => {
                    const b=[...document.querySelectorAll('button')]
                      .find(x=>x.getAttribute('aria-label')==='Show API key');
                    if(b) b.click(); }""")
            await farm_page.wait_for_timeout(2000)
    except Exception as e:
        log(f"eye err {str(e)[:100]}")
    content = await farm_page.content()
    body = await farm_page.evaluate("() => document.body.innerText")
    clean = re.sub(r"sentry\.io|ingest|dsn", "", content, flags=re.I)
    m = (re.search(r"zenrows login --api-key ([a-f0-9]{40})", content)
         or re.search(r"zenrows login --api-key ([a-f0-9]{40})", body))
    if not m and "overview" in farm_page.url:
        try:
            val = await farm_page.evaluate("() => document.querySelector('input[aria-label=\"API key\"]')?.value || ''")
            if val and re.match(r"^[a-f0-9]{40}$", val):
                m = re.search(r"\b([a-f0-9]{40})\b", val)
            else:
                m = re.search(r"\b([a-f0-9]{40})\b", clean)
        except Exception:
            m = re.search(r"\b([a-f0-9]{40})\b", clean)
    if not m:
        raise RuntimeError("NO-API-KEY")
    return m.group(1) if m.groups() else m.group(0)


def merge_registry(entry: dict) -> None:
    with open(REG, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0)
            try:
                data = json.load(f)
                if not isinstance(data, list):
                    data = []
            except Exception:
                data = []
            if all(r.get("api_key") != entry["api_key"] for r in data):
                data.append(entry)
                f.seek(0)
                f.truncate()
                json.dump(data, f, indent=2)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    with open(JSONL, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.write(json.dumps(entry) + "\n")
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


async def run_once(key: dict, max_addrs: int, wait_s: int):
    from playwright.async_api import async_playwright
    data = await asyncio.to_thread(kn_create, key["api_key"])
    sid = data["session_id"]
    log(f"BROWSER {data['browser_live_view_url']}")
    try:
        async with async_playwright() as pw:
            browser = None
            for _cc in range(4):
                try:
                    browser = await pw.chromium.connect_over_cdp(data["cdp_ws_url"], timeout=45000)
                    break
                except Exception as e:
                    log(f"cdp try {_cc+1}/4: {str(e)[:80]}")
                    await asyncio.sleep(15)
            if browser is None:
                raise RuntimeError("CDP-UNREACHABLE")
            email, inbox_page, inbox_ctx = await phase_probe(browser, max_addrs, wait_s)
            if not email:
                raise RuntimeError("NO-LIVE-ADDRESS")
            farm_page, farm_ctx = await phase_register(browser, email)
            try:
                ok = await phase_verify(farm_page, inbox_page)
                if not ok:
                    raise RuntimeError("VERIFY-TIMEOUT")
                api_key = await phase_key(farm_page)
            finally:
                try:
                    await farm_ctx.close()
                except Exception:
                    pass
                try:
                    await inbox_ctx.close()
                except Exception:
                    pass
            entry = {"email": email, "password": PASSWORD, "api_key": api_key,
                     "url": "https://app.zenrows.com/overview", "source": "dispose-probe",
                     "onk": key["dir"],
                     "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            merge_registry(entry)
            log(f"SUCCESS {email} / {PASSWORD} / {api_key}")
            return entry
    finally:
        kn_delete(key["api_key"], sid)
        log("browser cleaned")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key-index", type=int, default=70)
    ap.add_argument("--max-addrs", type=int, default=10)
    ap.add_argument("--wait", type=int, default=40)
    ap.add_argument("--attempts", type=int, default=3)
    a = ap.parse_args()
    key = pick_key(a.key_index)
    log(f"key: {key['email']}")
    for att in range(1, a.attempts + 1):
        try:
            await run_once(key, a.max_addrs, a.wait)
            log(f"SUCCESS on attempt {att}")
            return
        except Exception as e:
            log(f"Attempt {att} fail: {str(e)[:150]}")
            await asyncio.sleep(5)
    log("All attempts failed")
    sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
