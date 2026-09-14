#!/usr/bin/env python3
"""
Inside-namespace check for GitHub Actions (obni-style):
Runs INSIDE the WARP network namespace, opens Chromium on the Xvfb
display, and reports the egress IP the browser actually sees.

Usage (from workflow, inside the namespace):
    sudo ip netns exec warp-<id> sudo -u runner env DISPLAY=:99 HOME=/home/runner \
        python3 finals/core/gh_warp_xvfb_check.py
"""

import asyncio
import os
import sys


async def main():
    display = os.environ.get("DISPLAY", ":99")
    print(f"DISPLAY={display}", flush=True)

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("FAIL: playwright not installed", flush=True)
        sys.exit(1)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=["--no-sandbox"])
        page = await browser.new_page()
        await page.goto("https://www.cloudflare.com/cdn-cgi/trace", timeout=30000)
        await page.wait_for_timeout(2000)
        content = await page.content()

        print("--- browser egress trace ---", flush=True)
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith(("ip=", "warp=", "colo=", "loc=")):
                print(line, flush=True)
        print("--- end trace ---", flush=True)

        if "warp=on" not in content:
            print("WARN: browser is NOT going through WARP", flush=True)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())