#!/usr/bin/env python3
import asyncio, json, os
from playwright.async_api import async_playwright

BRD_WSS = os.environ.get("BRD_WSS",
    "wss://brd-customer-hl_e895b201-zone-scraping_browser1:b65xwy1jycfq@brd.superproxy.io:9222")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(BRD_WSS)
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto("https://api.ipify.org?format=json", wait_until="domcontentloaded", timeout=15000)
        ip = json.loads(await page.inner_text("body"))["ip"]
        print(f"[+] BD alive | IP: {ip} | WSS: {BRD_WSS}", flush=True)
        # Keep alive forever
        while True:
            await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
