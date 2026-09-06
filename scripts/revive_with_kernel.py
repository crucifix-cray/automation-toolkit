#!/usr/bin/env python3
"""
Lovable Session Reviver via OnKernel Stealth Browsers
Spins up unique, fresh OnKernel stealth browsers in batches of 5 to revive sessions.

Usage:
  python3 scripts/revive_with_kernel.py --pth session-7
  python3 scripts/revive_with_kernel.py --pth all --par 5
"""

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

KERNEL_API_KEY = os.environ.get(
    "KERNEL_API_KEY",
    "sk_f0a9980a-d5e6-fc2e-869e-ce2143c00595.HZD7XmkCxPGjvbgur-zL2qIa8sEQfXmdDgolE-XXAOk",
)

DEFAULT_SESSIONS_DIR = Path(__file__).resolve().parent / "sessions"
DASHBOARD_MARKERS = ["/dashboard", "/projects"]
LOGIN_URL = "https://lovable.dev/login"

# Already verified alive sessions to skip unless specifically requested
KNOWN_ALIVE = {
    "session-3",
    "session-4",
    "session-11",
    "session-1788604282",
    "session-1788604452",
}


def natural_sort_key(s: Path):
    nums = re.findall(r"\d+", s.name)
    return int(nums[0]) if nums else 999999


def resolve_targets(pth_arg: str, sessions_dir: Path, skip_alive: bool = True) -> list[Path]:
    pth_clean = pth_arg.strip().lower()

    if pth_clean == "all":
        sessions = sorted(sessions_dir.glob("session-*"), key=natural_sort_key)
        if skip_alive:
            sessions = [s for s in sessions if s.name not in KNOWN_ALIVE]
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


def create_kernel_browser(timeout: int = 180) -> tuple[str, str]:
    """Create a unique stealth OnKernel browser session. Returns (session_id, cdp_ws_url)."""
    cmd = f"kernel browsers create --stealth --timeout {timeout} -o json"
    env = {**os.environ, "KERNEL_API_KEY": KERNEL_API_KEY}
    out = subprocess.check_output(cmd, shell=True, env=env, timeout=30).decode()
    data = json.loads(out)
    return data["session_id"], data["cdp_ws_url"]


def delete_kernel_browser(session_id: str):
    """Delete the OnKernel browser session to free resources."""
    try:
        subprocess.run(
            f"kernel browsers delete {session_id}",
            shell=True,
            env={**os.environ, "KERNEL_API_KEY": KERNEL_API_KEY},
            timeout=10,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


async def revive_session_on_kernel(session_dir: Path, sem: asyncio.Semaphore) -> dict:
    session_id = session_dir.name
    config_file = session_dir / "config.json"
    cookies_file = session_dir / "cookies.json"

    result = {
        "session_id": session_id,
        "email": "",
        "status": "FAILED",
        "reason": "",
        "kernel_session": "",
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
        result["reason"] = f"Error reading config: {e}"
        return result

    email = cfg.get("email", "").strip()
    password = cfg.get("password", "").strip() or email
    result["email"] = email

    if not email:
        result["reason"] = "Email missing in config.json"
        return result

    start_time = time.time()

    async with sem:
        kernel_session_id = None
        try:
            print(f"[{session_id}] 🌐 Spawning unique OnKernel browser...")
            loop = asyncio.get_running_loop()
            kernel_session_id, cdp_ws_url = await loop.run_in_executor(
                None, create_kernel_browser, 240
            )
            result["kernel_session"] = kernel_session_id
            print(f"[{session_id}] ⚡ Connected to OnKernel ({kernel_session_id[:10]}...)")

            async with async_playwright() as p:
                browser = await p.chromium.connect_over_cdp(cdp_ws_url, timeout=20000)
                context = browser.contexts[0] if browser.contexts else await browser.new_context()
                page = context.pages[0] if context.pages else await context.new_page()

                print(f"[{session_id}] 🔄 Navigating to login for {email}...")
                await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)

                # Cookie consent
                try:
                    ok_btn = page.locator("[data-testid='consent-accept-all-button'], button:has-text('OK')").first
                    if await ok_btn.is_visible():
                        await ok_btn.click(timeout=1000)
                except Exception:
                    pass

                # Enter email
                email_inp = page.locator("input[type='email'], input[name='email']").first
                await email_inp.wait_for(state="visible", timeout=10000)
                await email_inp.fill(email)
                await page.wait_for_timeout(300)

                # Click Continue (exact data-testid)
                submit_btn = page.locator("button[data-testid='auth-submit-button']").first
                await submit_btn.click()

                # Wait for password
                pwd_inp = page.locator("input[type='password'], input[name='password']").first
                try:
                    await pwd_inp.wait_for(state="visible", timeout=10000)
                except Exception:
                    body_text = await page.locator("body").inner_text()
                    if "suspicious activity" in body_text.lower():
                        result["reason"] = "Blocked: Suspicious activity (at email step)"
                    else:
                        result["reason"] = "Password field did not appear"
                    print(f"[{session_id}] ❌ FAILED - {result['reason']}")
                    return result

                # Enter password
                await pwd_inp.fill(password)
                await page.wait_for_timeout(400)

                # Submit password
                submit_btn = page.locator("button[data-testid='auth-submit-button']").first
                await submit_btn.click()
                print(f"[{session_id}] 🔑 Password submitted, awaiting dashboard...")

                # Monitor for success or error
                revived = False
                detected_reason = "Login did not finish within timeout"

                for _ in range(20):  # 10s polling
                    await asyncio.sleep(0.5)
                    curr_url = page.url

                    if any(m in curr_url for m in DASHBOARD_MARKERS):
                        revived = True
                        detected_reason = f"Dashboard reached ({curr_url})"
                        break

                    try:
                        has_dash = await page.locator("a[href*='/projects'], a[href*='/templates'], button:has-text('New project'), [data-slot='avatar']").first.is_visible()
                        if has_dash:
                            revived = True
                            detected_reason = f"Dashboard UI authenticated ({curr_url})"
                            break
                    except Exception:
                        pass

                    try:
                        body_text = await page.locator("body").inner_text()
                        if "Login denied due to suspicious activity" in body_text:
                            detected_reason = "Blocked: 'Login denied due to suspicious activity'"
                            break
                        if "The provided credentials are invalid" in body_text or "Invalid email or password" in body_text:
                            detected_reason = "Invalid credentials"
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

                await browser.close()

        except Exception as e:
            result["status"] = "FAILED"
            result["reason"] = f"Error: {e}"
            print(f"[{session_id}] ❌ FAILED - {e}")
        finally:
            result["duration"] = round(time.time() - start_time, 2)
            if kernel_session_id:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, delete_kernel_browser, kernel_session_id)

    return result


async def main():
    parser = argparse.ArgumentParser(description="Revive Lovable sessions using unique OnKernel stealth browsers")
    parser.add_argument("--pth", type=str, default="all", help="Session ID (e.g. session-7, 7) or 'all'")
    parser.add_argument("--par", type=int, default=5, help="Parallel OnKernel browsers (default: 5)")
    parser.add_argument("--sessions-dir", type=Path, default=DEFAULT_SESSIONS_DIR, help="Sessions directory")
    parser.add_argument("--include-alive", action="store_true", help="Also retry already alive sessions")
    parser.add_argument("--log-file", type=str, default="kernel_revive_results.log", help="Log output file path")
    args = parser.parse_args()

    targets = resolve_targets(args.pth, args.sessions_dir, skip_alive=not args.include_alive)
    total_targets = len(targets)
    concurrency = min(args.par, total_targets) if total_targets > 0 else 1

    print("=" * 70)
    print("🚀 LOVABLE REVIVER (ONKERNEL REMOTE STEALTH BROWSERS)")
    print(f"  Target(s)    : {args.pth} ({total_targets} session{'s' if total_targets != 1 else ''})")
    print(f"  Parallelism  : {concurrency} concurrent OnKernel browsers")
    print(f"  Kernel Key   : {KERNEL_API_KEY[:15]}...{KERNEL_API_KEY[-8:]}")
    print(f"  Log File     : {args.log_file}")
    print("=" * 70)

    sem = asyncio.Semaphore(concurrency)
    tasks = [revive_session_on_kernel(target, sem) for target in targets]
    results = await asyncio.gather(*tasks)

    revived_list = [r for r in results if r["status"] == "REVIVED"]
    failed_list = [r for r in results if r["status"] == "FAILED"]

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log_lines = []
    log_lines.append("=" * 75)
    log_lines.append(f"ONKERNEL LOVABLE REVIVAL REPORT - {timestamp}")
    log_lines.append("=" * 75)
    log_lines.append(f"Total Attempted : {len(results)}")
    log_lines.append(f"REVIVED (Fresh) : {len(revived_list)} ({round(len(revived_list)/len(results)*100, 1) if results else 0}%)")
    log_lines.append(f"FAILED          : {len(failed_list)} ({round(len(failed_list)/len(results)*100, 1) if results else 0}%)")
    log_lines.append("-" * 75)
    log_lines.append(f"{'Session':<15} {'Status':<10} {'Cookies':<8} {'Email':<32} {'Failure Reason'}")
    log_lines.append("-" * 75)

    for r in results:
        status_sym = "✅ REVIVED" if r["status"] == "REVIVED" else "❌ FAILED"
        log_lines.append(f"{r['session_id']:<15} {status_sym:<10} {r['cookies_saved']:<8} {r['email']:<32} {r['reason']}")

    log_lines.append("-" * 75)
    log_lines.append(f"\nREVIVED SESSIONS ({len(revived_list)}):")
    log_lines.append(", ".join(r["session_id"] for r in revived_list) if revived_list else "None")
    log_lines.append(f"\nFAILED SESSIONS ({len(failed_list)}):")
    log_lines.append(", ".join(r["session_id"] for r in failed_list) if failed_list else "None")
    log_lines.append("=" * 75)

    report_text = "\n".join(log_lines)
    with open(args.log_file, "w") as f:
        f.write(report_text + "\n")

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
