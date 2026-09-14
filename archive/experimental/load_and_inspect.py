#!/usr/bin/env python3
"""Load session 8 and inspect lovable.dev/templates page."""

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
        
        # Navigate to templates page
        print("Navigating to templates page...")
        await page.goto("https://lovable.dev/templates", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)  # Wait for content to load
        
        print("Page loaded!")
        print()
        
        # Get all selectors
        print("="*60)
        print("INSPECTING PAGE SELECTORS:")
        print("="*60)
        print()
        
        # Get page title
        title = await page.title()
        print(f"Page Title: {title}")
        print()
        
        # Get main heading
        try:
            heading = await page.locator("h1").first.inner_text(timeout=2000)
            print(f"Main Heading: {heading}")
        except:
            print("Main Heading: Not found")
        print()
        
        # Get all template cards
        print("Looking for template cards...")
        
        # Try different selectors for template cards
        selectors_to_try = [
            "article",
            "[data-testid*='template']",
            "[class*='template']",
            "[class*='card']",
            "a[href*='/template']",
            "a[href*='/create']",
            "button",
        ]
        
        for selector in selectors_to_try:
            try:
                count = await page.locator(selector).count()
                if count > 0:
                    print(f"✓ Selector '{selector}': {count} elements")
                    
                    # Get first few text contents
                    if count <= 10:
                        for i in range(min(3, count)):
                            try:
                                text = await page.locator(selector).nth(i).inner_text(timeout=1000)
                                text_preview = text[:100].replace('\n', ' ')
                                print(f"  [{i}] {text_preview}")
                            except:
                                pass
            except:
                pass
        
        print()
        print("Getting body HTML structure...")
        
        # Get body HTML (first 2000 chars)
        body_html = await page.locator("body").inner_html()
        print()
        print("BODY HTML (first 2000 chars):")
        print("-"*60)
        print(body_html[:2000])
        print("-"*60)
        
        print()
        print("Getting all links...")
        links = await page.locator("a").all()
        print(f"Total links: {len(links)}")
        
        # Get hrefs of first 20 links
        for i, link in enumerate(links[:20]):
            try:
                href = await link.get_attribute("href")
                text = await link.inner_text(timeout=500)
                text_preview = text[:50].replace('\n', ' ').strip() if text else "(no text)"
                print(f"  Link {i}: {href} - {text_preview}")
            except:
                pass
        
        print()
        print("✋ Browser staying open. Press Enter to close...")
        input()
        
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
