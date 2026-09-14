#!/usr/bin/env python3
"""Minimal Turnstile test — just click the checkbox on a test page."""

import asyncio
import sys

try:
    from patchright.async_api import async_playwright
    PATCHRIGHT = True
except ImportError:
    from playwright.async_api import async_playwright
    PATCHRIGHT = False

try:
    from playwright_captcha import ClickSolver, CaptchaType, FrameworkType
    CAPTCHA_SOLVER = True
except ImportError:
    CAPTCHA_SOLVER = False


async def test_turnstile_click():
    """Test Turnstile click on Cloudflare demo page."""
    
    print(f"🦊 Using: {'Patchright' if PATCHRIGHT else 'Playwright'}")
    print(f"🧩 ClickSolver: {'Available' if CAPTCHA_SOLVER else 'NOT INSTALLED'}")
    
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-ipv6",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        
        page = await context.new_page()
        
        # Navigate to Turnstile demo page
        print("🌐 Loading Cloudflare Turnstile demo...")
        await page.goto("https://demo.turnstile.workers.dev/", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        
        # Wait for Turnstile iframe
        print("⏳ Waiting for Turnstile iframe...")
        try:
            await page.wait_for_selector('iframe[src*="challenges.cloudflare.com"]', timeout=10000)
            print("✅ Turnstile iframe detected")
        except Exception as e:
            print(f"❌ Turnstile iframe not found: {e}")
            await page.screenshot(path="/tmp/turnstile-test-no-iframe.png", full_page=True)
            print("📸 Screenshot: /tmp/turnstile-test-no-iframe.png")
            await browser.close()
            return
        
        turnstile_iframe = page.locator('iframe[src*="challenges.cloudflare.com"]')
        
        # Strategy 1: Direct frame_locator click
        print("\n🎯 Strategy 1: Direct frame_locator click...")
        clicked = False
        try:
            fl = page.frame_locator('iframe[src*="challenges.cloudflare.com"]')
            for sel in ['input[type="checkbox"]', '[role="checkbox"]', 'label', 'span', 'div']:
                try:
                    el = fl.locator(sel).first
                    if await el.count():
                        await page.wait_for_timeout(500)
                        await el.click(timeout=3000, force=True)
                        print(f"  ✅ Clicked via frame_locator({sel})")
                        clicked = True
                        break
                except Exception as e:
                    print(f"  ⚠️ frame_locator({sel}) failed: {e}")
        except Exception as e:
            print(f"  ❌ Strategy 1 failed: {e}")
        
        # Strategy 2: Coordinate click
        if not clicked:
            print("\n🎯 Strategy 2: Coordinate click (22px from left)...")
            try:
                box = await turnstile_iframe.first.bounding_box()
                if box:
                    x = int(box["x"] + 22)
                    y = int(box["y"] + box["height"] / 2)
                    await page.mouse.click(x, y, delay=100)
                    await page.wait_for_timeout(200)
                    await page.mouse.click(x + 5, y, delay=100)
                    print(f"  ✅ Clicked at ({x}, {y})")
                    clicked = True
            except Exception as e:
                print(f"  ❌ Strategy 2 failed: {e}")
        
        # Strategy 3: ClickSolver
        if not clicked and CAPTCHA_SOLVER:
            print("\n🎯 Strategy 3: ClickSolver...")
            fw = FrameworkType.PATCHRIGHT if PATCHRIGHT else FrameworkType.PLAYWRIGHT
            try:
                async with ClickSolver(framework=fw, page=page, max_attempts=2, attempt_delay=2) as solver:
                    await solver.solve_captcha(
                        captcha_container=page,
                        captcha_type=CaptchaType.CLOUDFLARE_TURNSTILE
                    )
                print(f"  ✅ Solved via ClickSolver({fw.name})")
                clicked = True
            except Exception as e:
                print(f"  ❌ ClickSolver failed: {e}")
        
        # Wait for token
        print("\n⏳ Waiting 7s for token generation...")
        await page.wait_for_timeout(7000)
        
        # Check token
        token_len = await page.evaluate(
            '''() => document.querySelector('input[name="cf-turnstile-response"]')?.value?.length || 0'''
        )
        
        print(f"\n📊 Results:")
        print(f"   Clicked: {clicked}")
        print(f"   Token: {token_len} chars")
        
        if token_len > 20:
            print("✅ SUCCESS — Turnstile solved!")
        else:
            print("❌ FAILED — No token generated")
            await page.screenshot(path="/tmp/turnstile-test-failed.png", full_page=True)
            print("📸 Screenshot: /tmp/turnstile-test-failed.png")
        
        # Keep browser open for inspection
        print("\n✋ Browser staying open. Press Enter to close...")
        input()
        
        await browser.close()


if __name__ == "__main__":
    asyncio.run(test_turnstile_click())
