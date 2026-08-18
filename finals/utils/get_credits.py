#!/usr/bin/env python3
"""Get Lovable credits - using exact selectors from inspected HTML."""

import asyncio
import json
import re
import sys
from pathlib import Path
from playwright.async_api import async_playwright


async def get_credits(session_num: int):
    """Load session and extract credits."""
    
    session_dir = Path(f"/home/alan/Documents/automation-toolkit/scripts/sessions/session-{session_num}")
    
    if not session_dir.exists():
        print(f"❌ Session {session_num} not found")
        return None
    
    with open(session_dir / "config.json") as f:
        config = json.load(f)
    
    with open(session_dir / "cookies.json") as f:
        cookies = json.load(f)
    
    print(f"📧 Email: {config['email']}")
    print(f"🔐 Session: {session_num}")
    print()
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="chrome",
            headless=False,
        )
        
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        await context.add_cookies(cookies)
        
        page = await context.new_page()
        
        print("🌐 Loading dashboard...")
        await page.goto("https://lovable.dev/dashboard", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        
        # Close cookie banner
        try:
            await page.get_by_testid("consent-accept-all-button").click(timeout=2000)
            await page.wait_for_timeout(1000)
        except:
            pass
        
        print("✅ Dashboard loaded")
        print()
        
        # Based on your HTML, the account menu button contains:
        # - A span with class containing "group/avatar"
        # - Or workspace number like "33"
        # - Located in top-right area
        
        print("🔍 Finding account menu button...")
        
        # Strategy: Click the workspace avatar button (has the "3" or workspace number)
        # From your HTML: <span class="...group/avatar..." translate="no">3</span>
        
        menu_button = None
        
        # Try to find button containing avatar span
        try:
            # Look for button that has nested structure with workspace indicator
            buttons = await page.locator("button").all()
            
            for btn in buttons:
                try:
                    html = await btn.inner_html()
                    text = await btn.inner_text(timeout=500)
                    
                    # From your HTML: workspace has number like "33" and "Free Plan"
                    # The button contains avatar with workspace number
                    if "group/avatar" in html or ("translate=\"no\"" in html and text.strip().isdigit()):
                        # Check if this is in top area (not sidebar)
                        box = await btn.bounding_box()
                        if box and box['y'] < 100 and box['x'] > 1000:  # Top-right corner
                            menu_button = btn
                            print(f"  ✓ Found button at ({box['x']:.0f}, {box['y']:.0f})")
                            break
                except:
                    continue
        except Exception as e:
            print(f"  ⚠️  Search error: {e}")
        
        if not menu_button:
            print("  ❌ Could not find account menu button automatically")
            print("\n  📸 Taking screenshot for manual inspection...")
            await page.screenshot(path="/tmp/dashboard_full.png", full_page=True)
            print("     Saved: /tmp/dashboard_full.png")
            print("\n  🖱️  Click the workspace button manually in the browser")
            print("     (top-right corner, shows workspace number)")
            print("\n  Press Enter after clicking...")
            input()
        else:
            # Click the menu button
            print("  🖱️  Clicking account menu...")
            await menu_button.click()
            await page.wait_for_timeout(2000)
        
        # Now extract credits from the opened menu
        print()
        print("💰 Extracting credits...")
        
        body_text = await page.locator("body").inner_text()
        
        # From your HTML: <p class="text-base font-normal md:text-sm text-tertiary-pulse">1.20 left</p>
        # Pattern: "X.XX left" or "X left"
        
        credits_match = re.search(r'(\d+\.?\d*)\s+left', body_text, re.IGNORECASE)
        
        if credits_match:
            credits = credits_match.group(1)
            
            print()
            print("="*60)
            print("💰 CREDITS FOUND")
            print("="*60)
            print(f"  Email: {config['email']}")
            print(f"  Credits Left: {credits}")
            print(f"  Session: {session_num}")
            
            # Look for plan info
            if "Free Plan" in body_text:
                print(f"  Plan: Free Plan")
            
            # Look for reset info
            reset_match = re.search(r'Daily credits reset at (.*)', body_text, re.IGNORECASE)
            if reset_match:
                print(f"  Reset: {reset_match.group(1).strip()}")
            
            print("="*60)
            print()
            
            result = {
                "email": config['email'],
                "credits": float(credits),
                "session": session_num,
            }
            
        else:
            print("❌ Could not extract credits from menu")
            print("\n  Menu content:")
            print("  " + "-"*56)
            for line in body_text.split('\n')[:50]:
                if line.strip():
                    print(f"  {line.strip()[:70]}")
            print("  " + "-"*56)
            result = None
        
        print()
        print("✋ Browser staying open. Press Enter to close...")
        input()
        
        await browser.close()
        
        return result


async def main():
    if len(sys.argv) < 2:
        print("Usage: python3 get_credits.py <session_number>")
        print("\nExample: python3 get_credits.py 8")
        sys.exit(1)
    
    session_num = int(sys.argv[1])
    result = await get_credits(session_num)
    
    if result:
        print(f"\n✅ Credits: {result['credits']}")
    else:
        print("\n❌ Failed to get credits")


if __name__ == "__main__":
    asyncio.run(main())
