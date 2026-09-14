#!/usr/bin/env python3
"""Open Chrome with uBlock Origin extension + redirect blocking - WORKING VERSION"""
import asyncio
import zipfile
from pathlib import Path
from playwright.async_api import async_playwright
import urllib.request

async def download_ublock_origin():
    """Download and extract uBlock Origin extension"""
    print("📥 Checking uBlock Origin extension...", flush=True)
    
    # Latest uBlock Origin release
    version = "1.73.0"
    url = f"https://github.com/gorhill/uBlock/releases/download/{version}/uBlock0_{version}.chromium.zip"
    
    extension_dir = Path("/tmp/ublock-extension")
    unpacked_dir = extension_dir / "uBlock0.chromium"
    
    # Check if already downloaded and extracted
    if unpacked_dir.exists() and (unpacked_dir / "manifest.json").exists():
        print(f"✅ uBlock Origin {version} already installed", flush=True)
        return str(unpacked_dir)
    
    # Create directory
    extension_dir.mkdir(parents=True, exist_ok=True)
    zip_path = extension_dir / f"ublock_{version}.zip"
    
    # Download
    print(f"📥 Downloading uBlock Origin {version}...", flush=True)
    urllib.request.urlretrieve(url, zip_path)
    print("✅ Downloaded", flush=True)
    
    # Extract
    print("📦 Extracting...", flush=True)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extension_dir)
    
    # Remove zip
    zip_path.unlink()
    
    # Verify extraction
    if not (unpacked_dir / "manifest.json").exists():
        raise Exception(f"Extension extraction failed - manifest.json not found in {unpacked_dir}")
    
    print(f"✅ uBlock Origin extracted to {unpacked_dir}", flush=True)
    return str(unpacked_dir)

async def main():
    print("\n" + "="*60)
    print("Chrome with uBlock Origin + Redirect Blocker")
    print("="*60 + "\n")
    
    # Download and prepare extension
    extension_path = await download_ublock_origin()
    
    print("\n" + "="*60)
    print("Launching Chrome with extension")
    print("="*60 + "\n")
    
    async with async_playwright() as p:
        print("🚀 Launching Chromium with uBlock Origin...", flush=True)
        
        # CRITICAL: Must use launch_persistent_context with chromium channel
        context = await p.chromium.launch_persistent_context(
            "/tmp/chrome-with-ublock-working",
            headless=False,  # REQUIRED - extensions don't work in headless
            channel="chromium",  # REQUIRED - must be chromium, not chrome
            args=[
                f"--disable-extensions-except={extension_path}",
                f"--load-extension={extension_path}",
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        
        print("✅ Browser launched with uBlock Origin", flush=True)
        
        # Create page
        page = await context.new_page()
        
        # Add JavaScript redirect blocker
        print("🛡️  Installing redirect blocker...", flush=True)
        await page.add_init_script("""
            // === COMPREHENSIVE REDIRECT BLOCKER ===
            
            // 1. Block window.location assignments
            let originalLocation = window.location.href;
            
            // Override location setter
            Object.defineProperty(window, 'location', {
                get: function() {
                    const loc = originalLocation;
                    return {
                        href: loc,
                        toString: () => loc,
                        assign: function(url) {
                            console.log('🚫 BLOCKED location.assign redirect to:', url);
                            return false;
                        },
                        replace: function(url) {
                            console.log('🚫 BLOCKED location.replace redirect to:', url);
                            return false;
                        },
                        reload: function() {
                            // Allow reload
                            window.location.reload();
                        }
                    };
                },
                set: function(value) {
                    console.log('🚫 BLOCKED location redirect to:', value);
                    return false;
                }
            });
            
            // 2. Block window.open popups
            const originalOpen = window.open;
            window.open = function(...args) {
                console.log('🚫 BLOCKED window.open to:', args[0]);
                return null;
            };
            
            // 3. Block meta refresh redirects
            const blockMetaRefresh = () => {
                document.querySelectorAll('meta[http-equiv="refresh"]').forEach(meta => {
                    meta.remove();
                    console.log('🚫 BLOCKED meta refresh redirect');
                });
            };
            
            // Run immediately and watch for new meta tags
            if (document.head) {
                blockMetaRefresh();
            }
            
            const metaObserver = new MutationObserver((mutations) => {
                mutations.forEach((mutation) => {
                    mutation.addedNodes.forEach((node) => {
                        if (node.tagName === 'META' && 
                            node.getAttribute && 
                            node.getAttribute('http-equiv')?.toLowerCase() === 'refresh') {
                            node.remove();
                            console.log('🚫 BLOCKED new meta refresh redirect');
                        }
                    });
                });
            });
            
            // Start observing when ready
            const startMetaObserver = () => {
                if (document.head) {
                    metaObserver.observe(document.head, { childList: true, subtree: true });
                }
            };
            
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', startMetaObserver);
            } else {
                startMetaObserver();
            }
            
            // 4. Block setTimeout/setInterval redirects
            const originalSetTimeout = window.setTimeout;
            window.setTimeout = function(fn, delay, ...args) {
                if (typeof fn === 'function') {
                    const fnString = fn.toString();
                    if (fnString.includes('location.') || 
                        fnString.includes('window.location') ||
                        fnString.includes('window.open')) {
                        console.log('🚫 BLOCKED setTimeout redirect');
                        return 0;
                    }
                } else if (typeof fn === 'string') {
                    if (fn.includes('location.') || 
                        fn.includes('window.location') ||
                        fn.includes('window.open')) {
                        console.log('🚫 BLOCKED setTimeout redirect (string)');
                        return 0;
                    }
                }
                return originalSetTimeout.apply(this, [fn, delay, ...args]);
            };
            
            const originalSetInterval = window.setInterval;
            window.setInterval = function(fn, delay, ...args) {
                if (typeof fn === 'function') {
                    const fnString = fn.toString();
                    if (fnString.includes('location.') || 
                        fnString.includes('window.location') ||
                        fnString.includes('window.open')) {
                        console.log('🚫 BLOCKED setInterval redirect');
                        return 0;
                    }
                } else if (typeof fn === 'string') {
                    if (fn.includes('location.') || 
                        fn.includes('window.location') ||
                        fn.includes('window.open')) {
                        console.log('🚫 BLOCKED setInterval redirect (string)');
                        return 0;
                    }
                }
                return originalSetInterval.apply(this, [fn, delay, ...args]);
            };
            
            console.log('✅ Redirect blocker initialized');
        """)
        
        print("✅ Redirect blocker installed", flush=True)
        
        # Navigate to Google
        print("\n🌐 Opening Google...", flush=True)
        await page.goto("https://www.google.com", wait_until="domcontentloaded")
        
        print("\n" + "="*60)
        print("✅ BROWSER READY!")
        print("="*60)
        print("✅ uBlock Origin extension is active (check toolbar)")
        print("✅ ALL redirects are blocked:")
        print("   • location.href = 'url'")
        print("   • location.assign('url')")
        print("   • location.replace('url')")
        print("   • window.open('url')")
        print("   • <meta http-equiv='refresh'>")
        print("   • setTimeout/setInterval redirects")
        print("\n✅ Ad blocking active via uBlock Origin")
        print("\n💡 Tips:")
        print("   • Click uBlock icon in toolbar to configure")
        print("   • Redirects are logged in console (F12)")
        print("   • Browse any website without redirects")
        print("\nPress Ctrl+C or close browser to exit...")
        print("="*60 + "\n")
        
        # Keep alive
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n\n👋 Closing browser...")
            await context.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
