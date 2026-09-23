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

def _kernel_env():
    """Env for `kernel` CLI only — optional Tor SOCKS, never touches cell-16 miner."""
    env = {**os.environ, "KERNEL_API_KEY": KERNEL_API_KEY}
    socks = os.environ.get("TOR_SOCKS", "").strip()
    if socks:
        env["ALL_PROXY"] = socks
        env["all_proxy"] = socks
        env["HTTPS_PROXY"] = socks
        env["HTTP_PROXY"] = socks
        env["https_proxy"] = socks
        env["http_proxy"] = socks
    return env

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
    tag = os.environ.get("KERNEL_BROWSER_NAME", f"remix-iso-{int(time.time())}")
    cmd = ["kernel", "browsers", "create", "--stealth",
           "--timeout", "2400", "--name", tag,
           "--start-url", "https://lovable.dev/dashboard", "-o", "json"]
    out = subprocess.check_output(cmd, env=_kernel_env(), text=True, timeout=120)
    d = json.loads(out)
    print(f"LIVE: {d.get('browser_live_view_url')} | SID: {d['session_id']} | NAME: {tag}", file=sys.stderr)
    return d["cdp_ws_url"], d["session_id"]

def _del_browser(sid):
    if sid:
        subprocess.run(["kernel", "browsers", "delete", sid],
            env=_kernel_env(),
            timeout=15, capture_output=True)

async def _dismiss_overlays(page):
    """Kill cookie-consent / upgrade / dialog banners that crop or cover inputs."""
    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass
    try:
        await page.evaluate("""() => {
            const want = [
                'ok', 'accept', 'accept all', 'got it', 'agree', 'allow all',
                'close', 'dismiss', 'not now', 'maybe later', 'skip', 'continue',
                'keep editing', 'no thanks', 'x'
            ];
            const btns = [...document.querySelectorAll('button, [role="button"], [aria-label="Close"]')];
            for (const b of btns) {
                const t = ((b.innerText || b.getAttribute('aria-label') || '') + '').trim().toLowerCase();
                if (!want.includes(t) && !/close|dismiss|not now|maybe later/i.test(t)) continue;
                const r = b.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) { try { b.click(); } catch (e) {} }
            }
            // nuke fixed/full-screen dialog backdrops that trap clicks
            for (const el of document.querySelectorAll('[role="dialog"], [data-state="open"]')) {
                const t = (el.innerText || '').toLowerCase();
                if (/upgrade|pro plan|credits|subscribe|billing/.test(t)) {
                    const x = el.querySelector('button[aria-label="Close"], button:has(svg)');
                    if (x) try { x.click(); } catch (e) {}
                }
            }
        }""")
    except Exception:
        pass
    try:
        await page.wait_for_timeout(400)
        await page.keyboard.press("Escape")
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

async def _login(page, email, password, totp_secret=None, totp_backup=None, password_alts=None):
    """Cookies already injected by caller; full login fallback incl. TOTP."""
    await page.goto("https://lovable.dev/dashboard", timeout=40000, wait_until="domcontentloaded")
    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    await page.wait_for_timeout(4000)
    if "Log in" not in await _safe_text(page, 500):
        return True
    candidates = []
    for p in [password, *(password_alts or []), email, email + "1", email + "K01"]:
        if p and p not in candidates:
            candidates.append(p)
    await page.goto("https://lovable.dev/login?redirect=%2Fdashboard", timeout=40000, wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)
    await page.locator('input[placeholder="Email"]').fill(email)
    await page.locator('[data-testid="auth-submit-button"]').click()
    await page.wait_for_timeout(3000)
    for i, pwd in enumerate(candidates):
        try:
            pw_inp = page.locator('input[placeholder="Password"]')
            await pw_inp.wait_for(state="visible", timeout=8000)
            await pw_inp.fill(pwd)
        except Exception:
            try:
                await page.locator('input[placeholder="Email"]').fill(email)
                await page.locator('[data-testid="auth-submit-button"]').click()
                await page.wait_for_timeout(2500)
                await page.locator('input[placeholder="Password"]').fill(pwd)
            except Exception:
                continue
        await page.locator('[data-testid="auth-submit-button"]').click()
        await page.wait_for_timeout(6000)
        txt = await _safe_text(page, 800)
        low = txt.lower()
        if "invalid" in low or "incorrect" in low:
            log(f"login pwd try {i+1}/{len(candidates)} rejected")
            continue
        if "verification code" in low or "two-factor" in low or "authenticator" in low:
            if not totp_secret:
                return False
            await _totp_fill(page, totp_secret)
            await page.wait_for_timeout(6000)
            txt2 = await _safe_text(page, 800)
            if (
                totp_backup
                and totp_backup != totp_secret
                and ("verification code" in txt2.lower() or "two-factor" in txt2.lower() or "authenticator" in txt2.lower())
            ):
                log("primary TOTP rejected, trying backup secret")
                await _totp_fill(page, totp_backup)
                await page.wait_for_timeout(6000)
        if "Log in" not in await _safe_text(page, 500):
            return True
        log(f"login pwd try {i+1} still on auth page")
    return "Log in" not in await _safe_text(page, 500)


async def _scroll_chat_bottom(page):
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


async def _find_chat_input(page):
    """Scroll chat column and locate Ask Lovable input."""
    chat_input = None
    for _scroll_try in range(4):
        await _scroll_chat_bottom(page)
        await page.wait_for_timeout(2000)
        for sel in [
            'div[contenteditable="true"][role="textbox"]',
            'div[contenteditable="true"]',
            '.ProseMirror[contenteditable="true"]',
            '[data-testid="chat-input"]',
            'textarea[placeholder*="Ask"]',
            '[contenteditable="true"]',
            'textarea',
        ]:
            try:
                cand = page.locator(sel).first
                await cand.wait_for(state="visible", timeout=4000)
                chat_input = cand
                break
            except Exception:
                continue
        if chat_input:
            await _dismiss_overlays(page)
            # click Ask Lovable placeholder / composer to force hydrate
            try:
                ask = page.get_by_text("Ask Lovable", exact=False).first
                if await ask.count():
                    await ask.click(timeout=2000, force=True)
            except Exception:
                pass
            if await _uncrop(page, chat_input, "chat input"):
                return chat_input
            # last tries: still return input — paste path force-clicks
            if _scroll_try >= 2:
                log("chat input covered — forcing through")
                return chat_input
            chat_input = None
        log(f"chat input not yet rendered (scroll try {_scroll_try+1}/4)")
    return None


async def _paste_bridge_prompt(page, chat_input, prompt=None):
    """Paste full prompts/Build a debug terminal.txt into chat (not trivial wake)."""
    prompt = prompt if prompt is not None else SUBPROCESS_PROMPT
    try:
        await chat_input.scroll_into_view_if_needed(timeout=8000)
    except Exception:
        pass
    try:
        await chat_input.click(timeout=8000, force=True)
    except Exception:
        try:
            await chat_input.focus(timeout=8000)
        except Exception:
            await js_click(page, chat_input, "chat input focus")
    # 1) fill
    try:
        await chat_input.fill(prompt, timeout=20000)
        got = (await chat_input.inner_text()).strip()
        if len(got) >= min(200, len(prompt) // 4):
            return True
    except Exception as e:
        log(f"chat fill fail: {e}")
    # 2) clipboard + Ctrl+V
    try:
        await page.evaluate(
            """async (text) => { try { await navigator.clipboard.writeText(text); } catch (e) {} }""",
            prompt,
        )
        await page.keyboard.press("ControlOrMeta+a")
        await page.keyboard.press("ControlOrMeta+v")
        await page.wait_for_timeout(600)
        got = (await chat_input.inner_text()).strip()
        if len(got) >= min(200, len(prompt) // 4):
            return True
    except Exception as e:
        log(f"clipboard paste fail: {e}")
    # 3) insertText (handles long prompts without per-char type)
    await page.keyboard.press("ControlOrMeta+a")
    await page.keyboard.insert_text(prompt)
    await page.wait_for_timeout(400)
    return True


async def _project_id_from_page(page):
    try:
        m = _re.search(r"/projects/([0-9a-fA-F-]{36})", page.url or "")
        return m.group(1) if m else None
    except Exception:
        return None


async def _ensure_lovableproject_term(page, label="", ctx=None):
    """Make lovableproject.com /term visible — that's where window.doc lives.

    Prefer navigating an existing lovableproject iframe. If Kernel only shows
    id-preview/about:blank, open https://{project}.lovableproject.com/term in a
    same-cookie tab and probe there.
    """
    await _dismiss_overlays(page)
    for name in ("Previewing", "Preview", "Shell", "Terminal", "Restore preview", "Restore"):
        try:
            loc = page.get_by_role("button", name=re.compile(name, re.I))
            if await loc.count() and await loc.first.is_visible():
                await loc.first.click(timeout=2500, force=True)
                await page.wait_for_timeout(800)
        except Exception:
            pass

    # 1) navigate existing lovableproject frame → /term
    for fr in list(page.frames):
        u = fr.url or ""
        if "lovableproject.com" not in u:
            continue
        if "/term" in u:
            return fr, None
        try:
            m = _re.match(r"(https://[^/]+\.lovableproject\.com)", u.split("?")[0])
            host = m.group(1) if m else u.split("?")[0].rstrip("/")
            dest = host + "/term"
            log(f"{label} inject: navigate iframe → /term")
            await fr.goto(dest, timeout=25000, wait_until="domcontentloaded")
            await page.wait_for_timeout(1500)
            return fr, None
        except Exception as e:
            log(f"{label} inject: iframe /term nav warn: {type(e).__name__}")

    # 2) no lovableproject iframe — open dedicated tab (same cookies)
    if ctx is None:
        try:
            ctx = page.context
        except Exception:
            ctx = None
    pid = await _project_id_from_page(page)
    if ctx is not None and pid:
        dest = f"https://{pid}.lovableproject.com/term"
        try:
            log(f"{label} inject: open tab {dest}")
            tab = await ctx.new_page()
            await tab.goto(dest, timeout=60000, wait_until="domcontentloaded")
            await tab.wait_for_timeout(2500)
            return None, tab
        except Exception as e:
            log(f"{label} inject: lovableproject tab fail: {type(e).__name__}: {e}")
    return None, None


async def _probe_doc_on_target(page=None, tab=None):
    """Probe window.doc on iframe frames and/or a dedicated lovableproject tab."""
    targets = []
    if tab is not None:
        targets.append(("tab", tab, tab.url or ""))
        for fr in tab.frames:
            targets.append(("tab-fr", fr, fr.url or ""))
    if page is not None:
        for fr in page.frames:
            u = fr.url or ""
            if not u or u.startswith("chrome") or u == "about:blank":
                continue
            if "lovable.dev" in u and "lovableproject" not in u:
                continue
            score = 0
            if "lovableproject.com" in u:
                score += 100
            if "/term" in u:
                score += 50
            if "id-preview" in u or "lovable.app" in u:
                score += 10
            targets.append((score, fr, u))
    # sort: prefer dedicated tab, then high-score frames (lovableproject /term first)
    def key(t):
        kind = t[0]
        if kind == "tab":
            return (0, 0)
        if kind == "tab-fr":
            return (1, 0)
        return (2, -int(kind))

    for kind, fr, u in sorted(targets, key=key):
        if not u:
            continue
        if isinstance(kind, int) and kind < 10:
            continue
        try:
            ok = await fr.evaluate(
                """() => {
                  try {
                    if (typeof window.doc === 'function') return true;
                    if (typeof window.bug === 'function' || typeof window.bug !== 'undefined') return true;
                  } catch (e) {}
                  return false;
                }"""
            )
            if ok:
                return True, u, fr
            # helpful when /term not built yet
            if "/term" in u or "lovableproject.com" in u:
                try:
                    snip = await fr.evaluate(
                        "() => (document.body&&document.body.innerText||'').slice(0,60)"
                    )
                    if snip and ("404" in snip or "proxy error" in snip.lower()):
                        # not ready
                        pass
                except Exception:
                    pass
        except Exception:
            continue
    return False, None, None


async def _probe_doc_in_frames(page):
    ok, u, _ = await _probe_doc_on_target(page=page)
    return ok, u


async def _remount_preview(page, label="", ctx=None):
    return await _ensure_lovableproject_term(page, label=label, ctx=ctx)


async def inject_and_wait_bridge(page, ctx=None, label="", wait_s=900, prompt=None):
    """Send Build a debug terminal.txt and wait until window.doc is live.

    window.doc lives on lovableproject.com /term — Homepage / id-preview will miss it.
    """
    prompt = prompt if prompt is not None else SUBPROCESS_PROMPT
    if ctx is None:
        try:
            ctx = page.context
        except Exception:
            ctx = None
    term_tab = None
    try:
        _, term_tab = await _ensure_lovableproject_term(page, label=label, ctx=ctx)
        ok0, url0, fr0 = await _probe_doc_on_target(page=page, tab=term_tab)
        if ok0:
            pwd_out = None
            try:
                if fr0 is not None:
                    pwd_out = await fr0.evaluate(
                        "async () => typeof window.doc === 'function' ? await window.doc('pwd') : null"
                    )
            except Exception:
                pass
            log(f"{label} inject: window.doc already live @ {(url0 or '')[:90]} pwd={str(pwd_out)[:60]}")
            return {"bridge": True, "reason": "doc_already", "preview_url": url0, "pwd": pwd_out}

        log(f"{label} inject: Build a debug terminal ({len(prompt)} chars), wait≤{wait_s}s")
        chat_input = await _find_chat_input(page)
        if not chat_input:
            return {"bridge": False, "reason": "no_chat_input"}
        await _paste_bridge_prompt(page, chat_input, prompt)
        try:
            got = (await chat_input.inner_text()).strip()
            log(f"{label} inject: composer_len={len(got)} head={got[:50]!r}")
            if "debug terminal" not in got.lower() and len(got) < 200:
                await page.keyboard.press("ControlOrMeta+a")
                await page.keyboard.insert_text(prompt)
                await page.wait_for_timeout(500)
        except Exception as e:
            log(f"{label} inject: composer verify warn: {e}")
        await wait(800, 1200)
        try:
            await js_click(page, page.locator('button[data-testid="chat-input-send"]'), "send bridge prompt")
        except Exception:
            await page.keyboard.press("Enter")
        log(f"{label} inject: prompt sent — polling lovableproject /term for window.doc")
        deadline = asyncio.get_running_loop().time() + wait_s
        last_status = ""
        ticks = 0
        while asyncio.get_running_loop().time() < deadline:
            ticks += 1
            await _dismiss_overlays(page)
            if ticks == 1 or (last_status in ("Previewing", "Stopped") and ticks % 3 == 0) or ticks % 8 == 0:
                # reuse tab when possible; only reopen periodically / after Previewing
                need_new = term_tab is None
                if term_tab is not None:
                    try:
                        body = await term_tab.evaluate(
                            "() => (document.body && document.body.innerText || '').slice(0,80)"
                        )
                        if "404" in (body or "") or "proxy error" in (body or "").lower():
                            need_new = True
                        else:
                            await term_tab.reload(wait_until="domcontentloaded", timeout=30000)
                            await term_tab.wait_for_timeout(1500)
                    except Exception:
                        need_new = True
                if need_new:
                    try:
                        if term_tab is not None:
                            await term_tab.close()
                    except Exception:
                        pass
                    _, term_tab = await _ensure_lovableproject_term(page, label=label, ctx=ctx)
            # also try navigate in-editor lovableproject iframe when it appears
            for fr in list(page.frames):
                u = fr.url or ""
                if "lovableproject.com" in u and "/term" not in u:
                    try:
                        m = _re.match(r"(https://[^/]+\.lovableproject\.com)", u.split("?")[0])
                        if m:
                            await fr.goto(m.group(1) + "/term", timeout=20000, wait_until="domcontentloaded")
                            log(f"{label} inject: editor iframe → /term")
                    except Exception:
                        pass
            ok, url, fr = await _probe_doc_on_target(page=page, tab=term_tab)
            if ok:
                pwd_out = None
                try:
                    if fr is not None:
                        pwd_out = await fr.evaluate(
                            "async () => typeof window.doc === 'function' ? await window.doc('pwd') : null"
                        )
                except Exception as e:
                    log(f"{label} inject: pwd probe warn: {e}")
                log(f"{label} inject: window.doc live @ {(url or '')[:90]} pwd={str(pwd_out)[:80]}")
                return {"bridge": True, "reason": "doc_ready", "preview_url": url, "pwd": pwd_out}
            try:
                st = await page.evaluate("""() => {
                    const t = document.body.innerText || '';
                    if (/Previewing/i.test(t)) return 'Previewing';
                    if (/\\bStopped\\b/i.test(t)) return 'Stopped';
                    if (/Building|Thinking|Thought for|Working|Generating/i.test(t)) return 'Building';
                    return 'wait';
                }""")
                if st != last_status:
                    log(f"{label} inject: status={st}")
                    last_status = st
            except Exception:
                pass
            if ticks % 5 == 0:
                try:
                    urls = [fr.url for fr in page.frames if fr.url][:6]
                    if term_tab is not None:
                        urls.append("TAB:" + (term_tab.url or "")[:80])
                    log(f"{label} inject: frames={urls}")
                except Exception:
                    pass
            await asyncio.sleep(6)
        return {"bridge": False, "reason": "timeout_no_doc"}
    finally:
        if term_tab is not None:
            try:
                await term_tab.close()
            except Exception:
                pass


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
        _alts = [cfg.get("password_alt"), cfg.get("password_backup")]
        if not await _login(
            page, email, password, cfg.get("totp_secret"), cfg.get("totp_secret_backup"),
            password_alts=[a for a in _alts if a],
        ):
            return {"session": num, "email": email, "success": False, "reason": "login failed"}

        # Finish onboarding if still on /getting-started
        try:
            txt0 = await _safe_text(page, 800)
            if (
                "/getting-started" in page.url
                or "Pick your style" in txt0
                or "What's your name" in txt0
                or "Which role fits you best" in txt0
            ):
                log(f"session-{num} completing onboarding before remix")
                import importlib.util
                _p = os.path.join(CORE, "account_creation.py")
                _spec = importlib.util.spec_from_file_location("lov_ac_onboard", _p)
                _mod = importlib.util.module_from_spec(_spec)
                _spec.loader.exec_module(_mod)
                await _mod.handle_onboarding(page)
                await page.wait_for_timeout(2000)
                log(f"session-{num} onboarding done url={page.url[:80]}")
        except Exception as e:
            log(f"session-{num} onboarding warn: {e}")

        try:
            await page.goto("https://lovable.dev/dashboard", timeout=40000, wait_until="domcontentloaded")
            await page.wait_for_timeout(2500)
            if "Log in" in await _safe_text(page, 500):
                return {"session": num, "email": email, "success": False, "reason": "login failed (post-check)"}
        except Exception:
            pass

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
        # Radix-style custom checkbox: idempotent — stop after first successful tick
        ticked = False
        try:
            for sel in ['div[role="dialog"] button[role="checkbox"]',
                        'div[role="dialog"] [role="checkbox"]',
                        'div[role="dialog"] input[type="checkbox"]',
                        'input[type="checkbox"]', '[role="checkbox"]']:
                try:
                    loc = page.locator(sel).first
                    if not await loc.count():
                        continue
                    try:
                        checked = await loc.is_checked()
                    except Exception:
                        checked = None
                    if checked:
                        ticked = True
                        break
                    try:
                        log(f"session-{num} ticking checkbox sel={sel}")
                    except Exception:
                        pass
                    try:
                        await loc.scroll_into_view_if_needed(timeout=5000)
                    except Exception:
                        pass
                    try:
                        await loc.check(timeout=5000, force=True)
                        ticked = True
                    except Exception:
                        try:
                            await loc.click(timeout=5000, force=True)
                            ticked = True
                        except Exception:
                            try:
                                await loc.evaluate("el => el.click()")
                                ticked = True
                            except Exception:
                                pass
                    await page.wait_for_timeout(800)
                    try:
                        if await loc.is_checked():
                            break
                    except Exception:
                        break  # assume ticked, avoid double-toggle
                    break  # one attempt only — never toggle twice
                except Exception:
                    continue
            if not ticked:
                try:
                    await page.evaluate("""() => {
                        const dlg = document.querySelector('div[role="dialog"]') || document.body;
                        const el = dlg.querySelector('input[type="checkbox"], [role="checkbox"]');
                        if (el) {
                            el.scrollIntoView({block:'center'});
                            el.click();
                            try {
                                el.checked = true;
                                el.setAttribute('aria-checked','true');
                                el.setAttribute('data-state','checked');
                                el.dispatchEvent(new Event('input',{bubbles:true}));
                                el.dispatchEvent(new Event('change',{bubbles:true}));
                            } catch(e) {}
                        }
                    }""")
                except Exception:
                    pass
            await page.wait_for_timeout(1200)
        except Exception:
            pass
        ack = page.locator('button:has-text("Acknowledge and remix")')
        try:
            await ack.wait_for(state="visible", timeout=15000)
        except Exception as e:
            try:
                dbg_url = page.url
                dbg_txt = await _safe_text(page, 1500)
                log(f"session-{num} ack not visible url={dbg_url[:100]} txt={dbg_txt[:300]!r}")
                # fallback: any button with Acknowledge text, or dialog submit
                for fsel in ['button:has-text("Acknowledge and remix")',
                             'button:has-text("Acknowledge & remix")',
                             'div[role="dialog"] button:has-text("Acknowledge")',
                             'div[role="dialog"] button:has-text("Remix")']:
                    try:
                        fl = page.locator(fsel).first
                        if await fl.count() and await fl.is_visible():
                            label = ((await fl.inner_text()) or "").strip().lower()
                            if any(bad in label for bad in ("close", "cancel", "continue", "dismiss")):
                                continue
                            log(f"session-{num} ack fallback sel={fsel} label={label!r}")
                            ack = fl
                            break
                    except Exception:
                        continue
                else:
                    # dialog may have closed after tick (auto-submit?) — check redirect directly
                    if "/projects/" in page.url:
                        pass
                    else:
                        raise e
            except Exception as ie:
                # re-raise original if fallback failed
                if "/projects/" not in page.url:
                    raise e
        for _ in range(15):
            try:
                if await ack.is_enabled():
                    break
            except Exception:
                pass
            await page.wait_for_timeout(1000)
        # if still disabled, force-enable (React state may lag after tick)
        try:
            if not await ack.is_enabled():
                log(f"session-{num} ack disabled after tick, force-enabling")
                await ack.evaluate("""el => {
                    el.removeAttribute('disabled');
                    el.setAttribute('aria-disabled','false');
                    el.classList.remove('opacity-50','cursor-not-allowed');
                }""")
                await page.wait_for_timeout(800)
        except Exception:
            pass
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
            try:
                await page.goto("https://lovable.dev/dashboard", timeout=60000, wait_until="domcontentloaded")
                await page.wait_for_timeout(4000)
                href = await page.evaluate("""() => {
                  const a = [...document.querySelectorAll('a[href*="/projects/"]')]
                    .map(x => x.href)
                    .find(h => /\\/projects\\/[0-9a-f-]{8,}/i.test(h));
                  return a || null;
                }""")
                if href and "/projects/" in href:
                    await page.goto(href.split("?")[0], timeout=60000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(3000)
                    log(f"session-{num} recovered project via dashboard {page.url[:100]}")
            except Exception as e:
                log(f"session-{num} dashboard recover warn: {e}")
        if "/projects/" not in page.url:
            return {"session": num, "email": email, "success": False, "reason": f"no redirect after remix ({page.url[:80]})"}
        project_id = page.url.split("/projects/")[-1].split("?")[0] if "/projects/" in page.url else ""
        project_link = page.url.split("?")[0] if "/projects/" in page.url else ""
        log(f"session-{num} remixed project {project_id} {project_link}")
        # persist project immediately — bridge may still fail
        cfg["last_remix_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        cfg["project_id"] = project_id
        cfg["project_link"] = project_link
        projects = cfg.get("projects") if isinstance(cfg.get("projects"), list) else []
        if not any(p.get("project_id") == project_id for p in projects if isinstance(p, dict)):
            projects.append({
                "project_id": project_id,
                "project_link": project_link,
                "invite_link": None,
                "from_session": int(num) if str(num).isdigit() else num,
            })
        cfg["projects"] = projects
        json.dump(cfg, open(cfg_path, "w"), indent=2)
        try:
            fresh = await ctx.cookies()
            json.dump(fresh, open(ck_path, "w"), indent=2)
        except Exception:
            pass
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=20000)
        except Exception:
            pass
        await page.wait_for_timeout(10000)  # let editor hydrate after remix

        # --- inject bridge via chat (Build a debug terminal.txt — wait for window.doc) ---
        inj = await inject_and_wait_bridge(page, ctx, label=f"session-{num}", wait_s=900)
        has_doc = bool(inj.get("bridge"))
        if not has_doc:
            return {
                "session": num, "email": email, "success": True,
                "reason": f"project_ok_no_bridge:{inj.get('reason')}",
                "project_id": project_id, "project_link": project_link, "bridge": False,
            }

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
        tag = os.environ.get("KERNEL_BROWSER_NAME", f"remix-iso-{int(time.time())}")
        cmd = ["kernel", "browsers", "create", "--stealth",
               "--timeout", "2400", "--name", tag,
               "--start-url", "https://lovable.dev/dashboard", "-o", "json"]
        out = subprocess.check_output(cmd, env=_kernel_env(), text=True, timeout=120)
        d = json.loads(out)
        print(f"LIVE: {d.get('browser_live_view_url')} | SID: {d['session_id']} | NAME: {tag}", file=sys.stderr)
        return d["cdp_ws_url"], d["session_id"]

    def _del_browser(sid):
        if sid:
            subprocess.run(["kernel", "browsers", "delete", sid],
                env=_kernel_env(),
                timeout=15, capture_output=True)

    if os.environ.get("SKIP_PRECLEAN") or os.environ.get("ISOLATE"):
        print("pre-cleanup skipped (isolate/sibling)", flush=True)
    else:  # ONLY delete remix-iso-* — never foreign / cell browsers
        try:
            _ls = subprocess.check_output(["kernel", "browsers", "list", "-o", "json"],
                env=_kernel_env(), text=True, timeout=30)
            for _b in json.loads(_ls):
                _name = str(_b.get("name") or "")
                if _name.startswith("remix-iso"):
                    _del_browser(_b.get("session_id"))
                else:
                    print(f"pre-cleanup keep foreign browser name={_name!r}", flush=True)
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
