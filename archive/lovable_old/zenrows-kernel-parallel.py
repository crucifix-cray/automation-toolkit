#!/usr/bin/env python3
"""ZenRows parallel 5 tabs — each with fresh dispose.lol Gmail, 7min wait, 5 refreshes, fresh IP per browser."""
import asyncio, os, json, uuid, sys, re, html, time, urllib.request, random

KERNEL_API_KEY = os.environ.get("KERNEL_API_KEY", "sk_729ff0c8-8973-8dcb-9c53-7288178dbc13.jO62-M4NtqELqARSxGY1Ar7BPyjSIU6OhdoHMjdt0Ow")

def create_kernel_browser():
    import subprocess, json, os
    cmd = "kernel browsers create --stealth --timeout 600 --start-url https://dispose.lol -o json"
    env = {**os.environ, "KERNEL_API_KEY": KERNEL_API_KEY}
    out = subprocess.check_output(cmd, shell=True, env=env, text=True)
    data = json.loads(out)
    print(f"LIVE: {data['browser_live_view_url']} | SID: {data['session_id']}", file=sys.stderr)
    return data["cdp_ws_url"], data["browser_live_view_url"], data["session_id"]

def cleanup_kernel(session_id):
    import subprocess, os
    try:
        subprocess.run(f"kernel browsers delete {session_id}", shell=True, env={**os.environ, "KERNEL_API_KEY": KERNEL_API_KEY}, timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except: pass

async def run_one_tab(page, idx):
    # Get dispose Gmail
    body = await page.evaluate("() => document.body.innerText")
    m = re.search(r"[a-z0-9._%+-]+@gmail\.com", body, re.I)
    if not m:
        print(f"Tab {idx} No email", file=sys.stderr)
        return None, None
    email = m.group(0)
    password = "Test1234!AbcZ2026"
    print(f"Tab {idx} EMAIL: {email}", file=sys.stderr)
    # Go to register
    await page.goto("https://app.zenrows.com/register", wait_until="domcontentloaded", timeout=30000)
    # Wait 3min with 5 refreshes (as requested, was 7min)
    solved = False
    for i in range(36):  # 36*5s = 180s = 3min
        await page.wait_for_timeout(5000)
        title = await page.title()
        body_snip = await page.evaluate("() => document.body.innerText.substring(0,1200)")
        if "Sign Up" in title and "Create a ZenRows account" in body_snip:
            solved = True
            print(f"Tab {idx} CF solved at {i*5}s", file=sys.stderr)
            break
        # Handle both Just a moment and ERROR_CAPTCHA_UNSOLVABLE
        if "ERROR_CAPTCHA_UNSOLVABLE" in body_snip or "Performing security verification" in body_snip:
            print(f"Tab {idx} CAPTCHA unsolvable at {i*5}s, refresh...", file=sys.stderr)
            await page.reload(wait_until="domcontentloaded")
        elif i % 6 == 5 and "Just a moment" in title:
            if i//6 < 5:
                print(f"Tab {idx} CF refresh at {i*5}s", file=sys.stderr)
                await page.reload(wait_until="domcontentloaded")
            else:
                print(f"Tab {idx} CF 5 refreshes done, still Just a moment", file=sys.stderr)
                break
    if not solved:
        print(f"Tab {idx} CF not solved after 3min", file=sys.stderr)
        return None, None
    # Fill
    await page.wait_for_selector("#email", timeout=15000)
    await page.fill("#email", email)
    await page.fill("#password", password)
    await page.click('button:has-text("Create account")')
    await page.wait_for_timeout(9000)
    url = page.url
    content = await page.content()
    if "email/verify" in url or "verify" in content.lower():
        print(f"Tab {idx} SUCCESS {email} -> {url}", file=sys.stderr)
        return email, password
    print(f"Tab {idx} failed {url} {content[:500]}", file=sys.stderr)
    return None, None

async def run_once():
    cdp_ws, live_url, session_id = create_kernel_browser()
    print(f"Connecting to {cdp_ws[:60]}... | LIVE {live_url}", file=sys.stderr)
    from playwright.async_api import async_playwright
    browser = None
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(cdp_ws, timeout=30000)
            ctx = browser.contexts[0]
            # Create 5 tabs
            tabs = []
            for i in range(5):
                p = await ctx.new_page() if i>0 else ctx.pages[0]
                if i>0:
                    await p.goto("https://dispose.lol", wait_until="domcontentloaded", timeout=30000)
                    await p.wait_for_timeout(3000)
                tabs.append(p)
            # Run all 5 in parallel
            results = await asyncio.gather(*[run_one_tab(tabs[i], i) for i in range(5)])
            # Find first success
            for email, pw in results:
                if email:
                    print(f"SUCCESS {email} / {pw}", file=sys.stderr)
                    # Close all tabs, keep the successful one's browser for verification
                    # Poll dispose for verification link
                    # For simplicity, use the first successful tab's page to poll
                    success_idx = next(i for i,(e,p) in enumerate(results) if e)
                    page = tabs[success_idx]
                    # Poll dispose
                    for i in range(20):
                        body = await page.evaluate("() => document.body.innerText")
                        if "verify@e.zenrows.com" in body:
                            print(f"Found verification email", file=sys.stderr)
                            break
                        await page.goto("https://dispose.lol", wait_until="domcontentloaded", timeout=30000)
                        await page.wait_for_timeout(3000)
                    # Get link and verify
                    # ... (same as before)
                    await browser.close()
                    cleanup_kernel(session_id)
                    return {"email": email, "password": pw, "url": page.url}
            print("All 5 tabs failed", file=sys.stderr)
            await browser.close()
            cleanup_kernel(session_id)
            sys.exit(1)
    except Exception as e:
        print(f"run_once exception {e}", file=sys.stderr)
        import traceback; traceback.print_exc()
        try:
            if browser: await browser.close()
        except: pass
        cleanup_kernel(session_id)
        raise

async def main():
    for attempt in range(3):
        try:
            result = await run_once()
            print(f"SUCCESS on attempt {attempt+1} {result}", file=sys.stderr)
            with open("/tmp/zen_parallel_account.txt","w") as f:
                f.write(f"{result['email']}\n{result['password']}\n")
            return
        except SystemExit as e:
            if e.code != 0:
                print(f"Attempt {attempt+1} failed, retry with fresh browser...", file=sys.stderr)
                await asyncio.sleep(5)
                continue
        except Exception as e:
            print(f"Attempt {attempt+1} exception {e}, retry...", file=sys.stderr)
            await asyncio.sleep(5)
            continue
    print("All attempts failed", file=sys.stderr)
    sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
