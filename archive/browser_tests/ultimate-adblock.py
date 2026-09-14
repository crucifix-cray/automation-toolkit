#!/usr/bin/env python3
"""
ULTIMATE AD BLOCKER - AdGuard Level Power
Combines 3 blocking methods:
1. uBlock Origin extension (visual ad blocking)
2. Network-level blocking (resource interception)
3. JavaScript redirect blocking (anti-redirect)
"""
import asyncio
import zipfile
from pathlib import Path
from playwright.async_api import async_playwright
import urllib.request

# Comprehensive block lists
BLOCK_RESOURCE_TYPES = [
    'beacon',         # Analytics beacons
    'csp_report',     # CSP reports
    'font',           # External fonts (optional, commented out if needed)
    'image',          # Images (ads often images)
    'imageset',       # Image sets
    'media',          # Video/audio ads
    'object',         # Flash/objects
    'texttrack',      # Subtitles/tracks
]

# Block these domains/patterns - comprehensive list
BLOCK_DOMAINS = [
    # Ad networks
    'doubleclick.net',
    'googlesyndication.com',
    'googleadservices.com',
    'adservice',
    'adsystem',
    'adserver',
    'advertising',
    'adzerk',
    'ads.yahoo',
    'ads.bing',
    'ads.twitter',
    
    # Analytics & Trackers
    'google-analytics.com',
    'googletagmanager.com',
    'analytics',
    'tracking',
    'tracker',
    'telemetry',
    'hotjar.com',
    'mouseflow.com',
    'clicktale',
    'crazyegg',
    
    # Social trackers
    'facebook.net',
    'facebook.com/tr',
    'facebook.com/plugins',
    'connect.facebook',
    'pixel.facebook',
    'twitter.com/i/jot',
    'linkedin.com/px',
    
    # More ad networks
    'adnxs.com',
    'criteo.com',
    'outbrain.com',
    'taboola.com',
    'smartadserver.com',
    'advertising.com',
    'revcontent.com',
    'mgid.com',
    
    # Popups & redirects
    'popup',
    'popunder',
    'redirect',
    '/ad/',
    '/ads/',
    '/advert',
    'banner',
]

async def download_ublock_origin():
    """Download and extract uBlock Origin extension"""
    print("📥 Setting up uBlock Origin extension...", flush=True)
    
    version = "1.73.0"
    url = f"https://github.com/gorhill/uBlock/releases/download/{version}/uBlock0_{version}.chromium.zip"
    
    extension_dir = Path("/tmp/ublock-extension")
    unpacked_dir = extension_dir / "uBlock0.chromium"
    
    if unpacked_dir.exists() and (unpacked_dir / "manifest.json").exists():
        print(f"✅ uBlock Origin {version} ready", flush=True)
        return str(unpacked_dir)
    
    extension_dir.mkdir(parents=True, exist_ok=True)
    zip_path = extension_dir / f"ublock_{version}.zip"
    
    print(f"📥 Downloading uBlock Origin {version}...", flush=True)
    urllib.request.urlretrieve(url, zip_path)
    
    print("📦 Extracting...", flush=True)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extension_dir)
    
    zip_path.unlink()
    
    if not (unpacked_dir / "manifest.json").exists():
        raise Exception(f"Extension extraction failed")
    
    print(f"✅ uBlock Origin extracted", flush=True)
    return str(unpacked_dir)

def should_block_request(url: str, resource_type: str) -> bool:
    """Check if request should be blocked"""
    # Block by resource type
    if resource_type in BLOCK_RESOURCE_TYPES:
        return True
    
    # Block redirects at network level
    url_lower = url.lower()
    if any(keyword in url_lower for keyword in ['redirect', 'redir', 'track', 'click']):
        return True
    
    # Block by domain pattern
    for pattern in BLOCK_DOMAINS:
        if pattern in url_lower:
            return True
    
    return False

async def setup_network_blocking(page):
    """Set up network-level request blocking"""
    print("🛡️  Setting up network-level ad blocking...", flush=True)
    
    blocked_count = [0]  # Mutable counter
    
    async def intercept_route(route):
        """Intercept and block unwanted requests"""
        request = route.request
        url = request.url
        resource_type = request.resource_type
        
        # AGGRESSIVE: Block navigation to redirect URLs
        if resource_type == 'document':
            url_lower = url.lower()
            if any(keyword in url_lower for keyword in ['/redirect', '/redir/', 'redirect.', 'track?', 'click?', 'r.php', 'go.php']):
                print(f"   🚫 BLOCKED REDIRECT NAVIGATION: {url[:80]}", flush=True)
                await route.abort()
                return
        
        if should_block_request(url, resource_type):
            blocked_count[0] += 1
            if blocked_count[0] <= 10:  # Print first 10
                print(f"   🚫 Blocked: {resource_type} from {url[:60]}...", flush=True)
            await route.abort()
        else:
            await route.continue_()
    
    await page.route("**/*", intercept_route)
    print("✅ Network blocking active", flush=True)

async def setup_redirect_blocking(page):
    """Set up comprehensive JavaScript redirect blocking"""
    print("🛡️  Setting up redirect blocker...", flush=True)
    
    await page.add_init_script("""
        // ==========================================
        // ULTIMATE REDIRECT BLOCKER
        // ==========================================
        
        console.log('🛡️ Ultimate Redirect Blocker loading...');
        
        // 1. Block window.location changes
        const originalLocationHref = window.location.href;
        
        // Nuclear option: freeze location object
        try {
            delete window.location;
            window.location = new Proxy({}, {
                get: function(target, prop) {
                    if (prop === 'href') return document.URL;
                    if (prop === 'assign') return function(url) { console.log('🚫 BLOCKED location.assign:', url); };
                    if (prop === 'replace') return function(url) { console.log('🚫 BLOCKED location.replace:', url); };
                    if (prop === 'reload') return function() { window.location.reload(); };
                    return window.location[prop];
                },
                set: function(target, prop, value) {
                    console.log('🚫 BLOCKED location.' + prop + ' =', value);
                    return true;
                }
            });
        } catch(e) {
            console.warn('Proxy location failed, using fallback');
        }
        
        // 2. Block location.href direct assignment (backup method)
        try {
            const locationDescriptor = Object.getOwnPropertyDescriptor(Location.prototype, 'href');
            if (locationDescriptor) {
                Object.defineProperty(Location.prototype, 'href', {
                    set: function(value) {
                        console.log('🚫 BLOCKED location.href redirect:', value);
                    },
                    get: locationDescriptor.get
                });
            }
        } catch(e) {}
        
        // 3. Block window.open
        window.open = function(...args) {
            console.log('🚫 BLOCKED window.open:', args[0]);
            return null;
        };
        
        // 4. Block meta refresh
        const blockMetaRefresh = () => {
            document.querySelectorAll('meta[http-equiv="refresh"]').forEach(meta => {
                meta.remove();
                console.log('🚫 BLOCKED meta refresh');
            });
        };
        
        // Watch for new meta tags
        const metaObserver = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                mutation.addedNodes.forEach((node) => {
                    if (node.tagName === 'META' && 
                        node.getAttribute && 
                        node.getAttribute('http-equiv')?.toLowerCase() === 'refresh') {
                        node.remove();
                        console.log('🚫 BLOCKED new meta refresh');
                    }
                });
            });
        });
        
        const startObserving = () => {
            if (document.head) {
                blockMetaRefresh();
                metaObserver.observe(document.head, { childList: true, subtree: true });
            }
            if (document.body) {
                metaObserver.observe(document.body, { childList: true, subtree: true });
            }
        };
        
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', startObserving);
        } else {
            startObserving();
        }
        
        // 5. Block setTimeout/setInterval redirects
        const originalSetTimeout = window.setTimeout;
        window.setTimeout = function(fn, delay, ...args) {
            if (typeof fn === 'function') {
                const fnString = fn.toString();
                if (fnString.includes('location') || 
                    fnString.includes('window.open') ||
                    fnString.includes('redirect')) {
                    console.log('🚫 BLOCKED setTimeout redirect');
                    return 0;
                }
            } else if (typeof fn === 'string') {
                if (fn.includes('location') || 
                    fn.includes('window.open') ||
                    fn.includes('redirect')) {
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
                if (fnString.includes('location') || 
                    fnString.includes('window.open') ||
                    fnString.includes('redirect')) {
                    console.log('🚫 BLOCKED setInterval redirect');
                    return 0;
                }
            } else if (typeof fn === 'string') {
                if (fn.includes('location') || 
                    fn.includes('window.open') ||
                    fn.includes('redirect')) {
                    console.log('🚫 BLOCKED setInterval redirect (string)');
                    return 0;
                }
            }
            return originalSetInterval.apply(this, [fn, delay, ...args]);
        };
        
        // 6. Block History API redirects
        const originalPushState = history.pushState;
        const originalReplaceState = history.replaceState;
        
        history.pushState = function(state, title, url) {
            if (url && url.toString().includes('redirect')) {
                console.log('🚫 BLOCKED pushState redirect:', url);
                return;
            }
            return originalPushState.apply(this, arguments);
        };
        
        history.replaceState = function(state, title, url) {
            if (url && url.toString().includes('redirect')) {
                console.log('🚫 BLOCKED replaceState redirect:', url);
                return;
            }
            return originalReplaceState.apply(this, arguments);
        };
        
        // 7. Block beforeunload redirect tricks
        window.addEventListener('beforeunload', (e) => {
            // Allow normal beforeunload but prevent redirect tricks
            if (e.returnValue) {
                e.preventDefault();
                console.log('🚫 BLOCKED beforeunload redirect trick');
            }
        }, true);
        
        console.log('✅ Ultimate Redirect Blocker ACTIVE');
    """)
    
    print("✅ Redirect blocker installed", flush=True)

async def main():
    print("\n" + "="*70)
    print("🛡️  ULTIMATE AD BLOCKER - AdGuard Power Level")
    print("="*70 + "\n")
    
    # Step 1: Download extension
    extension_path = await download_ublock_origin()
    
    print("\n" + "="*70)
    print("🚀 Launching Browser")
    print("="*70 + "\n")
    
    async with async_playwright() as p:
        # Launch with extension
        context = await p.chromium.launch_persistent_context(
            "/tmp/ultimate-adblock-browser",
            headless=False,
            channel="chromium",
            args=[
                f"--disable-extensions-except={extension_path}",
                f"--load-extension={extension_path}",
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        
        print("✅ Browser launched with uBlock Origin", flush=True)
        
        page = await context.new_page()
        
        # NUCLEAR OPTION: Block ALL navigation after initial page load
        navigation_allowed = [True]  # Mutable flag
        initial_url = [None]
        
        async def block_all_navigation(route):
            """Block ALL navigation requests after first page load"""
            request = route.request
            
            # Allow the first navigation
            if navigation_allowed[0]:
                if request.resource_type == 'document':
                    initial_url[0] = request.url
                    navigation_allowed[0] = False
                await route.continue_()
                return
            
            # Block ALL subsequent document navigations (redirects)
            if request.resource_type == 'document':
                url = request.url
                # Allow same-page navigations
                if initial_url[0] and url.startswith(initial_url[0].split('?')[0]):
                    await route.continue_()
                else:
                    print(f"   🚫🚫🚫 BLOCKED REDIRECT NAVIGATION: {url[:80]}", flush=True)
                    await route.abort()
                return
            
            # Check normal blocking for other resources
            if should_block_request(request.url, request.resource_type):
                await route.abort()
            else:
                await route.continue_()
        
        await page.route("**/*", block_all_navigation)
        print("✅ NUCLEAR redirect blocking enabled - ALL navigations blocked after page load", flush=True)
        
        # Step 2: Set up redirect blocking (JavaScript level)
        await setup_redirect_blocking(page)
        
        # Step 3: Additional network blocking for non-document resources
        # (document blocking is in the main route above)
        
        print("\n" + "="*70)
        print("🌐 Opening test page...")
        print("="*70 + "\n")
        
        # Navigate to Google
        await page.goto("https://www.google.com", wait_until="domcontentloaded")
        
        print("\n" + "="*70)
        print("✅ ULTIMATE AD BLOCKER READY!")
        print("="*70)
        print("\n🛡️  PROTECTION ACTIVE:")
        print("   ✅ uBlock Origin extension (visual ad blocking)")
        print("   ✅ NUCLEAR redirect blocking (blocks ALL page navigations)")
        print("   ✅ JavaScript redirect blocking (prevents all JS redirects)")
        print("   ✅ Network-level blocking (blocks ad domains/trackers)")
        print("\n🚫 BLOCKED:")
        print("   • ALL page redirects (you will stay on the page you load)")
        print("   • All ad networks (Google Ads, DoubleClick, etc.)")
        print("   • Analytics & trackers (GA, GTM, Facebook Pixel, etc.)")
        print("   • Popups & pop-unders")
        print("   • Media ads (images, videos)")
        print("   • location.href, window.open, meta refresh")
        print("   • setTimeout/setInterval redirects")
        print("\n⚠️  WARNING:")
        print("   • This NUCLEAR mode blocks ALL page navigations after load")
        print("   • You can only visit ONE page, no clicking links will work")
        print("   • This is MAXIMUM anti-redirect protection")
        print("\n💡 TO USE:")
        print("   • Navigate to your target page in the code (line ~330)")
        print("   • The page will load but NO redirects will work")
        print("   • Check console (F12) to see blocked redirects")
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
