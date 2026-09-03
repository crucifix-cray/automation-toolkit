#!/usr/bin/env python3
"""
Final working Lovable flow: genev.aochea@gmail.com (100 credits, verified) + ZenRows/Kernel stealth + SaaS Remix + Build a debug terminal.txt → doc
- Uses Kernel stealth browser (or any CDP) with raw IP (no Tor)
- Login via 2-step (Email → Continue → Password → Log In) correctly
- Remix via article[aria-label] → More options → Remix → dialog checkbox → Acknowledge
- Prompt via [data-testid="chat-composer-editor"] [role="textbox"] fill (not type cut)
- Tests doc.connect() in preview
"""
import asyncio, os, re, random, json, sys
from pathlib import Path

# Use KERNEL_API_KEY from env or the known one
KERNEL_KEY = os.environ.get("KERNEL_API_KEY", "sk_729ff0c8-8973-8dcb-9c53-7288178dbc13.jO62-M4NtqELqARSxGY1Ar7BPyjSIU6OhdoHMjdt0Ow")

async def get_kernel_browser():
    import subprocess, json, os
    env = {**os.environ, "KERNEL_API_KEY": KERNEL_KEY}
    res = subprocess.run(
        ["kernel", "browsers", "create", "--stealth", "--start-url", "https://lovable.dev/dashboard", "--timeout", "3600", "--output", "json"],
        capture_output=True, text=True, env=env, timeout=60,
    )
    if res.returncode != 0:
        raise RuntimeError(f"kernel create fail: {res.stdout} {res.stderr}")
    j = json.loads(res.stdout)
    return j["cdp_ws_url"], j["browser_live_view_url"]

async def main():
    WSS, LIVE = await get_kernel_browser()
    print(f"Live view: {LIVE}")
    print(f"WSS: {WSS[:60]}...", file=sys.stderr)
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp(WSS, timeout=30000)
        ctx = b.contexts[0] if b.contexts else await b.new_context()
        page = await ctx.new_page()

        # Login
        print("Goto login")
        await page.goto("https://lovable.dev/login", timeout=30000)
        await page.wait_for_timeout(4000)
        email = "genev.aochea@gmail.com"
        el_email = page.locator('input#email')
        await el_email.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await el_email.fill(email)
        print("Filled email")
        await page.locator('[data-testid="auth-submit-button"]').click()
        print("Clicked Continue")
        await page.wait_for_timeout(4000)
        el_pw = page.locator('input#password')
        await el_pw.wait_for(state="visible", timeout=10000)
        print("Password found")
        await el_pw.click()
        await el_pw.fill("GmailK01")
        print("Filled pw")
        await page.locator('[data-testid="auth-submit-button"]').click()
        print("Clicked Log In")
        await page.wait_for_timeout(8000)
        print(f"After login URL {page.url} Title {await page.title()}")
        await page.screenshot(path="/tmp/final_working_login.png", full_page=True)

        # Dashboard
        await page.goto("https://lovable.dev/dashboard", timeout=30000)
        await page.wait_for_timeout(5000)
        print(f"Dashboard {page.url}")
        content = await page.content()
        m = re.search(r"(\d+)\s*credits?", content, re.I)
        if m:
            print(f"Credits: {m.group(0)}")
        await page.screenshot(path="/tmp/final_working_dashboard.png", full_page=True)

        # Templates SaaS
        await page.goto("https://lovable.dev/templates/apps/saas", timeout=30000)
        await page.wait_for_timeout(5000)
        print(f"Templates {page.url}")
        cards = page.locator('article[aria-label]')
        count = await cards.count()
        print(f"Found {count} templates")
        idx = random.randint(0, min(count-1, 9))
        card = cards.nth(idx)
        print(f"Selected {idx}")
        await card.wait_for(state="visible", timeout=10000)
        menu_btn = card.locator('button[aria-label*="More options"]')
        el = await menu_btn.element_handle()
        await page.evaluate("(el)=>el.click()", el)
        print("Clicked menu")
        await page.wait_for_timeout(2000)
        remix = page.locator('div[role="menuitem"]:has-text("Remix")')
        await remix.wait_for(state="attached", timeout=5000)
        print("Remix attached")
        el2 = await remix.element_handle()
        await page.evaluate("(el)=>el.click()", el2)
        print("Clicked Remix")
        await page.wait_for_timeout(2000)
        dialog = page.locator('div[role="dialog"]')
        await dialog.wait_for(state="visible", timeout=10000)
        print("Dialog visible")
        await page.screenshot(path="/tmp/final_working_dialog.png", full_page=True)
        checkbox = dialog.locator('input[type="checkbox"]')
        print(f"Checkbox checked {await checkbox.is_checked()}")
        el3 = await checkbox.element_handle()
        await page.evaluate("(el)=>el.click()", el3)
        print("Clicked checkbox")
        await page.wait_for_timeout(1000)
        text_input = dialog.locator('input[type="text"]')
        if await text_input.count() > 0:
            await text_input.first.fill(f"Test Project {random.randint(1000,9999)}")
            print("Filled text input")
            await page.wait_for_timeout(1000)
        btn = dialog.locator('button:has-text("Acknowledge and remix")')
        for i in range(10):
            disabled = await btn.is_disabled()
            print(f"Btn disabled {disabled} i {i}")
            if not disabled:
                break
            await page.wait_for_timeout(1000)
        el4 = await btn.element_handle()
        await page.evaluate("(el)=>el.click()", el4)
        print("Clicked Ack")
        for i in range(20):
            await page.wait_for_timeout(3000)
            url = page.url
            print(f"URL {i} {url}")
            if "/projects/" in url:
                print(f"Project {url}")
                break
        await page.screenshot(path="/tmp/final_working_project.png", full_page=True)

        # Prompt
        prompt_path = "/home/alae/Documents/repos/automation-toolkit/prompts/Build a debug terminal.txt"
        prompt = open(prompt_path).read()
        print(f"Prompt {len(prompt)}")
        chat_sel = '[data-testid="chat-composer-editor"] [role="textbox"]'
        loc = page.locator(chat_sel).first
        await loc.wait_for(timeout=20000)
        print(f"Found chat {chat_sel}")
        await loc.click()
        # Use fill via evaluate to avoid cut
        await page.evaluate("(args)=>{ const [sel,prompt]=args; const el=document.querySelector(sel); if(el){ el.focus(); document.execCommand('insertText', false, prompt); } }", [chat_sel, prompt])
        print("Filled prompt via execCommand")
        val = await page.evaluate("(sel)=>{ const el=document.querySelector(sel); return el?.innerText?.length || 0 }", chat_sel)
        print(f"Chat len after fill {val} expected {len(prompt)}")
        send_sel = '[data-testid="chat-input-send"]'
        btn2 = page.locator(send_sel).first
        await btn2.wait_for(state="visible", timeout=5000)
        print(f"Found send {send_sel}")
        await btn2.click(timeout=5000)
        print(f"Clicked send {send_sel}")
        await page.wait_for_timeout(20000)
        await page.screenshot(path="/tmp/final_working_prompt.png", full_page=True)
        print("Prompt sent")
        for i in range(30):
            loading = await page.evaluate("() => !!document.querySelector('[data-testid=\"loading\"], .loading, [aria-busy=\"true\"], [data-testid=\"chat-timeline\"] > [role=\"status\"]')")
            print(f"Loading {loading} i {i}")
            if not loading:
                break
            await page.wait_for_timeout(10000)
        await page.screenshot(path="/tmp/final_working_after.png", full_page=True)
        url = page.url
        m = re.search(r"/projects/([a-f0-9\-]+)", url)
        if m:
            pid = m.group(1)
            preview = f"https://{pid}.lovableproject.com"
            print(f"Project {pid} Preview {preview}")
            page2 = await ctx.new_page()
            await page2.goto(preview, timeout=30000)
            await page2.wait_for_timeout(8000)
            await page2.screenshot(path="/tmp/final_working_preview.png", full_page=True)
            for cmd in ["doc.connect()", "await doc('pwd')", "await doc('ls')"]:
                try:
                    res = await page2.evaluate(f"async () => {{ try{{ return await {cmd} }}catch(e){{ return e.message }} }}")
                    print(f"Console {cmd} -> {str(res)[:800]}")
                except Exception as e:
                    print(f"Console {cmd} fail {e}")
            await page2.screenshot(path="/tmp/final_working_console.png", full_page=True)
            open("/tmp/final_working_account.txt","w").write(f"genev.aochea@gmail.com\nGmailK01\n{pid}\n{preview}\n")
            print("Saved /tmp/final_working_account.txt")
        print("Done - keeping browser open 30s for inspection")
        print(f"Live view: {LIVE}")
        await page.wait_for_timeout(30000)
        await b.close()
        print("Closed")

if __name__ == "__main__":
    asyncio.run(main())
