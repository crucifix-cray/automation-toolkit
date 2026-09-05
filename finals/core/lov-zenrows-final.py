#!/usr/bin/env python3
"""Lovable account creation via ZenRows Browser Cloud (GB residential) + dispose.lol"""
import asyncio, os, json, uuid, re, html, time, random, urllib.request, base64
from pathlib import Path
ZENROWS_WSS = "wss://browser.zenrows.com?apikey=5afd422125c5fd5c75efe3da015689da3c7a3a80&proxy_country=gb"
DISPOSE_API = "https://dispose.lol"
TEMP_TF_API = "https://temp.tf/api"

def clear_proxy():
    for k in list(os.environ):
        if k.lower().endswith('_proxy') or k=='LD_PRELOAD':
            os.environ.pop(k,None)
clear_proxy()

class DisposeLolInbox:
    """dispose.lol inbox manager using browser context tab (from lov-api-effective.py)"""
    BASE_URL = "https://dispose.lol"

    def __init__(self, context) -> None:
        self.context = context
        self.page = None
        self.address = None

    async def init_mailbox(self) -> str:
        self.page = await self.context.new_page()
        await self.page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=60000)
        await self.page.wait_for_timeout(4000)

        for attempt in range(1, 6):
            email_text = await self.page.evaluate("""() => {
                const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT,null);
                let n; while(n=w.nextNode()){
                    const t=n.textContent.trim();
                    if(t.includes('@gmail.com')&&t.length<80) return t;
                }
                for(const i of document.querySelectorAll('input')) if(i.value&&i.value.includes('@gmail.com')) return i.value;
                return null;
            }""")
            if email_text and "@gmail.com" in email_text:
                self.address = email_text.strip()
                print(f"✅ Mailbox ready: {self.address} (via dispose.lol tab)")
                return self.address
            print(f"  ⏳ Waiting for dispose.lol email to render (attempt {attempt}/5)...")
            await self.page.wait_for_timeout(2000)
            await self.page.reload(wait_until="domcontentloaded")
            await self.page.wait_for_timeout(3000)
        raise Exception("Could not find dispose.lol Gmail after 5 attempts")

    async def wait_for_lovable_link(self, timeout_seconds: int = 180) -> str:
        print(f"📥 Waiting for Lovable verify link on dispose.lol ({self.address})...")
        deadline = time.time() + timeout_seconds
        check = 0

        while time.time() < deadline:
            check += 1
            try:
                await self.page.reload(wait_until="domcontentloaded")
            except Exception: pass
            await self.page.wait_for_timeout(2200)

            try:
                buttons = await self.page.locator('button[aria-label^="View "]').all()
            except Exception:
                buttons = []

            if check % 3 == 1:
                print(f"  Check #{check}: {len(buttons)} message(s) found")

            for btn in buttons:
                try:
                    aria = (await btn.get_attribute("aria-label") or "")
                except Exception: aria = ""

                if "lovable" not in aria.lower() and "verify" not in aria.lower() and "verification" not in aria.lower():
                    continue

                print(f"  ✅ Found Lovable email: {aria[:100]}")
                try:
                    await btn.click(timeout=5000, force=True)
                    await self.page.wait_for_timeout(3000)

                    # Scan all iframe frames (dispose.lol renders email body inside iframe srcdoc)
                    for frame in self.page.frames:
                        try:
                            fhtml = await frame.content()
                        except Exception: continue

                        m = re.search(r'https?://lovable\.dev/auth/action\?[^"\'\s<>]*oobCode=[^"\'\s<>]+', fhtml or "")
                        if m:
                            link = html.unescape(m.group(0)).replace("&amp;", "&")
                            print(f"  🎯 FOUND VERIFY LINK (frame html): {link}")
                            return link

                        m2 = re.search(r'https?://[^"\'\s<>]*lovable\.dev[^"\'\s<>]*', fhtml or "")
                        if m2 and "oobCode" in m2.group(0):
                            link = html.unescape(m2.group(0)).replace("&amp;", "&")
                            print(f"  🎯 FOUND VERIFY LINK (frame oobCode): {link}")
                            return link
                except Exception as e:
                    print(f"  Extraction error on button click: {e}")
            await asyncio.sleep(3)
        raise Exception("Lovable verify link not received on dispose.lol (timeout)")

    async def close(self):
        if self.page:
            try: await self.page.close()
            except: pass

import argparse

async def run_signup(args, run_attempt=1):
    pw = None
    browser = None
    ctx = None
    page = None
    inbox = None

    # ZenRows CDP URL pool (rotates key & proxy country for clean residential IP)
    zenrows_keys = [
        "a71406ecf7cfd8ae0aec54b2d1bf11aa92c917e7",
        "3a6a9ee9aee5e3fa9a76b934eafd8dd1cf6dd39f",
        "b71908b722a88c56ee0ed960730465ab8e4bdfa3",
        "5afd422125c5fd5c75efe3da015689da3c7a3a80"
    ]
    countries = ["gb", "gf"]
    key = zenrows_keys[(run_attempt - 1) % len(zenrows_keys)]
    proxy_country = countries[(run_attempt - 1) % len(countries)]
    zenrows_wss_url = f"wss://browser.zenrows.com?apikey={key}&proxy_country={proxy_country}"

    if args.local:
        print(f"🦊 [Attempt {run_attempt}] Launching local Camoufox Stealth browser...")
        try:
            from camoufox.async_api import AsyncCamoufox
            camou = AsyncCamoufox(headless=args.headless)
            browser = await camou.__aenter__()
            ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        except ImportError:
            print("⚠️ Camoufox not found, falling back to Patchright...")
            from patchright.async_api import async_playwright
            pw = await async_playwright().start()
            browser = await pw.chromium.launch(headless=args.headless, args=["--disable-blink-features=AutomationControlled"])
            ctx = await browser.new_context()
    else:
        print(f"🌐 [Attempt {run_attempt}] Connecting to ZenRows CDP WSS (Country: {proxy_country.upper()})...")
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        browser = await pw.chromium.connect_over_cdp(zenrows_wss_url, timeout=30000)
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()

    # Stealth Init Scripts
    await ctx.add_init_script("""() => {
        try { Object.defineProperty(navigator, 'webdriver', {get: () => undefined}); } catch(e){}
        try { Object.defineProperty(navigator, 'plugins', {get: () => [{name: 'PDF Viewer'}]}); } catch(e){}
        try { if(!window.chrome) window.chrome = {runtime: {}}; } catch(e){}
        try { window.__nativeSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; } catch(e){}
    }""")

    try:
        # Create dispose.lol inbox in separate tab
        inbox = DisposeLolInbox(ctx)
        email = await inbox.init_mailbox()
        password = email + "K01"  # 8+ chars
        print(f"EMAIL {email} PW {password}")

        # Open Lovable page in second tab
        page = await ctx.new_page()
        for page_attempt in range(1, 3):
            try:
                await page.goto("https://lovable.dev/signup", timeout=60000, wait_until="domcontentloaded")
                break
            except Exception as e:
                print(f"⚠️ Page load attempt {page_attempt} failed ({e}), retrying...")
                await asyncio.sleep(2)
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

        # Fill password using nativeSetter or fill fallback
        pw_input = page.locator('input#password')
        await pw_input.wait_for(timeout=10000)
        try:
            await page.evaluate("(pw) => window.__nativeSetter ? window.__nativeSetter.call(document.querySelector('#password'), pw) : (document.querySelector('#password').value = pw)", password)
            await page.evaluate("el => el.dispatchEvent(new Event('input', {bubbles: true}))", await pw_input.element_handle())
        except Exception:
            await pw_input.fill(password)

        val = await page.evaluate("() => document.querySelector('#password')?.value?.length || 0")
        print(f"PW len {val}")
        await page.screenshot(path="/tmp/zen_final_pw.png", full_page=True)

        # Wait Turnstile Success
        for i in range(15):
            token = await page.evaluate("() => document.querySelector('input[name=\"cf-turnstile-response\"]')?.value?.length || 0")
            print(f"Token {token} i {i}")
            if token > 100:
                break
            try:
                await page.evaluate("() => { if(window.turnstile && typeof window.turnstile.execute === 'function') window.turnstile.execute(); }")
            except: pass
            await page.wait_for_timeout(2000)

        token = await page.evaluate("() => document.querySelector('input[name=\"cf-turnstile-response\"]')?.value || ''")
        print(f"Final token {len(token)}")

        if len(token) == 0:
            print("⛔ Turnstile challenge failed/blocked (token 0). Killing browser...")
            raise Exception("SUSPICIOUS_BLOCK_DETECTED: Cloudflare Turnstile token missing")

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
            content_lower = content.lower()

            suspicious_keywords = [
                "suspicious",
                "denied due to suspicious activity",
                "blocked due to suspicious activity",
                "requests from this device have been blocked",
                "signups from this ip address are temporarily disabled",
                "too many requests",
                "try again later"
            ]

            detected_err = None
            for kw in suspicious_keywords:
                if kw in content_lower:
                    detected_err = kw
                    break

            if not detected_err:
                try:
                    alert_el = page.locator('[role="alert"], .text-destructive, [data-invalid]').first
                    if await alert_el.is_visible(timeout=1000):
                        detected_err = (await alert_el.inner_text()).strip()
                except Exception: pass

            if detected_err:
                print(f"⛔ BLOCKED / SUSPICIOUS ERROR DETECTED: '{detected_err}'! Killing browser to rotate IP...")
                raise Exception(f"SUSPICIOUS_BLOCK_DETECTED: {detected_err}")

            if "Check your inbox" in content:
                print("SUCCESS Check your inbox")
            else:
                print(f"Page response snippet: {content[:500]}")

            # Wait for Lovable verify link from dispose.lol tab
            link = await inbox.wait_for_lovable_link()
            if link:
                print(f"🎯 Navigating to verify link: {link}")
                await page.goto(link, timeout=30000)
                await page.wait_for_timeout(5000)
                await page.screenshot(path="/tmp/zen_final_verified.png", full_page=True)

                # ── POST-VERIFICATION ONBOARDING FLOW ─────────────────────────────
                print("🚀 Completing onboarding flow until redirected to /dashboard...")
                display_name = email.split('@')[0].replace('.', ' ').title()

                for step_attempt in range(25):
                    await page.wait_for_timeout(1500)
                    url = page.url
                    content = await page.content()

                    if "/dashboard" in url or "/projects" in url:
                        print(f"🎯 Reached Dashboard! URL: {url}")
                        break

                    # Step 1: "Pick your style" -> Click Next
                    if "Pick your style" in content or "Step 1" in content:
                        try:
                            nxt = page.locator('button:has-text("Next"), button:has-text("Continue")').first
                            if await nxt.is_visible(timeout=1500):
                                await nxt.click()
                                print("  ✅ Step 1: Clicked Next (Style selected)")
                                await page.wait_for_timeout(2000)
                        except Exception: pass

                    # Step 2: "What's your name?" -> Fill display name
                    name_input = page.locator('input[placeholder*="name"], input#name, input[name="name"]').first
                    try:
                        if await name_input.is_visible(timeout=1500):
                            await name_input.fill(display_name)
                            print(f"  ✅ Step 2: Filled display name '{display_name}'")
                            await name_input.press("Enter")
                            await page.wait_for_timeout(2000)
                    except Exception: pass

                    # Step 3: "Which role fits you best?" -> Click "Engineer" / "Developer" / "Founder"
                    if "Which role" in content or "Step 3" in content:
                        for role in ["Engineer", "Developer", "Founder", "Other"]:
                            try:
                                r_btn = page.locator(f'button:has-text("{role}")').first
                                if await r_btn.is_visible(timeout=1000):
                                    await r_btn.click()
                                    print(f"  ✅ Step 3: Selected role '{role}'")
                                    await page.wait_for_timeout(2000)
                                    break
                            except Exception: pass

                    # Step 4: "How many people work at your company?" -> Click "Solo" / "1-5" / "2 - 20"
                    if "How many people" in content or "company" in content or "Step 4" in content:
                        for sz in ["Solo", "Just me", "1-5", "2 - 20", "200+"]:
                            try:
                                s_btn = page.locator(f'button:has-text("{sz}")').first
                                if await s_btn.is_visible(timeout=1000):
                                    await s_btn.click()
                                    print(f"  ✅ Step 4: Selected size '{sz}' (Submitting onboarding)")
                                    await page.wait_for_timeout(2500)
                                    break
                            except Exception: pass

                    # Fallback buttons (Next / Continue / Get Started / Skip)
                    for btn_text in ["Next", "Continue", "Get Started", "Skip"]:
                        try:
                            b = page.locator(f'button:has-text("{btn_text}")').first
                            if await b.is_visible(timeout=1000):
                                await b.click()
                                print(f"  ✅ Fallback: Clicked button '{btn_text}'")
                                await page.wait_for_timeout(2000)
                                break
                        except Exception: pass

                # Final Dashboard Wait
                await page.wait_for_timeout(4000)
                final_url = page.url
                await page.screenshot(path="/tmp/zen_final_dashboard.png", full_page=True)

                # ── SAVE COOKIES & CONFIG TO SESSIONS DIR ──────────────────────────
                sessions_dir = Path(__file__).resolve().parents[2] / "scripts" / "sessions"
                sessions_dir.mkdir(parents=True, exist_ok=True)
                session_id_dir = f"session-{int(time.time())}"
                session_path = sessions_dir / session_id_dir
                session_path.mkdir(parents=True, exist_ok=True)

                cookies = await ctx.cookies()
                (session_path / "cookies.json").write_text(json.dumps(cookies, indent=2))
                config_data = {
                    "email": email,
                    "password": password,
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "dashboard_url": final_url,
                    "verified": True,
                    "provider": "dispose.lol",
                    "verify_link": link
                }
                (session_path / "config.json").write_text(json.dumps(config_data, indent=2))

                with open("/tmp/zen_final_account.txt", "w") as f:
                    f.write(f"{email}\n{password}\n{link}\n{final_url}\n")

                print(f"✅ SAVED SESSION {session_id_dir} to {session_path}")
                print(f"✅ Saved {len(cookies)} cookies & config.json for {email}")
                return True
    finally:
        if inbox:
            try: await inbox.close()
            except: pass
        if browser:
            try: await browser.close()
            except: pass
        if pw:
            try: await pw.stop()
            except: pass
    return False

async def main():
    parser = argparse.ArgumentParser(description="Lovable account creation via ZenRows Cloud or Local Camoufox Stealth")
    parser.add_argument("--local", action="store_true", help="Use local Camoufox browser with stealth bypass")
    parser.add_argument("--headless", action="store_true", help="Run local browser in headless mode")
    parser.add_argument("--max-retries", type=int, default=10, help="Max retries on suspicious block")
    args = parser.parse_args()

    for attempt in range(1, args.max_retries + 1):
        try:
            print(f"\n==========================================")
            print(f"🚀 SIGNUP ATTEMPT {attempt}/{args.max_retries}")
            print(f"==========================================")
            success = await run_signup(args, run_attempt=attempt)
            if success:
                print(f"🎉 Signup completed successfully on attempt {attempt}!")
                break
        except Exception as e:
            if "SUSPICIOUS_BLOCK_DETECTED" in str(e):
                print(f"⛔ [Attempt {attempt}] Suspicious error encountered! Browser process killed.")
                if not args.local:
                    print(f"🔄 ZenRows mode: Changing IP / Proxy Country & Session ID for attempt {attempt + 1}...")
                else:
                    print(f"🔄 Local mode: Restarting fresh browser instance for attempt {attempt + 1}...")
                await asyncio.sleep(3)
            else:
                print(f"⚠️ Error on attempt {attempt}: {e}")
                await asyncio.sleep(2)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

