#!/usr/bin/env python3
"""Read ZenRows credit balance via dashboard login (headed Chromium under Xvfb).
Usage: python3 scripts/zenrows_balance.py [--keys 11d7d0ee,7213c843 | --all]
Reads finals/zenrows_onkernel_farmed.json for email+password per api_key.
Costs zero API credits (plain web login, local browser).
"""
import json, re, subprocess, sys, time, os
from pathlib import Path

REPO = Path("/home/alan/Documents/railways")
FARMED = json.load(open(REPO / "finals/zenrows_onkernel_farmed.json"))
BYKEY = {e["api_key"]: e for e in FARMED}


def start_xvfb():
    p = subprocess.Popen(["Xvfb", ":99", "-screen", "0", "1280x720x24"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    return p


def get_balance(email, password):
    from patchright.sync_api import sync_playwright
    env = dict(os.environ, DISPLAY=":99", LD_PRELOAD="")
    # patchright reads DISPLAY from env at launch
    os.environ["DISPLAY"] = ":99"
    with sync_playwright() as p:
        b = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        pg = b.new_page()
        try:
            pg.goto("https://app.zenrows.com/login", timeout=45000)
            for _ in range(15):
                pg.wait_for_timeout(4000)
                if "Just a moment" not in pg.title() and pg.locator('input[type="email"]').count():
                    break
            if not pg.locator('input[type="email"]').count():
                return {"error": "cf-blocked: " + pg.title()}
            pg.fill('input[type="email"]', email)
            # Google OAuth: identifier -> Next -> password -> Next
            try:
                pg.locator('button:has-text("Next")').first.click(timeout=10000)
            except Exception:
                pg.press('input[type="email"]', "Enter")
            pg.wait_for_timeout(5000)
            if pg.locator('input[type="password"]').count():
                pg.fill('input[type="password"]', password)
                try:
                    pg.locator('button:has-text("Next")').first.click(timeout=10000)
                except Exception:
                    pg.press('input[type="password"]', "Enter")
                pg.wait_for_timeout(8000)
            # find credits anywhere ("231 of 5,000 credits used" on overview)
            txt = pg.inner_text("body")
            m = re.search(r"([\d,]+)\s+of\s+([\d,]+)\s+credits used", txt, re.I)
            if m:
                return {"used": m.group(1), "allowance": m.group(2)}
            m = re.search(r"([\d,]+)\s*(?:/\s*([\d,]+))?\s*credits?", txt, re.I)
            if m:
                return {"used_or_left": m.group(1), "of": m.group(2)}
            # try overview/billing pages
            for url in ("https://app.zenrows.com/overview", "https://app.zenrows.com/billing"):
                try:
                    pg.goto(url, timeout=30000)
                    pg.wait_for_timeout(4000)
                    txt = pg.inner_text("body")
                    m = re.search(r"([\d,]+)\s*(?:/\s*([\d,]+))?\s*credits?", txt, re.I)
                    if m:
                        return {"used_or_left": m.group(1), "of": m.group(2), "page": url}
                except Exception:
                    pass
            return {"error": "no-credits-found", "title": pg.title(), "url": pg.url}
        finally:
            try:
                b.close()
            except Exception:
                pass


def main():
    keys = None
    if "--keys" in sys.argv:
        keys = sys.argv[sys.argv.index("--keys") + 1].split(",")
    elif "--all" in sys.argv:
        keys = list(BYKEY)
    else:
        print("usage: --keys k1,k2 | --all")
        return
    xvfb = start_xvfb()
    out = {}
    try:
        for k in keys:
            k = k.strip()
            e = BYKEY.get(k)
            if not e:
                # prefix match
                cand = [kk for kk in BYKEY if kk.startswith(k)]
                e = BYKEY[cand[0]] if cand else None
            if not e:
                out[k] = {"error": "not-in-farmed"}
                continue
            print(f"{k[:8]} {e['email']} ...", flush=True)
            try:
                out[k] = {"email": e["email"], **get_balance(e["email"], e["password"])}
            except Exception as ex:
                out[k] = {"email": e["email"], "error": str(ex)[:120]}
            print(f"  -> {out[k]}", flush=True)
    finally:
        try:
            xvfb.terminate()
        except Exception:
            pass
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
