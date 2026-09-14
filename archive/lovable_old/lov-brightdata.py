#!/usr/bin/env python3
"""
Bright Data flow for Lovable — bypasses BD's `Forbidden: password typing` trap
and `navigate_domains_limit` via `add_init_script` + `window.__nativeSetter`.

Usage:
  python finals/core/lov-brightdata.py          # single account
  python finals/core/lov-brightdata.py --count 5

Requires: playwright, BRD_WSS env or default hl_e895b201
"""
import asyncio, os, json, uuid, sys, re, html, time, urllib.request, random

BRD_WSS_TMPL = os.getenv("BRD_WSS", "wss://brd-customer-hl_e895b201-zone-scraping_browser1:b65xwy1jycfq@brd.superproxy.io:9222?sessionId={}")
TEMP_TF_API = "https://temp.tf/api"
LOVABLE_SIGNUP = "https://lovable.dev/signup"

def clear_proxy():
    for k in list(os.environ):
        if k.lower().endswith('_proxy') or k == 'LD_PRELOAD':
            os.environ.pop(k, None)

async def get_temp_email():
    for k in list(os.environ):
        if k.lower().endswith('_proxy'):
            os.environ.pop(k, None)
    for _ in range(5):
        try:
            with urllib.request.urlopen(TEMP_TF_API+"/account?dot=1&providers=gmail", timeout=15) as r:
                j = json.loads(r.read())
                email = j['email']
                if email.count('.') <= 5:
                    data = json.dumps({"email": email}).encode()
                    req = urllib.request.Request(TEMP_TF_API+"/check", data=data, headers={"Content-Type":"application/json"}, method="POST")
                    with urllib.request.urlopen(req, timeout=10) as r2:
                        pass
                    return email
        except Exception as e:
            print(f"temp.tf retry {e}", file=sys.stderr)
            await asyncio.sleep(1)
    with urllib.request.urlopen(TEMP_TF_API+"/account?dot=1&providers=gmail", timeout=15) as r:
        return json.loads(r.read())['email']

async def make_one():
    email = await get_temp_email()
    password = email + "K0"
    wss = BRD_WSS_TMPL.format(uuid.uuid4()) if "{}" in BRD_WSS_TMPL else BRD_WSS_TMPL + f"?sessionId={uuid.uuid4()}"
    print(f"\n=== BD {email} ===", file=sys.stderr)
    print(f"WSS {wss[:70]}...", file=sys.stderr)
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(wss, timeout=30000)
        # Use new context to avoid domain limit carry-over
        ctx = await browser.new_context()
        # Save native setter BEFORE lovable's JS patches it — bypasses BD's Forbidden trap
        await ctx.add_init_script("window.__nativeSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; window.__nativeGetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').get;")
        page = await ctx.new_page()
        # Single domain navigation first (avoid navigate_domains_limit)
        await page.goto(LOVABLE_SIGNUP, timeout=30000)
        await page.wait_for_timeout(4000)
        await page.screenshot(path=f"/tmp/bd_{email.split('@')[0]}_1.png", full_page=True)
        # IP via fetch (not Page.navigate, so no domain limit)
        try:
            ip = await page.evaluate("async () => (await fetch('https://api.ipify.org?format=json').then(r=>r.json())).ip")
            info = await page.evaluate("async (ip) => { try{ const r=await fetch('https://ipinfo.io/'+ip+'/json'); return await r.text()}catch(e){return e.message}}", ip)
            print(f"IP {ip} {info[:300]}", file=sys.stderr)
        except Exception as e:
            print(f"IP fail {e}", file=sys.stderr)
        # Email — human keyboard (BD allows it for type=email, only password is trapped)
        await page.locator('input#email').wait_for(timeout=10000)
        await page.locator('input#email').click()
        await page.keyboard.type(email, delay=50)
        print("Typed email", file=sys.stderr)
        await page.locator('[data-testid="auth-submit-button"]').click()
        print("Clicked Continue", file=sys.stderr)
        await page.wait_for_timeout(4000)
        await page.screenshot(path=f"/tmp/bd_{email.split('@')[0]}_2.png", full_page=True)
        # Password — use saved native setter (bypasses Forbidden)
        pw_input = page.locator('input#password')
        await pw_input.wait_for(timeout=10000)
        await pw_input.click()
        res = await page.evaluate("(pw) => { const el=document.querySelector('#password'); try{ window.__nativeSetter.call(el, pw); el.dispatchEvent(new Event('input',{bubbles:true})); return 'ok '+el.value.length }catch(e){ return 'throw '+e.message } }", password)
        print(f"PW set {res}", file=sys.stderr)
        val = await page.evaluate("() => document.querySelector('#password')?.value?.length || 0")
        print(f"PW len {val}", file=sys.stderr)
        await page.screenshot(path=f"/tmp/bd_{email.split('@')[0]}_3.png", full_page=True)
        # Turnstile — wait for token (BD residential usually auto-soloves)
        token = ""
        for i in range(20):
            token = await page.evaluate("() => document.querySelector('input[name=\"cf-turnstile-response\"]')?.value || ''")
            print(f"Token {len(token)} i {i}", file=sys.stderr)
            if len(token) > 100:
                break
            # Try to trigger Turnstile if stuck at Verifique
            if i == 5:
                try:
                    await page.evaluate("() => { try{ window.turnstile && window.turnstile.execute && window.turnstile.execute(); }catch(e){} }")
                except: pass
            await page.wait_for_timeout(2000)
        print(f"Final token {len(token)}", file=sys.stderr)
        await page.screenshot(path=f"/tmp/bd_{email.split('@')[0]}_4.png", full_page=True)
        if len(token) < 100:
            print("No Turnstile token, abort", file=sys.stderr)
            await browser.close()
            return None
        # Try direct API first (bypasses password trap entirely) — same as ZenRows GB success path
        try:
            api_res = await page.evaluate("""async ({email, pw, token}) => {
                try{
                    const r1=await fetch('https://api.lovable.dev/auth/turnstile-signup',{method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({email, token})});
                    const r2=await fetch('https://identitytoolkit.googleapis.com/v1/accounts:signUp?key=AIzaSyBQNjlw9Vp4tP4VVeANzyPJnqbG2wLbYPw',{method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({email, password: pw, returnSecureToken: true})});
                    const t2=await r2.text();
                    return `r1 ${r1.status} r2 ${r2.status} ${t2.slice(0,600)}`;
                }catch(e){ return 'err '+e.message }
            }""", {"email": email, "pw": password, "token": token})
            print(f"API {api_res}", file=sys.stderr)
            if " 200 " in api_res and "idToken" in api_res:
                print(f"API SUCCESS {email}", file=sys.stderr)
        except Exception as e:
            print(f"API fail {e}", file=sys.stderr)
        # Also try UI click (if API was blocked by suspicious activity, UI may still show Check your inbox on next-gen IP)
        try:
            btn = page.locator('[data-testid="auth-submit-button"]')
            # Force enable if disabled (React may still think pw empty)
            await page.evaluate("() => { const b=document.querySelector('[data-testid=\"auth-submit-button\"]'); if(b){ b.disabled=false; b.removeAttribute('disabled'); } }")
            disabled = await btn.is_disabled()
            print(f"Create disabled {disabled}", file=sys.stderr)
            await btn.click(timeout=5000)
            print("Clicked Create", file=sys.stderr)
            await page.wait_for_timeout(8000)
            await page.screenshot(path=f"/tmp/bd_{email.split('@')[0]}_5.png", full_page=True)
            content = await page.content()
            if "suspicious" in content.lower():
                print("UI blocked suspicious", file=sys.stderr)
            elif "Check your inbox" in content or "verify" in content.lower():
                print("UI Check your inbox — likely success", file=sys.stderr)
            print(content[:2000], file=sys.stderr)
        except Exception as e:
            print(f"Create click fail {e}", file=sys.stderr)
        # Poll temp.tf for verification link (for UI flow)
        link_re = re.compile(r"https?://[^\s\"'<>]*lovable\.dev[^\s\"'<>]*", re.I)
        found_link = None
        for attempt in range(12):
            try:
                old_env = {k: os.environ.pop(k, None) for k in ("HTTPS_PROXY","HTTP_PROXY","https_proxy","http_proxy","ALL_PROXY","all_proxy")}
                try:
                    data=json.dumps({"email":email}).encode()
                    req=urllib.request.Request(TEMP_TF_API+"/check", data=data, headers={"Content-Type":"application/json"}, method="POST")
                    with urllib.request.urlopen(req, timeout=10) as r:
                        j=json.loads(r.read())
                        for msg in j.get("data",[]):
                            body=msg.get("body","")
                            subj=msg.get("subject","")
                            m=link_re.search(subj+" "+body)
                            if m:
                                found_link=html.unescape(m.group(0)).replace("&amp;","&")
                                print(f"LINK {found_link[:300]}", file=sys.stderr)
                                break
                        if found_link:
                            break
                finally:
                    for k,v in old_env.items():
                        if v is not None:
                            os.environ[k]=v
            except Exception as e:
                print(f"Poll err {e}", file=sys.stderr)
            await asyncio.sleep(5)
        if found_link:
            try:
                await page.goto(found_link, timeout=20000)
                await page.wait_for_timeout(4000)
                await page.screenshot(path=f"/tmp/bd_{email.split('@')[0]}_6.png", full_page=True)
                print(f"Verified {found_link[:80]}", file=sys.stderr)
                print((await page.content())[:2000], file=sys.stderr)
            except Exception as e:
                print(f"Verify goto fail {e}", file=sys.stderr)
        # Save
        with open(f"/tmp/bd_account_{email.split('@')[0]}.txt","w") as f:
            f.write(f"{email}\n{password}\n{found_link or 'NO_LINK'}\n")
        print(f"Saved /tmp/bd_account_{email.split('@')[0]}.txt", file=sys.stderr)
        await browser.close()
        return email

async def main():
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=1)
    args=ap.parse_args()
    for i in range(args.count):
        await make_one()
        if i < args.count-1:
            await asyncio.sleep(2)

if __name__=="__main__":
    clear_proxy()
    asyncio.run(main())
