#!/usr/bin/env python3
"""
Open a Lovable session in browser and keep it open.
Usage: python3 open_session.py <session_number>
"""

import asyncio
import json
import sys
from pathlib import Path
from invisible_playwright.async_api import InvisiblePlaywright


SESSIONS_DIR = Path("/home/alan/Documents/automation-toolkit/scripts/sessions")
REAL_COOKIES_PATH = Path("/home/alan/Documents/automation-toolkit/finals/real_browser_cookies.json")


def log(msg: str):
    """Simple logger."""
    print(f"[INFO] {msg}", flush=True)


async def open_session(session_num: int):
    """Open browser with session cookies and keep it open."""
    
    session_dir = SESSIONS_DIR / f"session-{session_num}"
    
    if not session_dir.exists():
        print(f"❌ Session {session_num} not found at {session_dir}")
        sys.exit(1)
    
    # Load session config
    config_file = session_dir / "config.json"
    cookies_file = session_dir / "cookies.json"
    
    with open(config_file) as f:
        config = json.load(f)
    
    with open(cookies_file) as f:
        session_cookies = json.load(f)
    
    email = config.get("email", "unknown")
    
    print("=" * 60)
    print(f"🚀 OPENING SESSION {session_num}")
    print("=" * 60)
    print(f"📧 Email: {email}")
    print(f"🍪 Session cookies: {len(session_cookies)}")
    print()
    
    # Load real browser cookies
    real_cookies = []
    if REAL_COOKIES_PATH.exists():
        with open(REAL_COOKIES_PATH) as f:
            real_cookies = json.load(f)
        log(f"✅ Loaded {len(real_cookies)} real browser cookies")
    
    # Start invisible playwright
    async with InvisiblePlaywright() as browser:
        log("✅ Applied INVISIBLE-PLAYWRIGHT (passes ALL bot detection)")
        
        # Create context and page
        context = browser.contexts[0] if browser.contexts else await browser.new_context(
            proxy={
                "server": "socks5://127.0.0.1:40000"  # WARP proxy
            }
        )
        page = await context.new_page()
        
        # Add real browser cookies first
        if real_cookies:
            lovable_cookies = [c for c in real_cookies if 'lovable.dev' in c.get('domain', '')]
            if lovable_cookies:
                await context.add_cookies(lovable_cookies)
                log(f"✅ Added {len(lovable_cookies)} real lovable.dev cookies")
        
        # Add session cookies (overwrite any conflicts)
        await context.add_cookies(session_cookies)
        log(f"✅ Added {len(session_cookies)} session cookies")
        
        # Navigate to dashboard
        log("🌐 Navigating to Lovable dashboard...")
        await page.goto("https://lovable.dev/dashboard", timeout=60000)
        await page.wait_for_load_state("domcontentloaded")
        
        log("✅ Dashboard loaded!")
        print()
        print("=" * 60)
        print("✅ SESSION READY")
        print("=" * 60)
        print(f"Session: {session_num}")
        print(f"Email: {email}")
        print(f"URL: {page.url}")
        print()
        print("🔓 Browser will stay open. Press Enter to close...")
        print("=" * 60)
        
        # Keep browser open until user presses Enter
        input()
        
        log("Closing browser...")
        await browser.close()
        log("✅ Done!")


async def main():
    if len(sys.argv) < 2:
        print("Usage: python3 open_session.py <session_number>")
        print("\nExample: python3 open_session.py 1")
        print("\nAvailable sessions:")
        
        # List available sessions
        if SESSIONS_DIR.exists():
            sessions = sorted([d for d in SESSIONS_DIR.iterdir() if d.is_dir() and d.name.startswith("session-")])
            for session_dir in sessions:
                session_num = session_dir.name.split("-")[1]
                config_file = session_dir / "config.json"
                if config_file.exists():
                    with open(config_file) as f:
                        config = json.load(f)
                    email = config.get("email", "unknown")
                    print(f"  - Session {session_num}: {email}")
                else:
                    print(f"  - Session {session_num}: (no config)")
        
        sys.exit(1)
    
    session_num = int(sys.argv[1])
    await open_session(session_num)


if __name__ == "__main__":
    asyncio.run(main())
