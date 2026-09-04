#!/usr/bin/env python3
"""Lovable Nx via ZenRows GB — fresh browser/IP per run, rotates through all handlers from lov-api.py

- Imports HANDLERS (10×22.do) from lov-api.py and appends dispose.lol + temp.tf + mail.tm → 13 handlers
- Each run: new ZenRows CDP browser (wss://…&proxy_country=gb) = fresh IP, create email via handler's native method,
  try Lovable signup, report success/failure
"""
import asyncio, os, json, re, html, urllib.request, urllib.error, sys
from pathlib import Path
import importlib.util

def _load_zenrows_key():
    for p in [Path.home()/".zenrows/secrets.json", Path("/tmp/zenrows_key"), Path("/home/alae/.zenrows/secrets.json")]:
        try:
            if p.exists():
                j=json.loads(p.read_text())
                if "apiKey" in j: return j["apiKey"]
                if "apikey" in j: return j["apikey"]
        except: pass
    return os.environ.get("ZENROWS_API_KEY","6202c7099ecb4ce32fadb8f0afddc298630eb583")

ZENROWS_WSS = f"wss://browser.zenrows.com?apikey={_load_zenrows_key()}&proxy_country=gb"
TEMP_TF_API = "https://temp.tf/api"
MAIL_TM_API = "https://api.mail.tm"
RESET_LINK_RE = re.compile(r"https?://[^\s\"'<>]*lovable\.dev[^\s\"'<>]*", re.I)

def clear_proxy():
    for k in list(os.environ):
        if k.lower().endswith('_proxy') or k=='LD_PRELOAD':
            os.environ.pop(k,None)
clear_proxy()

# --- import HANDLERS from lov-api.py (hyphen filename → importlib) ---
HANDLERS_22DO = []
try:
    spec = importlib.util.spec_from_file_location("lov_api", Path(__file__).with_name("lov-api.py"))
    lov_api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lov_api)
    HANDLERS_22DO = list(lov_api.HANDLERS)
    print(f"Imported {len(HANDLERS_22DO)} handlers from lov-api.py", flush=True)
except Exception as e:
    print(f"Could not import lov-api.py HANDLERS ({e}), using fallback 10", flush=True)
    HANDLERS_22DO = [
        ("@linshiyou.com", "https://22.do/", "@linshiyou.com"),
        ("@colabeta.com", "https://22.do/", "@colabeta.com"),
        ("@youxiang.dev", "https://22.do/", "@youxiang.dev"),
        ("@colaname.com", "https://22.do/", "@colaname.com"),
        ("@usdtbeta.com", "https://22.do/", "@usdtbeta.com"),
        ("@tnbeta.com", "https://22.do/", "@tnbeta.com"),
        ("@fft.edu.do", "https://22.do/", "@fft.edu.do"),
        ("@gmail.com (Fake Gmail)", "https://22.do/fake-gmail-generator", "@gmail.com"),
        ("@hotmail.com", "https://22.do/temporary-hotmail", "@hotmail.com"),
        ("@outlook.com", "https://22.do/temporary-outlook", "@outlook.com"),
    ]

# Full rotation: 10×22.do + dispose.lol (browser) + temp.tf (API) + mail.tm (API) = 13
ALL_HANDLERS = [(n, u, d, "22do") for n, u, d in HANDLERS_22DO] + [
    ("dispose.lol", "https://dispose.lol", "@gmail.com", "dispose"),
    ("temp.tf", TEMP_TF_API, "@gmail.com", "temptf"),
    ("mail.tm", MAIL_TM_API, None, "mailtm"),
]

# --- helpers: bypass proxy for temp.tf / mail.tm (they block Tor exits) ---
def _bypass_proxy_open(req, timeout=15):
    old_env = {k: os.environ.pop(k, None) for k in ("HTTPS_PROXY","HTTP_PROXY","https_proxy","http_proxy","ALL_PROXY","all_proxy")}
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    finally:
        for k, v in old_env.items():
            if v is not None: os.environ[k]=v

def _temptf_get(path, data=None):
    url = f"{TEMP_TF_API}{path}"
    if data is not None:
        req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={"Content-Type":"application/json"}, method="POST")
    else:
        req = urllib.request.Request(url)
    return json.loads(_bypass_proxy_open(req, timeout=15))

def create_temptf_email_sync():
    for _ in range(10):
        try:
            acct = _temptf_get("/account?dot=1&providers=gmail")
            email = acct["email"]
            _temptf_get("/check", {"email": email})
            return email
        except urllib.error.HTTPError as e:
            if e.code==500:
                asyncio.sleep(0)  # placeholder
                continue
            raise
    raise RuntimeError("temp.tf create failed")

async def create_temptf_email():
    return await asyncio.to_thread(create_temptf_email_sync)

# mail.tm via urllib (no requests dep) — mirrors scripts/railway-mailtm.py
def create_mailtm_email_sync():
    # get domain
    dom_req = urllib.request.Request(f"{MAIL_TM_API}/domains", headers={"Content-Type":"application/json"})
    dom_raw = _bypass_proxy_open(dom_req, timeout=15)
    dom_j = json.loads(dom_raw)
    domains = dom_j["hydra:member"] if isinstance(dom_j, dict) and "hydra:member" in dom_j else dom_j
    domain = domains[0]["domain"]
    import time, random
    username = f"lov{int(time.time()*1000)%10**9}{random.randint(100,999)}"
    address = f"{username}@{domain}"
    password = "Lovable2024!"
    # create account
    acc_req = urllib.request.Request(f"{MAIL_TM_API}/accounts", data=json.dumps({"address":address,"password":password}).encode(), headers={"Content-Type":"application/json"}, method="POST")
    _bypass_proxy_open(acc_req, timeout=15)
    # token
    tok_req = urllib.request.Request(f"{MAIL_TM_API}/token", data=json.dumps({"address":address,"password":password}).encode(), headers={"Content-Type":"application/json"}, method="POST")
    tok_raw = _bypass_proxy_open(tok_req, timeout=15)
    token = json.loads(tok_raw)["token"]
    return address, password, token

async def create_mailtm_email():
    return await asyncio.to_thread(create_mailtm_email_sync)

def poll_mailtm_sync(token, timeout=300):
    import time
    deadline = time.time()+timeout
    while time.time()<deadline:
        req = urllib.request.Request(f"{MAIL_TM_API}/messages", headers={"Authorization": f"Bearer {token}", "Content-Type":"application/json"})
        try: raw = _bypass_proxy_open(req, timeout=15)
        except: time.sleep(5); continue
        j=json.loads(raw)
        msgs=j["hydra:member"] if isinstance(j, dict) and "hydra:member" in j else (j if isinstance(j,list) else [])
        for m in msgs:
            subj=str(m.get("subject") or "")
            intro=str(m.get("intro") or "")
            if "lovable" in (subj+" "+intro).lower():
                # fetch full
                mid=m.get("id")
                if mid:
                    freq=urllib.request.Request(f"{MAIL_TM_API}/messages/{mid}", headers={"Authorization": f"Bearer {token}"})
                    try:
                        fraw=_bypass_proxy_open(freq, timeout=15)
                        fj=json.loads(fraw)
                        body=json.dumps(fj, default=str)
                    except: body=subj+" "+intro
                else: body=subj+" "+intro
                mm=RESET_LINK_RE.search(body)
                if mm: return html.unescape(mm.group(0)).replace("&amp;","&")
        time.sleep(5)
    return None

# 22.do browser helpers — copied from lov-api.py TwoTwoDoInbox.create (adapted for ZenRows ctx)
async def _dismiss_22do_consent(pg):
    # GB IP triggers Google Funding Choices (fc-consent-root) overlay that intercepts clicks
    for _ in range(3):
        try:
            # try clicking Consent / Accept buttons if visible
            for sel in ['button:has-text("Consent")', 'button:has-text("Accept all")', 'button:has-text("I agree")', 'button:has-text("Agree")', 'button.fc-cta-consent', 'button[aria-label="Consent"]']:
                try:
                    btn = pg.locator(sel).first
                    if await btn.count() and await btn.is_visible(timeout=1000):
                        await btn.click(timeout=2000, force=True)
                        await pg.wait_for_timeout(1500)
                        print(f"  × dismissed consent via {sel}", flush=True)
                        break
                except: continue
            # JS removal of overlay that survives click
            await pg.evaluate("""() => {
                document.querySelectorAll('.fc-consent-root, .fc-dialog-overlay, div[aria-modal="true"]').forEach(e=>{
                    try{ e.remove(); }catch(_){}
                });
                document.body.style.overflow='auto';
                document.documentElement.style.overflow='auto';
            }""")
            # also Close ad if present
            try:
                close=pg.locator('button:has-text("Close ad")').first
                if await close.count() and await close.is_visible(timeout=1000):
                    await close.click(timeout=2000, force=True)
                    await pg.wait_for_timeout(800)
            except: pass
            # check if overlay gone
            cnt = await pg.locator('.fc-consent-root').count()
            if cnt==0: break
            await pg.wait_for_timeout(1000)
        except: break

async def create_22do_email(ctx, handler):
    name, handler_url, handler_domain = handler
    print(f"  22.do via {name} {handler_url} → {handler_domain}", flush=True)
    pg = await ctx.new_page()
    try:
        await pg.goto(handler_url, wait_until="domcontentloaded", timeout=60000)
        await pg.wait_for_timeout(3000)
        await _dismiss_22do_consent(pg)
        if handler_domain not in ("@gmail.com","@hotmail.com","@outlook.com"):
            try:
                choices=pg.locator(".choices__inner")
                if await choices.count():
                    await choices.click(timeout=5000)
                    await pg.wait_for_timeout(800)
                    item=pg.locator(f".choices__item--choice:has-text('{handler_domain}')").first
                    if not await item.count():
                        item=pg.locator(f".choices__list--dropdown .choices__item:has-text('{handler_domain}')").first
                    if await item.count():
                        await item.click(timeout=5000)
                        print(f"  → selected {handler_domain}", flush=True)
                    await pg.wait_for_timeout(800)
            except Exception as e:
                print(f"  domain select warn {e}", flush=True)
        # use force click + retry for overlay edge cases
        try:
            await pg.locator("#mail-random").click(timeout=5000, force=True)
        except:
            await pg.evaluate("() => document.querySelector('#mail-random')?.click()")
        await pg.wait_for_timeout(1200)
        if handler_domain=="@gmail.com":
            # ponytail: for @gmail on 22.do make it short with only one dot (helps Lovable disposable check)
            for _ in range(3):
                v=(await pg.locator("#mail-input").input_value()).strip()
                if v.lower().endswith(("@gmail.com","@googlemail.com")): break
                try: await pg.locator("#mail-random").click(timeout=3000, force=True)
                except: await pg.evaluate("() => document.querySelector('#mail-random')?.click()")
                await pg.wait_for_timeout(800)
            email=(await pg.locator("#mail-input").input_value()).strip()
            if "@" not in email:
                email=f"{email}{handler_domain}"
            # normalize: short + only one dot in local part
            if "@gmail.com" in email.lower():
                local, dom = email.split("@", 1)
                # keep only alnum, remove dots, make short (8-10 chars), insert one dot in middle
                clean = re.sub(r"[^a-z0-9]", "", local.lower())[:10]
                if len(clean) < 6:
                    clean = (clean + "test123")[:8]
                mid = len(clean)//2
                short_local = clean[:mid] + "." + clean[mid:]
                email = f"{short_local}@gmail.com"
                print(f"  → normalized Gmail to short one-dot {email}", flush=True)
        else:
            # read local and dom after random — tolerant to domain mismatch due to GB rotation
            raw_input=(await pg.locator("#mail-input").input_value(timeout=5000)).strip()
            if "@" in raw_input:
                email=raw_input
                try:
                    dom_check=await pg.locator(".choices__list--single .choices__item").first.inner_text(timeout=2000)
                    if dom_check.strip() not in email:
                        print(f"  ⚠️ input {email} vs dom {dom_check} mismatch — using input directly", flush=True)
                except: pass
            else:
                local=raw_input
                try:
                    dom=await pg.locator(".choices__list--single .choices__item").first.inner_text(timeout=2000)
                    dom=dom.strip()
                    print(f"  debug dom selected {dom} expected {handler_domain} local {local[:20]}", flush=True)
                    if dom and "@" in dom:
                        email=f"{local}{dom}"
                    else:
                        email=f"{local}{handler_domain}"
                    if handler_domain not in email:
                        print(f"  ⚠️ generated {email} != expected {handler_domain} — accepting anyway (GB rotation)", flush=True)
                except: email=f"{local}{handler_domain}"
        try: await pg.locator("#into-mailbox").click(timeout=5000, force=True)
        except: await pg.evaluate("() => document.querySelector('#into-mailbox')?.click()")
        await pg.wait_for_timeout(4000)
        email=email.strip()
        # final fallback: if no @, fetch via JS
        if "@" not in email:
            try:
                js_email=await pg.evaluate("() => document.querySelector('#mail-input')?.value || document.querySelector('.text-email')?.textContent")
                if js_email and "@" in js_email:
                    email=js_email.strip()
                    print(f"  ↻ recovered email via JS {email}", flush=True)
            except: pass
        print(f"  ✅ 22.do {email}", flush=True)
        return email
    finally:
        await pg.close()

async def poll_22do_link(ctx, email, timeout=180):
    pg=await ctx.new_page()
    await pg.goto(f"https://22.do/inbox/#/{email}", wait_until="domcontentloaded", timeout=60000)
    await pg.wait_for_timeout(3000)
    import time; deadline=time.time()+timeout
    try:
        while time.time()<deadline:
            await pg.reload(wait_until="domcontentloaded")
            await pg.wait_for_timeout(2000)
            rows=await pg.locator("#email-list-wrap .mail-item, #email-list-wrap tr, .inbox-item").all()
            for row in rows:
                try:
                    txt=await row.inner_text()
                    if "lovable" in txt.lower() or "verification" in txt.lower():
                        await row.click(timeout=5000)
                        await pg.wait_for_timeout(3000)
                        body=await pg.evaluate("() => document.body.innerHTML")
                        m=RESET_LINK_RE.search(body or "")
                        if m: return html.unescape(m.group(0)).replace("&amp;","&")
                        for frame in pg.frames:
                            try:
                                fhtml=await frame.content()
                                m2=RESET_LINK_RE.search(fhtml or "")
                                if m2: return html.unescape(m2.group(0)).replace("&amp;","&")
                            except: continue
                except: continue
            await asyncio.sleep(3)
    finally:
        await pg.close()
    return None

# dispose.lol browser helper — mirrors lov-api.py DisposeLolLovable
async def create_dispose_email(ctx):
    pg=await ctx.new_page()
    await pg.goto("https://dispose.lol", wait_until="domcontentloaded", timeout=60000)
    await pg.wait_for_timeout(5000)
    email_text=await pg.evaluate("""() => {
        const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT,null);
        let n; while(n=w.nextNode()){ const t=n.textContent.trim(); if(t.includes('@gmail.com')&&t.length<80) return t;}
        for(const i of document.querySelectorAll('input')) if(i.value.includes('@gmail.com')) return i.value;
        return null;}""")
    if not email_text or "@gmail.com" not in email_text:
        await pg.screenshot(path="/tmp/disposelol-error.png", full_page=True)
        await pg.close()
        raise RuntimeError("dispose.lol email not found")
    email=email_text.strip()
    print(f"  ✅ dispose.lol {email}", flush=True)
    # keep page open for polling — return page handle
    return email, pg

async def poll_dispose_link(pg, timeout=180):
    deadline=asyncio.get_running_loop().time()+timeout
    check=0
    def _dec(raw): return html.unescape(raw or "").replace("&amp;","&")
    while asyncio.get_running_loop().time()<deadline:
        check+=1
        await pg.reload(wait_until="domcontentloaded")
        await pg.wait_for_timeout(2000)
        buttons=await pg.locator('button[aria-label^="View "]').all()
        if check%5==1: print(f"  dispose poll #{check} {len(buttons)} msgs", flush=True)
        for btn in buttons:
            aria=await btn.get_attribute('aria-label') or ""
            if 'lovable' not in aria.lower(): continue
            print(f"  ✅ dispose found {aria[:80]}", flush=True)
            try:
                try: await btn.scroll_into_view_if_needed(timeout=2000)
                except: pass
                await btn.click(timeout=5000, force=True)
                await pg.wait_for_timeout(3000)
                for frame in pg.frames:
                    try:
                        fhtml=await frame.content()
                    except: continue
                    m=RESET_LINK_RE.search(fhtml or "")
                    if m: return _dec(m.group(0))
                body=await pg.evaluate("() => document.body.innerHTML.slice(0,60000)")
                m=RESET_LINK_RE.search(body or "")
                if m: return _dec(html.unescape(m.group(0)))
                txt=await pg.evaluate("() => document.body.innerText.slice(0,20000)")
                m2=RESET_LINK_RE.search(txt or "")
                if m2: return _dec(m2.group(0))
            except Exception as e:
                print(f"  dispose extract err {e}", flush=True)
                continue
        await asyncio.sleep(3)
    return None

async def poll_temptf_link(email, timeout=180):
    import time
    deadline=time.time()+timeout
    check=0
    while time.time()<deadline:
        check+=1
        try:
            resp=_temptf_get("/check", {"email": email})
            items=resp.get("data",[])
            if check%5==1: print(f"  temptf poll #{check} {len(items)} msgs", flush=True)
            for msg in items:
                body=msg.get("body","")
                subj=msg.get("subject","")
                m=RESET_LINK_RE.search(subj+" "+body)
                if m:
                    link=html.unescape(m.group(0)).replace("&amp;","&")
                    print(f"  🎯 temptf link {link[:120]}", flush=True)
                    return link
        except Exception as e:
            print(f"  temptf poll err {e}", flush=True)
        await asyncio.sleep(5)
    return None

async def one_run(run_idx, handler):
    name, url, domain, kind = handler
    print(f"\n=== Run {run_idx}/{len(ALL_HANDLERS)} [{kind}] {name} ===", flush=True)
    # --- fresh ZenRows browser = fresh IP ---
    from playwright.async_api import async_playwright
    email=None; mailtm_token=None; dispose_pg=None; ip="?"
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(ZENROWS_WSS, timeout=30000)
            ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
            # email generation per handler
            if kind=="22do":
                email = await create_22do_email(ctx, (name, url, domain))
            elif kind=="dispose":
                email, dispose_pg = await create_dispose_email(ctx)
            elif kind=="temptf":
                email = await create_temptf_email()
                print(f"  ✅ temp.tf {email}", flush=True)
            elif kind=="mailtm":
                email, _pw, mailtm_token = await create_mailtm_email()
                print(f"  ✅ mail.tm {email}", flush=True)
            else:
                raise RuntimeError(f"unknown kind {kind}")
            password = email + "K01"  # 8+ chars, deterministic
            # --- fresh page for Lovable + IP log ---
            page = await ctx.new_page()
            try:
                ip = await page.evaluate("async () => { try{ const r=await fetch('https://wtfismyip.com/json'); const j=await r.json(); return j.YourFuckingIPAddress+' '+j.YourFuckingISP }catch(e){ return 'fail' } }")
            except: pass
            print(f"Run {run_idx} IP {ip} email {email}", flush=True)

            for attempt in range(3):
                try:
                    await page.goto("https://lovable.dev/signup", timeout=40000, wait_until="domcontentloaded")
                    break
                except Exception as e:
                    print(f"Run {run_idx} goto retry {attempt} {e}", flush=True)
                    await page.wait_for_timeout(2000)
            else:
                print(f"Run {run_idx} goto failed", flush=True)
                await browser.close()
                return {"run":run_idx,"handler":name,"kind":kind,"email":email,"ip":ip,"success":False,"reason":"goto failed"}

            await page.wait_for_timeout(4000)
            # dismiss Lovable cookie banner (GB shows "We use cookies..." overlay)
            try:
                for sel in ['button:has-text("Accept all")','button:has-text("Reject all")','button:has-text("Accept All")']:
                    btn=page.locator(sel).first
                    if await btn.count() and await btn.is_visible(timeout=1500):
                        await btn.click(timeout=2000, force=True)
                        print(f"Run {run_idx} dismissed lovable cookie via {sel}", flush=True)
                        await page.wait_for_timeout(1000)
                        break
                # JS removal of any overlay
                await page.evaluate("""() => {
                    document.querySelectorAll('[aria-modal="true"], div[data-radix-portal]').forEach(e=>{
                        try{
                            const t=e.innerText || '';
                            if(t.includes('cookies')||t.includes('Privacy Policy')) e.remove();
                        }catch(_){}
                    });
                }""")
            except Exception as e:
                print(f"Run {run_idx} cookie dismiss warn {e}", flush=True)
            # fill email
            try:
                await page.locator('input#email').wait_for(timeout=10000)
                await page.locator('input#email').fill(email)
                await page.locator('[data-testid="auth-submit-button"]').click()
                await page.wait_for_timeout(5000)
                # check for immediate block after email submit (disposable detection)
                txt_after_email = await page.evaluate("() => document.body.innerText.slice(0,4000)")
                if "Unable to complete registration" in txt_after_email:
                    print(f"Run {run_idx} BLOCKED disposable {txt_after_email[:200]!r}", flush=True)
                    await page.screenshot(path=f"/tmp/zen5_run{run_idx}_blocked.png", full_page=True)
                    await browser.close()
                    if dispose_pg:
                        try: await dispose_pg.close()
                        except: pass
                    return {"run":run_idx,"handler":name,"kind":kind,"email":email,"ip":ip,"success":False,"reason":"blocked disposable (Unable to complete registration)"}
                if "already" in txt_after_email.lower() and "registered" in txt_after_email.lower():
                    print(f"Run {run_idx} blocked already registered", flush=True)
                    await browser.close()
                    return {"run":run_idx,"handler":name,"kind":kind,"email":email,"ip":ip,"success":False,"reason":"blocked already registered"}
                await page.locator('input#password').wait_for(timeout=10000)
                await page.locator('input#password').fill(password)
                print(f"Run {run_idx} fill ok", flush=True)
            except Exception as e:
                # capture body text for debugging
                try:
                    txt_dbg = await page.evaluate("() => document.body.innerText.slice(0,1000)")
                    print(f"Run {run_idx} fill debug txt {txt_dbg[:400]!r}", flush=True)
                except: pass
                print(f"Run {run_idx} fill failed {e}", flush=True)
                await page.screenshot(path=f"/tmp/zen5_run{run_idx}_fillfail.png", full_page=True)
                await browser.close()
                if dispose_pg:
                    try: await dispose_pg.close()
                    except: pass
                # classify disposable if present
                try:
                    if "Unable" in txt_dbg:
                        return {"run":run_idx,"handler":name,"kind":kind,"email":email,"ip":ip,"success":False,"reason":"blocked disposable (Unable)"}
                except: pass
                return {"run":run_idx,"handler":name,"kind":kind,"email":email,"ip":ip,"success":False,"reason":f"fill failed {e}"}

            for i in range(12):
                token = await page.evaluate("() => document.querySelector('input[name=\"cf-turnstile-response\"]')?.value?.length || 0")
                if token>100:
                    print(f"Run {run_idx} Token {token} i {i}", flush=True)
                    break
                if i==2:
                    await page.evaluate("() => { try{ window.turnstile && window.turnstile.execute && window.turnstile.execute(); }catch(e){} }")
                await page.wait_for_timeout(1000)
            else:
                print(f"Run {run_idx} no turnstile token", flush=True)

            btn = page.locator('[data-testid="auth-submit-button"]')
            disabled = await btn.is_disabled()
            print(f"Run {run_idx} Create disabled {disabled}", flush=True)
            await page.screenshot(path=f"/tmp/zen5_run{run_idx}_before.png", full_page=True)
            if disabled:
                await page.screenshot(path=f"/tmp/zen5_run{run_idx}_after.png", full_page=True)
                await browser.close()
                if dispose_pg:
                    try: await dispose_pg.close()
                    except: pass
                return {"run":run_idx,"handler":name,"kind":kind,"email":email,"ip":ip,"success":False,"reason":"turnstile/button disabled"}

            await btn.click()
            await page.wait_for_timeout(8000)
            txt = await page.evaluate("() => document.body.innerText.slice(0,3000)")
            url_now = page.url
            print(f"Run {run_idx} URL {url_now}", flush=True)
            await page.screenshot(path=f"/tmp/zen5_run{run_idx}_after.png", full_page=True)

            if "Check your inbox" in txt:
                print(f"Run {run_idx} SUCCESS — polling inbox", flush=True)
                link=None
                try:
                    if kind=="temptf":
                        link = await poll_temptf_link(email, timeout=120)
                    elif kind=="mailtm":
                        link = await asyncio.to_thread(poll_mailtm_sync, mailtm_token, 120)
                    elif kind=="22do":
                        link = await poll_22do_link(ctx, email, timeout=120)
                    elif kind=="dispose":
                        # reuse dispose_pg (same browser ctx)
                        link = await poll_dispose_link(dispose_pg, timeout=120)
                except Exception as e:
                    print(f"Run {run_idx} poll err {e}", flush=True)
                if link:
                    print(f"Run {run_idx} LINK {link[:300]}", flush=True)
                    try:
                        await page.goto(link, timeout=20000)
                        await page.wait_for_timeout(4000)
                        print(f"Run {run_idx} Verified {page.url}", flush=True)
                    except Exception as e:
                        print(f"Run {run_idx} verify goto err {e}", flush=True)
                    with open(f"/tmp/zen5_run{run_idx}_account.txt","w") as f:
                        f.write(f"{email}\n{password}\n{link}\n{ip}\n{kind} {name}\n")
                    await browser.close()
                    return {"run":run_idx,"handler":name,"kind":kind,"email":email,"ip":ip,"success":True,"link":link}
                else:
                    print(f"Run {run_idx} no verification link", flush=True)
                    with open(f"/tmp/zen5_run{run_idx}_account.txt","w") as f:
                        f.write(f"{email}\n{password}\nNO_LINK\n{ip}\n{kind} {name}\n")
                    await browser.close()
                    return {"run":run_idx,"handler":name,"kind":kind,"email":email,"ip":ip,"success":True,"reason":"no link (signup ok)"}
            elif "suspicious" in txt.lower():
                print(f"Run {run_idx} BLOCKED suspicious", flush=True)
                await browser.close()
                return {"run":run_idx,"handler":name,"kind":kind,"email":email,"ip":ip,"success":False,"reason":"blocked suspicious"}
            else:
                print(f"Run {run_idx} unknown {txt[:500]!r}", flush=True)
                await browser.close()
                return {"run":run_idx,"handler":name,"kind":kind,"email":email,"ip":ip,"success":False,"reason":txt[:300]}

            await browser.close()
            return {"run":run_idx,"handler":name,"kind":kind,"email":email,"ip":ip,"success":False,"reason":"unknown"}
    except Exception as e:
        print(f"Run {run_idx} exception {e}", flush=True)
        import traceback; traceback.print_exc()
        return {"run":run_idx,"handler":name,"kind":kind,"email":email or "?","ip":ip,"success":False,"reason":str(e)}
    finally:
        if dispose_pg:
            try: await dispose_pg.close()
            except: pass

async def main():
    import argparse
    ap=argparse.ArgumentParser(description="Lov ZenRows rotate handlers with fresh IP each run")
    ap.add_argument("--runs", type=int, default=len(ALL_HANDLERS), help="how many runs (default all handlers)")
    args=ap.parse_args()
    total = args.runs  # ponytail: 0 => dry listing
    print(f"Handlers: {len(ALL_HANDLERS)} (10×22.do + dispose + temptf + mailtm), will run {total}", flush=True)
    for n,u,d,k in ALL_HANDLERS:
        print(f"  - {k:7} {n:28} {u}", flush=True)
    results=[]
    for i in range(1, total+1):
        handler = ALL_HANDLERS[(i-1) % len(ALL_HANDLERS)]
        res = await one_run(i, handler)
        results.append(res)
        print(f"Run {i} result {res}", flush=True)
        await asyncio.sleep(1)
    print("\n=== SUMMARY ===", flush=True)
    for r in results:
        status="✅ SUCCESS" if r.get("success") else "❌ FAIL"
        print(f"{status} run {r['run']:2} {r['kind']:7} {r['handler']:28} {r['email']:40} IP {r['ip']} {r.get('reason','')[:60]}", flush=True)
    ok=sum(1 for r in results if r.get("success"))
    print(f"\n{ok}/{len(results)} succeeded", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
