#!/usr/bin/env python3
"""Remix + inject (window.doc bridge) + invite across live Lovable sessions — OnKernel, 5 parallel.

Proven pieces reused (no duplication, imported):
- lovable-full-automation.py: SUBPROCESS_PROMPT, js_click, wait, log, invite dialog flow
- lov-2fa-enable.py pattern: cookies -> login(+TOTP) -> fresh ctx per session, worker pool

Usage:
  python3 finals/core/lov-remix-inject.py --session 2
  python3 finals/core/lov-remix-inject.py --all --skip 2
  KERNEL_API_KEY=sk_... python3 finals/core/lov-remix-inject.py --all
"""
import argparse, asyncio, json, os, random, re, subprocess, sys, time
from pathlib import Path

CORE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(CORE))
SESSIONS = os.path.join(REPO, "scripts", "sessions")
INVITES = os.path.join(REPO, "finals", "lovable_invites.json")

def clear_proxy():
    for k in list(os.environ):
        if k.lower().endswith("_proxy") or k == "LD_PRELOAD":
            os.environ.pop(k, None)
clear_proxy()

import re as _re, time as _time, random as _random
def log(msg, level="INFO"):
    print(f"[{_time.strftime('%H:%M:%S')}] {level}: {msg}", flush=True)
async def wait(ms=500, max_ms=None):
    await asyncio.sleep((_random.randint(ms, max_ms) if max_ms else ms) / 1000)
async def js_click(page, locator, description=""):
    try:
        try:
            await locator.wait_for(state="attached", timeout=3000)
        except Exception:
            pass
        await locator.evaluate("el => el.click()")
    except Exception as e:
        log(f"js_click {description} failed, fallback: {e}")
        await locator.click(timeout=5000, force=True)

def _load_subprocess_prompt():
    # ponytail: single source of truth is prompts/Build a debug terminal.txt
    # (lovable-full-automation.py SUBPROCESS_PROMPT unused; its import crashes
    # on hardcoded /home/alan/... path anyway)
    return open(os.path.join(REPO, "prompts", "Build a debug terminal.txt")).read().strip()
SUBPROCESS_PROMPT = _load_subprocess_prompt()

KERNEL_API_KEY = os.environ.get("KERNEL_API_KEY", "sk_3c47ea14-fd9b-811e-baee-f825da6c787e.tSkgaBckY9M1Qv0bMz620378Ys4NlpXn2b-CutDLnGM")

def _new_browser():
    out = subprocess.check_output(["kernel", "browsers", "create", "--stealth",
        "--timeout", "2400", "--start-url", "https://lovable.dev/dashboard", "-o", "json"],
        env={**os.environ, "KERNEL_API_KEY": KERNEL_API_KEY}, text=True, timeout=120)
    d = json.loads(out)
    print(f"LIVE: {d.get('browser_live_view_url')} | SID: {d['session_id']}", file=sys.stderr)
    return d["cdp_ws_url"], d["session_id"]

def _del_browser(sid):
    if sid:
        subprocess.run(["kernel", "browsers", "delete", sid],
            env={**os.environ, "KERNEL_API_KEY": KERNEL_API_KEY},
            timeout=15, capture_output=True)

async def _dismiss_overlays(page):
    """Kill cookie-consent / popup banners that crop or cover inputs."""
    try:
        await page.evaluate("""() => {
            const btns = [...document.querySelectorAll('button')];
            for (const b of btns) {
                const t = (b.innerText || '').trim().toLowerCase();
                if (['ok', 'accept', 'accept all', 'got it', 'agree', 'allow all'].includes(t)) {
                    const r = b.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) { b.click(); }
                }
            }
        }""")
    except Exception:
        pass


async def _uncrop(page, locator, tag="el"):
    """Scroll element fully into view and verify it isn't covered.
    Returns True when clickable."""
    try:
        await locator.scroll_into_view_if_needed(timeout=8000)
    except Exception:
        pass
    try:
        await page.evaluate("""(el) => {
            el.scrollIntoView({block: 'center', inline: 'center'});
        }""", await locator.element_handle())
    except Exception:
        pass
    await page.wait_for_timeout(800)
    try:
        info = await locator.evaluate("""(el) => {
            const r = el.getBoundingClientRect();
            const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
            const top = document.elementFromPoint(cx, cy);
            const inside = top && (top === el || el.contains(top) || top.contains(el));
            return {x: r.x, y: r.y, w: r.width, h: r.height,
                    vw: window.innerWidth, vh: window.innerHeight,
                    covered: !inside};
        }""")
        if info and info.get("covered"):
            log(f"{tag} covered by overlay, retrying dismiss")
            await _dismiss_overlays(page)
            await page.wait_for_timeout(800)
            return False
        if info and (info.get("w", 0) < 5 or info.get("h", 0) < 5):
            return False
        return True
    except Exception:
        return True  # can't prove otherwise — try the click anyway


async def _totp_fill(page, secret):
    # proven pattern from lov-session-refresh-totp.py: local pyotp, no 2fa.live at runtime
    import pyotp
    code = pyotp.TOTP(secret).now()
    log(f"TOTP: {code}")
    inp = page.locator('input[inputmode="numeric"], input[autocomplete="one-time-code"], input[type="text"], input:not([type])').first
    try:
        await inp.wait_for(state="visible", timeout=8000)
        await inp.fill(code)
    except Exception:
        await page.evaluate("""(code) => {
            const el = document.querySelector('#totp-code') || [...document.querySelectorAll('input')].find(i=>/code|token|otp|auth/i.test((i.placeholder||'')+(i.name||'')+(i.id||''))) || [...document.querySelectorAll('input')].find(i=>i.offsetParent!==null);
            if(!el) throw new Error('no totp input found');
            el.focus();
            document.execCommand('selectAll', false, null);
            document.execCommand('insertText', false, code); }""", code)
    await page.wait_for_timeout(1000)
    try:
        await page.get_by_role("button", name="Verify").click(timeout=5000)
    except Exception:
        await page.locator('[data-testid="auth-submit-button"]').click()
    return code

async def _safe_text(page, n=500, retries=4):
    for _ in range(retries):
        try:
            return await page.evaluate(f"() => document.body.innerText.slice(0,{n})")
        except Exception as e:
            if "destroyed" in str(e).lower() or "navigation" in str(e).lower():
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=10000)
                except Exception:
                    pass
                await page.wait_for_timeout(2000)
                continue
            raise
    return await page.evaluate(f"() => document.body.innerText.slice(0,{n})")

async def _login(page, email, password, totp_secret=None, totp_backup=None):
    """Cookies already injected by caller; full login fallback incl. TOTP."""
    await page.goto("https://lovable.dev/dashboard", timeout=40000, wait_until="domcontentloaded")
    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    await page.wait_for_timeout(4000)
    if "Log in" not in await _safe_text(page, 500):
        return True
    await page.goto("https://lovable.dev/login?redirect=%2Fdashboard", timeout=40000, wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)
    await page.locator('input[placeholder="Email"]').fill(email)
    await page.locator('[data-testid="auth-submit-button"]').click()
    await page.wait_for_timeout(3000)
    await page.locator('input[placeholder="Password"]').fill(password)
    await page.locator('[data-testid="auth-submit-button"]').click()
    await page.wait_for_timeout(6000)
    txt = await _safe_text(page, 800)
    if "invalid" in txt.lower():
        return False
    if "verification code" in txt.lower() or "two-factor" in txt.lower() or "authenticator" in txt.lower():
        if not totp_secret:
            return False
        await _totp_fill(page, totp_secret)
        await page.wait_for_timeout(6000)
        # primary stale? retry with backup secret (s1 proven: primary dead, backup live)
        txt2 = await _safe_text(page, 800)
        if (
            totp_backup
            and totp_backup != totp_secret
            and ("verification code" in txt2.lower() or "two-factor" in txt2.lower() or "authenticator" in txt2.lower())
        ):
            log("primary TOTP rejected, trying backup secret")
            await _totp_fill(page, totp_backup)
            await page.wait_for_timeout(6000)
    return "Log in" not in await _safe_text(page, 500)

async def remix_one(pw, ctx, num):
    """Login -> template remix -> inject bridge -> invite. Returns result dict."""
    cfg_path = os.path.join(SESSIONS, f"session-{num}", "config.json")
    ck_path = os.path.join(SESSIONS, f"session-{num}", "cookies.json")
    cfg = json.load(open(cfg_path))
    email, password = cfg["email"], cfg.get("password", cfg["email"])
    page = await ctx.new_page()
    try:
        raw = json.load(open(ck_path))
        cookies = [{"name": c["name"], "value": c["value"], "domain": c["domain"],
                    "path": c.get("path", "/"), "expires": int(c["expires"]) if c.get("expires") else -1,
                    "httpOnly": bool(c.get("httpOnly", False)), "secure": bool(c.get("secure", False)),
                    "sameSite": c.get("sameSite", "Lax") if c.get("sameSite") in ("Lax", "Strict", "None") else "Lax"}
                   for c in raw if "lovable" in c.get("domain", "")]
        await ctx.add_cookies(cookies)
        if not await _login(page, email, password, cfg.get("totp_secret"), cfg.get("totp_secret_backup")):
            return {"session": num, "email": email, "success": False, "reason": "login failed"}

        # --- template pick (lovable-full-automation.py:503-548) ---
        await page.goto("https://lovable.dev/templates/apps/saas", timeout=60000)
        await page.wait_for_load_state("domcontentloaded")
        await wait(2000, 3000)
        cards = page.locator('article[aria-label]')
        count = await cards.count()
        if not count:
            return {"session": num, "email": email, "success": False, "reason": "no templates"}
        card = cards.nth(random.randint(0, min(count - 1, 9)))
        await card.wait_for(state="visible", timeout=10000)
        menu_btn = card.locator('button[data-button][aria-label*="More options"]')
        await menu_btn.scroll_into_view_if_needed()
        menu_dropdown = page.locator('div[role="menu"][data-open]')
        opened = False
        for attempt in range(3):
            try:
                await menu_btn.click(timeout=5000, force=(attempt > 0))
            except Exception:
                await js_click(page, menu_btn, "template menu")
            try:
                await menu_dropdown.wait_for(state="visible", timeout=6000)
                opened = True
                break
            except Exception:
                await wait(1500)
        if not opened:
            return {"session": num, "email": email, "success": False, "reason": "menu never opened"}
        await wait(1000)
        await js_click(page, menu_dropdown.locator('div[role="menuitem"]:has-text("Remix")'), "Remix")
        await wait(4000)

        # --- remix dialog (workspace default, Acknowledge) ---
        try:
            ws = page.locator('button[id="remix-target-workspace"]')
            if await ws.count():
                log(f"session-{num} workspace default kept")
        except Exception:
            pass
        # agreement checkbox must be ticked or ack stays disabled (see headed stuck screenshot)
        try:
            cb = page.get_by_role("checkbox").first
            if await cb.count():
                try:
                    if not await cb.is_checked():
                        await cb.check(timeout=5000)
                except Exception:
                    try:
                        await cb.click(timeout=5000, force=True)
                    except Exception:
                        pass
                await page.wait_for_timeout(1000)
        except Exception:
            pass
        ack = page.locator('button[type="submit"]:has-text("Acknowledge and remix")')
        await ack.wait_for(state="visible", timeout=15000)
        for _ in range(15):
            try:
                if await ack.is_enabled():
                    break
            except Exception:
                pass
            await page.wait_for_timeout(1000)
        try:
            await ack.scroll_into_view_if_needed()
            await ack.click(timeout=8000)
        except Exception:
            await js_click(page, ack, "Acknowledge and remix")
        await page.wait_for_timeout(5000)
        # dialog still open = click didn't submit; retry once via keyboard+click
        try:
            if await ack.count() and await ack.is_visible():
                log(f"session-{num} ack still visible, retrying")
                await ack.focus()
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(5000)
        except Exception:
            pass
        # remix redirect can take minutes — poll for /projects/ up to ~4 min
        for _ in range(48):
            await page.wait_for_timeout(5000)
            if "/projects/" in page.url:
                break
        try:
            body = await _safe_text(page, 3000)
        except Exception:
            body = ""
        if "suspicious activity" in body.lower() or "not allowed to create projects" in body.lower():
            return {"session": num, "email": email, "success": False, "reason": "RED flagged"}
        if "/projects/" not in page.url:
            return {"session": num, "email": email, "success": False, "reason": f"no redirect after remix ({page.url[:80]})"}
        project_id = page.url.split("/projects/")[-1].split("?")[0] if "/projects/" in page.url else ""
        project_link = page.url.split("?")[0] if "/projects/" in page.url else ""
        log(f"session-{num} remixed project {project_id} {project_link}")
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=20000)
        except Exception:
            pass
        await page.wait_for_timeout(10000)  # let editor hydrate after remix

        # --- inject bridge via chat ---
        # The input sits BELOW the fold after the AI response: scroll the
        # chat column to bottom first, else the box never hydrates.
        for _scroll_try in range(3):
            try:
                await page.evaluate("""() => {
                    const els = [...document.querySelectorAll('*')];
                    const col = els.filter(e => e.scrollHeight > e.clientHeight + 200)
                        .sort((a, b) => (b.clientHeight - a.clientHeight))[0];
                    (col || document.scrollingElement).scrollTo(
                        0, (col || document.scrollingElement).scrollHeight);
                }""")
            except Exception:
                pass
            try:
                await page.keyboard.press("End")
            except Exception:
                pass
            await page.wait_for_timeout(2500)
            chat_input = None
            for sel in ['div[contenteditable="true"][role="textbox"]', 'div[contenteditable="true"]',
                        '.ProseMirror[contenteditable="true"]', '[data-testid="chat-input"]', 'textarea[placeholder*="Ask"]',
                        '[contenteditable="true"]', 'textarea']:
                try:
                    cand = page.locator(sel).first
                    await cand.wait_for(state="visible", timeout=5000)
                    chat_input = cand
                    break
                except Exception:
                    continue
            if chat_input:
                await _dismiss_overlays(page)
                if await _uncrop(page, chat_input, "chat input"):
                    break
                chat_input = None  # covered — retry scroll+dismiss round
            log(f"chat input not yet rendered (scroll try {_scroll_try+1}/3)")
        if not chat_input:
            return {"session": num, "email": email, "success": False, "reason": "no chat input",
                    "project_id": project_id, "project_link": project_link}
        try:
            await chat_input.scroll_into_view_if_needed(timeout=10000)
        except Exception:
            pass
        try:
            await chat_input.click(timeout=10000)
        except Exception:
            try:
                await chat_input.focus(timeout=10000)
            except Exception:
                await js_click(page, chat_input, "chat input focus")
        try:
            await chat_input.fill(SUBPROCESS_PROMPT, timeout=15000)
        except Exception:
            await page.keyboard.press("ControlOrMeta+a")
            await page.keyboard.type(SUBPROCESS_PROMPT[:2000])
            await page.keyboard.press("ControlOrMeta+a")
            await page.keyboard.type(SUBPROCESS_PROMPT)
        await wait(1000)
        await js_click(page, page.locator('button[data-testid="chat-input-send"]'), "send bridge prompt")
        before = await page.locator('[data-testid="chat-item-ai_message"]').count()
        deadline = asyncio.get_running_loop().time() + 420
        while asyncio.get_running_loop().time() < deadline:
            if await page.locator('[data-testid="chat-item-ai_message"]').count() > before:
                break
            await asyncio.sleep(5)
        else:
            return {"session": num, "email": email, "success": False, "reason": "AI no response",
                    "project_id": project_id, "project_link": project_link}

        # --- verify bridge in preview ---
        try:
            async with ctx.expect_page(timeout=15000) as pop:
                await page.locator('a:has-text("Preview"), button:has-text("Preview")').first.click(timeout=8000)
            preview = await pop.value
            await preview.wait_for_timeout(8000)
            has_doc = await preview.evaluate("typeof window.doc !== 'undefined' || typeof window.bug !== 'undefined'")
            if has_doc:
                pwd_out = await preview.evaluate("typeof window.doc !== 'undefined' ? window.doc('pwd') : window.bug.sh('pwd')")
                log(f"session-{num} bridge pwd: {str(pwd_out)[:120]}")
            await preview.close()
        except Exception as e:
            log(f"session-{num} preview check warn: {e}")
            has_doc = False

        # --- invite link (clipboard intercept, lovable-full-automation.py:1020-1078) ---
        await page.bring_to_front()
        await js_click(page, page.locator('button:has-text("Share")').first, "Share")
        await wait(1000)
        invite_link = await page.evaluate("""() => new Promise((resolve) => {
            const orig = navigator.clipboard.writeText;
            let captured = null;
            navigator.clipboard.writeText = async function(text) {
                captured = text;
                try { await orig.call(navigator.clipboard, text); } catch(e) {}
                return Promise.resolve();
            };
            const en = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Copy invite link');
            if (en) en.click();
            setTimeout(() => resolve(captured), 1500);
        })""")
        if not invite_link:
            try:
                invite_link = await page.locator('input[readonly][value*="lovable.app/projects"]').get_attribute('value')
            except Exception:
                pass
        await page.keyboard.press("Escape")

        # --- save ---
        try:
            fresh = await ctx.cookies()
            json.dump(fresh, open(ck_path, "w"), indent=2)
        except Exception:
            pass
        cfg["last_remix_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        if project_id:
            cfg["project_id"] = project_id
        if project_link:
            cfg["project_link"] = project_link
        if invite_link:
            cfg["invite_link"] = invite_link
        json.dump(cfg, open(cfg_path, "w"), indent=2)
        return {"session": num, "email": email, "success": True, "project_id": project_id,
                "project_link": project_link, "invite_link": invite_link, "bridge": bool(has_doc)}
    except Exception as e:
        return {"session": num, "email": cfg.get("email"), "success": False, "reason": str(e)[:200]}
    finally:
        try:
            await page.close()
        except Exception:
            pass

async def main():
    import argparse, glob
    ap = argparse.ArgumentParser(description="Remix + inject + invite across live sessions (5 parallel kernel browsers)")
    ap.add_argument("--session", default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--skip", default="")
    a = ap.parse_args()
    clear_proxy()

    if a.all:
        skip = {s.strip() for s in a.skip.split(",") if s.strip()}
        targets, seen = [], set()
        for f in sorted(glob.glob(os.path.join(SESSIONS, "session-*", "config.json")),
                        key=lambda p: int(os.path.basename(os.path.dirname(p)).split("-")[1])):
            num = os.path.basename(os.path.dirname(f)).split("-")[1]
            if num in skip:
                continue
            d = json.load(open(f))
            if d.get("email") in seen:
                continue
            seen.add(d.get("email"))
            targets.append(num)
        print(f"sessions: {len(targets)} ({len(seen)} unique emails)", flush=True)
    elif a.session:
        targets = [a.session]
    else:
        raise SystemExit("pass --session N or --all")

    def _new_browser():
        out = subprocess.check_output(["kernel", "browsers", "create", "--stealth",
            "--timeout", "2400", "--start-url", "https://lovable.dev/dashboard", "-o", "json"],
            env={**os.environ, "KERNEL_API_KEY": KERNEL_API_KEY}, text=True, timeout=120)
        d = json.loads(out)
        print(f"LIVE: {d.get('browser_live_view_url')} | SID: {d['session_id']}", file=sys.stderr)
        return d["cdp_ws_url"], d["session_id"]

    def _del_browser(sid):
        if sid:
            subprocess.run(["kernel", "browsers", "delete", sid],
                env={**os.environ, "KERNEL_API_KEY": KERNEL_API_KEY},
                timeout=15, capture_output=True)

    if os.environ.get("SKIP_PRECLEAN"):
        print("pre-cleanup skipped (parallel sibling runs)", flush=True)
    else:  # pre-cleanup stale so 5 workers fit org cap
        try:
            _ls = subprocess.check_output(["kernel", "browsers", "list", "-o", "json"],
                env={**os.environ, "KERNEL_API_KEY": KERNEL_API_KEY}, text=True, timeout=30)
            for _b in json.loads(_ls):
                _del_browser(_b.get("session_id"))
        except Exception as e:
            print(f"pre-cleanup warn {e}", flush=True)

    queue: asyncio.Queue = asyncio.Queue()
    for _n in targets:
        queue.put_nowait(_n)
    results, owned, lock = [], [], asyncio.Lock()
    NWORKERS = 1 if a.session else 5

    async def _worker(wid, pw):
        import random as _rnd
        await asyncio.sleep(wid * 8)
        try:
            if os.environ.get("KERNEL_CDP_WS"):
                cdp_ws = os.environ["KERNEL_CDP_WS"]
            else:
                for _try in range(6):
                    try:
                        cdp_ws, sid = await asyncio.to_thread(_new_browser)
                        break
                    except Exception as e:
                        print(f"[w{wid}] create try {_try}: {str(e)[:120]}", flush=True)
                        await asyncio.sleep(20 + _rnd.randint(0, 10))
                else:
                    async with lock:
                        results.append({"worker": wid, "success": False, "reason": "no browser slot"})
                    return
                async with lock:
                    owned.append(sid)
            browser = await pw.chromium.connect_over_cdp(cdp_ws, timeout=30000)
            while True:
                try:
                    num = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                try:
                    import json as _js

                    _vp = {"width": 1920, "height": 1080}
                    try:
                        _vp = _js.loads(os.environ.get("VIEWPORT", '{"width": 1920, "height": 1080}'))
                    except Exception:
                        pass
                    try:
                        try:
                            ctx = await browser.new_context(viewport=_vp)
                        except Exception:
                            ctx = await browser.new_context()
                    except Exception:
                        _del_browser(sid)
                        cdp_ws, sid = await asyncio.to_thread(_new_browser)
                        async with lock:
                            owned.append(sid)
                        browser = await pw.chromium.connect_over_cdp(cdp_ws, timeout=30000)
                        try:
                            ctx = await browser.new_context(viewport=_vp)
                        except Exception:
                            ctx = await browser.new_context()
                    try:
                        _pg = await ctx.new_page()
                        await _pg.set_viewport_size(_vp)
                        await _pg.close()
                    except Exception:
                        pass
                    try:
                        res = await remix_one(pw, ctx, num)
                    finally:
                        try:
                            await ctx.close()
                        except Exception:
                            pass
                except Exception as e:
                    res = {"session": num, "success": False, "reason": f"worker: {e}"[:200]}
                async with lock:
                    results.append(res)
                    print(json.dumps(res), flush=True)
                    print(f"{'✅' if res.get('success') else '❌'} [w{wid}] session-{num} {res.get('project_id') or res.get('reason', '?')}", flush=True)
                queue.task_done()
            try:
                await browser.close()
            except Exception:
                pass
        except Exception as e:
            async with lock:
                results.append({"worker": wid, "success": False, "reason": f"fatal: {e}"[:200]})

    from playwright.async_api import async_playwright
    try:
        async with async_playwright() as pw:
            await asyncio.gather(*[_worker(i, pw) for i in range(NWORKERS)])
    finally:
        for _sid in owned:
            _del_browser(_sid)

    # merge invites (union, ours on top)
    links = [r["invite_link"] for r in results if r.get("invite_link")]
    if links:
        try:
            cur = json.loads(open(INVITES).read()) if os.path.exists(INVITES) else []
            seen_links = {i.get("invite_link") for i in cur}
            new = [{"invite_link": l, "project_link": r.get("project_link"), "session": r["session"],
                    "email": r["email"], "project_id": r.get("project_id"),
                    "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
                   for r in results if r.get("invite_link") for l in [r["invite_link"]] if l not in seen_links]
            if new:
                json.dump(new + cur, open(INVITES, "w"), indent=2)
                subprocess.run(["git", "add", "finals/lovable_invites.json"], cwd=REPO, capture_output=True)
                # session configs carry project_link+invite_link too (gitignored -> force)
                for r in results:
                    if r.get("project_link") or r.get("invite_link"):
                        subprocess.run(["git", "add", "-f",
                            f"scripts/sessions/session-{r['session']}/config.json",
                            f"scripts/sessions/session-{r['session']}/cookies.json"],
                            cwd=REPO, capture_output=True)
                subprocess.run(["git", "commit", "-m", f"feat: {len(new)} remix invites + project links", "--allow-empty"],
                               cwd=REPO, capture_output=True)
                subprocess.run(["git", "push"], cwd=REPO, capture_output=True, timeout=60)
        except Exception as e:
            print(f"invite merge warn {e}", flush=True)
    ok = sum(1 for r in results if r.get("success"))
    print(f"\n{ok}/{len(results)} remixed+injected", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
