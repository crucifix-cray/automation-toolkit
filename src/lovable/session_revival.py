#!/usr/bin/env python3
"""
Lovable Session Reviver
Attempts to revive sessions by logging in with their stored email & password from config.json.
If login succeeds, overwrites cookies.json with fresh authenticated cookies.
If login fails, logs the exact error (e.g. suspicious activity IP flag, invalid credentials).

Usage:
  python3 scripts/revive_sessions_login.py --pth session-7
  python3 scripts/revive_sessions_login.py --pth all --par 3
  python3 scripts/revive_sessions_login.py --pth all --par 5 --cdp-url "<ZENROWS_CDP>"
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

DEFAULT_SESSIONS_DIR = Path(__file__).resolve().parent / "sessions"
DASHBOARD_MARKERS = ["/dashboard", "/projects"]
LOGIN_URL = "https://lovable.dev/login"


def natural_sort_key(s: Path):
    nums = re.findall(r"\d+", s.name)
    return int(nums[0]) if nums else 999999


def resolve_targets(pth_arg: str, sessions_dir: Path) -> list[Path]:
    pth_clean = pth_arg.strip().lower()

    if pth_clean == "all":
        sessions = sorted(sessions_dir.glob("session-*"), key=natural_sort_key)
        return sessions

    if pth_clean.isdigit():
        target_name = f"session-{pth_clean}"
    elif pth_clean.startswith("session") and not pth_clean.startswith("session-"):
        target_name = f"session-{pth_clean.replace('session', '')}"
    else:
        target_name = pth_clean

    target_dir = sessions_dir / target_name
    if not target_dir.exists():
        print(f"❌ Session directory not found: {target_dir}", file=sys.stderr)
        sys.exit(1)

    return [target_dir]


async def revive_single_session(session_dir: Path, browser, sem: asyncio.Semaphore, timeout: int) -> dict:
    session_id = session_dir.name
    config_file = session_dir / "config.json"
    cookies_file = session_dir / "cookies.json"

    result = {
        "session_id": session_id,
        "email": "",
        "status": "FAILED",
        "reason": "",
        "cookies_saved": 0,
        "duration": 0.0,
    }

    if not config_file.exists():
        result["reason"] = "config.json missing"
        print(f"[{session_id}] ❌ FAILED - config.json missing")
        return result

    try:
        with open(config_file) as f:
            cfg = json.load(f)
    except Exception as e:
        result["reason"] = f"Error reading config.json: {e}"
        print(f"[{session_id}] ❌ FAILED - corrupt config.json")
        return result

    email = cfg.get("email", "").strip()
    password = cfg.get("password", "").strip()
    result["email"] = email

    if not email:
        result["reason"] = "No email in config.json"
        print(f"[{session_id}] ❌ FAILED - email missing in config")
        return result

    if not password:
        password = email  # default convention in early flows

    start_time = time.time()

    async with sem:
        context = None
        try:
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            print(f"[{session_id}] 🔄 Attempting login for {email}...")

            # 1. Navigate to login
            await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=timeout * 1000)
            await page.wait_for_timeout(1500)

            # Accept cookie banner if present
            try:
                ok_btn = page.locator("[data-testid='consent-accept-all-button'], button:has-text('OK')").first
                if await ok_btn.is_visible():
                    await ok_btn.click(timeout=1000)
            except Exception:
                pass

            # 2. Fill Email
            email_inp = page.locator("input[type='email'], input[name='email']").first
            await email_inp.wait_for(state="visible", timeout=8000)
            await email_inp.fill(email)
            await page.wait_for_timeout(300)

            submit_btn = page.locator("button[data-testid='auth-submit-button']").first
            await submit_btn.click()

            # 3. Wait for password input or immediate error
            pwd_inp = page.locator("input[type='password'], input[name='password']").first
            try:
                await pwd_inp.wait_for(state="visible", timeout=8000)
            except Exception as pwd_err:
                # Check what appeared
                body_text = await page.locator("body").inner_text()
                if "suspicious activity" in body_text.lower():
                    result["reason"] = "Suspicious activity IP block (at email step)"
                elif "invalid email" in body_text.lower():
                    result["reason"] = "Invalid email format"
                else:
                    result["reason"] = f"Password field did not appear: {pwd_err}"
                print(f"[{session_id}] ❌ FAILED - {result['reason']}")
                return result

            # 4. Fill Password
            await pwd_inp.fill(password)
            await page.wait_for_timeout(400)

            # Submit login form (exact auth-submit-button)
            submit_btn = page.locator("button[data-testid='auth-submit-button']").first
            await submit_btn.click()
            print(f"[{session_id}] 🔑 Password submitted, awaiting response...")

            # 5. Monitor response for success or specific error
            revived = False
            detected_reason = "Login did not complete within timeout"

            for _ in range(20):  # Poll for up to 10s (0.5s intervals)
                await asyncio.sleep(0.5)
                curr_url = page.url

                # Check for dashboard success
                if any(m in curr_url for m in DASHBOARD_MARKERS):
                    revived = True
                    detected_reason = f"Dashboard reached ({curr_url})"
                    break

                has_dash_el = await page.locator("a[href*='/projects'], a[href*='/templates'], button:has-text('New project'), [data-slot='avatar']").first.is_visible()
                if has_dash_el:
                    revived = True
                    detected_reason = f"Dashboard UI authenticated ({curr_url})"
                    break

                # Check for specific failure indicators in page content
                try:
                    body_text = await page.locator("body").inner_text()
                    if "Login denied due to suspicious activity" in body_text or "suspicious activity" in body_text.lower():
                        detected_reason = "Blocked by Lovable: 'Login denied due to suspicious activity' (IP flagged)"
                        revived = False
                        break
                    if "The provided credentials are invalid" in body_text or "Invalid email or password" in body_text:
                        detected_reason = "Invalid credentials (wrong password or unlinked account)"
                        revived = False
                        break
                    if "Turnstile" in body_text or "verify you are human" in body_text.lower():
                        detected_reason = "Cloudflare Turnstile challenge triggered"
                        revived = False
                        break
                except Exception:
                    pass

            if revived:
                fresh_cookies = await context.cookies()
                with open(cookies_file, "w") as f:
                    json.dump(fresh_cookies, f, indent=2)

                cfg["status"] = "active"
                cfg["last_revived_at"] = datetime.now().isoformat()
                cfg["verified"] = True
                with open(config_file, "w") as f:
                    json.dump(cfg, f, indent=2)

                result["status"] = "REVIVED"
                result["reason"] = detected_reason
                result["cookies_saved"] = len(fresh_cookies)
                print(f"[{session_id}] 🎉 SUCCESS: REVIVED! Saved {len(fresh_cookies)} cookies.")
            else:
                result["status"] = "FAILED"
                result["reason"] = detected_reason
                print(f"[{session_id}] ❌ FAILED - {detected_reason}")

        except Exception as e:
            result["status"] = "FAILED"
            result["reason"] = f"Exception: {e}"
            print(f"[{session_id}] ❌ FAILED - {e}")
        finally:
            result["duration"] = round(time.time() - start_time, 2)
            if context:
                try:
                    await context.close()
                except Exception:
                    pass

    return result


async def main():
    parser = argparse.ArgumentParser(description="Revive Lovable sessions by logging in with email & password")
    parser.add_argument("--pth", type=str, default="all", help="Session identifier (e.g. session-7, 7) or 'all'")
    parser.add_argument("--par", type=int, default=3, help="Parallel worker concurrency (default: 3)")
    parser.add_argument("--sessions-dir", type=Path, default=DEFAULT_SESSIONS_DIR, help="Path to sessions directory")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout in seconds (default: 30)")
    parser.add_argument("--cdp-url", type=str, default=None, help="Optional remote CDP URL (e.g. ZenRows)")
    parser.add_argument("--log-file", type=str, default="revive_results.log", help="Log output file path")
    args = parser.parse_args()

    targets = resolve_targets(args.pth, args.sessions_dir)
    total_targets = len(targets)
    concurrency = min(args.par, total_targets) if total_targets > 0 else 1

    print("=" * 70)
    print("🚀 LOVABLE RED REVIVER (LOGIN VIA EMAIL & PWD)")
    print(f"  Target(s)    : {args.pth} ({total_targets} session{'s' if total_targets != 1 else ''})")
    print(f"  Parallelism  : {concurrency}")
    print(f"  Sessions Dir : {args.sessions_dir}")
    print(f"  CDP Remote   : {args.cdp_url or 'Local Chromium'}")
    print(f"  Log File     : {args.log_file}")
    print("=" * 70)

    sem = asyncio.Semaphore(concurrency)

    async with async_playwright() as p:
        if args.cdp_url:
            print(f"Connecting to remote CDP: {args.cdp_url[:60]}...")
            browser = await p.chromium.connect_over_cdp(args.cdp_url)
        else:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ]
            )

        tasks = [revive_single_session(target, browser, sem, args.timeout) for target in targets]
        results = await asyncio.gather(*tasks)

        await browser.close()

    revived_list = [r for r in results if r["status"] == "REVIVED"]
    failed_list = [r for r in results if r["status"] == "FAILED"]

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log_lines = []
    log_lines.append("=" * 75)
    log_lines.append(f"LOVABLE SESSION REVIVAL REPORT - {timestamp}")
    log_lines.append("=" * 75)
    log_lines.append(f"Total Attempted : {len(results)}")
    log_lines.append(f"REVIVED (Fresh) : {len(revived_list)} ({round(len(revived_list)/len(results)*100, 1) if results else 0}%)")
    log_lines.append(f"FAILED          : {len(failed_list)} ({round(len(failed_list)/len(results)*100, 1) if results else 0}%)")
    log_lines.append("-" * 75)
    log_lines.append(f"{'Session':<15} {'Status':<10} {'Cookies':<8} {'Email':<32} {'Failure Reason / Detail'}")
    log_lines.append("-" * 75)

    for r in results:
        status_sym = "✅ REVIVED" if r["status"] == "REVIVED" else "❌ FAILED"
        log_lines.append(f"{r['session_id']:<15} {status_sym:<10} {r['cookies_saved']:<8} {r['email']:<32} {r['reason']}")

    log_lines.append("-" * 75)
    log_lines.append("\nCATEGORY SUMMARY:")
    
    suspicious_count = sum(1 for r in failed_list if "suspicious activity" in r["reason"].lower())
    invalid_creds_count = sum(1 for r in failed_list if "invalid credentials" in r["reason"].lower())
    other_count = len(failed_list) - suspicious_count - invalid_creds_count

    log_lines.append(f"- Suspicious Activity (IP Block): {suspicious_count}")
    log_lines.append(f"- Invalid Credentials: {invalid_creds_count}")
    log_lines.append(f"- Other / Timeout: {other_count}")

    log_lines.append(f"\nREVIVED SESSIONS ({len(revived_list)}):")
    log_lines.append(", ".join(r["session_id"] for r in revived_list) if revived_list else "None")
    log_lines.append(f"\nFAILED SESSIONS ({len(failed_list)}):")
    log_lines.append(", ".join(r["session_id"] for r in failed_list) if failed_list else "None")
    log_lines.append("=" * 75)

    report_text = "\n".join(log_lines)

    with open(args.log_file, "w") as f:
        f.write(report_text + "\n")

    print("\n" + report_text)
    print(f"\n📄 Complete revival report saved to: {args.log_file}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}", file=sys.stderr)
        sys.exit(1)
