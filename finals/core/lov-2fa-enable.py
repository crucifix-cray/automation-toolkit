#!/usr/bin/env python3
"""Enable Lovable 2FA (authenticator app) on a live session — OnKernel or any CDP browser.

Proven 2026-09-07 on scripts/sessions/session-2 (altonlehman16@gmail.com):
  cookies -> dashboard -> /settings/account#2fa -> Reauthenticate (if shown)
  -> Enable -> Authenticator app -> Manual code? -> TOTP verify -> Disable shown.

Usage:
  KERNEL_API_KEY=sk_... python3 finals/core/lov-2fa-enable.py --session 2
  KERNEL_CDP_WS=wss://... python3 finals/core/lov-2fa-enable.py --session 2   # reuse existing browser
  python3 finals/core/lov-2fa-enable.py --session 2 --totp-secret IG7X...     # skip to verify-only
"""
import argparse, asyncio, json, os, subprocess, sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SESSIONS = os.path.join(REPO, "scripts", "sessions")

def clear_proxy():
    for k in list(os.environ):
        if k.lower().endswith("_proxy") or k == "LD_PRELOAD":
            os.environ.pop(k, None)

async def enable_one(pw, ctx, num, live_id=None, totp_secret=None):
    """Enable 2FA on one session dir. Returns dict result. Fresh context per session."""
    import pyotp
    cfg_path = os.path.join(SESSIONS, f"session-{num}", "config.json")
    ck_path = os.path.join(SESSIONS, f"session-{num}", "cookies.json")
    cfg = json.load(open(cfg_path))
    if cfg.get("totp_secret") or cfg.get("2fa_done"):
        return {"session": num, "email": cfg.get("email"), "skipped": "already has 2FA"}
    email, password = cfg["email"], cfg["password"]
    page = await ctx.new_page()
    try:
        raw = json.load(open(ck_path))
        cookies = [{"name": c["name"], "value": c["value"], "domain": c["domain"],
                    "path": c.get("path", "/"), "expires": int(c["expires"]) if c.get("expires") else -1,
                    "httpOnly": bool(c.get("httpOnly", False)), "secure": bool(c.get("secure", False)),
                    "sameSite": c.get("sameSite", "Lax") if c.get("sameSite") in ("Lax", "Strict", "None") else "Lax"}
                   for c in raw if "lovable" in c.get("domain", "")]
        await ctx.add_cookies(cookies)
        await page.goto("https://lovable.dev/dashboard", timeout=40000, wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)
        if "Log in" in await page.evaluate("() => document.body.innerText.slice(0,500)"):
            await page.goto("https://lovable.dev/login?redirect=%2Fdashboard", timeout=40000, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            await page.locator('input[placeholder="Email"]').fill(email)
            await page.locator('[data-testid="auth-submit-button"]').click()
            await page.wait_for_timeout(3000)
            await page.locator('input[placeholder="Password"]').fill(password)
            await page.locator('[data-testid="auth-submit-button"]').click()
            await page.wait_for_timeout(6000)
            if "invalid" in (await page.evaluate("() => document.body.innerText.slice(0,500)")).lower():
                return {"session": num, "email": email, "success": False, "reason": "bad credentials"}

        tab = await ctx.new_page()
        await tab.goto("https://lovable.dev/settings/account", timeout=40000, wait_until="domcontentloaded")
        await tab.wait_for_timeout(6000)

        # Bilingual clicks (Lovable renders fr for our sessions): try EN then FR.
        async def click_text(text, fr=None):
            opts = [text] + ([fr] if fr else [])
            for _t in opts:
                try:
                    await tab.evaluate(f"""() => {{ const b=[...document.querySelectorAll('button')].find(x=>x.innerText.trim()==={_t!r}); if(!b) throw new Error('no {_t}'); b.click(); }}""")
                    await tab.wait_for_timeout(2500)
                    return
                except Exception:
                    continue
            raise Exception(f"no {'/'.join(opts)}")

        async def click_includes(*needles):
            import json as _js
            await tab.evaluate(f"""(nds) => {{ const b=[...document.querySelectorAll('button')].find(x=>{{ const t=x.innerText||''; return nds.some(n=>t.includes(n)); }}); if(!b) throw new Error('no method btn'); b.click(); }}""", list(needles))
            await tab.wait_for_timeout(4000)

        if await tab.evaluate("() => document.body.innerText.includes('Re-authentication required')"):
            await click_text("Reauthenticate", "Se réauthentifier")
            await tab.wait_for_timeout(4000)
            await tab.locator('input[placeholder="Email"]').fill(email)
            await tab.locator('[data-testid="auth-submit-button"]').click()
            await tab.wait_for_timeout(3000)
            await tab.locator('input[placeholder="Password"]').fill(password)
            await tab.locator('[data-testid="auth-submit-button"]').click()
            await tab.wait_for_timeout(6000)

        # already enabled?
        if await tab.evaluate("() => document.body.innerText.includes('Manage your 2FA methods')"):
            return {"session": num, "email": email, "success": False, "reason": "already enabled (no secret captured)"}
        await click_text("Enable", "Activer")
        await click_includes("Authenticator app", "authentification", "Authenticator")
        if "/login" in tab.url:  # step-up kick
            await tab.locator('input[placeholder="Email"]').fill(email)
            await tab.locator('[data-testid="auth-submit-button"]').click()
            await tab.wait_for_timeout(3000)
            await tab.locator('input[placeholder="Password"]').fill(password)
            await tab.locator('[data-testid="auth-submit-button"]').click()
            await tab.wait_for_timeout(6000)
            await click_text("Enable", "Activer")
            await click_includes("Authenticator app", "authentification", "Authenticator")
        await tab.evaluate("() => { const s=[...document.querySelectorAll('*')].find(e=>e.children.length===0&&/manual code/i.test(e.innerText||'')); const b=s?.closest('button'); if(!b) throw new Error('no manual btn'); b.click(); }")
        await tab.wait_for_timeout(2000)
        secret = totp_secret
        if not secret:
            secret = await tab.evaluate("""() => {
                const t=document.body.innerText;
                const m=t.match(/Manual entry key\\s*([A-Z2-7]{16,})/) || t.match(/([A-Z2-7]{32})/);
                return m ? m[1] : ''; }""")
        if not secret or len(secret) < 16:
            return {"session": num, "email": email, "success": False, "reason": "no TOTP secret"}
        code = pyotp.TOTP(secret).now()
        await tab.evaluate(f"""(code) => {{
            const el=document.querySelector('#totp-code');
            const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
            s.call(el,code);
            el.dispatchEvent(new Event('input',{{bubbles:true}}));
            el.dispatchEvent(new Event('change',{{bubbles:true}})); }}""", code)
        await tab.evaluate("() => { const b=[...document.querySelectorAll('button')].find(x=>{ const t=x.innerText.trim(); return t==='Verify & Enable'||t.startsWith('Vérifier'); }); if(!b) throw new Error('no verify'); b.click(); }")
        await tab.wait_for_timeout(5000)
        ok = await tab.evaluate("() => { const t=document.body.innerText; return t.includes('Manage your 2FA methods')||t.includes('Désactiver'); }")
        if ok:
            cfg["totp_secret"] = secret
            if live_id:
                cfg["2fa_live_id"] = live_id
            json.dump(cfg, open(cfg_path, "w"), indent=2)
        return {"session": num, "email": email, "success": ok, "secret": secret if ok else None}
    except Exception as e:
        return {"session": num, "email": cfg.get("email"), "success": False, "reason": str(e)[:200]}
    finally:
        try:
            await page.close()
        except Exception:
            pass

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", default=None, help="session number, e.g. 2")
    ap.add_argument("--all", action="store_true", help="all sessions lacking totp_secret, deduped by email")
    ap.add_argument("--skip", default="", help="comma-separated session numbers to skip, e.g. 1,2")
    ap.add_argument("--totp-secret", default=None)
    ap.add_argument("--id", default=None, dest="live_id", help="2fa.live label id to store alongside secret")
    a = ap.parse_args()
    clear_proxy()

    import glob
    if a.all:
        skip = {s.strip() for s in a.skip.split(",") if s.strip()}
        # backfill: copy known secrets to same-email dirs lacking them
        import glob as _gg
        _email_secret = {}
        for _f in _gg.glob(os.path.join(SESSIONS, "session-*", "config.json")):
            try:
                _d = json.load(open(_f))
            except Exception:
                continue
            if _d.get("email") and _d.get("totp_secret"):
                _email_secret.setdefault(_d["email"], (_d["totp_secret"], _d.get("2fa_live_id")))
        for _f in _gg.glob(os.path.join(SESSIONS, "session-*", "config.json")):
            try:
                _d = json.load(open(_f))
            except Exception:
                continue
            if _d.get("email") in _email_secret and not _d.get("totp_secret"):
                _s, _lid = _email_secret[_d["email"]]
                _d["totp_secret"] = _s
                if _lid:
                    _d.setdefault("2fa_live_id", _lid)
                json.dump(_d, open(_f, "w"), indent=2)
                print(f"backfilled secret to {os.path.basename(os.path.dirname(_f))}", flush=True)
        targets = []
        seen_emails = set()
        for f in sorted(glob.glob(os.path.join(SESSIONS, "session-*", "config.json")),
                        key=lambda p: int(os.path.basename(os.path.dirname(p)).split("-")[1])):
            num = os.path.basename(os.path.dirname(f)).split("-")[1]
            if num in skip:
                continue
            d = json.load(open(f))
            if d.get("totp_secret") or d.get("2fa_done"):
                continue
            if d.get("email") in seen_emails:
                continue  # same account already queued; secrets are per-account
            seen_emails.add(d.get("email"))
            targets.append(num)
        print(f"sessions lacking 2FA: {len(targets)} ({len(seen_emails)} unique emails)", flush=True)
    elif a.session:
        targets = [a.session]
    else:
        raise SystemExit("pass --session N or --all")

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

    owned_sids = []
    import asyncio as _aio
    NWORKERS = 1 if a.session else 5  # ponytail: 5 parallel kernel browsers max
    queue: _aio.Queue = _aio.Queue()
    for _num in targets:
        queue.put_nowait(_num)
    results, owned_sids, _lock = [], [], _aio.Lock()

    async def _worker(wid, pw):
        import random as _rnd
        await _aio.sleep(wid * 8)  # stagger creates; org cap is 5 concurrent
        cdp_ws, sid = None, None
        try:
            if os.environ.get("KERNEL_CDP_WS"):
                cdp_ws = os.environ["KERNEL_CDP_WS"]
            else:
                for _try in range(6):  # slot may be full; wait and retry
                    try:
                        cdp_ws, sid = await _aio.to_thread(_new_browser)
                        break
                    except Exception as e:
                        print(f"[w{wid}] browser create try {_try}: {str(e)[:120]}", flush=True)
                        await _aio.sleep(20 + _rnd.randint(0, 10))
                else:
                    results.append({"worker": wid, "success": False, "reason": "no browser slot after retries"})
                    return
                async with _lock:
                    owned_sids.append(sid)
            browser = await pw.chromium.connect_over_cdp(cdp_ws, timeout=30000)
            while True:
                try:
                    num = queue.get_nowait()
                except _aio.QueueEmpty:
                    break
                try:
                    try:
                        ctx = await browser.new_context()
                    except Exception:
                        _del_browser(sid)  # dead browser -> fresh one, same worker
                        cdp_ws, sid = await _aio.to_thread(_new_browser)
                        async with _lock:
                            owned_sids.append(sid)
                        browser = await pw.chromium.connect_over_cdp(cdp_ws, timeout=30000)
                        ctx = await browser.new_context()
                    try:
                        res = await enable_one(pw, ctx, num, live_id=a.live_id, totp_secret=a.totp_secret)
                    finally:
                        try:
                            await ctx.close()
                        except Exception:
                            pass
                except Exception as e:
                    res = {"session": num, "success": False, "reason": f"worker: {e}"[:200]}
                async with _lock:
                    results.append(res)
                    print(json.dumps(res), flush=True)
                    if res.get("success"):
                        print(f"✅ [w{wid}] session-{num} 2FA on", flush=True)
                        import glob as _g
                        for _f in _g.glob(os.path.join(SESSIONS, "session-*", "config.json")):
                            try:
                                _d = json.load(open(_f))
                            except Exception:
                                continue
                            if _d.get("email") == res.get("email") and not _d.get("totp_secret"):
                                _d["totp_secret"] = res["secret"]
                                if a.live_id:
                                    _d["2fa_live_id"] = a.live_id
                                json.dump(_d, open(_f, "w"), indent=2)
                                print(f"  ↳ secret copied to {os.path.basename(os.path.dirname(_f))}", flush=True)
                    else:
                        print(f"❌ [w{wid}] session-{num} {res.get('reason', res.get('skipped', '?'))}", flush=True)
                queue.task_done()
            try:
                await browser.close()
            except Exception:
                pass
        finally:
            pass

    try:  # pre-cleanup stale browsers so 5 workers fit under org cap
        _ls = subprocess.check_output(["kernel", "browsers", "list", "-o", "json"],
            env={**os.environ, "KERNEL_API_KEY": KERNEL_API_KEY}, text=True, timeout=30)
        for _b in json.loads(_ls):
            _del_browser(_b.get("session_id"))
            print(f"cleaned stale {_b.get('session_id')}", flush=True)
    except Exception as e:
        print(f"pre-cleanup warn {e}", flush=True)

    from playwright.async_api import async_playwright
    try:
        async with async_playwright() as pw:
            await _aio.gather(*[_worker(i, pw) for i in range(NWORKERS)])
    finally:
        for _sid in owned_sids:  # workers own their browsers (new_browser flag unused in pool mode)
            _del_browser(_sid)
    ok = sum(1 for r in results if r.get("success"))
    print(f"\n{ok}/{len(results)} enabled", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
