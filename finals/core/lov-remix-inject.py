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
    # ponytail: parse source instead of importing (lovable-full-automation.py has
    # import-time side effect opening hardcoded /home/alan/... path)
    src = open(os.path.join(CORE, "lovable-full-automation.py")).read()
    m = _re.search(r'SUBPROCESS_PROMPT\s*=\s*"""(.*?)"""', src, _re.S)
    assert m, "SUBPROCESS_PROMPT not found"
    return m.group(1)
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

async def _totp_fill(page, secret):
    import pyotp
    code = pyotp.TOTP(secret).now()
    await page.evaluate(f"""(code) => {{
        const el = document.querySelector('#totp-code') || [...document.querySelectorAll('input')].find(i=>i.placeholder.includes('code'));
        const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
        s.call(el, code);
        el.dispatchEvent(new Event('input',{{bubbles:true}}));
        el.dispatchEvent(new Event('change',{{bubbles:true}})); }}""", code)
    return code

async def _login(page, email, password, totp_secret=None):
    """Cookies already injected by caller; full login fallback incl. TOTP."""
    await page.goto("https://lovable.dev/dashboard", timeout=40000, wait_until="domcontentloaded")
    await page.wait_for_timeout(4000)
    if "Log in" not in await page.evaluate("() => document.body.innerText.slice(0,500)"):
        return True
    await page.goto("https://lovable.dev/login?redirect=%2Fdashboard", timeout=40000, wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)
    await page.locator('input[placeholder="Email"]').fill(email)
    await page.locator('[data-testid="auth-submit-button"]').click()
    await page.wait_for_timeout(3000)
    await page.locator('input[placeholder="Password"]').fill(password)
    await page.locator('[data-testid="auth-submit-button"]').click()
    await page.wait_for_timeout(6000)
    txt = await page.evaluate("() => document.body.innerText.slice(0,800)")
    if "invalid" in txt.lower():
        return False
    if "verification code" in txt.lower() or "two-factor" in txt.lower():
        if not totp_secret:
            return False
        await _totp_fill(page, totp_secret)
        await page.locator('[data-testid="auth-submit-button"]').click()
        await page.wait_for_timeout(6000)
    return "Log in" not in await page.evaluate("() => document.body.innerText.slice(0,500)")

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
        if not await _login(page, email, password, cfg.get("totp_secret")):
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
        await js_click(page, menu_btn, "template menu")
        await wait(2000)
        menu_dropdown = page.locator('div[role="menu"][data-open]')
        await menu_dropdown.wait_for(state="visible", timeout=5000)
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
        ack = page.locator('button[type="submit"]:has-text("Acknowledge and remix")')
        await ack.wait_for(state="visible", timeout=15000)
        await js_click(page, ack, "Acknowledge and remix")
        await page.wait_for_timeout(15000)
        body = await page.evaluate("() => document.body.innerText.slice(0,3000)")
        if "suspicious activity" in body.lower() or "RED" in body[:500]:
            return {"session": num, "email": email, "success": False, "reason": "RED flagged"}
        project_id = page.url.split("/projects/")[-1].split("?")[0] if "/projects/" in page.url else ""
        log(f"session-{num} remixed project {project_id}")

        # --- inject bridge via chat ---
        chat_input = None
        for sel in ['div[contenteditable="true"][role="textbox"]', 'div[contenteditable="true"]',
                    '.ProseMirror[contenteditable="true"]', '[data-testid="chat-input"]', 'textarea[placeholder*="Ask"]']:
            try:
                cand = page.locator(sel).first
                await cand.wait_for(state="visible", timeout=8000)
                chat_input = cand
                break
            except Exception:
                continue
        if not chat_input:
            return {"session": num, "email": email, "success": False, "reason": "no chat input", "project_id": project_id}
        await chat_input.click()
        await chat_input.fill(SUBPROCESS_PROMPT)
        await wait(1000)
        await js_click(page, page.locator('button[data-testid="chat-input-send"]'), "send bridge prompt")
        before = await page.locator('[data-testid="chat-item-ai_message"]').count()
        deadline = asyncio.get_running_loop().time() + 420
        while asyncio.get_running_loop().time() < deadline:
            if await page.locator('[data-testid="chat-item-ai_message"]').count() > before:
                break
            await asyncio.sleep(5)
        else:
            return {"session": num, "email": email, "success": False, "reason": "AI no response", "project_id": project_id}

        # --- verify bridge in preview ---
        try:
            async with ctx.expect_page(timeout=15000) as pop:
                await page.locator('a:has-text("Preview"), button:has-text("Preview")').first.click(timeout=8000)
            preview = await pop.value
            await preview.wait_for_timeout(8000)
            has_doc = await preview.evaluate("typeof window.doc !== 'undefined'")
            if has_doc:
                pwd_out = await preview.evaluate("window.doc('pwd')")
                log(f"session-{num} window.doc pwd: {str(pwd_out)[:120]}")
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
        json.dump(cfg, open(cfg_path, "w"), indent=2)
        return {"session": num, "email": email, "success": True, "project_id": project_id,
                "invite_link": invite_link, "bridge": bool(has_doc)}
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

    try:  # pre-cleanup stale so 5 workers fit org cap
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
                    try:
                        ctx = await browser.new_context()
                    except Exception:
                        _del_browser(sid)
                        cdp_ws, sid = await asyncio.to_thread(_new_browser)
                        async with lock:
                            owned.append(sid)
                        browser = await pw.chromium.connect_over_cdp(cdp_ws, timeout=30000)
                        ctx = await browser.new_context()
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
            new = [{"invite_link": l, "session": r["session"], "email": r["email"],
                    "project_id": r.get("project_id"), "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
                   for r in results if r.get("invite_link") for l in [r["invite_link"]] if l not in seen_links]
            if new:
                json.dump(new + cur, open(INVITES, "w"), indent=2)
                subprocess.run(["git", "add", "finals/lovable_invites.json"], cwd=REPO, capture_output=True)
                subprocess.run(["git", "commit", "-m", f"feat: {len(new)} remix invites", "--allow-empty"],
                               cwd=REPO, capture_output=True)
                subprocess.run(["git", "push"], cwd=REPO, capture_output=True, timeout=60)
        except Exception as e:
            print(f"invite merge warn {e}", flush=True)
    ok = sum(1 for r in results if r.get("success"))
    print(f"\n{ok}/{len(results)} remixed+injected", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
