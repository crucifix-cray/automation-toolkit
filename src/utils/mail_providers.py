#!/usr/bin/env python3
"""Multi mail providers for ZenRows farm: 22.do, temp.tf, tempmailhub, dispose.
All Gmail one-dot (tempmailhub: clean). Tab-fetch pattern (from lov-zenrows-final.py):
a provider-homed tab does same-origin fetch (beats raw-IP CF blocks + CORS).

Usage:
    from mail_providers import TabFetch, create_22do, create_temptf, create_hub, poll_22do, poll_temptf, poll_hub
"""
import asyncio
import html as _h
import json as _j
import re as _re
import sys
import time

TEMP_TF_API = "https://temp.tf/api"
HUB_API = "https://api.tempmailhub.org"
ZEN_RE = _re.compile(r"https?://[^\s'\"<>]+(?:zenrows\.com|url4722)[^\s'\"<>]*", _re.I)


class TabFetch:
    """A tab homed on origin_url; call() does same-origin fetch via evaluate."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.page = None

    async def home(self, origin_url):
        try:
            if self.page is None:
                self.page = await self.ctx.new_page()
            await self.page.goto(origin_url, wait_until="domcontentloaded", timeout=30000)
            await self.page.wait_for_timeout(2500)
            return True
        except Exception as e:
            print(f"  zf home {origin_url} fail: {str(e)[:100]}", file=sys.stderr)
            return False

    async def call(self, method, url, data=None, headers=None, timeout_ms=20000):
        try:
            return await self.page.evaluate("""async (p) => {
                const ctl = new AbortController();
                const to = setTimeout(() => ctl.abort(), p.timeout_ms);
                try {
                    const r = await fetch(p.url, {method: p.method,
                        headers: p.headers || {'Content-Type':'application/json'},
                        body: (p.data !== undefined && p.data !== null) ? JSON.stringify(p.data) : undefined,
                        signal: ctl.signal});
                    const t = await r.text();
                    return {status: r.status, body: t};
                } catch(e) { return {status: 0, body: 'FETCH_ERR:' + String(e).slice(0,120)}; }
                finally { clearTimeout(to); }
            }""", {"method": method, "url": url, "data": data,
                   "headers": headers or {}, "timeout_ms": timeout_ms})
        except Exception as e:
            return {"status": 0, "body": f"EVAL_ERR:{str(e)[:100]}"}

    async def close(self):
        if self.page:
            try:
                await self.page.close()
            except Exception:
                pass
        self.page = None


def one_dot_gmail(em):
    em = (em or "").strip()
    if not em.lower().endswith("@gmail.com") or "+" in em:
        return False
    return em.split("@")[0].count(".") == 1


# ── 22.do ────────────────────────────────────────────────────────────────
async def create_22do(zf, tries=40):
    for _t in range(tries):
        try:
            _r = await zf.call("POST", "https://22.do/action/mailbox/gmail", {"type": "random"},
                               {"Content-Type": "application/json",
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"})
            if _r["status"] != 200:
                continue
            _em = (((_j.loads(_r["body"])).get("data") or {}).get("email") or "").strip()
            if one_dot_gmail(_em):
                return _em
        except Exception:
            pass
    return None


async def poll_22do(zf, email, timeout_seconds=240):
    import random as _r22
    _uuid = "".join(_r22.choices("0123456789abcdef", k=32))
    _tok = None
    try:
        _tr = await zf.call("POST", "https://22.do/action/mailbox/applyToken",
                            {"email": email, "uuid": _uuid},
                            {"Content-Type": "application/json"})
        _tj = _j.loads(_tr["body"]) if _tr["status"] == 200 else {}
        if _tj.get("status") and (_tj.get("data") or {}).get("token"):
            _tok = _tj["data"]["token"]
    except Exception as _te:
        print(f"  22.do applyToken fail: {str(_te)[:80]}", file=sys.stderr)
    if not _tok:
        return None
    deadline = time.time() + timeout_seconds
    check = 0
    while time.time() < deadline:
        check += 1
        try:
            _mr = await zf.call("POST", "https://22.do/action/mailbox/message",
                                {"email": email, "lastime": 0},
                                {"Content-Type": "application/json",
                                 "Authorization": f"Bearer {_tok}"})
            _mj = _j.loads(_mr["body"]) if _mr["status"] == 200 else {}
            _items = (_mj.get("data") or []) if _mj.get("status") else []
        except Exception:
            _items = []
        if check % 3 == 1:
            print(f"  22.do fetch poll #{check}: {len(_items)} msgs", file=sys.stderr)
        for _m in _items:
            _s = str(_m.get("subject", ""))
            _f = str(_m.get("from", _m.get("sender", "")))
            if "zenrows" in (_s + _f).lower() or "verify" in _s.lower():
                _mid = str(_m.get("messageId", _m.get("id", "")))
                print(f"  FOUND 22.do mail {_s[:80]}", file=sys.stderr)
                _html22 = ""
                if _mid:
                    try:
                        _cr = await zf.call("GET", f"https://22.do/content/{_mid}")
                        _html22 = _cr["body"] if _cr["status"] == 200 else ""
                    except Exception:
                        pass
                _m22 = ZEN_RE.search(_html22 or "")
                if _m22:
                    link = _h.unescape(_m22.group(0)).replace("&amp;", "&")
                    print(f"  LINK via 22.do fetch: {link[:120]}...", file=sys.stderr)
                    return link
                print("  mail found but no link in content", file=sys.stderr)
                return None
        await asyncio.sleep(5)
    return None


# ── temp.tf ──────────────────────────────────────────────────────────────
async def create_temptf(zf, tries=6):
    for _t in range(tries):
        try:
            _r = await zf.call("GET", f"{TEMP_TF_API}/account?dot=1&providers=gmail")
            if _r["status"] != 200:
                continue
            _em = (_j.loads(_r["body"]) or {}).get("email", "")
            _c = await zf.call("POST", f"{TEMP_TF_API}/check", {"email": _em},
                               {"Content-Type": "application/json"})
            if _c["status"] == 200 and one_dot_gmail(_em):
                return _em
        except Exception:
            pass
    return None


async def poll_temptf(zf, email, timeout_seconds=240):
    deadline = time.time() + timeout_seconds
    check = 0
    while time.time() < deadline:
        check += 1
        try:
            _r = await zf.call("POST", f"{TEMP_TF_API}/check", {"email": email},
                               {"Content-Type": "application/json"})
            _items = (_j.loads(_r["body"]).get("data", []) if _r["status"] == 200 else [])
            if check % 5 == 1:
                print(f"  temp.tf poll #{check}: {len(_items)} msgs", file=sys.stderr)
            for _m in _items:
                _mt = ZEN_RE.search(str(_m.get("subject", "")) + " " + str(_m.get("body", "")))
                if _mt:
                    link = _h.unescape(_mt.group(0)).replace("&amp;", "&")
                    print(f"  LINK via temp.tf: {link[:120]}...", file=sys.stderr)
                    return link
        except Exception as _e:
            if check % 5 == 1:
                print(f"  temp.tf poll err {str(_e)[:100]}", file=sys.stderr)
        await asyncio.sleep(5)
    return None


# ── tempmailhub ──────────────────────────────────────────────────────────
async def create_hub(zf, tries=4):
    for _t in range(tries):
        try:
            _r = await zf.call("POST", f"{HUB_API}/emails", {"domain": "gmail.com"},
                               {"Content-Type": "application/json", "Origin": "https://tempmailhub.org"})
            if _r["status"] != 201:
                continue
            _acct = _j.loads(_r["body"])
            _em, _eid = _acct.get("email", ""), str(_acct.get("email_id", ""))
            if _em.lower().endswith("@gmail.com") and "+" not in _em:
                return _em, _eid
        except Exception:
            pass
    return None, None


async def poll_hub(zf, email_id, timeout_seconds=240):
    deadline = time.time() + timeout_seconds
    check = 0
    while time.time() < deadline:
        check += 1
        try:
            _r = await zf.call("GET", f"{HUB_API}/emails/messages?email_id={email_id}",
                               None, {"Origin": "https://tempmailhub.org"})
            _d = _j.loads(_r["body"]) if _r["status"] == 200 else []
            _items = _d if isinstance(_d, list) else _d.get("emails", _d.get("messages", []))
            if check % 5 == 1:
                print(f"  hub poll #{check}: {len(_items)} msgs", file=sys.stderr)
            for _m in _items:
                _mt = ZEN_RE.search(str(_m.get("subject", "")) + " " + str(_m.get("body", _m.get("html", ""))))
                if _mt:
                    link = _h.unescape(_mt.group(0)).replace("&amp;", "&")
                    print(f"  LINK via hub: {link[:120]}...", file=sys.stderr)
                    return link
        except Exception as _e:
            if check % 5 == 1:
                print(f"  hub poll err {str(_e)[:100]}", file=sys.stderr)
        await asyncio.sleep(5)
    return None