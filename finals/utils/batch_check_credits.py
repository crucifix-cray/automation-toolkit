#!/usr/bin/env python3
"""Batch check credits for all sessions - headless and fast."""

import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright


async def check_one_session(session_num: int) -> tuple[int, float | None, str]:
    """Check credits for one session. Returns (session_num, credits, email)."""
    
    session_dir = Path(f"/home/alan/Documents/automation-toolkit/scripts/sessions/session-{session_num}")
    
    if not session_dir.exists():
        return (session_num, None, "not found")
    
    try:
        # Load config
        with open(session_dir / "config.json") as f:
            config = json.load(f)
        email = config.get('email', 'unknown')
        
        # Load cookies
        with open(session_dir / "cookies.json") as f:
            cookies = json.load(f)
    except Exception as e:
        return (session_num, None, f"error: {e}")
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                channel="chrome",
                headless=True,
            )
            
            context = await browser.new_context(viewport={"width": 1440, "height": 900})
            await context.add_cookies(cookies)
            
            page = await context.new_page()
            
            # Navigate to dashboard
            await page.goto("https://lovable.dev/dashboard", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            
            # Close cookie banner if present
            try:
                await page.get_by_testid("consent-accept-all-button").click(timeout=2000)
                await page.wait_for_timeout(500)
            except:
                pass
            
            # Find and click account menu - SAME METHOD AS WORKING SCRIPT
            menu_opened = False
            
            # Try buttons with base-ui IDs
            try:
                buttons_with_ids = await page.locator("button[id^='base-ui-']").all()
                
                for btn in buttons_with_ids[:10]:  # Try first 10
                    try:
                        btn_id = await btn.get_attribute("id")
                        
                        # Skip known buttons
                        if "consent" in (btn_id or ""):
                            continue
                        
                        await btn.click(timeout=2000)
                        await page.wait_for_timeout(2000)
                        
                        body_text = await page.locator("body").inner_text()
                        if "Credits" in body_text and "left" in body_text:
                            menu_opened = True
                            break
                        
                        await page.keyboard.press("Escape")
                        await page.wait_for_timeout(500)
                    except:
                        continue
            except:
                pass
            
            if not menu_opened:
                await browser.close()
                return (session_num, None, email)
            
            # Extract credits from the menu - SAME METHOD
            body_text = await page.locator("body").inner_text()
            
            credits_value = None
            for line in body_text.split('\n'):
                if 'left' in line.lower() and any(char.isdigit() for char in line):
                    import re
                    match = re.search(r'(\d+\.?\d*)\s*left', line, re.IGNORECASE)
                    if match:
                        credits_value = float(match.group(1))
                        break
            
            await browser.close()
            return (session_num, credits_value, email)
            
    except Exception as e:
        return (session_num, None, f"{email} (error: {str(e)[:50]})")


async def main():
    """Check all sessions 1-10."""
    
    print("🔍 Checking credits for all sessions...\n")
    
    tasks = [check_one_session(i) for i in range(1, 11)]
    results = await asyncio.gather(*tasks)
    
    # Print results
    print("=" * 60)
    print("CREDIT REPORT")
    print("=" * 60)
    
    above_3 = []
    
    for session_num, credits, email in sorted(results):
        if credits is None:
            print(f"Session {session_num:2d}: ❌ {email}")
        else:
            emoji = "✅" if credits >= 3 else "⚠️ "
            print(f"Session {session_num:2d}: {emoji} {credits:.1f} credits - {email}")
            if credits >= 3:
                above_3.append((session_num, credits, email))
    
    print("=" * 60)
    
    if above_3:
        print(f"\n🎉 Sessions with ≥3 credits: {len(above_3)}")
        for session_num, credits, email in above_3:
            print(f"  • Session {session_num}: {credits:.1f} credits ({email})")
    else:
        print("\n❌ No sessions with ≥3 credits found")


if __name__ == "__main__":
    asyncio.run(main())
