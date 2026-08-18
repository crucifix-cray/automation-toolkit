#!/usr/bin/env python3
"""Deep inspection for credits - check account menu, settings, billing."""

import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright


async def main():
    # Load session 8
    session_dir = Path("/home/alan/Documents/automation-toolkit/scripts/sessions/session-8")
    
    with open(session_dir / "config.json") as f:
        config = json.load(f)
    
    with open(session_dir / "cookies.json") as f:
        cookies = json.load(f)
    
    print(f"Loading session: {config['email']}")
    print()
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="chrome",
            headless=False,
        )
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        await context.add_cookies(cookies)
        
        page = await context.new_page()
        
        # Navigate to dashboard
        print("1. Loading dashboard...")
        await page.goto("https://lovable.dev/dashboard", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        
        # Close cookie banner if present
        try:
            await page.get_by_testid("consent-accept-all-button").click(timeout=2000)
            await page.wait_for_timeout(500)
        except:
            pass
        
        print("✓ Dashboard loaded")
        print()
        
        # Check for account menu
        print("2. Looking for account menu...")
        
        account_menu_found = False
        menu_selectors = [
            'button[aria-label*="Account"]',
            'button[aria-label*="account"]',
            'button[aria-label*="User"]',
            'button[aria-label*="Profile"]',
            '[data-testid*="account"]',
            '[data-testid*="user"]',
            '[data-testid*="profile"]',
        ]
        
        for selector in menu_selectors:
            try:
                if await page.locator(selector).count() > 0:
                    print(f"✓ Found account menu: {selector}")
                    
                    # Click to open
                    await page.locator(selector).first.click()
                    await page.wait_for_timeout(2000)
                    
                    # Get menu content
                    body_text = await page.locator("body").inner_text()
                    print("\nAccount Menu Content:")
                    print("-" * 60)
                    
                    # Look for credit/billing/upgrade items
                    for line in body_text.split('\n'):
                        line_clean = line.strip()
                        if line_clean and len(line_clean) < 100:
                            if any(kw in line_clean.lower() for kw in [
                                'credit', 'balance', 'usage', 'plan', 'upgrade',
                                'billing', 'subscription', 'free', 'pro', 'pricing',
                                'settings', 'profile', 'account'
                            ]):
                                print(f"  → {line_clean}")
                    
                    print("-" * 60)
                    
                    # Take screenshot
                    await page.screenshot(path="/tmp/account_menu.png")
                    print("\n✓ Screenshot saved: /tmp/account_menu.png")
                    
                    account_menu_found = True
                    
                    # Try to find settings/billing links
                    print("\n3. Looking for Settings/Billing links...")
                    
                    links = await page.locator("a").all()
                    for link in links:
                        try:
                            href = await link.get_attribute("href")
                            text = await link.inner_text(timeout=500)
                            
                            if href and text:
                                if any(kw in href.lower() or kw in text.lower() for kw in [
                                    'settings', 'billing', 'account', 'profile', 
                                    'subscription', 'plan', 'upgrade', 'pricing'
                                ]):
                                    print(f"  Link: {text} → {href}")
                        except:
                            pass
                    
                    break
            except Exception as e:
                pass
        
        if not account_menu_found:
            print("❌ No account menu found")
            print("\nTrying alternative approaches...")
            
            # Check top-right corner for user avatar/button
            print("\n4. Checking top-right corner...")
            
            # Get all buttons
            buttons = await page.locator("button").all()
            print(f"\nTotal buttons on page: {len(buttons)}")
            
            for i, btn in enumerate(buttons):
                try:
                    aria_label = await btn.get_attribute("aria-label")
                    text = await btn.inner_text(timeout=500)
                    
                    print(f"  Button {i}:")
                    print(f"    aria-label: {aria_label}")
                    print(f"    text: {text.strip()[:50] if text else '(empty)'}")
                    
                    # Try clicking if it looks like account-related
                    if aria_label and any(kw in aria_label.lower() for kw in ['menu', 'account', 'user']):
                        print(f"    → Clicking this button...")
                        await btn.click()
                        await page.wait_for_timeout(2000)
                        
                        # Check what appeared
                        body_text = await page.locator("body").inner_text()
                        print("\n    Menu appeared:")
                        for line in body_text.split('\n')[:30]:
                            if line.strip():
                                print(f"      {line.strip()[:70]}")
                        
                        # Screenshot
                        await page.screenshot(path=f"/tmp/menu_{i}.png")
                        print(f"\n    ✓ Screenshot: /tmp/menu_{i}.png")
                        
                        # Close by pressing Escape
                        await page.keyboard.press("Escape")
                        await page.wait_for_timeout(500)
                except Exception as e:
                    pass
        
        print()
        print("5. Checking direct URLs...")
        
        # Try direct navigation to common pages
        urls_to_check = [
            ("https://lovable.dev/settings", "Settings"),
            ("https://lovable.dev/account", "Account"),
            ("https://lovable.dev/billing", "Billing"),
            ("https://lovable.dev/profile", "Profile"),
            ("https://lovable.dev/subscription", "Subscription"),
            ("https://lovable.dev/pricing", "Pricing"),
            ("https://lovable.dev/plans", "Plans"),
        ]
        
        for url, name in urls_to_check:
            try:
                print(f"\n  Trying {name}: {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=10000)
                await page.wait_for_timeout(2000)
                
                title = await page.title()
                print(f"    Title: {title}")
                
                # Check for credits
                body_text = await page.locator("body").inner_text()
                
                credit_found = False
                for line in body_text.split('\n'):
                    if any(kw in line.lower() for kw in ['credit', 'balance', 'usage', 'remaining']):
                        print(f"    → {line.strip()[:80]}")
                        credit_found = True
                
                if credit_found:
                    # Take screenshot
                    safe_name = name.lower().replace(' ', '_')
                    await page.screenshot(path=f"/tmp/{safe_name}.png")
                    print(f"    ✓ Screenshot: /tmp/{safe_name}.png")
                    print("\n    ✅ CREDITS FOUND ON THIS PAGE!")
                    
                    # Get all text content
                    print("\n    Full page text:")
                    print("    " + "-" * 56)
                    for line in body_text.split('\n')[:50]:
                        if line.strip():
                            print(f"    {line.strip()[:70]}")
                    print("    " + "-" * 56)
            except Exception as e:
                print(f"    ❌ Not accessible: {e}")
        
        print()
        print("6. Analyzing page structure for credit display...")
        
        # Go back to dashboard
        await page.goto("https://lovable.dev/dashboard", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        
        # Get all elements and analyze structure
        html = await page.content()
        
        # Look for credit-related data attributes or classes
        import re
        
        patterns_to_find = [
            r'data-[^=]*credit[^=]*="([^"]*)"',
            r'class="[^"]*credit[^"]*"',
            r'aria-label="[^"]*credit[^"]*"',
            r'id="[^"]*credit[^"]*"',
        ]
        
        print("\nSearching HTML for credit-related attributes:")
        for pattern in patterns_to_find:
            matches = re.finditer(pattern, html, re.IGNORECASE)
            for match in list(matches)[:5]:
                context_start = max(0, match.start() - 100)
                context_end = min(len(html), match.end() + 100)
                context = html[context_start:context_end]
                context_clean = re.sub(r'<[^>]+>', ' ', context).strip()
                print(f"  → {context_clean[:100]}")
        
        print()
        print("="*60)
        print("INSPECTION COMPLETE")
        print("="*60)
        print()
        print("Screenshots saved in /tmp/")
        print("✋ Browser staying open. Press Enter to close...")
        input()
        
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
