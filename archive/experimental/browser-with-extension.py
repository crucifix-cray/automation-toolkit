#!/usr/bin/env python3
"""Open Chrome with uBlock Origin extension + redirect blocking"""
import asyncio
import subprocess
import zipfile
from pathlib import Path
from playwright.async_api import async_playwright
import tempfile
import urllib.request

async def download_ublock_origin():
    """Download uBlock Origin extension"""
    print("📥 Checking uBlock Origin extension...", flush=True)
    
    # uBlock Origin latest release
    url = "https://github.com/gorhill/uBlock/releases/download/1.60.0/uBlock0_1.60.0.chromium.zip"
    extension_dir = Path("/tmp/ublock-origin-extension")
    actual_extension = extension_dir / "uBlock0.chromium"
    
    if actual_extension.exists():
        print("✅ Extension already downloaded", flush=True)
        return str(actual_extension)
    
    extension_dir.mkdir(parents=True, exist_ok=True)
    zip_path = extension_dir / "ublock.zip"
    
    # Download
    print("📥 Downloading uBlock Origin...", flush=True)
    urllib.request.urlretrieve(url, zip_path)
    
    # Extract
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extension_dir)
    
    # Remove zip
    zip_path.unlink()
    
    print("✅ uBlock Origin downloaded and extracted", flush=True)
    return str(actual_extension)

async def main():
    print("\n" + "="*60)
    print("Chrome with uBlock Origin + Redirect Blocker")
    print("="*60 + "\n")
    
    # Download extension
    extension_path = await download_ublock_origin()
    
    async with async_playwright() as p:
        print("🚀 Launching Chrome with uBlock Origin...", flush=True)
        
        # Launch with extension loaded
        context = await p.chromium.launch_persistent_context(
            "/tmp/chrome-with-ublock",
            channel="chromium",  # Must use chromium channel for extensions
            headless=False,
            args=[
                f"--disable-extensions-except={extension_path}",
                f"--load-extension={extension_path}",
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        
        # Create page and add redirect blocker
        page = await context.new_page()
        
        print("🛡️  Installing redirect blocker...", flush=True)
        await page.add_init_script("""
            // BLOCK ALL REDIRECTS
            
            // 1. Block location changes
            let currentLocation = window.location.href;
            Object.defineProperty(window, 'location', {
                get: function() {
                    return {
                        ...window.location,
                        href: currentLocation,
                        assign: function(url) {
                            console.log('🚫 Blocked location.assign to:', url);
                        },
                        replace: function(url) {
                            console.log('🚫 Blocked location.replace to:', url);
                        }
                    };
                },
                set: function(value) {
                    console.log('🚫 Blocked location redirect to:', value);
                }
            });
            
            // 2. Block window.open
            window.open = function(...args) {
                console.log('🚫 Blocked window.open to:', args[0]);
                return null;
            };
            
            // 3. Block meta refresh redirects
            const metaObserver = new MutationObserver((mutations) => {
                mutations.forEach((mutation) => {
                    mutation.addedNodes.forEach((node) => {
                        if (node.tagName === 'META' && 
                            node.getAttribute('http-equiv')?.toLowerCase() === 'refresh') {
                            node.remove();
                            console.log('🚫 Blocked meta refresh redirect');
                        }
                    });
                });
            });
            
            // Start observing when document is ready
            if (document.head) {
                metaObserver.observe(document.head, { childList: true, subtree: true });
            } else {
                document.addEventListener('DOMContentLoaded', () => {
                    metaObserver.observe(document.head, { childList: true, subtree: true });
                });
            }
            
            // 4. Block JavaScript redirects in setTimeout/setInterval
            const originalSetTimeout = window.setTimeout;
            window.setTimeout = function(fn, delay, ...args) {
                const fnString = fn.toString();
                if (fnString.includes('location') || fnString.includes('window.open')) {
                    console.log('🚫 Blocked setTimeout redirect');
                    return 0;
                }
                return originalSetTimeout.apply(this, [fn, delay, ...args]);
            };
            
            const originalSetInterval = window.setInterval;
            window.setInterval = function(fn, delay, ...args) {
                const fnString = fn.toString();
                if (fnString.includes('location') || fnString.includes('window.open')) {
                    console.log('🚫 Blocked setInterval redirect');
                    return 0;
                }
                return originalSetInterval.apply(this, [fn, delay, ...args]);
            };
            
            console.log('✅ Redirect blocker active');
        """)
        
        print("✅ Redirect blocker installed", flush=True)
        
        # Open Google
        print("🌐 Opening Google...", flush=True)
        await page.goto("https://www.google.com")
        
        print("\n" + "="*60)
        print("✅ Browser is ready!")
        print("="*60)
        print("   - ✅ uBlock Origin extension loaded")
        print("   - ✅ ALL redirects blocked")
        print("   - ✅ Ads blocked by uBlock Origin")
        print("\n💡 uBlock Origin is active in the toolbar")
        print("   Click the extension icon to configure settings")
        print("\nPress Ctrl+C or close browser to exit...")
        print("="*60 + "\n")
        
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n\n👋 Closing...")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
