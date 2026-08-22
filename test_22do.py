#!/usr/bin/env python3
"""22.do headless tester — pick handler, gen mail, poll inbox every 5s"""
import asyncio, sys
from playwright.async_api import async_playwright

HANDLERS = [
    ("@linshiyou.com", "https://22.do/", "@linshiyou.com"),
    ("@colabeta.com", "https://22.do/", "@colabeta.com"),
    ("@youxiang.dev", "https://22.do/", "@youxiang.dev"),
    ("@colaname.com", "https://22.do/", "@colaname.com"),
    ("@usdtbeta.com", "https://22.do/", "@usdtbeta.com"),
    ("@tnbeta.com", "https://22.do/", "@tnbeta.com"),
    ("@fft.edu.do", "https://22.do/", "@fft.edu.do"),
    ("@gmail.com (Fake Gmail)", "https://22.do/fake-gmail-generator", "@gmail.com"),
    ("@googlemail.com (Fake Gmail)", "https://22.do/fake-gmail-generator", "@googlemail.com"),
    ("@hotmail.com", "https://22.do/temporary-hotmail", "@hotmail.com"),
    ("@outlook.com", "https://22.do/temporary-outlook", "@outlook.com"),
]

async def run(handler=None):
    # handler is 1-10 or domain string
    target_url = "https://22.do/"
    target_domain = None
    is_random_custom = False
    if handler and handler.isdigit():
        idx = int(handler)-1
        if 0 <= idx < len(HANDLERS):
            target_url, target_domain = HANDLERS[idx][1], HANDLERS[idx][2]
            handler = target_domain
    elif handler and handler.startswith("@"):
        for name, url, dom in HANDLERS:
            if dom.lower() == handler.lower():
                target_url, target_domain = url, dom
                break
        handler = target_domain or handler
    elif handler and handler.lower() in ("random","custom"):
        is_random_custom = True
        handler = handler.lower()
        target_domain = None
    elif handler and "22.do" in handler:
        target_url = handler
    else:
        target_url, target_domain = HANDLERS[0][1], HANDLERS[0][2]
        handler = target_domain

    import os
    headless = os.environ.get("HEADLESS") == "1"
    async with async_playwright() as p:
        if headless:
            # headless=new (less CF-flagged) — explicit new mode
            browser = await p.chromium.launch(headless=False, args=["--headless=new","--no-sandbox","--disable-dev-shm-usage","--disable-blink-features=AutomationControlled"])
        else:
            browser = await p.chromium.launch(headless=False, args=["--no-sandbox","--disable-dev-shm-usage","--disable-blink-features=AutomationControlled"])
        ctx = await browser.new_context(viewport={"width":1280,"height":720})
        page = await ctx.new_page()

        print(f"→ opening {target_url}  (handler={handler})")
        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=90000)
        except Exception as e:
            print(f"goto timeout {e}, trying reload")
            await page.wait_for_timeout(3000)
        await page.wait_for_timeout(4000)
        # detect Cloudflare block on headless
        try:
            title = await page.title()
            body = await page.content()
            if "Attention Required" in title or "Sorry, you have been blocked" in body:
                print("⛔ Cloudflare blocked this page in headless mode (fake-gmail/hotmail/outlook are WAF-protected).")
                print("   → retry without --headless via Xvfb: xvfb-run -a python3 -u /home/alae/Documents/repos/automation-toolkit/test_22do.py 8")
                await browser.close(); return
        except: pass
        try:
            await page.wait_for_selector("#mail-random", timeout=15000)
        except:
            # if still blocked, screenshot
            await page.screenshot(path="/tmp/22do_cf.png")
            print("⚠️  #mail-random not visible — saved /tmp/22do_cf.png (likely CF). Try without --headless.")
            await browser.close(); return

        # close google vignette / ad overlay if present
        try:
            close = page.locator('button:has-text("Close ad")').first
            if await close.count() and await close.is_visible():
                await close.click(timeout=2000)
                print("× closed ad overlay")
                await page.wait_for_timeout(1000)
        except: pass

        # pick domain handler then Random
        if target_domain and target_domain not in ("@gmail.com","@hotmail.com","@outlook.com"):
            # select domain from dropdown on main page
            try:
                await page.locator(".choices__inner").click(timeout=3000)
                await page.wait_for_timeout(500)
                await page.locator(f".choices__item--choice >> text={target_domain}").first.click(timeout=3000)
                print(f"→ selected domain {target_domain}")
                await page.wait_for_timeout(800)
            except Exception as e:
                print(f"domain select failed {target_domain}: {e}")

        if is_random_custom and handler == "custom":
            print("→ Custom handler (using random as base)")
            await page.locator("#mail-custom").click()
            await page.wait_for_timeout(500)
            await page.locator("#mail-random").click()
            await page.wait_for_timeout(500)
        else:
            print(f"→ Random gen for {target_domain or handler}")
            try:
                await page.locator("#mail-random").click(timeout=5000)
            except:
                pass
            await page.wait_for_timeout(1000)

        try:
            local = await page.locator("#mail-input").input_value(timeout=5000)
        except Exception as e:
            print(f"⛔ #mail-input not ready: {e} — likely headless CF block. Use xvfb-run without --headless.")
            await page.screenshot(path="/tmp/22do_input_fail.png")
            await browser.close(); return
        # domain — for fake gmail differentiate @gmail vs @googlemail
        email = ""
        try:
            maybe_full = local
            if "@" in maybe_full:
                email = maybe_full.strip()
            else:
                dom = await page.locator(".choices__list--single .choices__item").first.inner_text(timeout=2000)
                email = f"{maybe_full.strip()}{dom.strip()}"
        except:
            email = f"{local.strip()}@linshiyou.com"
        # fallback: if target_domain is googlemail/gmail, enforce differentiation
        if target_domain in ("@gmail.com","@googlemail.com"):
            # page may have generated the other variant → retry Random until match
            for _ in range(5):
                if email.lower().endswith(target_domain.lower()):
                    break
                print(f"  got {email} but wanted {target_domain}, retrying Random…")
                try: await page.locator("#mail-random").click(timeout=3000); await page.wait_for_timeout(800)
                except: pass
                try:
                    v = await page.locator("#mail-input").input_value()
                    email = v.strip() if "@" in v else f"{v.strip()}{target_domain}"
                except: pass
        print(f"📧 generated: {email}  (handler {target_domain or 'auto'} → {'@gmail' if email.lower().endswith('@gmail.com') else '@googlemail' if email.lower().endswith('@googlemail.com') else email.split('@')[-1]})")

        # click Open and wait for inbox
        print("→ Opening inbox…")
        # ensure no overlay
        try:
            await page.locator("#into-mailbox").click(timeout=5000)
        except Exception as e:
            print(f"Open click failed: {e}")
            await page.screenshot(path="/tmp/22do_open_fail.png")
            print("saved /tmp/22do_open_fail.png")
            await browser.close(); return

        await page.wait_for_timeout(4000)
        print(f"→ after Open url: {page.url}")
        await page.screenshot(path="/tmp/22do_inbox.png")
        print("📸 /tmp/22do_inbox.png")

        # poll inbox every 5s (no reload — keep ws alive)
        print(f"\n📬 Inbox for {email} — polling every 5s (Ctrl+C to stop)\nURL: {page.url}\n")
        for i in range(1, 1000):
            try:
                body = await page.locator("body").inner_text(timeout=4000)
                # 22.do inbox: #email-list-wrap .tr (each mail), .item.subject/from/time
                try:
                    count = await page.locator("#email-list-wrap .tr").count()
                except:
                    count = 0
                sample = ""
                if count > 0:
                    try:
                        subj = await page.locator("#email-list-wrap .tr .item.subject").first.inner_text(timeout=2000)
                        frm = await page.locator("#email-list-wrap .tr .item.from").first.inner_text(timeout=2000)
                        tm = await page.locator("#email-list-wrap .tr .item.time").first.inner_text(timeout=2000)
                        sample = f"subject='{subj.strip()}' from='{frm.strip()}' time='{tm.strip()}'"
                    except:
                        try:
                            sample = (await page.locator("#email-list-wrap .tr").first.inner_text(timeout=2000))[:100].replace("\n"," ")
                        except:
                            sample = ""
                has_empty = count == 0
                print(f"[{i}] {count} msgs | {sample} | {body[:100].replace(chr(10),' ')[:80]}")
                await page.wait_for_timeout(5000)
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"poll {i} err: {e}")
                await page.wait_for_timeout(5000)

        await browser.close()

def prompt_handler():
    print("\nAvailable @ handlers on 22.do:")
    for i,(name,url,dom) in enumerate(HANDLERS,1):
        print(f"  {i}. {name:25} → {url}")
    print("  r. Random   c. Custom")
    try:
        choice = input("\nSelect handler [1-11/r/c] (default 1): ").strip().lower() or "1"
    except EOFError:
        choice="1"
    if choice in ("r","random"): return "random"
    if choice in ("c","custom"): return "custom"
    if choice.isdigit() and 1 <= int(choice) <= len(HANDLERS):
        return str(int(choice))
    if choice.startswith("@"):
        return choice
    return "1"

async def run_recov(email: str):
    import os
    headless = os.environ.get("HEADLESS") == "1"
    async with async_playwright() as p:
        if headless:
            browser = await p.chromium.launch(headless=False, args=["--headless=new","--no-sandbox","--disable-dev-shm-usage","--disable-blink-features=AutomationControlled"])
        else:
            browser = await p.chromium.launch(headless=False, args=["--no-sandbox","--disable-dev-shm-usage","--disable-blink-features=AutomationControlled"])
        ctx = await browser.new_context(viewport={"width":1280,"height":720})
        page = await ctx.new_page()
        url = f"https://22.do/inbox/#/{email}"
        print(f"→ recovering inbox for {email}")
        print(f"→ opening {url}")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=90000)
        except Exception as e:
            print(f"goto timeout {e}")
        await page.wait_for_timeout(4000)
        try:
            title = await page.title()
            body = await page.content()
            if "Attention Required" in title or "Sorry, you have been blocked" in body:
                print("⛔ Cloudflare blocked in headless. Use xvfb-run without --headless.")
                await browser.close(); return
        except: pass
        await page.screenshot(path="/tmp/22do_recov.png")
        print(f"📸 /tmp/22do_recov.png  url={page.url}")
        print(f"\n📬 Inbox for {email} — polling every 5s\nURL: {page.url}\n")
        for i in range(1, 1000):
            try:
                body = await page.locator("body").inner_text(timeout=4000)
                try:
                    count = await page.locator("#email-list-wrap .tr").count()
                except:
                    count = 0
                sample = ""
                if count > 0:
                    try:
                        subj = await page.locator("#email-list-wrap .tr .item.subject").first.inner_text(timeout=2000)
                        frm = await page.locator("#email-list-wrap .tr .item.from").first.inner_text(timeout=2000)
                        tm = await page.locator("#email-list-wrap .tr .item.time").first.inner_text(timeout=2000)
                        sample = f"subject='{subj.strip()}' from='{frm.strip()}' time='{tm.strip()}'"
                    except:
                        try:
                            sample = (await page.locator("#email-list-wrap .tr").first.inner_text(timeout=2000))[:100].replace("\n"," ")
                        except:
                            sample = ""
                print(f"[{i}] {count} msgs | {sample} | {body[:100].replace(chr(10),' ')[:80]}")
                await page.wait_for_timeout(5000)
            except Exception as e:
                print(f"poll {i} err: {e}")
                await page.wait_for_timeout(5000)
        await browser.close()

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="22.do inbox tester")
    ap.add_argument("handler", nargs="?", help="1-11 / @gmail.com / random / url")
    ap.add_argument("--headless", action="store_true", help="run truly headless (no xvfb, may be blocked by CF)")
    ap.add_argument("--recov", metavar="EMAIL", help="recover inbox for existing mail: https://22.do/inbox/#/<mail>")
    args = ap.parse_args()
    import os
    os.environ["HEADLESS"] = "1" if args.headless else "0"
    if args.recov:
        asyncio.run(run_recov(args.recov.strip()))
    else:
        h = args.handler
        if not h:
            h = prompt_handler()
        elif h.lower() not in ("random","custom") and not h.isdigit() and "22.do" not in h and not h.startswith("@"):
            if h.isdigit():
                h = HANDLERS[int(h)-1][1] if 1 <= int(h) <= len(HANDLERS) else HANDLERS[-1][1]
        asyncio.run(run(h))
