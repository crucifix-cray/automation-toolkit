#!/usr/bin/env python3
import asyncio, os, json, uuid, sys, re, html, time, urllib.request, random, string
for k in list(os.environ):
    if k.lower().endswith('_proxy') or k=='LD_PRELOAD':
        os.environ.pop(k,None)
os.environ['LD_PRELOAD']=""
os.environ['NO_PROXY']="*"
os.environ['no_proxy']="*"
ZENROWS_WSS = "wss://browser.zenrows.com?apikey=a71406ecf7cfd8ae0aec54b2d1bf11aa92c917e7&proxy_country=gb"
def get_duckspam_email():
    prefix = ''.join(random.choices(string.ascii_lowercase, k=12))
    email = f"{prefix}@duckspam.com"
    print(f"DuckSpam {email}", file=sys.stderr)
    return email
async def make_one():
    email = get_duckspam_email()
    password = "TestPass123!"
    print(f"\n=== BrightData Raw {email} ===", file=sys.stderr)
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.connect_over_cdp(ZENROWS_WSS, timeout=30000)
            print(f"Connected ZenRows", file=sys.stderr)
            ctx = await browser.new_context()
        except Exception as e:
            print(f"ZenRows fail {e}, fallback to local raw", file=sys.stderr)
            browser = await pw.chromium.launch(channel='chrome', headless=False, args=['--no-sandbox'])
            ctx = await browser.new_context()
        page = await ctx.new_page()
        try:
            await page.goto("https://www.duckspam.com", timeout=20000)
            await page.wait_for_timeout(2000)
            print("DuckSpam loaded", file=sys.stderr)
        except: pass
        await page.goto("https://brightdata.com/cp/signup", timeout=30000)
        await page.wait_for_timeout(4000)
        try:
            cb = page.locator('button:has-text("Accept all"), button:has-text("Accept")')
            if await cb.count() > 0:
                await cb.first.click(timeout=3000)
                print("Dismissed cookie", file=sys.stderr)
                await page.wait_for_timeout(1000)
        except: pass
        try:
            await page.screenshot(path=f"/tmp/bd_raw_{email.split('@')[0]}_1.png", timeout=10000)
        except: pass
        print(f"Screenshot 1", file=sys.stderr)
        try:
            email_input = page.locator('input[name="email"]')
            await email_input.wait_for(timeout=15000)
            await email_input.fill(email)
            print("Filled email", file=sys.stderr)
            btn = page.locator('input.hs-button[value="Create Account"]')
            for i in range(10):
                cls = await btn.get_attribute("class") or ""
                print(f"Button class {cls}", file=sys.stderr)
                if "disabled" not in cls:
                    break
                await page.wait_for_timeout(1000)
            await btn.click(timeout=8000, force=True)
            print("Clicked Create", file=sys.stderr)
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except: pass
            await page.wait_for_timeout(5000)
            try:
                await page.screenshot(path=f"/tmp/bd_raw_{email.split('@')[0]}_2.png", timeout=10000)
            except: pass
            print(f"After Create URL {page.url}", file=sys.stderr)
            # Handle HubSpot redirect
            if "?hs_signup=1" in page.url:
                print("HubSpot redirect detected, waiting for CP password page", file=sys.stderr)
                # The CP password page may be at https://brightdata.com/cp/signup with password fields
                # Try to wait for password input
                for _ in range(5):
                    if await page.locator('input[type="password"]').count() > 0:
                        break
                    await page.wait_for_timeout(2000)
                    print(f"Waiting for PW at {page.url}, count {await page.locator('input[type=\"password\"]').count()}", file=sys.stderr)
                # If still not found, try to navigate to CP directly
                if await page.locator('input[type="password"]').count() == 0:
                    print("No PW, try direct CP", file=sys.stderr)
                    await page.goto("https://brightdata.com/cp/signup", timeout=30000)
                    await page.wait_for_timeout(4000)
            # Wait for password with polling
            pw_input = None
            for _ in range(10):
                pw_input = page.locator('input[type="password"]').first
                if await pw_input.count() > 0:
                    break
                alt = page.locator('input[placeholder*="Password"]')
                if await alt.count() > 0:
                    pw_input = alt.first
                    break
                print(f"Waiting for PW, URL {page.url}", file=sys.stderr)
                await page.wait_for_timeout(2000)
            cnt = await pw_input.count() if pw_input else 0
            print(f"PW count {cnt}", file=sys.stderr)
            if cnt > 0:
                await pw_input.wait_for(timeout=8000)
                await pw_input.fill(password)
                print("Filled password", file=sys.stderr)
                pw2 = page.locator('input[type="password"]').nth(1)
                if await pw2.count() > 0:
                    await pw2.fill(password)
                    print("Filled confirm", file=sys.stderr)
                try:
                    await page.locator('input.hs-button[value="Sign up"], input[value="Sign up"]').first.click(timeout=8000, force=True)
                except:
                    await page.get_by_role("button", name="Sign up").click(timeout=8000, force=True)
                print("Clicked Sign up", file=sys.stderr)
                await page.wait_for_timeout(5000)
                try:
                    await page.screenshot(path=f"/tmp/bd_raw_{email.split('@')[0]}_3.png", timeout=10000)
                except: pass
                otp_input = page.locator('input[maxlength="1"]')
                if await otp_input.count() > 0:
                    print("OTP page", file=sys.stderr)
                    otp = ""
                    for i in range(12):
                        try:
                            otp = await page.evaluate("""async (email) => {
                                try{
                                    const r=await fetch('https://www.duckspam.com/app/inbox/'+email);
                                    const t=await r.text();
                                    const m=t.match(/[A-Za-z0-9]{6}/);
                                    return m ? m[0] : '';
                                }catch(e){ return '' }
                            }""", email)
                            print(f"OTP try {i} {otp[:20]}", file=sys.stderr)
                            if otp and len(otp)==6:
                                break
                        except: pass
                        await page.wait_for_timeout(5000)
                    if otp and len(otp)==6:
                        print(f"Found OTP {otp}", file=sys.stderr)
                        for idx, ch in enumerate(otp):
                            try:
                                await page.locator(f'input[data-testid="otp_input-{idx}"]').fill(ch)
                            except:
                                await page.locator('input[maxlength="1"]').nth(idx).fill(ch)
                        print("Filled OTP", file=sys.stderr)
                        await page.wait_for_timeout(5000)
                        try:
                            await page.screenshot(path=f"/tmp/bd_raw_{email.split('@')[0]}_4.png", timeout=10000)
                        except: pass
                        content = await page.content()
                        if "Free tier" in content or "5,000" in content:
                            print(f"SUCCESS {email}", file=sys.stderr)
                            with open(f"/tmp/bd_raw_account_{email.split('@')[0]}.txt","w") as f:
                                f.write(f"{email}\n{password}\n")
                            await browser.close()
                            return True
                    print("No OTP", file=sys.stderr)
                else:
                    print("No OTP input", file=sys.stderr)
                    print((await page.content())[:2000], file=sys.stderr)
            else:
                print("No password input", file=sys.stderr)
                print((await page.content())[:2000], file=sys.stderr)
        except Exception as e:
            print(f"Flow fail {e}", file=sys.stderr)
            import traceback; traceback.print_exc()
            try:
                await page.screenshot(path=f"/tmp/bd_raw_fail_{email.split('@')[0]}.png", timeout=10000)
            except: pass
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
