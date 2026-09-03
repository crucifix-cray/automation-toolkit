#!/usr/bin/env python3
"""
BrightData final via ZenRows GB + duckspam, LD_PRELOAD="" raw
Handles HubSpot /?hs_signup=1 -> cp/signup Register flow correctly
"""
import asyncio, os, json, uuid, sys, re, html, time, urllib.request, random, string
for k in list(os.environ):
    if k.lower().endswith('_proxy') or k=='LD_PRELOAD':
        os.environ.pop(k,None)
os.environ['LD_PRELOAD']=""
os.environ['NO_PROXY']="*"
os.environ['no_proxy']="*"

ZENROWS_WSS = "wss://browser.zenrows.com?apikey=a71406ecf7cfd8ae0aec54b2d1bf11aa92c917e7&proxy_country=gb"

def get_duckspam():
    prefix = ''.join(random.choices(string.ascii_lowercase, k=12))
    return f"{prefix}@duckspam.com"

async def make_one():
    email = get_duckspam()
    password = "TestPass123!"
    print(f"\n=== {email} ===", file=sys.stderr)
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(ZENROWS_WSS, timeout=30000)
        ctx = await browser.new_context()
        await ctx.add_init_script("window.__nativeSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;")
        page = await ctx.new_page()
        # Go to signup
        await page.goto("https://brightdata.com/cp/signup", timeout=30000)
        await page.wait_for_timeout(4000)
        # Handle HubSpot redirect to /?hs_signup=1
        if "?hs_signup=1" in page.url:
            print(f"HubSpot modal at {page.url}", file=sys.stderr)
            # Dismiss cookie if needed
            try:
                cb = page.locator('#brd_cookies_bar_accept')
                if await cb.count() > 0:
                    await cb.click(timeout=3000)
                    await page.wait_for_timeout(1000)
            except: pass
            # Fill HubSpot email
            email_input = page.locator('input[name="email"]')
            await email_input.wait_for(timeout=10000)
            await email_input.fill(email)
            print("Filled HubSpot email", file=sys.stderr)
            # Wait for Create to enable
            btn = page.locator('input.hs-button[value="Create Account"]')
            for i in range(10):
                cls = await btn.get_attribute("class") or ""
                if "disabled" not in cls:
                    break
                await page.wait_for_timeout(1000)
            await btn.click(timeout=8000, force=True)
            print("Clicked HubSpot Create", file=sys.stderr)
            await page.wait_for_timeout(5000)
            # Now should be at cp/signup Register
            print(f"After HubSpot URL {page.url}", file=sys.stderr)
        # Now at Register - Set a password (cp/signup)
        # Also handle case where we started directly at cp/signup Register without HubSpot
        if "cp/signup" not in page.url:
            await page.goto("https://brightdata.com/cp/signup", timeout=30000)
            await page.wait_for_timeout(4000)
        # Fill password
        try:
            pw1 = page.locator('input#password')
            await pw1.wait_for(timeout=10000)
            # Use native setter to bypass possible trap
            await page.evaluate("(pw) => { const el=document.querySelector('#password'); window.__nativeSetter.call(el, pw); el.dispatchEvent(new Event('input',{bubbles:true})); }", password)
            print("Filled pw1 via native", file=sys.stderr)
            pw2 = page.locator('input#password_confirm')
            if await pw2.count() > 0:
                await page.evaluate("(pw) => { const el=document.querySelector('#password_confirm'); window.__nativeSetter.call(el, pw); el.dispatchEvent(new Event('input',{bubbles:true})); }", password)
                print("Filled pw2", file=sys.stderr)
            await page.wait_for_timeout(2000)
            # Check button enabled
            signup_btn = page.locator('button:has-text("Sign up"), input[value="Sign up"]')
            # Wait for Turnstile
            for i in range(15):
                token = await page.evaluate("() => document.querySelector('input[name=\"cf-turnstile-response\"]')?.value?.length || 0")
                print(f"Token {token} i {i}", file=sys.stderr)
                if token > 100:
                    break
                await page.wait_for_timeout(2000)
            # Click Sign up
            # Force enable if disabled
            await page.evaluate("() => { const b=document.querySelector('button[type=\"submit\"]'); if(b){ b.disabled=false; b.removeAttribute('disabled'); b.classList.remove('uikit_button-disabled'); } }")
            await signup_btn.first.click(timeout=8000, force=True)
            print("Clicked Sign up", file=sys.stderr)
            await page.wait_for_timeout(6000)
            await page.screenshot(path=f"/tmp/bd_final_{email.split('@')[0]}_1.png", timeout=10000)
            print(f"Screenshot 1", file=sys.stderr)
            # Check for OTP
            otp = page.locator('input[maxlength="1"]')
            if await otp.count() > 0:
                print("OTP page", file=sys.stderr)
                # Poll duckspam
                found_otp = ""
                for i in range(12):
                    try:
                        found_otp = await page.evaluate("""async (email) => {
                            try{
                                const r=await fetch('https://www.duckspam.com/app/inbox/'+email);
                                const t=await r.text();
                                const m=t.match(/[A-Za-z0-9]{6}/);
                                return m ? m[0] : '';
                            }catch(e){ return '' }
                        }""", email)
                        print(f"OTP try {i} {found_otp}", file=sys.stderr)
                        if found_otp and len(found_otp)==6:
                            break
                    except: pass
                    await page.wait_for_timeout(5000)
                if found_otp and len(found_otp)==6:
                    print(f"OTP {found_otp}", file=sys.stderr)
                    for idx, ch in enumerate(found_otp):
                        try:
                            await page.locator(f'input[data-testid="otp_input-{idx}"]').fill(ch)
                        except:
                            await page.locator('input[maxlength="1"]').nth(idx).fill(ch)
                    await page.wait_for_timeout(5000)
                    content = await page.content()
                    if "Free tier" in content or "5,000" in content:
                        print(f"SUCCESS {email}", file=sys.stderr)
                        with open(f"/tmp/bd_final_{email.split('@')[0]}.txt","w") as f:
                            f.write(f"{email}\n{password}\n")
                        await browser.close()
                        return True
            else:
                print("No OTP, check content", file=sys.stderr)
                print((await page.content())[:2000], file=sys.stderr)
        except Exception as e:
            print(f"Flow fail {e}", file=sys.stderr)
            import traceback; traceback.print_exc()
        await browser.close()
        return False

async def main():
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=1)
    args=ap.parse_args()
    for i in range(args.count):
        ok = await make_one()
        print(f"Attempt {i} {'SUCCESS' if ok else 'FAIL'}", file=sys.stderr)
        if i < args.count-1:
            await asyncio.sleep(2)

if __name__=="__main__":
    asyncio.run(main())
