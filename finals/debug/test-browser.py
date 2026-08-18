#!/usr/bin/env python3
"""
Test Browser - Load session and keep browser open
"""

import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright

# Paths
SESSIONS_DIR = Path("/home/alan/Documents/automation-toolkit/scripts/sessions")

async def main(session_num: int):
    """Load session and keep browser open."""
    
    print("=" * 60)
    print(f"🌐 LOADING SESSION-{session_num}")
    print("=" * 60)
    
    # Load session cookies
    session_dir = SESSIONS_DIR / f"session-{session_num}"
    cookies_file = session_dir / "cookies.json"
    config_file = session_dir / "config.json"
    
    if not cookies_file.exists():
        print(f"❌ Session {session_num} cookies not found!")
        return
    
    if not config_file.exists():
        print(f"❌ Session {session_num} config not found!")
        return
    
    # Load config
    with open(config_file) as f:
        config = json.load(f)
    
    print(f"📧 Email: {config['email']}")
    
    # Load cookies
    with open(cookies_file) as f:
        cookies = json.load(f)
    
    print(f"🍪 Loaded {len(cookies)} cookies")
    
    # Start browser
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        # Add session cookies
        await context.add_cookies(cookies)
        print("✅ Session cookies loaded")
        
        # Go to Lovable dashboard
        print("🚀 Opening Lovable dashboard...")
        await page.goto("https://lovable.dev/dashboard", timeout=60000)
        await page.wait_for_load_state("domcontentloaded")
        
        print("\n" + "=" * 60)
        print("✅ Browser is ready!")
        print("=" * 60)
        print("\nPress Enter to close browser...")
        
        # Keep browser open
        input()
        
        await browser.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 test-browser.py <session_number>")
        print("Example: python3 test-browser.py 9")
        sys.exit(1)
    
    session = int(sys.argv[1])
    asyncio.run(main(session))
