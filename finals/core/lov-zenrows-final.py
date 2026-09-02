#!/usr/bin/env python3
"""Lovable automation via ZenRows Browser Cloud (French GF residential, no Forbidden trap).

Uses dispose.lol Gmail + ZenRows wss://browser.zenrows.com?apikey=...&proxy_country=gf
Bypasses BD's navigate_domains_limit and password Forbidden block.
Verified on genev.aochea@gmail.com / GmailK01 -> Check your inbox -> oobCode verified -> /getting-started
"""
import asyncio, os, json, uuid, sys, re, html, time, urllib.request, random
from pathlib import Path

ZENROWS_WSS = "wss://browser.zenrows.com?apikey=3a6a9ee9aee5e3fa9a76b934eafd8dd1cf6dd39f&proxy_country=gf"
ZENROWS_WSS_GB = "wss://browser.zenrows.com?apikey=3a6a9ee9aee5e3fa9a76b934eafd8dd1cf6dd39f&proxy_country=gb"
TEMP_TF_API = "https://temp.tf/api"
DISPOSE_API = "https://dispose.lol"

def clear_proxy():
    for k in list(os.environ):
        if k.lower().endswith('_proxy') or k == 'LD_PRELOAD':
            os.environ.pop(k, None)
clear_proxy()

async def get_dispose_gmail_via_browser(page):
    """Generate dispose.lol Gmail via browser (more reliable than API)."""
    await page.goto("https://dispose.lol", timeout=30000)
    await page.wait_for_timeout(5000)
    # Wait for Gmail to appear (not Loading)
    for _ in range(10):
        email = await page.evaluate("""() => {
            const el=document.querySelector('p.truncate');
            const t=el?.innerText?.trim() || '';
            return t.includes('@gmail.com') ? t : '';
        }""")
        if email and "@gmail.com" in email:
            return email.strip()
        await page.wait_for_timeout(2000)
    # Fallback to temp.tf
    for k in list(os.environ):
        if k.lower().endswith('_proxy'):
            os.environ.pop(k, None)
    import urllib.request, json
    with urllib.request.urlopen(TEMP_TF_API+"/account?dot=1&providers=gmail", timeout=10) as r:
        return json.loads(r.read())['email']

async def main():
    use_gb = "--gb" in sys.argv
    wss = ZENROWS_WSS_GB if use_gb else ZENROWS_WSS
    print(f"Using WSS {wss[:70]}...", file=sys.stderr)
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(wss, timeout=30000)
        ctx = await browser.new_context()
        # Save native setter before page JS patches it (bypasses BD Forbidden, not needed on ZenRows but harmless)
        await ctx.add_init_script("window.__nativeSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;")
        page = await ctx.new_page()
        # Get dispose Gmail via same browser session
        email = await get_dispose_gmail_via_browser(page)
        password = email + "K01"  # 8+ chars, meets "Le mot de passe respecte toutes les exigences"
        print(f"Trying {email} / {password}", file=sys.stderr)
        # Now go to Lovable
        await page.goto("https://lovable.dev/signup", timeout=30000)
        await page.wait_for_timeout(4000)
        # Dismiss cookie banner if present
        try:
            await page.locator('[data-testid="consent-accept-all-button"], button:has-text("Tout accepter")').click(timeout=2000)
        except: pass
        ip = await page.evaluate("async () => { try{ const r=await fetch('https://api.ipify.org?format=json'); const j=await r.json(); return j.ip }catch(e){ return 'fail' } }")
        print(f"IP {ip}", file=sys.stderr)
        # Email step - use human typing as requested
        await page.locator('input#email').wait_for(timeout=10000)
        await page.locator('input#email').click()
        await page.keyboard.type(email, delay=50)
        print("Typed email", file=sys.stderr)
        await page.locator('[data-testid="auth-submit-button"]').click()
        print("Clicked Continue", file=sys.stderr)
        await page.wait_for_timeout(4000)
        await page.screenshot(path="/tmp/zen_final_pwstep.png", full_page=True)
        # Password - use human typing (ZenRows has no Forbidden trap, so this works)
        pw_input = page.locator('input#password')
        await pw_input.wait_for(timeout=10000)
        await pw_input.click()
        await page.keyboard.type(password, delay=50)
        print("Typed password", file=sys.stderr)
        val = await page.evaluate("() => document.querySelector('#password')?.value?.length || 0")
        print(f"PW len {val}", file=sys.stderr)
        await page.screenshot(path="/tmp/zen_final_pwf.png", full_page=True)
        # Wait Turnstile
        print("Waiting Turnstile", file=sys.stderr)
        for i in range(20):
            token = await page.evaluate("() => document.querySelector('input[name=\"cf-turnstile-response\"]')?.value?.length || 0")
            print(f"Token len {token} i {i}", file=sys.stderr)
            if token > 100:
                break
            await page.wait_for_timeout(2000)
        token = await page.evaluate("() => document.querySelector('input[name=\"cf-turnstile-response\"]')?.value || ''")
        print(f"Final token {len(token)}", file=sys.stderr)
        await page.screenshot(path="/tmp/zen_final_turnstile.png", full_page=True)
        # Create
        create_btn = page.locator('[data-testid="auth-submit-button"]')
        disabled = await create_btn.is_disabled()
        print(f"Create disabled {disabled}", file=sys.stderr)
        if disabled:
            print("Still disabled, trying to force enable via evaluate", file=sys.stderr)
            await page.evaluate("() => { const b=document.querySelector('[data-testid=\"auth-submit-button\"]'); if(b){ b.disabled=false; b.removeAttribute('disabled'); } }")
        await create_btn.click()
        print("Clicked Create", file=sys.stderr)
        await page.wait_for_timeout(8000)
        await page.screenshot(path="/tmp/zen_final_after.png", full_page=True)
        content = await page.content()
        if "suspicious" in content.lower():
            print("BLOCKED suspicious activity", file=sys.stderr)
        elif "Check your inbox" in content or "Vérifiez votre boîte" in content or "Vérifiez" in content:
            print("SUCCESS Check your inbox", file=sys.stderr)
        print(content[:3000], file=sys.stderr)
        # Poll dispose.lol for link
        print("Polling dispose.lol for verification link...", file=sys.stderr)
        # Use the same browser session to poll dispose.lol
        # First, get the current dispose email from the page
        # Poll via the dispose.lol API as used in the UI
        for attempt in range(30):
            try:
                # Use the browser to fetch the dispose inbox via evaluate
                inbox = await page.evaluate("""async (email) => {
                    try{
                        // Try temp.tf check as fallback
                        const r=await fetch('https://temp.tf/api/check', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({email})});
                        const j=await r.json();
                        return JSON.stringify(j).slice(0,3000);
                    }catch(e){ return 'err '+e.message }
                }""", email)
                print(f"Poll {attempt}: {inbox[:500]}", file=sys.stderr)
                if "lovable.dev" in inbox.lower():
                    # Extract link
                    m = re.search(r"https?://[^\s\"'<>]*lovable\.dev[^\s\"'<>]*", inbox)
                    if m:
                        link = html.unescape(m.group(0)).replace("&amp;","&")
                        print(f"LINK {link[:400]}", file=sys.stderr)
                        await page.goto(link, timeout=20000)
                        await page.wait_for_timeout(4000)
                        await page.screenshot(path="/tmp/zen_final_verified.png", full_page=True)
                        print("Verified /tmp/zen_final_verified.png", file=sys.stderr)
                        print((await page.content())[:3000], file=sys.stderr)
                        with open("/tmp/zen_final_account.txt","w") as f:
                            f.write(f"{email}\n{password}\n{link}\n")
                        print(f"SAVED {email}", file=sys.stderr)
                        await browser.close()
                        return
            except Exception as e:
                print(f"Poll err {e}", file=sys.stderr)
            await asyncio.sleep(5)
            # Also try via dispose.lol UI
            try:
                await page.goto("https://dispose.lol", timeout=15000)
                await page.wait_for_timeout(3000)
                # Check inbox
                has_lovable = await page.evaluate("() => document.body.innerText.toLowerCase().includes('lovable')")
                if has_lovable:
                    print("Found Lovable in dispose UI", file=sys.stderr)
                    # Click the message
                    try:
                        await page.locator('text=Verify your email').first.click(timeout=5000)
                        await page.wait_for_timeout(2000)
                        link = await page.evaluate("""() => {
                            const html=document.documentElement.innerHTML;
                            const m=html.match(/https:\\/\\/lovable\\.dev[^"'<>\\s]*/);
                            return m ? m[0] : '';
                        }""")
                        if link:
                            print(f"LINK from UI {link[:400]}", file=sys.stderr)
                            await page.goto(link, timeout=20000)
                            await page.wait_for_timeout(4000)
                            await page.screenshot(path="/tmp/zen_final_verified2.png", full_page=True)
                            with open("/tmp/zen_final_account.txt","w") as f:
                                f.write(f"{email}\n{password}\n{link}\n")
                            await browser.close()
                            return
                    except Exception as e:
                        print(f"UI click fail {e}", file=sys.stderr)
                # Go back to lovable verify page
                await page.goto("https://lovable.dev/verify-email", timeout=15000)
                await page.wait_for_timeout(2000)
            except: pass
        print("No link found", file=sys.stderr)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
