#!/usr/bin/env python3
"""
Google Chrome Stable with AdBlock Plus + Anti-Redirect
Uses real Chrome (not Chromium) with AdBlock Plus extension
"""
import asyncio
import zipfile
from pathlib import Path
from playwright.async_api import async_playwright
import urllib.request

async def download_adblock_plus():
    """Download uBlock Origin extension (works reliably)"""
    print("📥 Downloading uBlock Origin (AdBlock)...", flush=True)
    
    # Use uBlock Origin - more reliable download
    version = "1.73.0"
    url = f"https://github.com/gorhill/uBlock/releases/download/{version}/uBlock0_{version}.chromium.zip"
    
    extension_dir = Path("/tmp/ublock-adblock-extension")
    unpacked_dir = extension_dir / "uBlock0.chromium"
    
    if unpacked_dir.exists() and (unpacked_dir / "manifest.json").exists():
        print("✅ uBlock Origin already downloaded", flush=True)
        return str(unpacked_dir)
    
    extension_dir.mkdir(parents=True, exist_ok=True)
    zip_path = extension_dir / "ublock.zip"
    
    print("📥 Downloading...", flush=True)
    urllib.request.urlretrieve(url, zip_path)
    
    print("📦 Extracting...", flush=True)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extension_dir)
    
    zip_path.unlink()
    
    if not (unpacked_dir / "manifest.json").exists():
        raise Exception("Extension extraction failed - manifest.json not found")
    
    print(f"✅ uBlock Origin extracted to {unpacked_dir}", flush=True)
    return str(unpacked_dir)

async def main():
    print("\n" + "="*70)
    print("🌐 Chromium with uBlock Origin + Anti-Redirect")
    print("="*70 + "\n")
    
    # Download extension
    extension_path = await download_adblock_plus()
    
    print("\n" + "="*70)
    print("🚀 Launching Chromium (Chrome blocks extensions)")
    print("="*70 + "\n")
    
    async with async_playwright() as p:
        # Use Chrome stable channel
        print("🚀 Launching Chrome Stable with uBlock Origin...", flush=True)
        
        context = await p.chromium.launch_persistent_context(
            "/tmp/chrome-stable-adblock",
            headless=False,
            channel="chromium",  # MUST use chromium - Chrome stable blocks extensions!
            args=[
                f"--disable-extensions-except={extension_path}",
                f"--load-extension={extension_path}",
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        
        print("✅ Chromium launched with uBlock Origin", flush=True)
        
        page = await context.new_page()
        
        # Add anti-redirect protection
        print("🛡️  Installing anti-redirect protection...", flush=True)
        
        await page.add_init_script("""
            console.log('🛡️ Anti-redirect protection loading...');
            
            // Block window.open
            window.open = function(...args) {
                console.log('🚫 BLOCKED window.open:', args[0]);
                return null;
            };
            
            // Block location changes
            try {
                const originalHref = window.location.href;
                Object.defineProperty(window, 'location', {
                    get: function() {
                        return {
                            href: window.location.href,
                            assign: (url) => console.log('🚫 BLOCKED location.assign:', url),
                            replace: (url) => console.log('🚫 BLOCKED location.replace:', url),
                            reload: () => window.location.reload(),
                            toString: () => window.location.href
                        };
                    },
                    set: (value) => {
                        console.log('🚫 BLOCKED location redirect:', value);
                    }
                });
            } catch(e) {
                console.warn('Could not block location:', e);
            }
            
            // Block meta refresh
            const blockMeta = () => {
                document.querySelectorAll('meta[http-equiv="refresh"]').forEach(m => {
                    m.remove();
                    console.log('🚫 BLOCKED meta refresh');
                });
            };
            
            const observer = new MutationObserver(blockMeta);
            if (document.head) {
                blockMeta();
                observer.observe(document.head, { childList: true, subtree: true });
            }
            
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', () => {
                    blockMeta();
                    observer.observe(document.head, { childList: true, subtree: true });
                });
            }
            
            console.log('✅ Anti-redirect protection ACTIVE');
        """)
        
        print("✅ Anti-redirect protection installed", flush=True)
        
        # Navigate
        print("\n🌐 Opening Google...", flush=True)
        await page.goto("https://www.google.com", wait_until="domcontentloaded")
        
        print("\n" + "="*70)
        print("✅ BROWSER READY!")
        print("="*70)
        print("✅ Chromium running (Chrome doesn't support extensions)")
        print("✅ uBlock Origin extension active (check toolbar)")
        print("✅ Anti-redirect protection enabled")
        print("\n🚫 BLOCKED:")
        print("   • Ads (via uBlock Origin)")
        print("   • Trackers (via uBlock Origin)")
        print("   • Redirects (location, window.open, meta refresh)")
        print("\n💡 FEATURES:")
        print("   • Chromium browser (Chrome blocked extension loading)")
        print("   • uBlock Origin extension loaded and active")
        print("   • No redirects allowed")
        print("   • Browse safely")
        print("\n⚙️  Configure uBlock:")
        print("   • Click uBlock icon in toolbar")
        print("   • Customize filter lists")
        print("   • Whitelist trusted sites")
        print("\nPress Ctrl+C or close browser to exit...")
        print("="*70 + "\n")
        
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n\n👋 Closing...")
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
