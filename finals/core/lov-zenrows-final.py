#!/usr/bin/env python3
"""Lovable account creation via ZenRows Browser Cloud (GB residential) + dispose.lol"""
import asyncio, os, json, uuid, re, html, time, random, urllib.request
ZENROWS_WSS = "wss://browser.zenrows.com?apikey=5afd422125c5fd5c75efe3da015689da3c7a3a80&proxy_country=gb"
DISPOSE_API = "https://dispose.lol"
TEMP_TF_API = "https://temp.tf/api"

def clear_proxy():
    for k in list(os.environ):
        if k.lower().endswith('_proxy') or k=='LD_PRELOAD':
            os.environ.pop(k,None)
clear_proxy()

async def get_dispose_email(page):
    # Use ZenRows browser to get dispose.lol Gmail
    await page.goto("https://dispose.lol", timeout=30000)
    await page.wait_for_timeout(5000)
    # Wait for Gmail to appear
    for _ in range(10):
        try:
            email = await page.evaluate("() => document.documentElement.innerText.match(/[a-z0-9._%+-]+@gmail\\.com/i)?.[0] || ''")
            if email and "@gmail.com" in email:
                return email.strip()
        except: pass
        await page.wait_for_timeout(1000)
    # Fallback to temp.tf
    for k in list(os.environ):
        if k.lower().endswith('_proxy'):
            os.environ.pop(k,None)
    with urllib.request.urlopen(TEMP_TF_API+"/account?dot=1&providers=gmail", timeout=10) as r:
        return json.loads(r.read())['email']

async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(ZENROWS_WSS, timeout=30000)
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await ctx.new_page()
        # Get dispose email via same browser
        email = await get_dispose_email(page)
        password = email + "K01"  # 8+ chars
        print(f"EMAIL {email} PW {password}")

        # Go to Lovable
        await page.goto("https://lovable.dev/signup", timeout=40000, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        # IP check (for log)
        try:
            ip = await page.evaluate("async () => { try{ const r=await fetch('https://wtfismyip.com/json'); const j=await r.json(); return j.YourFuckingIPAddress+' '+j.YourFuckingISP }catch(e){ return 'fail' } }")
            print(f"IP {ip}")
        except: pass

        # Fill email
        await page.locator('input#email').wait_for(timeout=10000)
        await page.locator('input#email').fill(email)
        await page.locator('[data-testid="auth-submit-button"]').click()
        await page.wait_for_timeout(4000)

        # Fill password (ZenRows has no Forbidden trap, so fill works)
        pw_input = page.locator('input#password')
        await pw_input.wait_for(timeout=10000)
        await pw_input.fill(password)
        # Verify
        val = await page.evaluate("() => document.querySelector('#password')?.value?.length || 0")
        print(f"PW len {val}")
        await page.screenshot(path="/tmp/zen_final_pw.png", full_page=True)

        # Wait Turnstile Success
        for i in range(15):
            token = await page.evaluate("() => document.querySelector('input[name=\"cf-turnstile-response\"]')?.value?.length || 0")
            print(f"Token {token} i {i}")
            if token>100:
                break
            await page.wait_for_timeout(2000)
        token = await page.evaluate("() => document.querySelector('input[name=\"cf-turnstile-response\"]')?.value || ''")
        print(f"Final token {len(token)}")

        # Click Create
        btn = page.locator('[data-testid="auth-submit-button"]')
        disabled = await btn.is_disabled()
        print(f"Create disabled {disabled}")
        await page.screenshot(path="/tmp/zen_final_before.png", full_page=True)
        if not disabled:
            await btn.click()
            await page.wait_for_timeout(8000)
            await page.screenshot(path="/tmp/zen_final_after.png", full_page=True)
            content = await page.content()
            if "Check your inbox" in content:
                print("SUCCESS Check your inbox")
            elif "suspicious" in content.lower():
                print("BLOCKED suspicious")
            else:
                print(content[:2000])
            # Poll dispose.lol for link
            print("Polling dispose.lol for link...")
            # Use the same page to poll dispose.lol API via evaluate
            for attempt in range(20):
                try:
                    # Use page.evaluate to fetch from dispose.lol (same session)
                    msgs = await page.evaluate("""async () => {
                        try{
                            const r=await fetch('https://dispose.lol/_app/remote/1i1fsx0/getMailboxMessages?payload=W3siYXNzaWdubWVudElkIjotMX1d');
                            const j=await r.json();
                            return JSON.stringify(j).slice(0,4000);
                        }catch(e){ return 'err '+e.message }
                    }""")
                    print(f"Poll {attempt}: {msgs[:500]}")
                    if "lovable" in msgs.lower():
                        # Extract link
                        link = await page.evaluate("""async () => {
                            const r=await fetch('https://dispose.lol/_app/remote/1i1fsx0/getMailboxMessages?payload=W3siYXNzaWdubWVudElkIjotMX1d');
                            const j=await r.json();
                            const txt=JSON.stringify(j);
                            const m=txt.match(/https:\\/\\/lovable\\.dev[^"']*/);
                            return m ? m[0].replace(/\\\\u002F/g,'/') : '';
                        }""")
                        print(f"LINK {link[:300]}")
                        if link:
                            await page.goto(link, timeout=20000)
                            await page.wait_for_timeout(4000)
                            await page.screenshot(path="/tmp/zen_final_verified.png", full_page=True)
                            print("Verified screenshot /tmp/zen_final_verified.png")
                            print((await page.content())[:3000])
                            with open("/tmp/zen_final_account.txt","w") as f:
                                f.write(f"{email}\n{password}\n{link}\n")
                            print(f"SAVED {email}")
                            break
                except Exception as e:
                    print(f"Poll err {e}")
                await page.wait_for_timeout(5000)
        await browser.close()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
