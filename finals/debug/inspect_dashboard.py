#!/usr/bin/env python3
"""Load session 8 and inspect dashboard credits and selectors."""

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
    print(f"Dashboard: {config['dashboard_url']}")
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
        print("Navigating to dashboard...")
        await page.goto("https://lovable.dev/dashboard", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)  # Wait for content to load
        
        print("Dashboard loaded!")
        print()
        
        # Get page title
        title = await page.title()
        print(f"Page Title: {title}")
        print()
        
        print("="*60)
        print("SEARCHING FOR CREDITS DISPLAY")
        print("="*60)
        print()
        
        # Look for credit-related text
        body_text = await page.locator("body").inner_text()
        
        # Search for credit keywords
        credit_keywords = [
            "credit", "credits", "balance", "remaining", 
            "usage", "quota", "limit", "tokens", "free"
        ]
        
        print("Text content with credit keywords:")
        for line in body_text.split('\n'):
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in credit_keywords):
                print(f"  → {line.strip()}")
        
        print()
        print("="*60)
        print("ANALYZING ALL SELECTORS")
        print("="*60)
        print()
        
        # Get all text nodes that might contain credits
        print("1. Looking for credit-related elements...")
        
        # Try different selectors for credits
        selectors_to_check = [
            "[data-testid*='credit']",
            "[data-testid*='balance']",
            "[class*='credit']",
            "[class*='balance']",
            "[aria-label*='credit']",
            "[aria-label*='balance']",
            "span:has-text('credit')",
            "div:has-text('credit')",
            "p:has-text('credit')",
            "span:has-text('remaining')",
            "div:has-text('remaining')",
        ]
        
        for selector in selectors_to_check:
            try:
                elements = await page.locator(selector).all()
                if elements:
                    print(f"\n✓ Selector '{selector}': {len(elements)} elements")
                    for i, elem in enumerate(elements[:3]):
                        try:
                            text = await elem.inner_text(timeout=1000)
                            print(f"  [{i}] {text.strip()[:100]}")
                        except:
                            pass
            except:
                pass
        
        print()
        print("2. Analyzing navigation/header area...")
        
        # Check header/nav for credits
        nav_selectors = [
            "header",
            "nav",
            "[role='navigation']",
            "[role='banner']",
        ]
        
        for selector in nav_selectors:
            try:
                nav = page.locator(selector).first
                if await nav.count():
                    text = await nav.inner_text(timeout=2000)
                    print(f"\n✓ {selector}:")
                    for line in text.split('\n'):
                        if line.strip():
                            print(f"  → {line.strip()[:80]}")
            except:
                pass
        
        print()
        print("3. Looking for account menu...")
        
        # Account menu
        account_menu_selectors = [
            "button[aria-label*='Account']",
            "button[aria-label*='account']",
            "button[aria-label*='Menu']",
            "button[aria-label*='menu']",
            "[data-testid='account-menu']",
            "[data-testid='user-menu']",
        ]
        
        for selector in account_menu_selectors:
            try:
                if await page.locator(selector).count():
                    print(f"\n✓ Found: {selector}")
                    
                    # Click to open menu
                    await page.locator(selector).first.click()
                    await page.wait_for_timeout(1000)
                    
                    # Check menu content
                    print("  Menu content:")
                    menu_text = await page.locator("body").inner_text()
                    for line in menu_text.split('\n'):
                        line_lower = line.lower()
                        if any(kw in line_lower for kw in credit_keywords):
                            print(f"    → {line.strip()}")
                    
                    # Close menu
                    await page.keyboard.press("Escape")
                    await page.wait_for_timeout(500)
                    break
            except Exception as e:
                pass
        
        print()
        print("4. Checking all buttons...")
        
        buttons = await page.locator("button").all()
        print(f"\nTotal buttons: {len(buttons)}")
        
        for i, btn in enumerate(buttons[:30]):  # First 30 buttons
            try:
                text = await btn.inner_text(timeout=500)
                aria_label = await btn.get_attribute("aria-label")
                
                if text or aria_label:
                    display = text or aria_label or ""
                    if any(kw in display.lower() for kw in credit_keywords + ["upgrade", "pro", "plan"]):
                        print(f"  Button {i}: {display.strip()[:60]}")
            except:
                pass
        
        print()
        print("5. Checking all links...")
        
        links = await page.locator("a").all()
        print(f"\nTotal links: {len(links)}")
        
        for i, link in enumerate(links[:50]):  # First 50 links
            try:
                text = await link.inner_text(timeout=500)
                href = await link.get_attribute("href")
                
                if text and any(kw in text.lower() for kw in credit_keywords + ["upgrade", "billing", "pricing", "plan"]):
                    print(f"  Link {i}: {text.strip()[:50]} → {href}")
            except:
                pass
        
        print()
        print("6. Getting page HTML structure (looking for credits)...")
        
        # Get HTML and search for credit patterns
        html = await page.content()
        
        import re
        
        # Look for credit numbers
        credit_patterns = [
            r'(\d+)\s*credit',
            r'credit[s]?\s*[:\-]?\s*(\d+)',
            r'(\d+)\s*remaining',
            r'balance[:\-]?\s*(\d+)',
            r'(\d+)\s*/\s*(\d+)',  # Like "5/100"
        ]
        
        print("\nCredit-related patterns found in HTML:")
        for pattern in credit_patterns:
            matches = re.finditer(pattern, html, re.IGNORECASE)
            for match in list(matches)[:5]:  # First 5 matches per pattern
                context_start = max(0, match.start() - 50)
                context_end = min(len(html), match.end() + 50)
                context = html[context_start:context_end]
                # Clean HTML tags
                context_clean = re.sub(r'<[^>]+>', ' ', context)
                print(f"  Pattern '{pattern}': {context_clean.strip()[:100]}")
        
        print()
        print("7. Checking for SVG icons (credit indicators)...")
        
        # Check for SVG icons near credit text
        svgs = await page.locator("svg").all()
        print(f"\nTotal SVG icons: {len(svgs)}")
        
        # Look for SVGs near text with credits
        for i, svg in enumerate(svgs[:20]):
            try:
                # Get parent element
                parent = svg.locator("xpath=..")
                parent_text = await parent.inner_text(timeout=500)
                
                if parent_text and any(kw in parent_text.lower() for kw in credit_keywords):
                    print(f"  SVG {i} near: {parent_text.strip()[:60]}")
            except:
                pass
        
        print()
        print("8. Extracting all data-* attributes...")
        
        # Get all elements with data attributes
        all_elements = await page.locator("[data-testid], [data-test], [data-cy]").all()
        print(f"\nElements with data attributes: {len(all_elements)}")
        
        for i, elem in enumerate(all_elements[:30]):
            try:
                testid = await elem.get_attribute("data-testid") or \
                         await elem.get_attribute("data-test") or \
                         await elem.get_attribute("data-cy")
                text = await elem.inner_text(timeout=500)
                
                if testid:
                    print(f"  [{i}] data-testid='{testid}': {text.strip()[:50]}")
            except:
                pass
        
        print()
        print("="*60)
        print("BODY HTML SAMPLE (first 3000 chars)")
        print("="*60)
        body_html = await page.locator("body").inner_html()
        print(body_html[:3000])
        print("...")
        
        print()
        print("="*60)
        print("COMPLETE ANALYSIS DONE")
        print("="*60)
        print()
        print("✋ Browser staying open. Press Enter to close...")
        input()
        
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
