#!/usr/bin/env python3
"""Quick test to open browser with WARP and ad blocker"""
import asyncio
import subprocess
from playwright.async_api import async_playwright

async def load_cookies_from_file(context, cookie_file: str) -> None:
    """Load cookies from Netscape format file."""
    import os
    
    if not os.path.exists(cookie_file):
        print(f"⚠️  Cookie file not found: {cookie_file}", flush=True)
        return
    
    print(f"🍪 Loading cookies from {cookie_file}...", flush=True)
    
    cookies = []
    with open(cookie_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            parts = line.split('\t')
            if len(parts) < 7:
                continue
            
            domain, _, path, secure, expires, name, value = parts[:7]
            
            cookie = {
                'name': name,
                'value': value,
                'domain': domain,
                'path': path,
                'expires': int(float(expires)) if expires != '0' else -1,
                'httpOnly': False,
                'secure': secure == 'TRUE',
                'sameSite': 'Lax'
            }
            cookies.append(cookie)
    
    if cookies:
        await context.add_cookies(cookies)
        print(f"✅ Loaded {len(cookies)} cookies", flush=True)

async def rotate_warp_ip() -> None:
    """Rotate WARP IP by restarting WireGuard."""
    print("🔄 Rotating WARP IP...", flush=True)
    try:
        subprocess.run(['sudo', 'wg-quick', 'down', 'wgcf'], capture_output=True, timeout=10)
        await asyncio.sleep(2)
        subprocess.run(['sudo', 'wg-quick', 'up', 'wgcf'], capture_output=True, timeout=10)
        await asyncio.sleep(3)
        print("✅ WARP IP rotated", flush=True)
    except Exception as e:
        print(f"⚠️  WARP rotation failed: {e}", flush=True)

async def install_ad_blocker(page):
    """Install ad blocker via JavaScript injection."""
    print("🛡️  Installing ad blocker...", flush=True)
    await page.add_init_script("""
        // Block ads and tracking
        const blockedDomains = ['ads', 'analytics', 'tracking', 'doubleclick', 'googlesyndication'];
        const originalFetch = window.fetch;
        window.fetch = function(...args) {
            const url = args[0].toString();
            if (blockedDomains.some(domain => url.includes(domain))) {
                return Promise.reject(new Error('Blocked by ad blocker'));
            }
            return originalFetch.apply(this, args);
        };
    """)
    print("✅ Ad blocker installed", flush=True)

async def main():
    # Step 1: Rotate WARP IP
    print("\n" + "="*60)
    print("STEP 1: Rotating WARP IP")
    print("="*60 + "\n")
    await rotate_warp_ip()
    
    # Step 2: Launch browser
    print("\n" + "="*60)
    print("STEP 2: Opening browser")
    print("="*60 + "\n")
    
    async with async_playwright() as p:
        print("🚀 Launching Chrome browser...", flush=True)
        context = await p.chromium.launch_persistent_context(
            user_data_dir="/tmp/test-warp-browser",
            headless=False,
            channel="chrome",
        )
        
        page = await context.new_page()
        
        # Step 3: Install ad blocker
        print("\n" + "="*60)
        print("STEP 3: Installing ad blocker")
        print("="*60 + "\n")
        await install_ad_blocker(page)
        
        # Step 4: Check IP
        print("\n" + "="*60)
        print("STEP 4: Checking IP address")
        print("="*60 + "\n")
        print("🌐 Navigating to Cloudflare trace...", flush=True)
        await page.goto("https://www.cloudflare.com/cdn-cgi/trace")
        await page.wait_for_timeout(3000)
        
        body = await page.locator("body").inner_text()
        print("\n" + "="*60)
        print("Current IP Info:")
        print("="*60)
        print(body)
        print("="*60 + "\n")
        
        input("\n✅ Browser is open. Press Enter to close...")
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
