#!/usr/bin/env python3
"""
Lovable Session Dashboard Checker
Checks if saved session cookies get into the Lovable dashboard.

Usage:
  python3 scripts/check_sessions_dashboard.py --pth session-1
  python3 scripts/check_sessions_dashboard.py --pth 1
  python3 scripts/check_sessions_dashboard.py --pth all --par 5
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

# Default directory
DEFAULT_SESSIONS_DIR = Path(__file__).resolve().parent / "sessions"
DASHBOARD_MARKERS = ["/dashboard", "/projects"]
LOGIN_MARKERS = ["/login", "/signup", "/auth", "/sign-in"]


def natural_sort_key(s: Path):
    """Sort session-1, session-2, ..., session-10 correctly."""
    nums = re.findall(r"\d+", s.name)
    return int(nums[0]) if nums else 999999


def resolve_targets(pth_arg: str, sessions_dir: Path) -> list[Path]:
    """Resolve session paths based on --pth argument."""
    if not sessions_dir.exists():
        print(f"❌ Sessions directory not found: {sessions_dir}", file=sys.stderr)
        sys.exit(1)

    pth_clean = pth_arg.strip().lower()

    if pth_clean == "all":
        sessions = sorted(sessions_dir.glob("session-*"), key=natural_sort_key)
        if not sessions:
            print(f"❌ No session-* directories found in {sessions_dir}", file=sys.stderr)
            sys.exit(1)
        return sessions

    # Handle formats like 'session1', 'session-1', '1'
    if pth_clean.isdigit():
        target_name = f"session-{pth_clean}"
    elif pth_clean.startswith("session") and not pth_clean.startswith("session-"):
        target_name = f"session-{pth_clean.replace('session', '')}"
    else:
        target_name = pth_clean

    target_dir = sessions_dir / target_name
    if not target_dir.exists():
        print(f"❌ Target session directory not found: {target_dir}", file=sys.stderr)
        sys.exit(1)

    return [target_dir]


async def check_session(session_dir: Path, browser, sem: asyncio.Semaphore, timeout: int) -> dict:
    """Check whether a single session gets into Lovable dashboard."""
    session_id = session_dir.name
    config_file = session_dir / "config.json"
    cookies_file = session_dir / "cookies.json"

    email = "unknown"
    if config_file.exists():
        try:
            with open(config_file) as f:
                cfg = json.load(f)
                email = cfg.get("email", "unknown")
        except Exception:
            pass

    result = {
        "session_id": session_id,
        "email": email,
        "status": "BAD",
        "reason": "",
        "final_url": "",
        "cookies_count": 0,
        "duration": 0.0,
    }

    if not cookies_file.exists():
        result["reason"] = "Missing cookies.json"
        print(f"[{session_id}] ❌ BAD - cookies.json missing")
        return result

    try:
        with open(cookies_file) as f:
            cookies = json.load(f)
    except Exception as e:
        result["reason"] = f"Invalid cookies.json: {e}"
        print(f"[{session_id}] ❌ BAD - invalid cookies.json")
        return result

    result["cookies_count"] = len(cookies)
    if not cookies:
        result["reason"] = "cookies.json is empty"
        print(f"[{session_id}] ❌ BAD - 0 cookies found")
        return result

    start_time = time.time()

    async with sem:
        context = None
        try:
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            )
            await context.add_cookies(cookies)
            page = await context.new_page()

            print(f"[{session_id}] 🔄 Checking ({email})...")

            # Navigate to dashboard
            try:
                await page.goto("https://lovable.dev/dashboard", wait_until="domcontentloaded", timeout=timeout * 1000)
            except Exception as nav_e:
                result["reason"] = f"Navigation error: {nav_e}"
                print(f"[{session_id}] ❌ BAD - {result['reason']}")
                return result

            # Actively poll for either a login redirect or genuine authenticated dashboard elements
            authenticated = False
            detected_reason = "Timed out waiting for dashboard to authenticate"

            # Check for up to 8 seconds (0.5s intervals)
            for _ in range(16):
                await asyncio.sleep(0.5)
                curr_url = page.url
                result["final_url"] = curr_url

                # Check if redirected to login
                if "/login" in curr_url or "/signup" in curr_url or "/auth" in curr_url:
                    detected_reason = f"Redirected to login ({curr_url})"
                    authenticated = False
                    break

                # Check if login form is rendered on page
                try:
                    is_login_page = await page.locator("input[type='email'], input[type='password'], button:has-text('Log in'), button:has-text('Sign in')").first.is_visible()
                    if is_login_page:
                        detected_reason = f"Login form detected on page ({curr_url})"
                        authenticated = False
                        break
                except Exception:
                    pass

                # Check for genuine authenticated dashboard elements
                try:
                    is_dash = await page.locator("a[href*='/projects'], a[href*='/templates'], button:has-text('New project'), [data-slot='avatar'], [data-slot='workspace-title'], button[id^='base-ui-']").first.is_visible()
                    if is_dash:
                        detected_reason = f"Authenticated dashboard loaded ({curr_url})"
                        authenticated = True
                        break
                except Exception:
                    pass

            if authenticated:
                result["status"] = "GOOD"
                result["reason"] = detected_reason
                print(f"[{session_id}] ✅ GOOD - Authenticated ({email})")
            else:
                result["status"] = "BAD"
                result["reason"] = detected_reason
                print(f"[{session_id}] ❌ BAD - {detected_reason}")

        except Exception as e:
            result["status"] = "BAD"
            result["reason"] = f"Error: {e}"
            print(f"[{session_id}] ❌ BAD - Exception: {e}")
        finally:
            result["duration"] = round(time.time() - start_time, 2)
            if context:
                try:
                    await context.close()
                except Exception:
                    pass

    return result


async def main():
    parser = argparse.ArgumentParser(description="Check if Lovable session cookies get into /dashboard")
    parser.add_argument("--pth", type=str, required=True, help="Session identifier (e.g. session-1, session1, 1) or 'all'")
    parser.add_argument("--par", type=int, default=5, help="Parallel concurrency count (default: 5)")
    parser.add_argument("--sessions-dir", type=Path, default=DEFAULT_SESSIONS_DIR, help="Path to sessions directory")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout in seconds for page load (default: 30)")
    parser.add_argument("--headless", action="store_true", default=True, help="Run headless (default: True)")
    parser.add_argument("--headed", action="store_false", dest="headless", help="Run headed (show browser windows)")
    parser.add_argument("--log-file", type=str, default="session_check_results.log", help="Output log file path")
    args = parser.parse_args()

    targets = resolve_targets(args.pth, args.sessions_dir)
    total_targets = len(targets)
    concurrency = min(args.par, total_targets) if total_targets > 0 else 1

    print("=" * 70)
    print("🔍 LOVABLE SESSIONS DASHBOARD CHECKER")
    print(f"  Target(s)    : {args.pth} ({total_targets} session{'s' if total_targets != 1 else ''})")
    print(f"  Parallelism  : {concurrency}")
    print(f"  Headless     : {args.headless}")
    print(f"  Sessions Dir : {args.sessions_dir}")
    print(f"  Log File     : {args.log_file}")
    print("=" * 70)

    sem = asyncio.Semaphore(concurrency)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=args.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ]
        )

        tasks = [check_session(target, browser, sem, args.timeout) for target in targets]
        results = await asyncio.gather(*tasks)

        await browser.close()

    good_list = [r for r in results if r["status"] == "GOOD"]
    bad_list = [r for r in results if r["status"] == "BAD"]

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Format log content
    log_lines = []
    log_lines.append("=" * 75)
    log_lines.append(f"LOVABLE SESSION CHECK REPORT - {timestamp}")
    log_lines.append("=" * 75)
    log_lines.append(f"Total Checked : {len(results)}")
    log_lines.append(f"GOOD (Alive)  : {len(good_list)} ({round(len(good_list)/len(results)*100, 1) if results else 0}%)")
    log_lines.append(f"BAD (Dead)    : {len(bad_list)} ({round(len(bad_list)/len(results)*100, 1) if results else 0}%)")
    log_lines.append("-" * 75)
    log_lines.append(f"{'Session':<15} {'Status':<8} {'Cookies':<8} {'Email':<32} {'Reason'}")
    log_lines.append("-" * 75)

    for r in results:
        status_sym = "✅ GOOD" if r["status"] == "GOOD" else "❌ BAD"
        log_lines.append(f"{r['session_id']:<15} {status_sym:<8} {r['cookies_count']:<8} {r['email']:<32} {r['reason']}")

    log_lines.append("-" * 75)
    log_lines.append("\nSUMMARY LISTS:")
    log_lines.append(f"GOOD SESSIONS ({len(good_list)}):")
    log_lines.append(", ".join(r["session_id"] for r in good_list) if good_list else "None")
    log_lines.append(f"\nBAD SESSIONS ({len(bad_list)}):")
    log_lines.append(", ".join(r["session_id"] for r in bad_list) if bad_list else "None")
    log_lines.append("=" * 75)

    report_text = "\n".join(log_lines)

    # Save to file
    with open(args.log_file, "w") as f:
        f.write(report_text + "\n")

    # Output to console
    print("\n" + report_text)
    print(f"\n📄 Complete report saved to: {args.log_file}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}", file=sys.stderr)
        sys.exit(1)
