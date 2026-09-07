#!/usr/bin/env python3
"""ZenRows account creation via Kernel Browser Cloud — deterministic, no AI, no opencode.
Uses Kernel stealth browser (fresh IP per run) + dispose.lol Gmail + iframe srcdoc verify extraction.

Flow proven 2026-09-02 on rprb81jbgg2gt6uyd0l6ozps (prod-jfk-hypeman-7, live 5a79zRDd8ZLd):
  dispose.lol cyn.thiabayaletan@gmail.com → app.zenrows.com/register (CF reload fix) → email/verify → dispose poll → url4722 Verify email → overview → API e7e88777223864ab0252b6983c98a8927c60cf8b
Also verified: s.ofiareeyesa@gmail.com → 3f7d260bab1d75874f8992d28eb536b575eb9a28

Usage:
  KERNEL_API_KEY=sk_729ff0c8-8973-8dcb-9c53-7288178dbc13.jO62-M4NtqELqARSxGY1Ar7BPyjSIU6OhdoHMjdt0Ow python3 finals/core/zenrows-kernel-final.py
"""
import asyncio, os, json, re, subprocess, sys, time, random

KERNEL_API_KEY = os.environ.get("KERNEL_API_KEY", "sk_729ff0c8-8973-8dcb-9c53-7288178dbc13.jO62-M4NtqELqARSxGY1Ar7BPyjSIU6OhdoHMjdt0Ow")
os.environ["PATH"] = os.environ.get("PATH","") + f":{os.path.expanduser('~')}/.local/bin"

def create_kernel_browser():
    if os.environ.get("KERNEL_CDP_WS"):
        wss = os.environ["KERNEL_CDP_WS"]
        return wss, os.environ.get("KERNEL_LIVE_URL",""), os.environ.get("KERNEL_SESSION_ID","")
    import shlex as _sh
    _proxy = os.environ.get("KERNEL_PROXY_NAME", "farm-res-us")
    _px = f" --proxy-name {_sh.quote(_proxy)}" if _proxy else ""
    cmd = f"kernel browsers create --stealth --timeout 2400{_px} --start-url https://dispose.lol -o json"
    env = {**os.environ, "KERNEL_API_KEY": KERNEL_API_KEY}
    out = subprocess.check_output(cmd, shell=True, env=env, text=True)
    data = json.loads(out)
    print(f"LIVE: {data['browser_live_view_url']} | SID: {data['session_id']}", file=sys.stderr)
    return data["cdp_ws_url"], data["browser_live_view_url"], data["session_id"]

def cleanup_kernel(session_id):
    try:
        subprocess.run(f"kernel browsers delete {session_id}", shell=True, env={**os.environ, "KERNEL_API_KEY": KERNEL_API_KEY}, timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except: pass

def create_22do_gmail(tries=40):
    """22.do fake-gmail API (pure HTTP, no browser). Returns @gmail.com or None."""
    import urllib.request as _u, json as _j
    for _k in list(os.environ):
        if _k.lower().endswith('_proxy'):
            os.environ.pop(_k, None)
    for _t in range(tries):
        try:
            _d = _j.dumps({"type": "random"}).encode()
            _rq = _u.Request("https://22.do/action/mailbox/gmail", data=_d,
                headers={"Content-Type": "application/json",
                         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"},
                method="POST")
            with _u.urlopen(_rq, timeout=15) as _r:
                _res = _j.loads(_r.read())
            _em = ((_res.get("data") or {}).get("email") or "").strip()
            _local = _em.split("@")[0] if "@" in _em else ""
            if _em.lower().endswith("@gmail.com") and _local.count(".") == 1 and "+" not in _em:
                return _em
            print(f"22.do skip {_em} (need @gmail.com + exactly 1 dot, no plus), retry {_t+1}/{tries}", file=sys.stderr)
        except Exception as _e:
            print(f"22.do API try {_t+1} err {str(_e)[:120]}", file=sys.stderr)
    return None

async def run_once():
    cdp_ws, live_url, session_id = create_kernel_browser()
    print(f"Connecting to {cdp_ws[:60]}... | LIVE {live_url}", file=sys.stderr)
    from playwright.async_api import async_playwright
    for k in list(os.environ):
        if k.lower().endswith('_proxy'):
            os.environ.pop(k, None)

    browser = None
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(cdp_ws, timeout=30000)
            ctx = browser.contexts[0]
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            if "dispose.lol" not in page.url:
                await page.goto("https://dispose.lol", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(5000)
            body = await page.evaluate("() => document.body.innerText")
            # 0) 22.do fake-gmail API first (pure HTTP, instant; polled via 22.do inbox)
            email = create_22do_gmail()
            email_source = "22do" if email else "dispose"
            if email:
                print(f"22.do Gmail {email} (skip dispose)", file=sys.stderr)
            if not email:
                # Gmail ONLY: astroai.eu.cc + mail.tm blocked ("Email domain not allowed").
                # Fallback = dispose.lol page Gmail (must have exactly 1 dot, no plus).
                print("22.do miss, fallback to dispose.lol Gmail (astroai/mail.tm blocked)", file=sys.stderr)
                _gm = [m for m in re.findall(r"[a-z0-9._%+-]+@gmail\.com", body, re.I)
                       if m.split("@")[0].count(".") == 1 and "+" not in m]
                if not _gm:
                    print("No valid dispose Gmail (1 dot, no plus) — fresh browser", file=sys.stderr)
                    await page.screenshot(path="/tmp/zen_no_email_found.png", full_page=True)
                    await browser.close()
                    cleanup_kernel(session_id)
                    sys.exit(1)
                email = _gm[0]
                print(f"dispose Gmail {email}", file=sys.stderr)
            password = "Test1234!AbcZ2026"
            print(f"EMAIL: {email} | PASS: {password} | SRC: {email_source}", file=sys.stderr)

            # Human path: land on homepage first, follow real signup href (keeps _gl params)
            try:
                await page.goto("https://www.zenrows.com/", wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(random.randint(2500, 4500))
                await page.mouse.move(random.randint(400, 800), random.randint(200, 400))
                _su = page.locator('a:has-text("Sign up"), a:has-text("Sign Up"), a[href*="register"]').first
                if await _su.count():
                    try:
                        _href = await _su.get_attribute("href", timeout=3000)
                    except Exception:
                        _href = None
                    if _href and "http" in _href:
                        print(f"Following signup href {_href[:100]}", file=sys.stderr)
                        await page.goto(_href, wait_until="domcontentloaded", timeout=30000,
                                        referer="https://www.zenrows.com/")
                    else:
                        await _su.click(timeout=8000)
                    await page.wait_for_timeout(4000)
                else:
                    raise Exception("no signup link")
            except Exception as _nav_e:
                print(f"Homepage path miss ({str(_nav_e)[:80]}), direct /register", file=sys.stderr)
                await page.goto("https://app.zenrows.com/register", wait_until="domcontentloaded", timeout=30000)
            solved = False
            # CF spec: wait 10min per cycle (auto-captcha needs time, auto-redirects),
            # if not redirected -> refresh, x3 times, then kill browser + fresh one
            for i in range(48):  # 48 *5s = 240s total = 3 cycles x 1m20s
                try:
                    title = await page.title()
                    body_snip = await page.evaluate("() => document.body.innerText.substring(0,1200)")
                except Exception as nav_e:
                    # CF auto-redirect navigated mid-poll -> likely SOLVED, wait + recheck
                    if "navigation" in str(nav_e).lower() or "destroyed" in str(nav_e).lower() or "closed" in str(nav_e).lower():
                        print(f"CF navigation mid-poll at {(i+1)*5}s (auto-redirect?) waiting 5s...", file=sys.stderr)
                        await page.wait_for_timeout(5000)
                        continue
                    raise
                # Solved = register form actually present (copy changes; form doesn't)
                try:
                    has_form = await page.locator("#email").count()
                except Exception:
                    has_form = 0
                if (("Sign Up" in title and "Create a ZenRows account" in body_snip)
                        or (has_form and "Create account" in body_snip)):
                    solved = True
                    print(f"CF solved attempt {i} title={title} has_form={has_form}", file=sys.stderr)
                    break
                if i % 16 == 15 and "Just a moment" in title:
                    print(f"CF still Just a moment at {(i+1)*5}s (cycle {(i+1)//16}/3), refresh...", file=sys.stderr)
                    try:
                        await page.reload(wait_until="domcontentloaded")
                    except Exception:
                        await page.wait_for_timeout(5000)
                elif "Reliable web data" in title and i > 6 and i % 6 == 5:
                    # Still on homepage (signup click missed) -> re-click signup
                    print(f"Still on homepage at {(i+1)*5}s, follow signup href...", file=sys.stderr)
                    try:
                        _su2 = page.locator('a:has-text("Sign up"), a:has-text("Sign Up"), a[href*="register"]').first
                        if await _su2.count():
                            try:
                                _href2 = await _su2.get_attribute("href", timeout=3000)
                            except Exception:
                                _href2 = None
                            if _href2 and "http" in _href2:
                                await page.goto(_href2, wait_until="domcontentloaded", timeout=30000,
                                                referer="https://www.zenrows.com/")
                                await page.wait_for_timeout(3000)
                            else:
                                await _su2.click(timeout=5000)
                    except Exception as _e2:
                        print(f"re-click err {str(_e2)[:80]}", file=sys.stderr)
                else:
                    if i % 6 == 5:
                        print(f"CF waiting... {(i+1)*5}s title={title[:40]}", file=sys.stderr)
                    await page.wait_for_timeout(5000)
            if not solved:
                print("CF not solved", file=sys.stderr)
                await browser.close()
                cleanup_kernel(session_id)
                sys.exit(1)

            await page.wait_for_selector("#email", timeout=15000)
            # Human-like: mouse wander -> click field -> slow type (no instant fill)
            await page.mouse.move(random.randint(300, 700), random.randint(200, 400))
            await page.wait_for_timeout(random.randint(250, 600))
            await page.mouse.wheel(0, random.randint(40, 120))
            await page.wait_for_timeout(random.randint(250, 500))
            async def _human_fill(sel, val):
                for _att in range(3):
                    try:
                        await page.click(sel, timeout=5000)
                    except Exception:
                        pass
                    await page.wait_for_timeout(random.randint(200, 450))
                    try:
                        await page.fill(sel, "")
                    except Exception:
                        pass
                    await page.type(sel, val, delay=random.randint(45, 120))
                    await page.wait_for_timeout(400)
                    try:
                        cur = await page.input_value(sel, timeout=3000)
                    except Exception:
                        cur = ""
                    if cur == val:
                        return True
                    print(f"fill {sel} mismatch (try {_att+1}): got {cur[:30]!r}", file=sys.stderr)
                try:
                    await page.fill(sel, val)
                    await page.wait_for_timeout(400)
                    return (await page.input_value(sel, timeout=3000)) == val
                except Exception as _fe:
                    print(f"fill {sel} fallback err {_fe}", file=sys.stderr)
                    return False
            if not await _human_fill("#email", email):
                print("EMAIL fill failed -> fresh run", file=sys.stderr)
                await browser.close()
                cleanup_kernel(session_id)
                sys.exit(1)
            await page.wait_for_timeout(random.randint(500, 1100))
            await page.mouse.move(random.randint(300, 700), random.randint(350, 550))
            if not await _human_fill("#password", password):
                print("PASSWORD fill failed -> fresh run", file=sys.stderr)
                await browser.close()
                cleanup_kernel(session_id)
                sys.exit(1)
            await page.wait_for_timeout(random.randint(600, 1300))
            _btn = page.locator('button:has-text("Create account")').first
            try:
                _bb = await _btn.bounding_box()
            except Exception:
                _bb = None
            if _bb:
                await page.mouse.move(int(_bb["x"] + _bb["width"] / 2 + random.randint(-20, 20)), int(_bb["y"] + _bb["height"] / 2))
                await page.wait_for_timeout(random.randint(250, 550))
            await _btn.click(timeout=8000)
            await page.wait_for_timeout(9000)
            url = page.url
            print(f"After Create URL: {url}", file=sys.stderr)
            content = await page.content()
            if "Too many accounts detected from your IP" in content:
                print("IP FLAGGED (too many accounts) -> kill browser, fresh IP next run", file=sys.stderr)
                await page.screenshot(path="/tmp/zen_ip_flagged.png", full_page=True)
                await browser.close()
                cleanup_kernel(session_id)
                sys.exit(1)
            if "Email domain not allowed" in content or "Invalid email address" in content:
                print(f"DOMAIN/EMAIL REJECTED for {email} -> kill, fresh email next run", file=sys.stderr)
                await page.screenshot(path="/tmp/zen_domain_blocked.png", full_page=True)
                await browser.close()
                cleanup_kernel(session_id)
                sys.exit(1)
            if "email/verify" not in url and "verify" not in content.lower():
                print(f"Register failed, url={url} {content[:2000]}", file=sys.stderr)
                await page.screenshot(path="/tmp/zen_register_failed.png", full_page=True)
                await browser.close()
                cleanup_kernel(session_id)
                sys.exit(1)
            print(f"Registered {email} → email/verify, polling inbox...", file=sys.stderr)
            # Poll correct inbox: 22.do for 22do mails, temp.tf for dispose @gmail.com, dispose.lol for custom
            is_gmail = email.lower().endswith("@gmail.com")
            print(f"Email {email} is_gmail {is_gmail} src {email_source}", file=sys.stderr)
            found = False
            if email_source == "22do":
                # Poll 22.do inbox in-browser (same kernel session, second tab)
                import re as _re22, html as _html22
                link_re22 = _re22.compile(r"https?://[^\s'\"<>]+(?:zenrows\.com|url4722)[^\s'\"<>]*", _re22.I)
                pg22 = await ctx.new_page()
                await pg22.goto(f"https://22.do/inbox/#/{email}", wait_until="domcontentloaded", timeout=60000)
                await pg22.wait_for_timeout(4000)
                for i in range(30):
                    try:
                        n22 = await pg22.locator("#email-list-wrap .tr").count()
                    except Exception:
                        n22 = 0
                    if i % 5 == 0:
                        try:
                            _t22 = await pg22.title()
                            _b22 = (await pg22.evaluate("() => document.body.innerText.substring(0,150)")).replace("\n", " ")
                        except Exception:
                            _t22, _b22 = "?", "?"
                        print(f"Poll 22.do {i}: {n22} msgs title={_t22[:50]} body={_b22[:120]}", file=sys.stderr)
                    if n22:
                        for k in range(n22):
                            try:
                                tr22 = pg22.locator("#email-list-wrap .tr").nth(k)
                                subj22 = await tr22.locator(".item.subject").inner_text(timeout=2000)
                                from22 = await tr22.locator(".item.from").inner_text(timeout=2000)
                            except Exception:
                                continue
                            if "zenrows" in (subj22 + from22).lower() or "verify" in subj22.lower():
                                print(f"FOUND 22.do mail {subj22} / {from22}", file=sys.stderr)
                                try:
                                    await tr22.locator(".item.subject").click(timeout=3000)
                                except Exception:
                                    pass
                                await pg22.wait_for_timeout(2500)
                                # mail body sits in a scrollable pane below the fold:
                                # scroll every scrollable container to bottom + bring
                                # Verify email / Verification link into view before scanning
                                try:
                                    await pg22.evaluate("""() => {
                                        const scrollables = [...document.querySelectorAll('*')].filter(e => {
                                            try { return e.scrollHeight > e.clientHeight + 50; } catch { return false; }
                                        });
                                        for (const e of scrollables) { try { e.scrollTop = e.scrollHeight; } catch {} }
                                        const t = [...document.querySelectorAll('a,button')].find(x => /verif/i.test(x.innerText||'') && /email|link/i.test(x.innerText||''));
                                        if (t) { try { t.scrollIntoView({block:'center'}); } catch {} }
                                        window.scrollTo(0, document.body.scrollHeight);
                                    }""")
                                except Exception:
                                    pass
                                await pg22.wait_for_timeout(1500)
                                try:
                                    html22 = await pg22.content()
                                except Exception:
                                    html22 = ""
                                # mail body may render inside iframe -> scan all frames too
                                try:
                                    for _fr in pg22.frames:
                                        try:
                                            html22 += "\n" + await _fr.content()
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                                m22 = link_re22.search(html22)
                                if not m22:
                                    # fallback: extract messageId from row onclick -> direct content URL
                                    try:
                                        _mid = await tr22.evaluate("(el) => el.getAttribute('onclick') || el.innerHTML.slice(0,300)")
                                    except Exception:
                                        _mid = ""
                                    _mnum = _re22.search(r"viewEml\(['\"]?(\w+)['\"]?\)", _mid or "")
                                    if _mnum:
                                        try:
                                            await pg22.goto(f"https://22.do/content/{_mnum.group(1)}", wait_until="domcontentloaded", timeout=20000)
                                            await pg22.wait_for_timeout(2500)
                                            html22 = await pg22.content()
                                            m22 = link_re22.search(html22)
                                        except Exception as _ce:
                                            print(f"22.do content url err {_ce}", file=sys.stderr)
                                if m22:
                                    # mail holds TWO distinct tracking URLs (button +
                                    # Verification link) — keep them all, deduped
                                    _all22 = _re22.findall(r"https?://[^\s'\"<>]+(?:zenrows\.com|url4722)[^\s'\"<>]*", html22)
                                    _uniq22 = []
                                    for _u in _all22:
                                        _u = _html22.unescape(_u).replace("&amp;", "&")
                                        if _u not in _uniq22:
                                            _uniq22.append(_u)
                                    print(f"FOUND {len(_uniq22)} LINK(s) via 22.do", file=sys.stderr)
                                    for _u in _uniq22:
                                        print(f"  LINK {_u[:160]}", file=sys.stderr)
                                    verify_url2 = _uniq22[0]
                                    print(f"FOUND LINK via 22.do {verify_url2[:200]}", file=sys.stderr)
                                    await page.evaluate("(urls) => { window.__verifyUrl = urls[0]; window.__verifyUrls = urls; }", _uniq22)
                                    found = True
                                    break
                        if found:
                            break
                    if i == 8 and not found:
                        print("No 22.do mail after 8 polls, Resend...", file=sys.stderr)
                        try:
                            await page.goto("https://app.zenrows.com/email/verify", wait_until="domcontentloaded", timeout=30000)
                            await page.wait_for_timeout(3000)
                            await page.evaluate("() => { const b=[...document.querySelectorAll('button')].find(x=>x.innerText.includes('Resend')); if(b) b.click(); }")
                            await page.wait_for_timeout(5000)
                            await pg22.goto(f"https://22.do/inbox/#/{email}", wait_until="domcontentloaded", timeout=60000)
                            await pg22.wait_for_timeout(4000)
                        except Exception as re22e:
                            print(f"22.do resend err {re22e}", file=sys.stderr)
                    try:
                        await pg22.reload(wait_until="domcontentloaded", timeout=30000)
                    except Exception:
                        pass
                    await pg22.wait_for_timeout(3000)
                try:
                    await pg22.close()
                except Exception:
                    pass
            if is_gmail and email_source not in ("22do", "dispose"):
                # Poll temp.tf directly (no browser needed; NOTE: API 404s as of 2026-09-06)
                import urllib.request, json as _json2, re as _re, html as _html2, time as _time2
                link_re2 = _re.compile(r"https://[^\s]+zenrows\.com[^\s]+", _re.I)
                found = False
                for i in range(20):
                    try:
                        old_env2 = {k: __import__('os').environ.pop(k,None) for k in ("HTTPS_PROXY","HTTP_PROXY","https_proxy","http_proxy","ALL_PROXY","all_proxy")}
                        try:
                            data2=_json2.dumps({"email":email}).encode()
                            req2=urllib.request.Request("https://temp.tf/api/check", data=data2, headers={"Content-Type":"application/json"}, method="POST")
                            with urllib.request.urlopen(req2, timeout=10) as r2:
                                j2=_json2.loads(r2.read())
                                items2=j2.get("data",[])
                                print(f"Poll temp.tf {i}: {len(items2)} msgs", file=sys.stderr)
                                for msg2 in items2:
                                    body2=msg2.get("body","")
                                    subj2=msg2.get("subject","")
                                    m2=link_re2.search(subj2+" "+body2)
                                    if m2:
                                        # Save link for later use via page
                                        verify_url2=_html2.unescape(m2.group(0)).replace("&amp;","&")
                                        print(f"FOUND LINK via temp.tf {verify_url2[:200]}", file=sys.stderr)
                                        # Store in page for later
                                        await page.evaluate("(url) => { window.__verifyUrl = url; }", verify_url2)
                                        found = True
                                        break
                                if found:
                                    break
                        finally:
                            for k,v in old_env2.items():
                                if v is not None:
                                    __import__('os').environ[k]=v
                    except Exception as e:
                        print(f"Poll temp.tf err {e}", file=sys.stderr)
                    await page.wait_for_timeout(2000)
                    if i == 4 and not found:
                        print("No email after 8 polls, trying Resend...", file=sys.stderr)
                        await page.goto("https://app.zenrows.com/email/verify", wait_until="domcontentloaded", timeout=30000)
                        await page.wait_for_timeout(3000)
                        await page.evaluate("() => { const b=[...document.querySelectorAll('button')].find(x=>x.innerText.includes('Resend')); if(b) b.click(); }")
                        await page.wait_for_timeout(5000)
                        print("Resent", file=sys.stderr)
                # For Gmail, we already have verify_url via window.__verifyUrl, skip dispose polling
                if found and email.lower().endswith("@gmail.com"):
                    # Skip dispose polling, use the found link
                    pass
                else:
                    # Poll dispose.lol in SECOND TAB (page stays parked on email/verify)
                    import re as _red, html as _htmld
                    link_red = _red.compile(r"https?://[^\s'\"<>]+(?:zenrows\.com|url4722)[^\s'\"<>]*", _red.I)
                    pgD = await ctx.new_page()
                    await pgD.goto("https://dispose.lol", wait_until="domcontentloaded", timeout=60000)
                    await pgD.wait_for_timeout(4000)
                    for i in range(20):
                        try:
                            bodyD = await pgD.evaluate("() => document.body.innerText")
                        except Exception:
                            bodyD = ""
                        hitD = ("verify@e.zenrows.com" in bodyD or "Verify your email to activate" in bodyD)
                        print(f"Poll dispose {i} hit={hitD} waiting...", file=sys.stderr)
                        if hitD:
                            try:
                                await pgD.evaluate("() => { const b=[...document.querySelectorAll('button')].find(x=>x.getAttribute('aria-label')?.includes('Verify your email')); if(b) b.click(); }")
                            except Exception:
                                pass
                            await pgD.wait_for_timeout(3000)
                            try:
                                htmlD = await pgD.content()
                            except Exception:
                                htmlD = ""
                            mD = link_red.search(htmlD)
                            if mD:
                                verify_url2 = _htmld.unescape(mD.group(0)).replace("&amp;", "&")
                                print(f"FOUND LINK via dispose {verify_url2[:200]}", file=sys.stderr)
                                await page.evaluate("(url) => { window.__verifyUrl = url; }", verify_url2)
                                found = True
                                break
                        try:
                            await pgD.evaluate("() => { const r=[...document.querySelectorAll('button')].find(x=>x.innerText.includes('Refresh')); if(r) r.click(); }")
                        except Exception:
                            pass
                        await pgD.wait_for_timeout(3000)
                        if i == 8 and not found:
                            print("No email after 8 polls, Resend via verify tab...", file=sys.stderr)
                            try:
                                await page.evaluate("() => { const b=[...document.querySelectorAll('button')].find(x=>x.innerText.includes('Resend')); if(b) b.click(); }")
                                await page.wait_for_timeout(5000)
                            except Exception as reD:
                                print(f"resend err {reD}", file=sys.stderr)
                            print("Resent (verify tab kept alive)", file=sys.stderr)
                            try:
                                await pgD.reload(wait_until="domcontentloaded", timeout=30000)
                            except Exception:
                                pass
                            await pgD.wait_for_timeout(2000)
                    try:
                        await pgD.close()
                    except Exception:
                        pass
            if not found:
                print("No verification email after 20 polls", file=sys.stderr)
                await page.screenshot(path="/tmp/zen_no_email.png", full_page=True)
                await browser.close()
                cleanup_kernel(session_id)
                sys.exit(1)

            # For Gmail via temp.tf, verify_url already in window.__verifyUrl
            verify_url = await page.evaluate("() => window.__verifyUrl || ''")
            if verify_url:
                print(f"Using window.__verifyUrl {verify_url[:80]}", file=sys.stderr)
                verify_links = []
                try:
                    _extra = await page.evaluate("() => window.__verifyUrls || []")
                    for _u in _extra[1:]:
                        verify_links.append({"href": _u, "text": "Verification link"})
                    if _extra[1:]:
                        print(f"Extra candidates from mail: {len(_extra)-1}", file=sys.stderr)
                except Exception:
                    pass
            else:
                # Try iframe srcdoc first, then fallback to direct link in dispose UI
                srcdoc = await page.evaluate("() => document.querySelector('iframe')?.getAttribute('srcdoc') || ''")
                verify_links = []
                if srcdoc:
                    verify_links = await page.evaluate("""(sd) => {
                    const p = new DOMParser();
                    const d = p.parseFromString(sd, "text/html");
                    return Array.from(d.querySelectorAll("a")).map(a=> ({ href: a.getAttribute("href"), text: (a.innerText||"").trim() }));
                }""", srcdoc)
                print(f"Links in srcdoc: {verify_links}", file=sys.stderr)
            if not verify_links:
                # Fallback: look for Verification link directly in dispose UI
                verify_links = await page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('a')).map(a=> ({ href: a.getAttribute('href') || a.href, text: (a.innerText||"").trim() })).filter(x=>x.href && (x.href.includes('zenrows') || x.href.includes('url4722') || x.text.includes('Verification')));
                }""")
                print(f"Links in dispose UI: {verify_links}", file=sys.stderr)
                # Also try to find the Verify email button's link
                btn_link = await page.evaluate("""() => {
                    const btn=[...document.querySelectorAll('a','button')].find(b=>b.innerText && b.innerText.includes('Verify email'));
                    if(btn && btn.href) return btn.href;
                    const a=[...document.querySelectorAll('a')].find(x=>x.innerText.includes('Verification link'));
                    return a ? (a.href || a.getAttribute('href')) : '';
                }""")
                if btn_link and "http" in btn_link:
                    verify_links.append({"href": btn_link, "text": "Verify email"})
            if not verify_url:
                verify_url = None
            for link in verify_links:
                if link["text"] == "Verify email" or "Verify" in link["text"]:
                    if link["href"] and ("url4722" in link["href"] or "zenrows" in link["href"]):
                        verify_url = link["href"]
                        break
            if not verify_url:
                for link in verify_links:
                    if link["href"] and ("url4722" in link["href"] or "zenrows" in link["href"]):
                        verify_url = link["href"]
                        break
            if not verify_url:
                # Last resort: click the Verify email button directly
                print(f"No verify_url found, trying to click Verify email button", file=sys.stderr)
                clicked = await page.evaluate("""() => {
                    const btn=[...document.querySelectorAll('button')].find(b=>b.innerText.includes('Verify email'));
                    if(btn){ btn.click(); return 'clicked button'; }
                    const a=[...document.querySelectorAll('a')].find(x=>x.innerText.includes('Verify email'));
                    if(a){ a.click(); return 'clicked a '+a.href.slice(0,80); }
                    return 'not found';
                }""")
                print(f"Click result {clicked}", file=sys.stderr)
                await page.wait_for_timeout(4000)
                # Check if navigated to verification
                if "zenrows" in page.url and "verify" in page.url:
                    verify_url = page.url
                    print(f"Got verify_url via click: {verify_url[:120]}", file=sys.stderr)
                else:
                    print(f"No verify_url found links={verify_links}", file=sys.stderr)
                    await browser.close()
                    cleanup_kernel(session_id)
                    sys.exit(1)
            print(f"VERIFY_URL: {verify_url[:120]}...", file=sys.stderr)

            # The mail carries TWO distinct tracking URLs (Verify email button
            # href != Verification link href). Try every url4722 candidate in
            # order until one lands on overview (not the www homepage).
            # Candidates must be url4722 tracking links ONLY — never mailto:,
            # logout, or www homepage links scraped from the inbox UI.
            _cands = []
            for _l in [verify_url] + [l.get("href") for l in verify_links if l.get("href")]:
                if _l and "url4722" in _l and _l not in _cands:
                    _cands.append(_l)
            url = page.url
            for _cand in _cands:
                print(f"TRY {str(_cand)[:120]}", file=sys.stderr)
                try:
                    await page.goto(_cand, wait_until="domcontentloaded", timeout=30000)
                except Exception as _nerr:
                    print(f"goto err {_nerr}", file=sys.stderr)
                    continue
                await page.wait_for_timeout(8000)
                url = page.url
                print(f"After verify URL: {url}", file=sys.stderr)
                if "overview" in url:
                    break

            if "app.zenrows.com/overview" not in url and "overview" not in url:
                await page.goto("https://app.zenrows.com/overview", wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(5000)
                url = page.url
                print(f"After overview goto URL: {url}", file=sys.stderr)

            content = await page.content()
            body_text = await page.evaluate("() => document.body.innerText")
            # Real ZenRows keys are 40-hex. Bare 32-hex matches the Sentry DSN
            # public key in page HTML — only accept bare 40-hex on overview.
            _clean = re.sub(r"sentry\.io|ingest|dsn", "", content, flags=re.I)
            m = re.search(r"zenrows login --api-key ([a-f0-9]{40})", content) or re.search(r"zenrows login --api-key ([a-f0-9]{40})", body_text)
            if not m and "overview" in url:
                m = re.search(r"\b([a-f0-9]{40})\b", _clean)
            if not m:
                print(f"No API key found at {url} body={body_text[:2000]}", file=sys.stderr)
                await page.screenshot(path="/tmp/zen_no_apikey.png", full_page=True)
                await browser.close()
                cleanup_kernel(session_id)
                sys.exit(1)
            api_key = m.group(1) if m.groups() else m.group(0)
            print(f"SUCCESS {email} / {password} / {api_key} → {url}", file=sys.stderr)
            result = {"email": email, "password": password, "api_key": api_key, "url": url, "live_url": live_url, "session_id": session_id}
            print(json.dumps(result, indent=2))
            with open("/tmp/zen_kernel_account.txt","w") as f:
                f.write(f"EMAIL={email}\nPASSWORD={password}\nAPI_KEY={api_key}\nURL={url}\nLIVE={live_url}\nSID={session_id}\n")
            await page.screenshot(path="/tmp/zen_verified.png", full_page=True)
            print(f"Saved /tmp/zen_kernel_account.txt and /tmp/zen_verified.png", file=sys.stderr)
            await browser.close()
            cleanup_kernel(session_id)
            return result
    except SystemExit:
        # already cleaned, re-raise
        raise
    except Exception as e:
        print(f"run_once exception {e}", file=sys.stderr)
        import traceback; traceback.print_exc()
        try:
            if browser:
                await browser.close()
        except: pass
        cleanup_kernel(session_id)
        raise

async def main():
    for attempt in range(5):
        try:
            result = await run_once()
            print(f"SUCCESS on attempt {attempt+1}", file=sys.stderr)
            return
        except SystemExit as e:
            if e.code != 0:
                print(f"Attempt {attempt+1} failed with exit {e.code}, retrying with fresh browser...", file=sys.stderr)
                await asyncio.sleep(5)
                continue
            else:
                return
        except Exception as e:
            print(f"Attempt {attempt+1} exception {e}, retrying...", file=sys.stderr)
            await asyncio.sleep(5)
            continue
    print("All 5 attempts failed", file=sys.stderr)
    sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())