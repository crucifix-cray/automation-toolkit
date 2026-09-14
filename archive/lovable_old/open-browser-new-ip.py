#!/usr/bin/env python3
"""
Open Browser with New IP (WARP Multi-Instance)

Opens browser with UNIQUE IP using isolated WARP instance.
Each run gets a DIFFERENT IP through network namespace isolation.

Usage:
    obni                    # New unique IP
    obni --session 3        # New unique IP + load session-3
    obni --url lovable.dev  # New unique IP + specific URL
"""

import asyncio
import json
import sys
import signal
import subprocess
import random
from pathlib import Path

# Add script directory to path for local imports
sys.path.insert(0, str(Path(__file__).parent))

from invisible_playwright.async_api import InvisiblePlaywright


# Paths
SESSIONS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts/sessions"
REAL_COOKIES_PATH = Path(__file__).resolve().parent / "real_browser_cookies.json"
WARP_SCRIPT = Path(__file__).resolve().parent / "warp_multi_instance.sh"

# Global cleanup tracker
CLEANUP_INSTANCE_ID = None


def log(msg: str):
    """Simple logger."""
    print(msg, flush=True)


def cleanup_warp():
    """Kill WARP instance on exit."""
    global CLEANUP_INSTANCE_ID
    if CLEANUP_INSTANCE_ID:
        log(f"\n🔴 Stopping WARP instance {CLEANUP_INSTANCE_ID}...")
        subprocess.run(
            ["sudo", "bash", str(WARP_SCRIPT), str(CLEANUP_INSTANCE_ID), "stop"],
            capture_output=True
        )


def signal_handler(sig, frame):
    """Handle Ctrl+C."""
    log("\n⚠️  Interrupted by user")
    cleanup_warp()
    sys.exit(0)


# Register handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


async def get_current_ip(page):
    """Check current IP via Cloudflare trace."""
    try:
        await page.goto("https://www.cloudflare.com/cdn-cgi/trace", timeout=10000)
        await asyncio.sleep(2)
        content = await page.content()
        
        for line in content.split('\n'):
            if 'ip=' in line:
                ip = line.split('ip=')[1].split('<')[0].strip()
                log(f"📍 Browser IP: {ip}")
                return ip
        return None
    except Exception as e:
        log(f"⚠️  Could not check IP: {e}")
        return None


async def main(session_num: int = None, url: str = None):
    """Open browser (runs INSIDE namespace)."""
    
    print("=" * 60)
    print("🌐 BROWSER WITH UNIQUE IP")
    print("=" * 60)
    
    # Load session if provided
    session_cookies = []
    email = None
    if session_num:
        session_dir = SESSIONS_DIR / f"session-{session_num}"
        if not session_dir.exists():
            log(f"❌ Session {session_num} not found")
            sys.exit(1)
        
        with open(session_dir / "config.json") as f:
            config = json.load(f)
        
        with open(session_dir / "cookies.json") as f:
            session_cookies = json.load(f)
        
        email = config["email"]
        log(f"✅ Loaded session-{session_num}")
        log(f"📧 Email: {email}")
    
    # Load real browser cookies
    real_cookies = []
    if REAL_COOKIES_PATH.exists():
        with open(REAL_COOKIES_PATH) as f:
            real_cookies = json.load(f)
        log(f"✅ Loaded {len(real_cookies)} real browser cookies")
    
    # Start browser
    log("\n🚀 Starting InvisiblePlaywright...")
    
    try:
        async with InvisiblePlaywright() as browser:
            log("✅ Applied INVISIBLE-PLAYWRIGHT (passes ALL bot detection)")
            
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = await context.new_page()
            
            # Add cookies
            if real_cookies:
                lovable_cookies = [c for c in real_cookies if 'lovable.dev' in c.get('domain', '')]
                if lovable_cookies:
                    await context.add_cookies(lovable_cookies)
                    log(f"✅ Added {len(lovable_cookies)} Lovable cookies")
            
            if session_cookies:
                await context.add_cookies(session_cookies)
                log(f"✅ Added {len(session_cookies)} session cookies")
            
            # Show current IP
            log("\n📍 Checking current IP...")
            await get_current_ip(page)
            
            # Navigate to URL
            if url:
                if not url.startswith('http'):
                    url = f'https://{url}'
                log(f"\n🌐 Navigating to: {url}")
                await page.goto(url, timeout=30000)
            else:
                log("\n🌐 Opening blank page")
            
            # Keep browser open
            print("\n" + "=" * 60)
            print("✅ BROWSER READY")
            print("=" * 60)
            if session_num:
                print(f"📁 Session: session-{session_num} ({email})")
            if url:
                print(f"🌐 URL: {url}")
            print("\nPress ENTER to close browser...")
            print("=" * 60)
            
            await asyncio.get_event_loop().run_in_executor(None, input)
            
            log("\n🔒 Closing browser...")
            await browser.close()
    
    except Exception as e:
        log(f"❌ Error: {e}")
        raise


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Open browser with new WARP IP")
    parser.add_argument("--session", type=int, help="Session number (1-10)")
    parser.add_argument("--url", type=str, help="URL to navigate to")
    parser.add_argument("--no-warp", action="store_true", help="Skip WARP (direct connection)")
    parser.add_argument("--inside-namespace", action="store_true", help="Internal flag: already inside namespace")
    
    args = parser.parse_args()
    
    # Check if we're already inside a namespace
    try:
        import os
        self_ns = os.readlink("/proc/self/ns/net")
        init_ns = os.readlink("/proc/1/ns/net")
        in_namespace = self_ns != init_ns
    except:
        in_namespace = False
    
    if args.no_warp or args.inside_namespace or in_namespace:
        # Run browser directly (already in namespace or no WARP)
        if args.no_warp:
            log("⚠️  Running without WARP (direct connection)")
        asyncio.run(main(args.session, args.url))
    else:
        # Create namespace and re-run ourselves inside it
        log("🔧 Creating WARP instance with unique IP...")
        
        instance_id = random.randint(10, 250)
        namespace = f"warp-{instance_id}"
        CLEANUP_INSTANCE_ID = instance_id
        
        # Start WARP instance
        result = subprocess.run(
            ["sudo", "bash", str(WARP_SCRIPT), str(instance_id), "start"],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode != 0:
            log(f"❌ Failed to start WARP instance:")
            log(result.stderr)
            sys.exit(1)
        
        log(f"✅ WARP instance {instance_id} created")
        log(f"   Namespace: {namespace}")
        
        # Get IP of the instance
        ip_result = subprocess.run(
            ["sudo", "ip", "netns", "exec", namespace,
             "curl", "-s", "--max-time", "5", "https://www.cloudflare.com/cdn-cgi/trace"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        for line in ip_result.stdout.split('\n'):
            if line.startswith('ip='):
                ip = line.split('=')[1].strip()
                log(f"   IP: {ip}")
                break
        
        # Run browser inside namespace
        log(f"\n🚀 Running browser inside namespace...")
        
        cmd = [
            "sudo", "ip", "netns", "exec", namespace,
            "sudo", "-u", "alan",
            "python3", __file__,
            "--inside-namespace"
        ]
        
        if args.session:
            cmd.extend(["--session", str(args.session)])
        if args.url:
            cmd.extend(["--url", args.url])
        
        try:
            subprocess.run(cmd, check=True)
        except KeyboardInterrupt:
            log("\n⚠️  Interrupted")
        finally:
            cleanup_warp()
