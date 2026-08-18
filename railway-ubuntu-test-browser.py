#!/usr/bin/env python3
"""
Test browser in Railway Ubuntu terminal
"""
import asyncio
from patchright.async_api import async_playwright

async def test_browser():
    print("="*60)
    print("🎭 TESTING PLAYWRIGHT CHROMIUM IN RAILWAY")
    print("="*60)
    print()
    
    try:
        async with async_playwright() as p:
            print("📦 Launching Chromium (headless)...")
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--no-first-run',
                    '--no-zygote',
                    '--disable-gpu'
                ]
            )
            print("✅ Browser launched!")
            
            print("📄 Creating new page...")
            page = await browser.new_page()
            print("✅ Page created!")
            
            print("🌐 Navigating to Railway.com...")
            await page.goto('https://railway.com', timeout=30000)
            print("✅ Navigation successful!")
            
            title = await page.title()
            print(f"📝 Page title: {title}")
            
            await browser.close()
            print("✅ Browser closed!")
            
            print()
            print("="*60)
            print("🎉 ALL TESTS PASSED!")
            print("="*60)
            return True
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_browser())
    exit(0 if success else 1)
