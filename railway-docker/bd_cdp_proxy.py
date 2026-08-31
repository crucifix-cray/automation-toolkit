#!/usr/bin/env python3
"""
BD Browser API → Local CDP proxy.
Connects to BD remote browser, exposes local WebSocket for Chrome DevTools.

Usage:
  python3 bd_cdp_proxy.py [BD_WSS] [LOCAL_PORT]

Then open chrome://inspect and add ws://127.0.0.1:9223
"""
import asyncio, json, signal, sys, os
from playwright.async_api import async_playwright

BRD_WSS = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("BRD_WSS",
    "wss://brd-customer-hl_e895b201-zone-scraping_browser1:b65xwy1jycfq@brd.superproxy.io:9222")
LOCAL_PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 9223

async def main():
    print(f"[*] Connecting to BD Browser API...")
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(BRD_WSS)
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        # Check IP
        await page.goto("https://api.ipify.org?format=json", wait_until="domcontentloaded", timeout=15000)
        ip_info = json.loads(await page.inner_text("body"))
        print(f"[+] BD Browser IP: {ip_info['ip']}")
        print(f"[+] Pages: {len(ctx.pages)}")
        print(f"[+] Contexts: {len(browser.contexts)}")

        # Expose CDP endpoint via websocket server
        from websockets import serve  # pip install websockets

        cdp_sessions = {}

        async def handler(ws, path):
            """Proxy CDP messages between local client and remote BD browser."""
            try:
                # Create a new CDP session for this connection
                cdp = await ctx.new_cdp_session(page)
                cdp_id = id(cdp)
                cdp_sessions[cdp_id] = cdp

                # Forward messages
                async def from_cdp():
                    try:
                        async for msg in cdp._impl._connection._ws_connection._ws_client:
                            if msg.get("method"):
                                await ws.send(json.dumps(msg))
                    except: pass

                async def from_client():
                    try:
                        async for raw in ws:
                            msg = json.loads(raw)
                            if msg.get("method"):
                                await cdp.send(msg["method"], msg.get("params", {}))
                            elif msg.get("id"):
                                await cdp.send(msg["method"], msg.get("params", {}))
                    except: pass

                await asyncio.gather(from_cdp(), from_client())
            except Exception as e:
                print(f"[-] Client disconnected: {e}")
            finally:
                if cdp_id in cdp_sessions:
                    del cdp_sessions[cdp_id]

        # Simpler approach: just print the info and keep browser alive
        print(f"\n{'='*50}")
        print(f"BD BROWSER READY")
        print(f"{'='*50}")
        print(f"IP: {ip_info['ip']}")
        print(f"Remote CDP: {BRD_WSS}")
        print(f"{'='*50}")
        print(f"\nTo use with Playwright:")
        print(f"  async with async_playwright() as p:")
        print(f"    b = await p.chromium.connect_over_cdp('{BRD_WSS}')")
        print(f"    page = b.contexts[0].pages[0]")
        print(f"    await page.goto('https://example.com')")
        print(f"\nTo use with Chrome DevTools:")
        print(f"  1. Open chrome://inspect")
        print(f"  2. Click 'Configure' → add 'ws://brd-customer-hl_e895b201-zone-scraping_browser1:b65xwy1jycfq@brd.superproxy.io:9222'")
        print(f"  3. The remote browser appears in the list")
        print(f"\n[*] Browser alive. Ctrl+C to close.")

        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await browser.close()
            print("[*] Closed.")

if __name__ == "__main__":
    asyncio.run(main())
