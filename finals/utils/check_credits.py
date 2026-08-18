#!/usr/bin/env python3
"""Check Lovable credits for a session."""

import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright


async def check_credits(session_num: int, headless: bool = True, auto_close: bool = False):
    """Load session and check credits."""
    
    session_dir = Path(f"/home/alan/Documents/automation-toolkit/scripts/sessions/session-{session_num}")
    
    if not session_dir.exists():
        print(f"❌ Session {session_num} not found")
        return None
    
    # Load config
    with open(session_dir / "config.json") as f:
        config = json.load(f)
    
    # Load cookies
    with open(session_dir / "cookies.json") as f:
        cookies = json.load(f)
    
    print(f"📧 Email: {config['email']}")
    print(f"🔐 Loading session {session_num}...")
    print()
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="chrome",
            headless=headless,
        )
        
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        await context.add_cookies(cookies)
        
        page = await context.new_page()
        
        # Navigate to dashboard
        print("🌐 Navigating to dashboard...")
        await page.goto("https://lovable.dev/dashboard", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        
        # Close cookie banner if present
        try:
            await page.get_by_testid("consent-accept-all-button").click(timeout=2000)
            await page.wait_for_timeout(500)
        except:
            pass
        
        print("✅ Dashboard loaded")
        print()
        
        # Find account menu button - use the pattern from the HTML you provided
        print("🔍 Looking for account menu button...")
        
        # The button has a dynamic ID pattern like "base-ui-_r_2i_"
        # Try multiple approaches
        
        menu_opened = False
        
        # Approach 1: Look for button with workspace number/avatar in top-right
        try:
            # Find all buttons
            buttons = await page.locator("button").all()
            
            for btn in buttons:
                try:
                    # Check button HTML to see if it contains workspace info
                    html = await btn.inner_html()
                    
                    # Look for patterns that indicate account menu button
                    if ('avatar' in html.lower() and 'workspace' not in html.lower()) or \
                       (btn.locator("span.group\\/avatar").count() > 0):
                        
                        print("  Found potential account menu button, clicking...")
                        await btn.click(timeout=2000)
                        await page.wait_for_timeout(2000)
                        
                        # Check if credits menu appeared
                        body_text = await page.locator("body").inner_text()
                        if "Credits" in body_text and "left" in body_text:
                            print("  ✅ Account menu opened!")
                            menu_opened = True
                            break
                        
                        # Not the right button, press escape
                        await page.keyboard.press("Escape")
                        await page.wait_for_timeout(500)
                except:
                    continue
        except:
            pass
        
        # Approach 2: Look for button with ID starting with "base-ui-"
        if not menu_opened:
            try:
                # Get all buttons with IDs
                buttons_with_ids = await page.locator("button[id^='base-ui-']").all()
                print(f"  Found {len(buttons_with_ids)} buttons with base-ui IDs")
                
                for btn in buttons_with_ids[:5]:  # Try first 5
                    try:
                        btn_id = await btn.get_attribute("id")
                        
                        # Skip known buttons (consent buttons, etc)
                        if "consent" in btn_id or "testid" in str(await btn.get_attribute("data-testid") or ""):
                            continue
                        
                        print(f"  Trying button: {btn_id}")
                        await btn.click(timeout=2000)
                        await page.wait_for_timeout(2000)
                        
                        body_text = await page.locator("body").inner_text()
                        if "Credits" in body_text and "left" in body_text:
                            print("  ✅ Account menu opened!")
                            menu_opened = True
                            break
                        
                        await page.keyboard.press("Escape")
                        await page.wait_for_timeout(500)
                    except:
                        continue
            except:
                pass
        
        # Approach 3: Take screenshot and let user identify
        if not menu_opened:
            print("\n  ⚠️  Automated detection failed")
            await page.screenshot(path="/tmp/dashboard.png")
            print("  📸 Screenshot saved: /tmp/dashboard.png")
            print("\n  Looking for buttons manually in the page...")
            
            # Get all visible buttons
            all_buttons = await page.locator("button:visible").all()
            print(f"  Total visible buttons: {len(all_buttons)}")
        
        if not menu_opened:
            print("❌ Could not find account menu")
            print("\n✋ Browser staying open for manual inspection...")
            input("Press Enter to close...")
            await browser.close()
            return None
        
        print()
        print("💰 Extracting credits information...")
        print()
        
        # Extract credits from the menu
        body_text = await page.locator("body").inner_text()
        
        # Find the credits line
        credits_value = None
        for line in body_text.split('\n'):
            if 'left' in line.lower() and any(char.isdigit() for char in line):
                # Extract number from line like "1.20 left"
                import re
                match = re.search(r'(\d+\.?\d*)\s*left', line, re.IGNORECASE)
                if match:
                    credits_value = match.group(1)
                    break
        
        if credits_value:
            print("="*60)
            print("💰 CREDITS INFORMATION")
            print("="*60)
            print(f"  Email: {config['email']}")
            print(f"  Credits Left: {credits_value}")
            print(f"  Session: {session_num}")
            print("="*60)
            print()
            
            # Also look for plan info
            if "Free Plan" in body_text:
                print("📋 Plan: Free Plan")
            
            if "midnight UTC" in body_text:
                print("🕐 Daily credits reset at midnight UTC")
            
            print()
            
            # Close browser based on auto_close flag
            if auto_close:
                await browser.close()
            else:
                print("✋ Browser staying open. Press Enter to close...")
                input()
                await browser.close()
            
            return credits_value
        else:
            print("❌ Could not extract credits value")
            print("\nMenu content:")
            print("-" * 60)
            # Print relevant lines
            for line in body_text.split('\n'):
                if any(kw in line.lower() for kw in ['credit', 'left', 'free', 'plan', 'reset']):
                    print(f"  {line.strip()}")
            print("-" * 60)
        
        if auto_close:
            await browser.close()
        else:
            print("\n✋ Browser staying open. Press Enter to close...")
            input()
            await browser.close()
        
        return credits_value


async def main():
    if len(sys.argv) < 2:
        print("Usage: python3 check_credits.py <session_number> [--visible] [--end]")
        print("\nExamples:")
        print("  python3 check_credits.py 8              # Headless, browser stays open")
        print("  python3 check_credits.py 8 --visible    # Show browser, stays open")
        print("  python3 check_credits.py 8 --end        # Headless, auto-close")
        print("  python3 check_credits.py 8 --visible --end  # Show browser, auto-close")
        sys.exit(1)
    
    session_num = int(sys.argv[1])
    headless = "--visible" not in sys.argv  # Headless by default
    auto_close = "--end" in sys.argv        # Keep open by default
    
    await check_credits(session_num, headless, auto_close)


if __name__ == "__main__":
    asyncio.run(main())
