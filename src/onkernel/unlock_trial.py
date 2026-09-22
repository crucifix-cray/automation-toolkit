#!/usr/bin/env python3
"""Unlock OnKernel full trial potential after signup / org reset.

Owner flow (2026-09-22):
  proxies page → click "start trial"
  → select "just exploring"
  → click "start trial" again
"""
from __future__ import annotations

import re


PROXIES_URLS = (
    "https://dashboard.onkernel.com/proxies",
    "https://dashboard.onkernel.com/platform/proxies",
    "https://dashboard.onkernel.com/settings/proxies",
)


async def unlock_full_potential(page, log=print) -> bool:
    """Run proxies → start trial → just exploring → start trial.

    Returns True if the second start-trial click succeeded (best-effort otherwise).
    """
    log("🔓 Unlock trial: goto proxies…")
    landed = False
    for url in PROXIES_URLS:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(4000)
            body = (await page.evaluate("() => (document.body && document.body.innerText) || ''") or "").lower()
            if "sign-in" in page.url or "sign-up" in page.url:
                log(f"  unlock: bounced to auth @ {page.url}")
                return False
            if "prox" in body or "trial" in body or "start trial" in body:
                landed = True
                log(f"  unlock: on {page.url}")
                break
        except Exception as e:
            log(f"  unlock goto {url}: {e}")
    if not landed:
        # last resort: click nav link
        try:
            await page.evaluate("""() => {
              const a = [...document.querySelectorAll('a,button')].find(
                x => /prox/i.test((x.innerText||'') + (x.getAttribute('href')||'')));
              if (a) a.click();
            }""")
            await page.wait_for_timeout(4000)
            log(f"  unlock: nav-click → {page.url}")
        except Exception as e:
            log(f"  unlock nav-click: {e}")

    await page.screenshot(path="/tmp/onk-unlock-proxies.png")

    # 1) first Start trial (opens agent-count form)
    log("🔓 Unlock: click start trial #1…")
    if not await _click_start_trial(page, log):
        log("  unlock: no start trial #1 — maybe already unlocked")
        await page.screenshot(path="/tmp/onk-unlock-no-trial1.png")
        return False
    await page.wait_for_timeout(3000)
    await page.screenshot(path="/tmp/onk-unlock-trial-form.png")

    # 2) just exploring
    log("🔓 Unlock: select just exploring…")
    clicked_explore = False
    for attempt in (
        lambda: page.get_by_role("button", name=re.compile(r"just\s*exploring", re.I)).first,
        lambda: page.get_by_text(re.compile(r"just\s*exploring", re.I)).first,
        lambda: page.locator("text=/just\\s*exploring/i").first,
    ):
        try:
            loc = attempt()
            await loc.click(timeout=5000)
            clicked_explore = True
            log("  unlock: clicked just exploring")
            break
        except Exception:
            continue
    if not clicked_explore:
        try:
            ok = await page.evaluate("""() => {
              const el = [...document.querySelectorAll('button,div,label,span,a')]
                .find(x => /just\\s*exploring/i.test((x.innerText||'').trim())
                       && (x.innerText||'').trim().length < 40);
              if (!el) return false;
              el.click();
              return true;
            }""")
            clicked_explore = bool(ok)
            log(f"  unlock: JS just exploring → {ok}")
        except Exception as e:
            log(f"  unlock just exploring fail: {e}")
    await page.wait_for_timeout(1500)

    # 3) start trial again (confirm)
    log("🔓 Unlock: click start trial #2…")
    ok2 = await _click_start_trial(page, log)
    await page.wait_for_timeout(4000)
    await page.screenshot(path="/tmp/onk-unlock-done.png")
    log(f"🔓 Unlock done (start#2={ok2}) @ {page.url}")
    return ok2


async def _click_start_trial(page, log) -> bool:
    # proxies CTA = "start a trial"; form confirm = "start trial"
    for attempt in (
        lambda: page.get_by_role("button", name=re.compile(r"start\s+(a\s+)?trial", re.I)).first,
        lambda: page.locator('button:has-text("start a trial")').first,
        lambda: page.locator('button:has-text("start trial")').first,
        lambda: page.locator('button:has-text("Start a trial")').first,
        lambda: page.locator('button:has-text("Start trial")').first,
        lambda: page.get_by_text(re.compile(r"^start\s+(a\s+)?trial$", re.I)).first,
    ):
        try:
            loc = attempt()
            await loc.click(timeout=6000)
            log("  unlock: start trial clicked")
            return True
        except Exception:
            continue
    try:
        ok = await page.evaluate("""() => {
          const b = [...document.querySelectorAll('button')]
            .find(x => /^start\\s+(a\\s+)?trial$/i.test((x.innerText||'').trim()));
          if (!b) return false;
          b.click();
          return true;
        }""")
        log(f"  unlock: JS start trial → {ok}")
        return bool(ok)
    except Exception as e:
        log(f"  unlock start trial fail: {e}")
        return False
