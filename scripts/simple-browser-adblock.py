#!/usr/bin/env python3
"""Simple: Open Chrome with ad blocker (no WARP needed for now)"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    print("\n" + "="*60)
    print("Opening Chrome with Ad Blocker")
    print("="*60 + "\n")
    
    async with async_playwright() as p:
        print("🚀 Launching browser...", flush=True)
        
        context = await p.chromium.launch_persistent_context(
            user_data_dir="/tmp/simple-browser-adblock",
            headless=False,
            channel="chrome",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        
        page = await context.new_page()
        
        print("🛡️  Installing aggressive ad blocker + redirect blocker...", flush=True)
        await page.add_init_script("""
            // Block ads, trackers, analytics
            const blockedPatterns = [
                'doubleclick.net', 'googlesyndication.com', 'googleadservices.com',
                'google-analytics.com', 'googletagmanager.com', 'facebook.net',
                'facebook.com/tr', 'analytics', '/ads/', '/ad/', 'advertising',
                'tracker', 'tracking', 'adservice', 'adsystem', 'adserver',
                'banner', 'popup', 'popunder',
            ];
            
            // BLOCK ALL REDIRECTS
            const originalLocationSetter = Object.getOwnPropertyDescriptor(window, 'location').set;
            Object.defineProperty(window, 'location', {
                set: function(value) {
                    console.log('🚫 Blocked redirect to:', value);
                    return false;
                },
                get: function() {
                    return originalLocationSetter;
                }
            });
            
            // Block location.href changes
            Object.defineProperty(window.location, 'href', {
                set: function(value) {
                    console.log('🚫 Blocked location.href redirect to:', value);
                    return false;
                },
                get: function() {
                    return window.location.href;
                }
            });
            
            // Block window.open
            window.open = function() {
                console.log('🚫 Blocked window.open');
                return null;
            };
            
            // Block meta refresh
            const observer = new MutationObserver((mutations) => {
                mutations.forEach((mutation) => {
                    mutation.addedNodes.forEach((node) => {
                        if (node.tagName === 'META' && node.getAttribute('http-equiv') === 'refresh') {
                            node.remove();
                            console.log('🚫 Blocked meta refresh redirect');
                        }
                    });
                });
            });
            observer.observe(document.head || document.documentElement, { childList: true, subtree: true });
            
            // Intercept fetch
            const originalFetch = window.fetch;
            window.fetch = function(...args) {
                const url = args[0].toString();
                if (blockedPatterns.some(pattern => url.toLowerCase().includes(pattern))) {
                    console.log('🚫 Blocked fetch:', url.substring(0, 80));
                    return Promise.reject(new Error('Blocked'));
                }
                return originalFetch.apply(this, args);
            };
            
            // Intercept XHR
            const originalOpen = XMLHttpRequest.prototype.open;
            XMLHttpRequest.prototype.open = function(method, url, ...rest) {
                if (blockedPatterns.some(pattern => url.toLowerCase().includes(pattern))) {
                    console.log('🚫 Blocked XHR:', url.substring(0, 80));
                    throw new Error('Blocked');
                }
                return originalOpen.apply(this, [method, url, ...rest]);
            };
            
            // Remove ad elements continuously
            const removeAds = () => {
                const selectors = [
                    '[class*="ad-"]', '[id*="ad-"]', '[class*="ads"]', 
                    'iframe[src*="ads"]', '[class*="banner"]', '[id*="banner"]',
                    '[class*="popup"]', '[id*="popup"]'
                ];
                selectors.forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => el.remove());
                });
            };
            
            // Run on load and watch for new elements
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', removeAds);
            } else {
                removeAds();
            }
            
            const adObserver = new MutationObserver(removeAds);
            adObserver.observe(document.documentElement || document.body, { 
                childList: true, 
                subtree: true 
            });
        """)
        
        print("✅ Ad blocker + redirect blocker installed\n", flush=True)
        
        # Open AdGuard extension page
        print("🌐 Opening AdGuard AdBlocker extension page...", flush=True)
        await page.goto("https://chromewebstore.google.com/detail/adguard-adblocker/bgnkhhnnamicmpeenaelnjfhikgbkllg?hl=en")
        
        print("\n✅ Browser is ready!")
        print("   - ✅ Aggressive ad blocker active (JavaScript-based)")
        print("   - ✅ ALL redirects blocked")
        print("   - 📌 AdGuard extension page is open")
        print("\n💡 To install AdGuard extension:")
        print("   1. Click the blue 'Add to Chrome' button")
        print("   2. Confirm by clicking 'Add extension'")
        print("   3. AdGuard will be installed and active")
        print("\n💡 To add WARP later:")
        print("   1. Install: yay -S cloudflare-warp-bin")
        print("   2. Setup: warp-cli registration new")
        print("   3. Configure: warp-cli mode proxy && warp-cli proxy port 40000")
        print("   4. Connect: warp-cli connect")
        print("\nPress Ctrl+C or close browser to exit...")
        
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
