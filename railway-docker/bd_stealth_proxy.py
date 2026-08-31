#!/usr/bin/env python3
"""
Stealth local Chromium via BD ISP proxy. Exposes CDP endpoint.
Connect: chrome://inspect → Configure → add the CDP URL from output
"""
import asyncio, json, os, signal, sys

from playwright.async_api import async_playwright
try:
    from playwright_stealth import stealth_async
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

PROXY = {
    "server": "brd.superproxy.io:44445",
    "username": "brd-customer-hl_7357e514-zone-isp_proxy1",
    "password": "n7pq7twhpas9",
}

CDP_PORT = int(os.environ.get("CDP_PORT", "9222"))

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            proxy=PROXY,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=AutomationControlled",
                "--disable-infobars",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--window-size=1366,768",
                "--start-maximized",
                f"--remote-debugging-port={CDP_PORT}",
                "--remote-debugging-address=127.0.0.1",
            ],
        )

        ctx = browser.contexts[0] if browser.contexts else await browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="America/New_York",
        )

        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        if HAS_STEALTH:
            await stealth_async(page)
            print("[+] Stealth applied")

        # Extra anti-detection
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            window.chrome = {runtime: {}};
            Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 0});
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
        """)

        # Check IP
        await page.goto("https://api.ipify.org?format=json", wait_until="domcontentloaded", timeout=20000)
        ip = json.loads(await page.inner_text("body"))["ip"]

        # Check detection
        await page.goto("https://bot.sannysoft.com", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)

        print(f"\n{'='*55}")
        print(f"  STEALTH BROWSER LIVE")
        print(f"{'='*55}")
        print(f"  IP:       {ip}")
        print(f"  Proxy:    BD ISP (US/NY)")
        print(f"  CDP:      http://127.0.0.1:{CDP_PORT}")
        print(f"  Stealth:  {'ON' if HAS_STEALTH else 'OFF'}")
        print(f"{'='*55}")
        print(f"  Connect from another terminal:")
        print(f"    python3 -c \"")
        print(f"    from playwright.sync_api import sync_playwright")
        print(f"    p = sync_playwright().start()")
        print(f"    b = p.chromium.connect_over_cdp('http://127.0.0.1:{CDP_PORT}')")
        print(f"    page = b.contexts[0].pages[0]")
        print(f"    page.goto('https://example.com')\"")
        print(f"{'='*55}")
        print(f"  Ctrl+C to stop.\n", flush=True)

        stop = asyncio.Event()
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
        await stop.wait()

        await browser.close()
        print("[*] Closed.")

if __name__ == "__main__":
    asyncio.run(main())
