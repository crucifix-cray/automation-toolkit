#!/usr/bin/env python3
"""Load a saved Lovable session and open the browser.

Usage:
    python3 load_session.py              # Load latest session
    python3 load_session.py 1            # Load session-1
    python3 load_session.py --list       # List all sessions
"""

import argparse
import json
import pathlib
import sys
from datetime import datetime

import asyncio
from playwright.async_api import async_playwright


def list_sessions(sessions_dir: pathlib.Path) -> None:
    """List all saved sessions."""
    sessions = sorted(sessions_dir.glob("session-*"))
    
    if not sessions:
        print("No saved sessions found.")
        return
    
    print(f"\n{'Session':<12} {'Email':<30} {'Created':<25} {'Cookies':<10}")
    print("=" * 80)
    
    for session_dir in sessions:
        config_file = session_dir / "config.json"
        cookies_file = session_dir / "cookies.json"
        
        if not config_file.exists():
            continue
        
        with open(config_file) as f:
            config = json.load(f)
        
        num_cookies = 0
        if cookies_file.exists():
            with open(cookies_file) as f:
                num_cookies = len(json.load(f))
        
        created = config.get("created_at", "Unknown")
        try:
            created_dt = datetime.fromisoformat(created)
            created = created_dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            pass
        
        print(f"{session_dir.name:<12} {config['email']:<30} {created:<25} {num_cookies:<10}")
    
    print()


async def load_session(session_num: int, sessions_dir: pathlib.Path) -> None:
    """Load a session and open browser with cookies."""
    session_dir = sessions_dir / f"session-{session_num}"
    
    if not session_dir.exists():
        print(f"Error: {session_dir} does not exist", file=sys.stderr)
        sys.exit(1)
    
    config_file = session_dir / "config.json"
    cookies_file = session_dir / "cookies.json"
    
    if not config_file.exists():
        print(f"Error: {config_file} does not exist", file=sys.stderr)
        sys.exit(1)
    
    with open(config_file) as f:
        config = json.load(f)
    
    print(f"Loading session-{session_num}:", file=sys.stderr)
    print(f"  Email: {config['email']}", file=sys.stderr)
    print(f"  Created: {config.get('created_at', 'Unknown')}", file=sys.stderr)
    
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            channel="chrome",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        
        # Load cookies if they exist
        if cookies_file.exists():
            with open(cookies_file) as f:
                cookies = json.load(f)
            await context.add_cookies(cookies)
            print(f"  Loaded {len(cookies)} cookies", file=sys.stderr)
        
        # Open dashboard
        page = await context.new_page()
        dashboard_url = config.get("dashboard_url", "https://lovable.dev/dashboard")
        await page.goto(dashboard_url, wait_until="domcontentloaded", timeout=60_000)
        
        print(f"\n✓ Browser opened with session-{session_num}", file=sys.stderr)
        print(f"  Dashboard: {page.url}", file=sys.stderr)
        print("\nPress Enter to close the browser...", file=sys.stderr)
        
        try:
            await asyncio.get_running_loop().run_in_executor(None, input)
        except (EOFError, KeyboardInterrupt):
            pass
        
        await browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "session",
        nargs="?",
        type=int,
        help="Session number to load (default: latest)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all saved sessions",
    )
    parser.add_argument(
        "--sessions-dir",
        type=pathlib.Path,
        default=pathlib.Path(__file__).parent / "sessions",
        help="Sessions directory (default: ./sessions)",
    )
    
    args = parser.parse_args()
    
    if not args.sessions_dir.exists():
        print(f"Error: Sessions directory {args.sessions_dir} does not exist", file=sys.stderr)
        return 1
    
    if args.list:
        list_sessions(args.sessions_dir)
        return 0
    
    # Find session to load
    sessions = sorted(args.sessions_dir.glob("session-*"))
    
    if not sessions:
        print("Error: No saved sessions found", file=sys.stderr)
        return 1
    
    if args.session:
        session_num = args.session
    else:
        # Load latest
        session_num = int(sessions[-1].name.split("-")[1])
        print(f"Loading latest session (session-{session_num})...", file=sys.stderr)
    
    asyncio.run(load_session(session_num, args.sessions_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
