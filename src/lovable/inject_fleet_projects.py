#!/usr/bin/env python3
"""Resume script2 bridge inject on already-remixed fleet projects (OnKernel).

For each (lovable_session, project_id): create Kernel browser → load cookies →
open project → paste prompts/Build a debug terminal.txt → wait for window.doc
(same helper as remix_inject.inject_and_wait_bridge).

Does NOT touch cell-16 / session-2 mining project 7d6f77a6.

Usage:
  python3 src/lovable/inject_fleet_projects.py
  python3 src/lovable/inject_fleet_projects.py --jobs /tmp/fleet_jobs.json
  python3 src/lovable/inject_fleet_projects.py --only 05da1af6,b06e4a07
  python3 src/lovable/inject_fleet_projects.py --workers 2 --wait 900
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

CORE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(CORE))
sys.path.insert(0, CORE)

import remix_inject as R  # noqa: E402

# rail_session, lovable_session, project_id — last remixed fleet batch
DEFAULT_JOBS = [
    [1, 1, "05da1af6-0626-4746-a339-92d7e6b2e3e1"],
    [3, 2, "b06e4a07-95fb-4dc3-89a8-72ca84f2f25d"],
    [4, 3, "211af3cb-5c3a-40b6-9a59-9bc0fe7b27de"],
    [5, 3, "0f318cab-b3a4-49a1-a168-7e9fe36304ca"],
    [6, 4, "ce592dc0-eb0f-4500-81ae-2f848840aaac"],
    [7, 5, "b3ded203-a845-4037-a648-5fbad0cba931"],
    [8, 6, "8ca51fa8-2c22-44d3-9510-a069084f791f"],
    [9, 7, "e8ee22a2-7ea3-4f0c-8650-bd6b933288b0"],
    [10, 8, "c0bafd1e-33d8-4625-89a4-1250f4755d23"],
    [11, 8, "9421eb8a-e853-49b2-a0dd-657c80246c5d"],
]
SKIP_PROJECTS = {"7d6f77a6-69a1-4b06-a1d3-53094c4c8019"}  # cell-16 mining

# OnKernel org unified_concurrent_sessions hard cap (observed: 5)
KERNEL_SLOT_LIMIT = int(os.environ.get("KERNEL_SLOT_LIMIT", "5"))
_kernel_slots: asyncio.Semaphore | None = None


def _slots() -> asyncio.Semaphore:
    global _kernel_slots
    if _kernel_slots is None:
        _kernel_slots = asyncio.Semaphore(max(1, KERNEL_SLOT_LIMIT))
    return _kernel_slots


async def _create_browser_retry(label: str, tries: int = 16):
    """Create Kernel browser; retry on org/rate limit until a slot frees."""
    import subprocess as _sp
    last = None
    for i in range(tries):
        try:
            return await asyncio.to_thread(R._new_browser)
        except Exception as e:
            last = e
            wait = min(60, 4 + i * 4)
            R.log(f"{label} kernel create fail ({type(e).__name__}) — retry {i+1}/{tries} in {wait}s")
            await asyncio.sleep(wait)
            continue
    raise last  # type: ignore[misc]



def _load_jobs(path: str | None, only: set[str] | None):
    jobs = DEFAULT_JOBS
    if path and os.path.exists(path):
        jobs = json.loads(Path(path).read_text())
    out = []
    for row in jobs:
        rail, lov, pid = int(row[0]), int(row[1]), str(row[2])
        if pid in SKIP_PROJECTS:
            continue
        if only and not any(pid.startswith(o) or o in pid for o in only):
            continue
        out.append((rail, lov, pid))
    return out


def _cookies_for_session(num: int):
    ck_path = os.path.join(R.SESSIONS, f"session-{num}", "cookies.json")
    raw = json.load(open(ck_path))
    cookies = []
    for c in raw:
        if "lovable" not in c.get("domain", ""):
            continue
        cookies.append({
            "name": c["name"], "value": c["value"], "domain": c["domain"],
            "path": c.get("path", "/"),
            "expires": int(c["expires"]) if c.get("expires") else -1,
            "httpOnly": bool(c.get("httpOnly", False)),
            "secure": bool(c.get("secure", False)),
            "sameSite": c.get("sameSite", "Lax") if c.get("sameSite") in ("Lax", "Strict", "None") else "Lax",
        })
    return cookies, ck_path


async def inject_one(pw, lov_sess: int, project_id: str, rail: int, wait_s: int):
    cfg_path = os.path.join(R.SESSIONS, f"session-{lov_sess}", "config.json")
    cfg = json.load(open(cfg_path))
    email = cfg["email"]
    password = cfg.get("password", email)
    url = f"https://lovable.dev/projects/{project_id}"
    label = f"rail-{rail}/lov-s{lov_sess}/{project_id[:8]}"
    R.log(f"{label} start email={email}")

    sid = None
    browser = None
    async with _slots():
        os.environ["KERNEL_BROWSER_NAME"] = f"fleet-inject-{project_id[:8]}-{int(time.time())}"
        try:
            cdp_ws, sid = await _create_browser_retry(label)
        except Exception as e:
            return {"rail": rail, "session": lov_sess, "email": email, "project_id": project_id,
                    "success": False, "reason": f"kernel create: {e}"[:240], "bridge": False}
        try:
        browser = await pw.chromium.connect_over_cdp(cdp_ws, timeout=60000)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        cookies, ck_path = _cookies_for_session(lov_sess)
        await ctx.add_cookies(cookies)
        page = await ctx.new_page()
        _alts = [cfg.get("password_alt"), cfg.get("password_backup")]
        if not await R._login(
            page, email, password, cfg.get("totp_secret"), cfg.get("totp_secret_backup"),
            password_alts=[a for a in _alts if a],
        ):
            return {"rail": rail, "session": lov_sess, "email": email, "project_id": project_id,
                    "success": False, "reason": "login failed", "bridge": False}

        await page.goto(url, timeout=90000, wait_until="domcontentloaded")
        await page.wait_for_timeout(8000)
        if "Log in" in await R._safe_text(page, 400):
            return {"rail": rail, "session": lov_sess, "email": email, "project_id": project_id,
                    "success": False, "reason": "auth wall on project", "bridge": False}

        inj = await R.inject_and_wait_bridge(page, ctx, label=label, wait_s=wait_s)
        try:
            fresh = await ctx.cookies()
            json.dump(fresh, open(ck_path, "w"), indent=2)
        except Exception:
            pass
        cfg["project_id"] = project_id
        cfg["project_link"] = url
        cfg["last_bridge_inject_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        cfg["bridge_ok"] = bool(inj.get("bridge"))
        json.dump(cfg, open(cfg_path, "w"), indent=2)

        return {
            "rail": rail, "session": lov_sess, "email": email, "project_id": project_id,
            "project_link": url, "success": bool(inj.get("bridge")),
            "reason": inj.get("reason"), "bridge": bool(inj.get("bridge")),
            "preview_url": inj.get("preview_url"), "pwd": inj.get("pwd"),
            "kernel_sid": sid, "live": None,
        }
    except Exception as e:
        return {"rail": rail, "session": lov_sess, "email": email, "project_id": project_id,
                "success": False, "reason": str(e)[:240], "bridge": False, "kernel_sid": sid}
    finally:
        try:
            if browser:
                await browser.close()
        except Exception:
            pass
        await asyncio.to_thread(R._del_browser, sid)


async def main():
    ap = argparse.ArgumentParser(description="Inject Build a debug terminal on fleet remix projects (OnKernel)")
    ap.add_argument("--jobs", default="/tmp/fleet_jobs.json")
    ap.add_argument("--only", default="", help="comma project-id prefixes to include")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--wait", type=int, default=900, help="seconds to wait for window.doc per project")
    ap.add_argument("--out", default="/tmp/fleet_inject_results.json")
    a = ap.parse_args()
    R.clear_proxy()

    only = {x.strip() for x in a.only.split(",") if x.strip()} or None
    jobs = _load_jobs(a.jobs, only)
    if not jobs:
        raise SystemExit("no jobs")
    print(f"jobs={len(jobs)} workers={a.workers} wait={a.wait}s prompt_chars={len(R.SUBPROCESS_PROMPT)}", flush=True)
    for rail, lov, pid in jobs:
        print(f"  rail-{rail} lov-s{lov} {pid}", flush=True)

    from playwright.async_api import async_playwright

    queue: asyncio.Queue = asyncio.Queue()
    for j in jobs:
        queue.put_nowait(j)
    results = []
    results_lock = asyncio.Lock()

    async def worker(wid: int, pw):
        await asyncio.sleep(wid * 5)
        while True:
            try:
                rail, lov, pid = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            R.log(f"worker-{wid} → rail-{rail} lov-s{lov} {pid[:8]}")
            res = await inject_one(pw, lov, pid, rail, a.wait)
            print(json.dumps(res, default=str), flush=True)
            async with results_lock:
                results.append(res)

    async with async_playwright() as pw:
        await asyncio.gather(*[worker(i, pw) for i in range(max(1, a.workers))])

    Path(a.out).write_text(json.dumps(results, indent=2, default=str))
    ok = sum(1 for r in results if r.get("bridge"))
    print(f"\n{ok}/{len(results)} bridge OK → {a.out}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
