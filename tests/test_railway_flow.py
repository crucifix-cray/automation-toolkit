#!/usr/bin/env python3
"""Quick Railway flow test - step by step debugging"""
import asyncio
from playwright.async_api import async_playwright, expect
import re

async def test():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir="/tmp/test_railway_flow",
            channel="chrome",
            headless=False,
            viewport={"width": 1440, "height": 900},
        )
        
        # Block ads
        async def block_ads(route):
            await route.abort()
        
        for pattern in ["**doubleclick.net/**", "**googleadservices.com/**", "**googlesyndication.com/**"]:
            await ctx.route(pattern, block_ads)
        
        inbox = await ctx.new_page()
        railway = await ctx.new_page()
        
        # Step 1: Create 22.do inbox
        print("\n=== Step 1: Creating 22.do inbox ===")
        await inbox.goto("https://22.do/", wait_until="domcontentloaded")
        await inbox.wait_for_timeout(3000)
        
        mail_input = inbox.locator("#mail-input")
        await expect(mail_input).to_be_visible()
        
        # JS click Random to avoid overlay
        prev = await mail_input.input_value()
        print(f"Current email: {prev}")
        for i in range(3):
            await inbox.evaluate("document.getElementById('mail-random')?.click()")
            await inbox.wait_for_timeout(1500)
            curr = await mail_input.input_value()
            if curr != prev:
                print(f"New email generated: {curr}")
                break
        
        email_val = await mail_input.input_value()
        domain_val = await inbox.locator("#mail-choices").input_value()
        email = f"{email_val}{domain_val}" if "@" not in email_val else email_val
        print(f"✓ Email ready: {email}")
        
        # Click Open with JS
        await inbox.evaluate("document.getElementById('into-mailbox')?.click()")
        await expect(inbox).to_have_url(re.compile(r"/inbox/"), timeout=15000)
        print("✓ Inbox opened")
        
        # Step 2: Railway login
        print("\n=== Step 2: Railway login ===")
        await railway.goto("https://railway.com/login", wait_until="domcontentloaded")
        await railway.wait_for_timeout(2000)
        print(f"Railway URL: {railway.url}")
        
        # Click "Log in using email" if visible
        try:
            email_link = railway.get_by_text(re.compile(r"Log in using email", re.I))
            if await email_link.is_visible(timeout=3000):
                print("Clicking 'Log in using email'")
                await email_link.click()
                await railway.wait_for_timeout(1500)
        except:
            print("Email login already shown")
        
        # Fill email
        email_field = railway.locator('input[type="email"]').first
        await expect(email_field).to_be_visible(timeout=10000)
        await email_field.fill(email)
        print(f"✓ Filled email: {email}")
        
        # Click Continue/Send
        continue_btn = railway.get_by_role("button", name=re.compile(r"Continue|Send|Next", re.I)).first
        await expect(continue_btn).to_be_visible()
        print("Clicking Continue/Send button")
        await continue_btn.click()
        await railway.wait_for_timeout(3000)
        
        # Step 3: Wait for code in inbox
        print("\n=== Step 3: Waiting for Railway code ===")
        await inbox.bring_to_front()
        
        code_msg = inbox.get_by_text(re.compile(r"\b\d{6}\s+is your Railway login code\b", re.I)).first
        refresh_btn = inbox.locator("#refresh")
        
        for attempt in range(20):
            try:
                await expect(code_msg).to_be_visible(timeout=5000)
                text = await code_msg.inner_text()
                match = re.search(r"\b(\d{6})\b", text)
                if match:
                    code = match.group(1)
                    print(f"✓ Railway code received: {code}")
                    break
            except:
                print(f"  Attempt {attempt+1}/20 - refreshing...")
                await refresh_btn.click()
                await inbox.wait_for_timeout(3000)
        else:
            print("✗ No code received in 20 attempts")
            await ctx.close()
            return
        
        # Step 4: Enter code
        print("\n=== Step 4: Entering code ===")
        await railway.bring_to_front()
        
        # Check for individual digit inputs
        digit_inputs = railway.locator('input[inputmode="numeric"]')
        count = await digit_inputs.count()
        print(f"Found {count} digit input boxes")
        
        if count >= 6:
            print("Filling digit-by-digit")
            for i, digit in enumerate(code):
                await digit_inputs.nth(i).fill(digit)
                await railway.wait_for_timeout(100)
        else:
            print("Filling single code field")
            code_field = railway.locator('input[type="text"], input[name="code"]').first
            await expect(code_field).to_be_visible(timeout=10000)
            await code_field.fill(code)
        
        print("✓ Code filled")
        await railway.wait_for_timeout(2000)
        
        # Check if auto-submitted or need to click Verify
        if "/dashboard" not in railway.url:
            try:
                verify_btn = railway.get_by_role("button", name=re.compile(r"Verify|Continue|Submit", re.I)).first
                if await verify_btn.is_visible(timeout=3000):
                    print("Clicking Verify button")
                    await verify_btn.click()
            except:
                print("No verify button found (maybe auto-submitted)")
        
        await railway.wait_for_timeout(5000)
        print(f"\n✓✓✓ Final URL: {railway.url}")
        
        if "/dashboard" in railway.url:
            print("✅ SUCCESS - Logged in to Railway!")
        else:
            print("⚠️  Not on dashboard yet")
        
        await railway.screenshot(path="/tmp/railway_final.png", full_page=True)
        print("Screenshot: /tmp/railway_final.png")
        
        print("\nPress Ctrl+C to close browser...")
        await asyncio.sleep(300)
        await ctx.close()

asyncio.run(test())
