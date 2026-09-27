#!/usr/bin/env python3
"""Dispose multi-address probe loop: cycle up to N dispose inboxes in ONE
fresh OnK browser (fresh context = fresh address), SMTP-probe each, keep
the browser open on the first LIVE address for handoff.

Handoff: --out JSON gets {email, cdp_ws_url, live_url, session_id, onk_email}.
A farmer attaches with KERNEL_CDP_WS / KERNEL_LIVE_URL / KERNEL_SESSION_ID.

Usage:
  python3 src/farming/probe_dispose_loop.py --key-index 62 --max 10 --wait 40 --out /tmp/dispose_live.json
"""
from __future__ import annotations

import argparse
import asyncio
import glob
import json
import os
import random
import re
import string
import subprocess
import sys
import time
from pathlib import Path

REPO = Path("/home/alan/Documents/railways")
SMTP_CFG = os.path.expanduser("~/.config/lovfarm/smtp.json")
GMAIL_RE = re.compile(r"[a-z0-9._%+-]+@gmail\.com", re.I)


def pick_key(idx: int) -> dict:
    fps = sorted(glob.glob(str(REPO / "finals" / "sessions" / "onk-*" / "session.json")))
    d = json.load(open(fps[idx % len(fps)]))
    return {"email": d.get("email"), "api_key": d["api_key"]}


def kn_create(key: str) -> dict:
    out = subprocess.check_output(
        "kernel browsers create --stealth --timeout 1800 --start-url https://dispose.lol -o json",
        shell=True, env={**os.environ, "KERNEL_API_KEY": key}, text=True, timeout=90)
    return json.loads(out)


def kn_delete(key: str, sid: str) -> None:
    subprocess.run(f"kernel browsers delete {sid}", shell=True,
                   env={**os.environ, "KERNEL_API_KEY": key},
                   timeout=20, capture_output=True)


def smtp_send(to_addr: str, marker: str) -> str:
    import smtplib, ssl
    from email.message import EmailMessage
    cfg = json.load(open(SMTP_CFG))
    user, pwd = cfg.get("gmail_user", ""), cfg.get("gmail_app_pwd", "")
    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = to_addr
    msg["Subject"] = marker
    msg.set_content(f"deliverability probe {marker}")
    ctx = ssl.create_default_context()
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as s:
        s.starttls(context=ctx)
        s.login(user, pwd.replace(" ", ""))
        s.send_message(msg)
    return user


async def inbox_labels(page) -> list:
    try:
        return await page.evaluate(
            """() => [...document.querySelectorAll('button[aria-label^="View "]')]
                 .map(b => b.getAttribute('aria-label') || '')""")
    except Exception:
        return []


async def probe_one(browser, marker: str, wait_s: int, tag: str) -> str | None:
    """Fresh context -> dispose Gmail -> SMTP probe -> poll. Returns live email or None."""
    ctx = await browser.new_context()
    page = await ctx.new_page()
    try:
        await page.goto("https://dispose.lol", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)
        body = await page.evaluate("() => document.body.innerText") or ""
        gmails = [m for m in GMAIL_RE.findall(body)]
        if not gmails:
            print(f"[{tag}] no Gmail on page", flush=True)
            return None
        addr = gmails[0]
        print(f"[{tag}] target {addr}", flush=True)
        try:
            await asyncio.to_thread(smtp_send, addr, marker)
        except Exception as e:
            print(f"[{tag}] send fail {str(e)[:100]}", flush=True)
            return None
        deadline = time.time() + wait_s
        check = 0
        while time.time() < deadline:
            check += 1
            try:
                await page.reload(wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass
            await page.wait_for_timeout(3000)
            labels = await inbox_labels(page)
            if any(marker in (a or "") for a in labels):
                print(f"[{tag}] LANDED check #{check} -> {addr}", flush=True)
                return addr
            if check % 4 == 1:
                print(f"[{tag}] poll #{check}: {len(labels)} msgs", flush=True)
            await asyncio.sleep(2)
        print(f"[{tag}] miss after {wait_s}s", flush=True)
        return None
    finally:
        try:
            await ctx.close()
        except Exception:
            pass


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key-index", type=int, default=62)
    ap.add_argument("--max", type=int, default=10)
    ap.add_argument("--wait", type=int, default=40)
    ap.add_argument("--out", type=str, default="/tmp/dispose_live.json")
    a = ap.parse_args()

    key = pick_key(a.key_index)
    print(f"key: {key['email']}  max={a.max} wait={a.wait}s", flush=True)
    data = kn_create(key["api_key"])
    sid = data["session_id"]
    print(f"LIVE: {data['browser_live_view_url']}", flush=True)
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = None
            for _cc in range(4):
                try:
                    browser = await pw.chromium.connect_over_cdp(data["cdp_ws_url"], timeout=45000)
                    break
                except Exception as _ce:
                    print(f"cdp connect try {_cc+1}/4: {str(_ce)[:100]}", flush=True)
                    await asyncio.sleep(15)
            if browser is None:
                print("CDP UNREACHABLE after retries", flush=True)
                sys.exit(3)
            for i in range(1, a.max + 1):
                marker = "lovprobe-" + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
                print(f"--- address {i}/{a.max} marker {marker}", flush=True)
                addr = await probe_one(browser, marker, a.wait, f"a{i}")
                if addr:
                    json.dump({"email": addr, "cdp_ws_url": data["cdp_ws_url"],
                               "live_url": data["browser_live_view_url"], "session_id": sid,
                               "onk_email": key["email"], "marker": marker},
                              open(a.out, "w"), indent=2)
                    print(f"LIVE ADDRESS: {addr} -> {a.out} (browser kept open)", flush=True)
                    return
            print("NO LIVE ADDRESS in loop", flush=True)
            sys.exit(1)
    except SystemExit:
        raise
    except Exception as e:
        print(f"LOOP FAIL: {e}", flush=True)
        sys.exit(2)
    finally:
        # delete the browser only if no live address was saved
        if not os.path.exists(a.out):
            kn_delete(key["api_key"], sid)
            print("browser cleaned (no live address)", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
