#!/usr/bin/env python3
"""Get Lovable credits - FINAL VERSION with exact selectors."""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from playwright.async_api import async_playwright


async def get_credits(session_num: int, headless: bool = False):
    """Load session and extract credits using exact selectors."""
    
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
            headless=headless,
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
        
        # Wait for workspace menu button to appear, then click
        print("🔍 Waiting for workspace menu button...")
        
        try:
            # Wait for the button to appear (up to 30 seconds)
            menu_button = page.get_by_test_id("workspace-menu-trigger")
            await menu_button.wait_for(state="visible", timeout=30000)
            print("✅ Button visible")
            
            print("🖱️  Clicking workspace menu...")
            await menu_button.click()
            await page.wait_for_timeout(2000)
            print("✅ Menu opened")
        except Exception as e:
            print(f"❌ Failed to click menu: {e}")
            print("\n📸 Taking screenshot...")
            await page.screenshot(path="/tmp/dashboard_error.png")
            print("   Saved: /tmp/dashboard_error.png")
            
            await browser.close()
            return None
        
        print()
        print("💰 Extracting credits...")
        
        # Extract credits from menu
        body_text = await page.locator("body").inner_text()
        
        # Pattern from your HTML: "5 left" or "1.20 left"
        credits_match = re.search(r'(\d+\.?\d*)\s+left', body_text, re.IGNORECASE)
        
        if credits_match:
            credits = credits_match.group(1)
            
            print()
            print("="*60)
            print("💰 CREDITS INFORMATION")
            print("="*60)
            print(f"  Email: {config['email']}")
            print(f"  Credits Left: {credits}")
            print(f"  Session: {session_num}")
            
            # Extract plan info
            plan_match = re.search(r'(Free Plan|Pro Plan|Premium Plan)[^•]*•\s*(\d+)\s*member', body_text, re.IGNORECASE)
            if plan_match:
                print(f"  Plan: {plan_match.group(1)}")
                print(f"  Members: {plan_match.group(2)}")
            
            # Reset info
            if "midnight UTC" in body_text:
                print(f"  Reset: Daily at midnight UTC")
            
            print("="*60)
            print()
            
            result = {
                "email": config['email'],
                "credits": float(credits),
                "session": session_num,
            }
            
        else:
            print("❌ Could not extract credits value")
            print("\n  Searching for credits in menu...")
            
            # Try alternative: find the credits card div
            try:
                credits_card = page.locator("div.group\\/credits-card, [role='menuitem']:has-text('Credits')")
                if await credits_card.count() > 0:
                    card_text = await credits_card.first.inner_text()
                    print(f"\n  Credits card text:\n{card_text}")
                    
                    # Try extracting again
                    match = re.search(r'(\d+\.?\d*)\s+left', card_text, re.IGNORECASE)
                    if match:
                        credits = match.group(1)
                        result = {
                            "email": config['email'],
                            "credits": float(credits),
                            "session": session_num,
                        }
                        print(f"\n  ✅ Found: {credits} credits left")
                    else:
                        result = None
                else:
                    print("  ❌ Credits card not found")
                    result = None
            except Exception as e:
                print(f"  ❌ Error: {e}")
                result = None
        
        print()
        print("✅ SUCCESS: Credits extracted")
        
        if not headless:
            print("✋ Browser staying open. Press Enter to close...")
            input()
        
        await browser.close()
        
        return result


async def main():
    parser = argparse.ArgumentParser(description="Get Lovable credits for a session")
    parser.add_argument("session_number", type=int, help="Session number to check")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode (no browser window)")
    
    args = parser.parse_args()
    
    result = await get_credits(args.session_number, headless=args.headless)
    
    if result:
        print(f"\n✅ SUCCESS: {result['credits']} credits remaining")
    else:
        print("\n❌ Failed to get credits")


if __name__ == "__main__":
    asyncio.run(main())
