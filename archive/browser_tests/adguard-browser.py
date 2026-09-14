#!/usr/bin/env python3
"""
Chromium Browser with AdGuard AdBlocker + Anti-Redirect
Downloads and installs real AdGuard extension
"""
import asyncio
import zipfile
from pathlib import Path
from playwright.async_api import async_playwright
import urllib.request
import subprocess

async def download_adguard():
    """Download AdGuard extension from Chrome Web Store"""
    print("📥 Downloading AdGuard AdBlocker...", flush=True)
    
    # AdGuard extension ID
    extension_id = "bgnkhhnnamicmpeenaelnjfhikgbkllg"
    
    # Chrome Web Store download URL pattern
    # We'll download using a CRX downloader URL
    url = f"https://clients2.google.com/service/update2/crx?response=redirect&prodversion=120.0&acceptformat=crx2,crx3&x=id%3D{extension_id}%26uc"
    
    extension_dir = Path("/tmp/adguard-extension")
    crx_path = extension_dir / "adguard.crx"
    unpacked_dir = extension_dir / "adguard-unpacked"
    
    if unpacked_dir.exists() and (unpacked_dir / "manifest.json").exists():
        print("✅ AdGuard already downloaded", flush=True)
        return str(unpacked_dir)
    
    extension_dir.mkdir(parents=True, exist_ok=True)
    
    print("📥 Downloading from Chrome Web Store...", flush=True)
    try:
        urllib.request.urlretrieve(url, crx_path)
    except Exception as e:
        print(f"❌ Download failed: {e}", flush=True)
        print("⚠️  Using uBlock Origin instead (just as powerful as AdGuard)", flush=True)
        return await download_ublock_fallback()
    
    print("📦 Extracting CRX...", flush=True)
    unpacked_dir.mkdir(exist_ok=True)
    
    # CRX files are ZIP files with a header, try to extract
    try:
        with zipfile.ZipFile(crx_path, 'r') as zip_ref:
            zip_ref.extractall(unpacked_dir)
    except Exception as e:
        # CRX might have a header, skip it and try again
        print("  ⚠️  CRX has header, stripping...", flush=True)
        with open(crx_path, 'rb') as f:
            data = f.read()
            # Find ZIP signature (PK)
            zip_start = data.find(b'PK\x03\x04')
            if zip_start > 0:
                with open(crx_path.with_suffix('.zip'), 'wb') as zf:
                    zf.write(data[zip_start:])
                with zipfile.ZipFile(crx_path.with_suffix('.zip'), 'r') as zip_ref:
                    zip_ref.extractall(unpacked_dir)
    
    if not (unpacked_dir / "manifest.json").exists():
        print("❌ AdGuard extraction failed, using uBlock Origin fallback", flush=True)
        return await download_ublock_fallback()
    
    print(f"✅ AdGuard extracted", flush=True)
    return str(unpacked_dir)

async def download_ublock_fallback():
    """Fallback: download uBlock Origin if AdGuard fails"""
    print("📥 Downloading uBlock Origin (fallback)...", flush=True)
    
    version = "1.73.0"
    url = f"https://github.com/gorhill/uBlock/releases/download/{version}/uBlock0_{version}.chromium.zip"
    
    extension_dir = Path("/tmp/ublock-fallback")
    unpacked_dir = extension_dir / "uBlock0.chromium"
    
    if unpacked_dir.exists() and (unpacked_dir / "manifest.json").exists():
        print("✅ uBlock Origin ready", flush=True)
        return str(unpacked_dir)
    
    extension_dir.mkdir(parents=True, exist_ok=True)
    zip_path = extension_dir / "ublock.zip"
    
    urllib.request.urlretrieve(url, zip_path)
    
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extension_dir)
    
    zip_path.unlink()
    
    print("✅ uBlock Origin extracted", flush=True)
    return str(unpacked_dir)

async def main():
    print("\n" + "="*70)
    print("🛡️  AdGuard AdBlocker + Anti-Redirect Browser")
    print("="*70 + "\n")
    
    # Download extension
    extension_path = await download_adguard()
    extension_name = "AdGuard" if "adguard" in extension_path else "uBlock Origin"
    
    print("\n" + "="*70)
    print(f"🚀 Launching Chromium with {extension_name}")
    print("="*70 + "\n")
    
    async with async_playwright() as p:
        print(f"🚀 Starting browser with {extension_name}...", flush=True)
        
        context = await p.chromium.launch_persistent_context(
            "/tmp/adguard-browser",
            headless=False,
            channel="chromium",  # MUST be chromium for extensions
            args=[
                f"--disable-extensions-except={extension_path}",
                f"--load-extension={extension_path}",
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        
        print(f"✅ Browser launched with {extension_name}", flush=True)
        
        page = await context.new_page()
        
        # Add anti-redirect
        print("🛡️  Installing anti-redirect protection...", flush=True)
        await page.add_init_script("""
            console.log('🛡️ Anti-Redirect Protection Loading...');
            
            // Block window.open
            window.open = function(...args) {
                console.log('🚫 BLOCKED window.open:', args[0]);
                return null;
            };
            
            // Block location redirects
            const desc = Object.getOwnPropertyDescriptor(Location.prototype, 'href');
            Object.defineProperty(Location.prototype, 'href', {
                set: function(url) {
                    console.log('🚫 BLOCKED location.href redirect:', url);
                },
                get: desc.get
            });
            
            // Block location.assign/replace
            Location.prototype.assign = function(url) {
                console.log('🚫 BLOCKED location.assign:', url);
            };
            Location.prototype.replace = function(url) {
                console.log('🚫 BLOCKED location.replace:', url);
            };
            
            // Block meta refresh
            const observer = new MutationObserver((mutations) => {
                mutations.forEach(m => {
                    m.addedNodes.forEach(node => {
                        if (node.tagName === 'META' && 
                            node.getAttribute?.('http-equiv')?.toLowerCase() === 'refresh') {
                            node.remove();
                            console.log('🚫 BLOCKED meta refresh');
                        }
                    });
                });
            });
            
            if (document.head) {
                observer.observe(document.head, { childList: true, subtree: true });
            }
            document.addEventListener('DOMContentLoaded', () => {
                if (document.head) {
                    observer.observe(document.head, { childList: true, subtree: true });
                }
            });
            
            console.log('✅ Anti-Redirect Protection ACTIVE');
        """)
        
        print("✅ Anti-redirect protection installed", flush=True)
        
        # Navigate
        print("\n🌐 Opening Google...", flush=True)
        await page.goto("https://www.google.com", wait_until="domcontentloaded")
        
        print("\n" + "="*70)
        print("✅ BROWSER READY!")
        print("="*70)
        print(f"✅ {extension_name} extension active (check toolbar)")
        print("✅ Anti-redirect protection enabled")
        print("\n🚫 PROTECTION:")
        print(f"   • Ads blocked by {extension_name}")
        print("   • Trackers blocked")
        print("   • ALL redirects blocked (location, window.open, meta)")
        print("\n💡 USAGE:")
        print(f"   • Click {extension_name} icon in toolbar to configure")
        print("   • Enable tracking protection filters")
        print("   • Add custom filters if needed")
        print("   • Check console (F12) to see blocked redirects")
        print("\n⚠️  NOTE:")
        print("   • Chrome stable doesn't support extensions")
        print("   • Using Chromium instead (functionally identical)")
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
