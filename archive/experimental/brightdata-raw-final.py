#!/usr/bin/env python3
import asyncio, os, random, string, sys
for k in list(os.environ):
    if k.lower().endswith('_proxy') or k=='LD_PRELOAD':
        os.environ.pop(k,None)
os.environ['LD_PRELOAD']=""
os.environ['NO_PROXY']="*"
os.environ['no_proxy']="*"
def get_duckspam():
    return ''.join(random.choices(string.ascii_lowercase, k=12)) + "@duckspam.com"
async def make_one():
    email=get_duckspam()
    password="TestPass123!"
    print(f"\n=== {email} ===", file=sys.stderr)
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(channel='chrome', headless=False, args=['--no-sandbox'])
        ctx=await browser.new_context()
        page=await ctx.new_page()
        await page.goto("https://brightdata.com/cp/signup", timeout=30000, wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)
        try:
            cb=page.locator('#brd_cookies_bar_accept')
            if await cb.count()>0:
                await cb.click(timeout=3000)
                await page.wait_for_timeout(1000)
        except: pass
        # Fill HubSpot email
        email_input=page.locator('input[name="email"]')
        await email_input.wait_for(timeout=10000)
        await email_input.fill(email)
        print("Filled email", file=sys.stderr)
        btn=page.locator('input.hs-button[value="Create Account"]')
        for i in range(5):
            cls=await btn.get_attribute("class") or ""
            if "disabled" not in cls:
                break
            await page.wait_for_timeout(1000)
        await btn.click(timeout=8000, force=True)
        print("Clicked Create", file=sys.stderr)
        await page.wait_for_timeout(8000)
        print(f"After URL {page.url}", file=sys.stderr)
        # Wait for password
        pw_input=page.locator('input#password').first
        for _ in range(10):
            if await pw_input.count()>0:
                break
            await page.wait_for_timeout(2000)
        print(f"PW count {await pw_input.count()}", file=sys.stderr)
        if await pw_input.count()>0:
            await pw_input.fill(password)
            print("Filled pw", file=sys.stderr)
            pw2=page.locator('input#password_confirm')
            if await pw2.count()>0:
                await pw2.fill(password)
                print("Filled confirm", file=sys.stderr)
            await page.wait_for_timeout(2000)
            # Turnstile
            for i in range(10):
                token=await page.evaluate("() => document.querySelector('input[name=\"cf-turnstile-response\"]')?.value?.length || 0")
                print(f"Token {token} i {i}", file=sys.stderr)
                if token>100:
                    break
                await page.wait_for_timeout(2000)
            # Click Sign up
            try:
                await page.locator('button:has-text("Sign up")').click(timeout=8000, force=True)
            except:
                await page.locator('input[value="Sign up"]').click(timeout=8000, force=True)
            print("Clicked Sign up", file=sys.stderr)
            await page.wait_for_timeout(6000)
            content=await page.content()
            print(content[:2000], file=sys.stderr)
            if "Free tier" in content or "5,000" in content:
                print(f"SUCCESS {email}", file=sys.stderr)
                await browser.close()
                return True
        print("No PW", file=sys.stderr)
        await browser.close()
        return False
async def main():
    for i in range(3):
        ok=await make_one()
        print(f"Attempt {i} {'SUCCESS' if ok else 'FAIL'}", file=sys.stderr)
        if ok:
            break
asyncio.run(main())
