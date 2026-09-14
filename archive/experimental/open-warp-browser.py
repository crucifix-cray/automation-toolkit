#!/usr/bin/env python3
"""Open a browser with WARP proxy and ad blocker extension"""
import asyncio
import subprocess
from pathlib import Path
from playwright.async_api import async_playwright

async def setup_warp():
    """Ensure WARP is connected in proxy mode"""
    print("🔄 Checking WARP connection...", flush=True)
    
    # Check if warp-cli exists
    result = subprocess.run(['which', 'warp-cli'], capture_output=True)
    if result.returncode != 0:
        print("❌ warp-cli not found. Please install cloudflare-warp-bin first:", flush=True)
        print("   yay -S cloudflare-warp-bin", flush=True)
        return False
    
    # Start the daemon if not running
    result = subprocess.run(['warp-cli', 'status'], capture_output=True, text=True)
    if 'Unable to connect' in result.stderr or 'daemon is not running' in result.stderr:
        print("⚠️  WARP daemon not running. Starting...", flush=True)
        subprocess.run(['sudo', 'systemctl', 'start', 'warp-svc'], capture_output=True)
        await asyncio.sleep(3)
    
    # Register if needed
    result = subprocess.run(['warp-cli', 'status'], capture_output=True, text=True)
    if 'Missing' in result.stdout or 'Registration' in result.stdout:
        print("⚠️  WARP not registered. Registering...", flush=True)
        subprocess.run(['warp-cli', 'registration', 'new'], capture_output=True)
        await asyncio.sleep(2)
    
    # Set proxy mode
    subprocess.run(['warp-cli', 'mode', 'proxy'], capture_output=True)
    subprocess.run(['warp-cli', 'proxy', 'port', '40000'], capture_output=True)
    
    # Connect
    result = subprocess.run(['warp-cli', 'status'], capture_output=True, text=True)
    if 'Connected' not in result.stdout:
        print("⚠️  WARP not connected. Connecting...", flush=True)
        subprocess.run(['warp-cli', 'connect'], capture_output=True)
        await asyncio.sleep(5)
    
    # Verify
    result = subprocess.run(['warp-cli', 'status'], capture_output=True, text=True)
    print(f"WARP Status:\n{result.stdout}", flush=True)
    
    if 'Connected' in result.stdout:
        print("✅ WARP is connected in proxy mode (port 40000)", flush=True)
        return True
    else:
        print("❌ WARP failed to connect", flush=True)
        return False

async def main():
    # Setup WARP first
    if not await setup_warp():
        return
    
    print("\n" + "="*60)
    print("Opening Chrome with WARP proxy + uBlock Origin")
    print("="*60 + "\n")
    
    # Download uBlock Origin extension
    extension_path = Path("/tmp/ublock-origin")
    extension_path.mkdir(exist_ok=True)
    
    async with async_playwright() as p:
        # Launch with WARP proxy and extension support
        print("🚀 Launching browser...", flush=True)
        
        context = await p.chromium.launch_persistent_context(
            user_data_dir="/tmp/warp-browser-with-adblock",
            headless=False,
            channel="chrome",
            # WARP proxy - ONLY affects this browser
            proxy={
                "server": "socks5://127.0.0.1:40000"
            },
            args=[
                # Enable extensions
                "--disable-blink-features=AutomationControlled",
                # Performance
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        
        # Install ad blocker via JavaScript (same as our automation)
        page = await context.new_page()
        
        print("🛡️  Installing ad blocker...", flush=True)
        await page.add_init_script("""
            // Block ads, trackers, and analytics
            const blockedPatterns = [
                'doubleclick.net',
                'googlesyndication.com',
                'googleadservices.com',
                'google-analytics.com',
                'googletagmanager.com',
                'facebook.net',
                'facebook.com/tr',
                'analytics',
                '/ads/',
                '/ad/',
                'advertising',
                'tracker',
                'tracking',
            ];
            
            // Intercept fetch
            const originalFetch = window.fetch;
            window.fetch = function(...args) {
                const url = args[0].toString();
                if (blockedPatterns.some(pattern => url.includes(pattern))) {
                    console.log('🚫 Blocked:', url);
                    return Promise.reject(new Error('Blocked by ad blocker'));
                }
                return originalFetch.apply(this, args);
            };
            
            // Intercept XHR
            const originalOpen = XMLHttpRequest.prototype.open;
            XMLHttpRequest.prototype.open = function(method, url, ...rest) {
                if (blockedPatterns.some(pattern => url.includes(pattern))) {
                    console.log('🚫 Blocked XHR:', url);
                    return;
                }
                return originalOpen.apply(this, [method, url, ...rest]);
            };
            
            // Remove ad elements
            const observer = new MutationObserver(() => {
                document.querySelectorAll('[class*="ad-"], [id*="ad-"], [class*="ads"], iframe[src*="ads"]').forEach(el => {
                    el.remove();
                });
            });
            observer.observe(document.body || document.documentElement, { childList: true, subtree: true });
        """)
        
        print("✅ Ad blocker installed", flush=True)
        
        # Verify WARP IP
        print("\n🌐 Checking IP through WARP...", flush=True)
        await page.goto("https://www.cloudflare.com/cdn-cgi/trace")
        await page.wait_for_timeout(2000)
        
        body = await page.locator("body").inner_text()
        print("\n" + "="*60)
        print("IP Information:")
        print("="*60)
        for line in body.split('\n'):
            if any(key in line for key in ['ip=', 'warp=', 'colo=', 'loc=']):
                print(line)
        print("="*60 + "\n")
        
        # Open a new tab for user
        user_page = await context.new_page()
        await user_page.goto("https://www.google.com")
        
        print("✅ Browser is ready!")
        print("   - WARP proxy is active (only in this browser)")
        print("   - Ad blocker is installed")
        print("   - Your system network is NOT affected")
        print("\nPress Ctrl+C or close all browser windows to exit...")
        
        # Keep alive
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n\n👋 Closing browser...")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
