#!/usr/bin/env python3
"""Lovable account creation via ZenRows Browser Cloud (GB residential) + dispose.lol"""
import asyncio, os, json, uuid, re, html, time, random, urllib.request, base64
from pathlib import Path
ZENROWS_WSS = "wss://browser.zenrows.com?apikey=5afd422125c5fd5c75efe3da015689da3c7a3a80&proxy_country=gb"
DISPOSE_API = "https://dispose.lol"
TEMP_TF_API = "https://temp.tf/api"

def clear_proxy():
    for k in list(os.environ):
        if k.lower().endswith('_proxy') or k=='LD_PRELOAD':
            os.environ.pop(k,None)
clear_proxy()

class DisposeLolInbox:
    """dispose.lol inbox manager using browser context tab (from lov-api-effective.py)"""
    BASE_URL = "https://dispose.lol"

    def __init__(self, context) -> None:
        self.context = context
        self.page = None
        self.address = None

    async def init_mailbox(self) -> str:
        self.page = await self.context.new_page()
        await self.page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=60000)
        await self.page.wait_for_timeout(4000)

        # 10 attempts: dispose.lol is slow/CF-gated on fresh IPs; reload-spam
        # resets their clearance, so every 3rd miss waits long WITHOUT reload.
        for attempt in range(1, 11):
            email_text = await self.page.evaluate("""() => {
                const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT,null);
                let n; while(n=w.nextNode()){
                    const t=n.textContent.trim();
                    if(t.includes('@gmail.com')&&t.length<80) return t;
                }
                for(const i of document.querySelectorAll('input')) if(i.value&&i.value.includes('@gmail.com')) return i.value;
                return null;
            }""")
            if email_text and "@gmail.com" in email_text:
                self.address = email_text.strip()
                print(f"✅ Mailbox ready: {self.address} (via dispose.lol tab)")
                return self.address
            print(f"  ⏳ Waiting for dispose.lol email to render (attempt {attempt}/10)...")
            if attempt % 3 == 0:
                await self.page.wait_for_timeout(8000)  # let CF settle, no reload
            else:
                await self.page.wait_for_timeout(2000)
                try:
                    await self.page.reload(wait_until="domcontentloaded")
                except Exception:
                    pass
                await self.page.wait_for_timeout(3000)
        raise Exception("Could not find dispose.lol Gmail after 10 attempts")

    async def wait_for_lovable_link(self, timeout_seconds: int = 180) -> str:
        print(f"📥 Waiting for Lovable verify link on dispose.lol ({self.address})...")
        deadline = time.time() + timeout_seconds
        check = 0

        # Batched poll: ONE evaluate per check returns all message labels —
        # the old locator.all() + per-button get_attribute() was N+1 CDP calls
        # per tick on a session that dies ~3min after creation.
        while time.time() < deadline:
            check += 1
            try:
                await self.page.reload(wait_until="domcontentloaded")
            except Exception: pass
            await self.page.wait_for_timeout(2200)

            try:
                labels = await self.page.evaluate("""() => [...document.querySelectorAll('button[aria-label^="View "]')]
                    .map(b => b.getAttribute('aria-label') || '')""")
            except Exception:
                labels = []

            if check % 3 == 1:
                print(f"  Check #{check}: {len(labels)} message(s) found")

            hit_idx = -1
            for _i, _aria in enumerate(labels):
                _al = (_aria or "").lower()
                if "lovable" in _al or "verify" in _al or "verification" in _al:
                    hit_idx = _i
                    print(f"  ✅ Found Lovable email: {_aria[:100]}")
                    break
            if hit_idx >= 0:
                try:
                    btn = self.page.locator('button[aria-label^="View "]').nth(hit_idx)
                    await btn.click(timeout=5000, force=True)
                    await self.page.wait_for_timeout(3000)

                    # Scan all iframe frames (dispose.lol renders email body inside iframe srcdoc)
                    for frame in self.page.frames:
                        try:
                            fhtml = await frame.content()
                        except Exception: continue

                        m = re.search(r'https?://lovable\.dev/auth/action\?[^"\'\s<>]*oobCode=[^"\'\s<>]+', fhtml or "")
                        if m:
                            link = html.unescape(m.group(0)).replace("&amp;", "&")
                            print(f"  🎯 FOUND VERIFY LINK (frame html): {link}")
                            return link

                        m2 = re.search(r'https?://[^"\'\s<>]*lovable\.dev[^"\'\s<>]*', fhtml or "")
                        if m2 and "oobCode" in m2.group(0):
                            link = html.unescape(m2.group(0)).replace("&amp;", "&")
                            print(f"  🎯 FOUND VERIFY LINK (frame oobCode): {link}")
                            return link
                except Exception as e:
                    print(f"  Extraction error on button click: {e}")
            await asyncio.sleep(3)
        raise Exception("Lovable verify link not received on dispose.lol (timeout)")

    async def close(self):
        if self.page:
            try: await self.page.close()
            except: pass


RUNS_LOG = Path(__file__).resolve().parents[1] / "runs.log"


def _log_run(**fields):
    """Append one JSON line per run (farm ops: flagged-ASN tracking, pacing)."""
    try:
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"), **fields}
        with open(RUNS_LOG, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass


def _asn_gate(ip, limit=2):
    """Kill early if this ISP was flagged `limit` times in a row (fresh IP is
    free — burning 3 min to rediscover a flagged ASN is not). Raises to rotate."""
    isp = (ip or "").split(" ", 1)[1].strip() if " " in (ip or "") else ""
    if not isp or isp == "fail":
        return
    try:
        lines = open(RUNS_LOG).read().strip().split("\n")[-20:]
    except Exception:
        return
    streak = 0
    for ln in reversed(lines):
        try:
            r = json.loads(ln)
        except Exception:
            continue
        if (r.get("isp") or "") != isp:
            break
        if r.get("outcome") in ("suspicious", "asn_gate"):
            streak += 1
        else:
            break
    if streak >= limit:
        print(f"⛔ ASN GATE: {isp} flagged {streak}x in a row — rotating without burning 3 min")
        raise Exception(f"ASN_GATE_BLOCKED: {isp} {streak}x streak")


TEMPMAILHUB_API = "https://api.tempmailhub.org"
TEMP_TF_API = "https://temp.tf/api"
RESET_LINK_RE = re.compile(r"https?://lovable\.dev/auth/action\?[^\"'\s<>]*oobCode=[^\"'\s<>]+", re.I)


def _clear_proxy_env():
    for _k in list(os.environ):
        if _k.lower().endswith('_proxy'):
            os.environ.pop(_k, None)


def lovable_email_available(email):
    """Pre-check via Lovable API: skip mails that already have an account
    (providers recycle — tempmailhub just re-issued our dead session-1 mail).
    On any error: optimistic True, browser flow decides."""
    import urllib.request as _u, json as _j
    _clear_proxy_env()
    try:
        _rq = _u.Request("https://api.lovable.dev/auth/check-auth-provider",
            data=_j.dumps({"email": email}).encode(),
            headers={"Content-Type": "application/json", "Origin": "https://lovable.dev",
                     "Referer": "https://lovable.dev/",
                     "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"},
            method="POST")
        with _u.urlopen(_rq, timeout=15) as _r:
            return not _j.loads(_r.read()).get("user_exists", True)
    except Exception:
        return True


def create_tempmailhub_email(tries=10):
    """TempMailHub API: real @gmail.com (no dots/plus), validated mailbox.
    Pure HTTP, pre-connect. Returns (email, email_id) or (None, None)."""
    import urllib.request as _u, urllib.error as _ue, json as _j
    _clear_proxy_env()
    for _t in range(tries):
        try:
            _d = _j.dumps({"domain": "gmail.com"}).encode()
            _rq = _u.Request(f"{TEMPMAILHUB_API}/emails", data=_d,
                headers={"Content-Type": "application/json", "Origin": "https://tempmailhub.org"}, method="POST")
            with _u.urlopen(_rq, timeout=20) as _r:
                if _r.status != 201:
                    continue
                _acct = _j.loads(_r.read())
            _em, _eid = _acct.get("email", ""), str(_acct.get("email_id", ""))
            _local = _em.split("@")[0] if "@" in _em else ""
            if not (_em.lower().endswith("@gmail.com") and "." not in _local and "+" not in _local):
                print(f"tempmailhub skip {_em} (need clean gmail), retry {_t+1}/{tries}")
                continue
            _mr = _u.Request(f"{TEMPMAILHUB_API}/emails/messages?email_id={_eid}",
                headers={"Origin": "https://tempmailhub.org"})
            with _u.urlopen(_mr, timeout=20) as _r2:
                _body = _r2.read().decode()
            if "norecentemails" in _body.lower() or '"emails":[' in _body:
                print(f"tempmailhub Gmail {_em} (id {_eid})")
                return _em, _eid
            print(f"tempmailhub mailbox not ready for {_em}, retry {_t+1}/{tries}")
        except Exception as _e:
            print(f"tempmailhub try {_t+1} err {str(_e)[:100]}")
    return None, None


def poll_tempmailhub_link(email_id, timeout_seconds=180):
    """Poll TempMailHub API for the Lovable verify link. Pure HTTP (no session burn)."""
    import urllib.request as _u, json as _j, html as _h
    _clear_proxy_env()
    deadline = time.time() + timeout_seconds
    check = 0
    while time.time() < deadline:
        check += 1
        try:
            _rq = _u.Request(f"{TEMPMAILHUB_API}/emails/messages?email_id={email_id}",
                headers={"Origin": "https://tempmailhub.org"})
            with _u.urlopen(_rq, timeout=20) as _r:
                _data = _j.loads(_r.read())
            _items = _data if isinstance(_data, list) else _data.get("emails", _data.get("messages", []))
            if check % 5 == 1:
                print(f"  tempmailhub poll #{check}: {len(_items)} msgs")
            for _m in _items:
                _txt = str(_m.get("subject", "")) + " " + str(_m.get("body", _m.get("html", "")))
                _mt = RESET_LINK_RE.search(_txt)
                if _mt:
                    link = _h.unescape(_mt.group(0)).replace("&amp;", "&")
                    print(f"  🎯 FOUND VERIFY LINK via tempmailhub: {link[:120]}...")
                    return link
        except Exception as _e:
            if check % 5 == 1:
                print(f"  tempmailhub poll err {str(_e)[:100]}")
        time.sleep(5)
    return None


def _temptf_get(path, data=None):
    import urllib.request as _u, json as _j
    _clear_proxy_env()
    url = f"{TEMP_TF_API}{path}"
    if data is not None:
        _rq = _u.Request(url, data=_j.dumps(data).encode(), headers={"Content-Type": "application/json"}, method="POST")
    else:
        _rq = _u.Request(url)
    with _u.urlopen(_rq, timeout=15) as _r:
        return _j.loads(_r.read())


def create_temptf_email(tries=10):
    """temp.tf API: dot-trick @gmail.com. Pure HTTP, pre-connect. Returns email or None."""
    import urllib.error as _ue
    for _t in range(tries):
        try:
            _acct = _temptf_get("/account?dot=1&providers=gmail")
            _em = _acct.get("email", "")
            _temptf_get("/check", {"email": _em})
            print(f"temp.tf Gmail {_em}")
            return _em
        except Exception as _e:
            print(f"temp.tf try {_t+1} err {str(_e)[:100]}")
    return None


def poll_temptf_link(email, timeout_seconds=180):
    """Poll temp.tf API for the Lovable verify link. Pure HTTP (no session burn)."""
    import html as _h
    deadline = time.time() + timeout_seconds
    check = 0
    while time.time() < deadline:
        check += 1
        try:
            _resp = _temptf_get("/check", {"email": email})
            _items = _resp.get("data", [])
            if check % 5 == 1:
                print(f"  temp.tf poll #{check}: {len(_items)} msgs")
            for _m in _items:
                _mt = RESET_LINK_RE.search(str(_m.get("subject", "")) + " " + str(_m.get("body", "")))
                if _mt:
                    link = _h.unescape(_mt.group(0)).replace("&amp;", "&")
                    print(f"  🎯 FOUND VERIFY LINK via temp.tf: {link[:120]}...")
                    return link
        except Exception as _e:
            if check % 5 == 1:
                print(f"  temp.tf poll err {str(_e)[:100]}")
        time.sleep(5)
    return None


def create_22do_gmail(tries=40):
    """22.do fake-gmail API (pure HTTP, no browser). Returns @gmail.com or None.
    Same approach as zenrows-kernel-final.py: @gmail.com + exactly 1 dot, no plus."""
    import urllib.request as _u, json as _j
    for _k in list(os.environ):
        if _k.lower().endswith('_proxy'):
            os.environ.pop(_k, None)
    for _t in range(tries):
        try:
            _d = _j.dumps({"type": "random"}).encode()
            _rq = _u.Request("https://22.do/action/mailbox/gmail", data=_d,
                headers={"Content-Type": "application/json",
                         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"},
                method="POST")
            with _u.urlopen(_rq, timeout=15) as _r:
                _res = _j.loads(_r.read())
            _em = ((_res.get("data") or {}).get("email") or "").strip()
            _local = _em.split("@")[0] if "@" in _em else ""
            if _em.lower().endswith("@gmail.com") and _local.count(".") == 1 and "+" not in _em:
                return _em
            print(f"22.do skip {_em} (need @gmail.com + exactly 1 dot, no plus), retry {_t+1}/{tries}")
        except Exception as _e:
            print(f"22.do API try {_t+1} err {str(_e)[:120]}")
    return None


async def poll_22do_lovable_link(ctx, email, timeout_seconds=180):
    """Poll 22.do inbox for the Lovable verify mail, return oobCode link or None.
    Same approach as zenrows-kernel-final.py: #email-list-wrap .tr rows,
    Subject/From match, /content/{id} fallback."""
    print(f"📥 Waiting for Lovable verify link on 22.do ({email})...")
    link_re = re.compile(r"https?://lovable\.dev/auth/action\?[^\"'\s<>]*oobCode=[^\"'\s<>]+", re.I)
    pg22 = await ctx.new_page()
    try:
        await pg22.goto(f"https://22.do/inbox/#/{email}", wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
        print(f"  22.do inbox load fail: {str(e)[:100]}")
        return None
    await pg22.wait_for_timeout(4000)
    deadline = time.time() + timeout_seconds
    check = 0
    while time.time() < deadline:
        check += 1
        try:
            await pg22.reload(wait_until="domcontentloaded")
        except Exception:
            pass
        await pg22.wait_for_timeout(2200)
        try:
            labels = await pg22.evaluate("""() => [...document.querySelectorAll('#email-list-wrap .tr')]
                .map(r => r.innerText.slice(0,150)).join(' | ').slice(0,600)""")
        except Exception:
            labels = ""
        n22 = len(labels.split(" | ")) if labels else 0
        if check % 3 == 1:
            print(f"  Check #{check}: {n22} message(s) rows={labels[:200]}")
        low = (labels or "").lower()
        if n22 and ("lovable" in low or "verify" in low):
            for k in range(n22):
                try:
                    tr22 = pg22.locator("#email-list-wrap .tr").nth(k)
                    subj22 = await tr22.locator(".item.subject").inner_text(timeout=2000)
                    from22 = await tr22.locator(".item.from").inner_text(timeout=2000)
                except Exception:
                    continue
                if "lovable" in (subj22 + from22).lower() or "verify" in subj22.lower():
                    print(f"  ✅ Found Lovable mail: {subj22} / {from22}")
                    try:
                        await tr22.locator(".item.subject").click(timeout=3000)
                    except Exception:
                        pass
                    await pg22.wait_for_timeout(2500)
                    try:
                        await pg22.evaluate("""() => {
                            const sc=[...document.querySelectorAll('*')].filter(e=>{try{return e.scrollHeight>e.clientHeight+50;}catch{return false;}});
                            for(const e of sc){try{e.scrollTop=e.scrollHeight;}catch{}}
                            window.scrollTo(0,document.body.scrollHeight); }""")
                    except Exception:
                        pass
                    await pg22.wait_for_timeout(1500)
                    try:
                        html22 = await pg22.content()
                    except Exception:
                        html22 = ""
                    try:
                        for _fr in pg22.frames:
                            try:
                                html22 += "\n" + await _fr.content()
                            except Exception:
                                pass
                    except Exception:
                        pass
                    m22 = link_re.search(html22 or "")
                    if not m22:
                        try:
                            _mid = await tr22.evaluate("(el) => el.getAttribute('onclick') || el.innerHTML.slice(0,300)")
                        except Exception:
                            _mid = ""
                        _mnum = re.search(r"viewEml\(['\"]?(\w+)['\"]?\)", _mid or "")
                        if _mnum:
                            try:
                                await pg22.goto(f"https://22.do/content/{_mnum.group(1)}", wait_until="domcontentloaded", timeout=20000)
                                await pg22.wait_for_timeout(2500)
                                html22 = await pg22.content()
                                m22 = link_re.search(html22 or "")
                            except Exception as _ce:
                                print(f"  22.do content url err {_ce}")
                    if m22:
                        link = html.unescape(m22.group(0)).replace("&amp;", "&")
                        print(f"  🎯 FOUND VERIFY LINK via 22.do: {link[:120]}...")
                        try:
                            await pg22.close()
                        except Exception:
                            pass
                        return link
        await asyncio.sleep(3)
    try:
        await pg22.close()
    except Exception:
        pass
    return None

class ZenvexInbox:
    """zenvex.dev inbox via browser tab (Vue SPA, LIVE auto-refresh).
    Recon: prefix input + domain btn (default souss.dev) + Open Inbox → /inbox,
    address in .inbox-email-display. Domains: souss.dev znvx.me zenvex.edu.pl
    encg.edu.pl ensam.edu.pl ofppt.edu.pl (NO gmail — 4th in chain)."""
    BASE_URL = "https://zenvex.dev"
    DOMAIN = "souss.dev"

    def __init__(self, context):
        self.context = context
        self.page = None
        self.address = None

    async def init_mailbox(self, prefix=None):
        import random as _rnd, string as _str
        self.page = await self.context.new_page()
        await self.page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=60000)
        await self.page.wait_for_timeout(3000)
        if not prefix:
            prefix = "lov" + "".join(_rnd.choices(_str.ascii_lowercase + _str.digits, k=10))
        try:
            _inp = self.page.locator('input[placeholder*="prefix"]').first
            await _inp.wait_for(state="visible", timeout=10000)
            await _inp.fill(prefix)
        except Exception as e:
            raise Exception(f"zenvex prefix fill failed: {e}")
        try:
            _open = self.page.get_by_role("button", name="Open Inbox").first
            await _open.click(timeout=8000)
        except Exception as e:
            raise Exception(f"zenvex Open Inbox click failed: {e}")
        await self.page.wait_for_timeout(4000)
        try:
            _disp = self.page.locator('.inbox-email-display').first
            await _disp.wait_for(state="visible", timeout=10000)
            self.address = (await _disp.inner_text(timeout=3000)).strip()
        except Exception:
            self.address = f"{prefix}@{self.DOMAIN}"
        print(f"✅ Mailbox ready: {self.address} (via zenvex tab)")
        return self.address

    async def wait_for_lovable_link(self, timeout_seconds=180):
        print(f"📥 Waiting for Lovable verify link on zenvex ({self.address})...")
        deadline = time.time() + timeout_seconds
        check = 0
        while time.time() < deadline:
            check += 1
            try:
                await self.page.reload(wait_until="domcontentloaded")
            except Exception:
                pass
            await self.page.wait_for_timeout(2500)
            try:
                rows = await self.page.evaluate("""() => [...document.querySelectorAll('button,li,[role="option"],tr')]
                    .map(e => (e.innerText||'').slice(0,150)).filter(t=>t.length>3).join(' || ').slice(0,800)""")
            except Exception:
                rows = ""
            if check % 3 == 1:
                print(f"  Check #{check}: rows={rows[:200]}")
            low = (rows or "").lower()
            if "lovable" in low or "verify" in low:
                try:
                    cand = self.page.locator('button,li').filter(has_text=re.compile("lovable|verify", re.I)).first
                    if await cand.count():
                        await cand.click(timeout=5000, force=True)
                        await self.page.wait_for_timeout(3000)
                except Exception:
                    pass
                try:
                    htmlzx = await self.page.content()
                except Exception:
                    htmlzx = ""
                try:
                    for _fr in self.page.frames:
                        try:
                            htmlzx += "\n" + await _fr.content()
                        except Exception:
                            pass
                except Exception:
                    pass
                mz = RESET_LINK_RE.search(htmlzx or "")
                if mz:
                    link = html.unescape(mz.group(0)).replace("&amp;", "&")
                    print(f"  🎯 FOUND VERIFY LINK via zenvex: {link[:120]}...")
                    return link
            await asyncio.sleep(3)
        raise Exception("Lovable verify link not received on zenvex (timeout)")

    async def close(self):
        if self.page:
            try:
                await self.page.close()
            except Exception:
                pass


import argparse

async def run_signup(args, run_attempt=1):
    pw = None
    browser = None
    ctx = None
    page = None
    inbox = None
    zxinbox = None

    # ZenRows CDP URL pool (rotates key & proxy country for clean residential IP)
    # NOTE: a71406 AUTH004 exhausted; 1a5d93 (2026-09-07, GB residential) is current live key
    zenrows_keys = [
        "1a5d93cda0d10ac0bd9ab3da3fa93019f126397a",
        "3a6a9ee9aee5e3fa9a76b934eafd8dd1cf6dd39f",
        "b71908b722a88c56ee0ed960730465ab8e4bdfa3",
        "5afd422125c5fd5c75efe3da015689da3c7a3a80"
    ]
    countries = ["gb", "gf"]
    import os as _oskey
    _envkey = _oskey.environ.get("ZENROWS_KEY", "").strip()
    key = _envkey or zenrows_keys[(run_attempt - 1) % len(zenrows_keys)]
    proxy_country = countries[(run_attempt - 1) % len(countries)]
    zenrows_wss_url = f"wss://browser.zenrows.com?apikey={key}&proxy_country={proxy_country}"

    # 0) PROVIDER CHAIN, all pure-HTTP pre-connect (no session burn):
    # tempmailhub (real clean gmail) → 22.do (1-dot gmail) → temp.tf (dot gmail).
    # Browser-tab providers (zenvex → dispose.lol) come after connect.
    pre_email, pre_src, pre_id = None, None, None
    _th_em, _th_id = create_tempmailhub_email()
    if _th_em and lovable_email_available(_th_em):
        pre_email, pre_src, pre_id = _th_em, "tempmailhub", _th_id
        print(f"tempmailhub Gmail {pre_email} (pre-connect, available)")
    else:
        if _th_em:
            print(f"tempmailhub {_th_em} already registered — next provider")
        pre_email = create_22do_gmail()
        if pre_email and not lovable_email_available(pre_email):
            print(f"22.do {pre_email} already registered — next provider")
            pre_email = None
        if pre_email:
            pre_src = "22do"
            print(f"22.do Gmail {pre_email} (pre-connect, available)")
        else:
            pre_email = create_temptf_email()
            if pre_email and not lovable_email_available(pre_email):
                print(f"temp.tf {pre_email} already registered — browser-tab chain")
                pre_email = None
            if pre_email:
                pre_src = "temptf"
                print(f"temp.tf Gmail {pre_email} (pre-connect, available)")

    if args.local:
        print(f"🦊 [Attempt {run_attempt}] Launching local Camoufox Stealth browser...")
        try:
            from camoufox.async_api import AsyncCamoufox
            camou = AsyncCamoufox(headless=args.headless)
            browser = await camou.__aenter__()
            ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        except ImportError:
            print("⚠️ Camoufox not found, falling back to Patchright...")
            from patchright.async_api import async_playwright
            pw = await async_playwright().start()
            browser = await pw.chromium.launch(headless=args.headless, args=["--disable-blink-features=AutomationControlled"])
            ctx = await browser.new_context()
    else:
        print(f"🌐 [Attempt {run_attempt}] Connecting to ZenRows CDP WSS (Country: {proxy_country.upper()})...")
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        browser = await pw.chromium.connect_over_cdp(zenrows_wss_url, timeout=30000)
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()

    # Stealth Init Scripts — JITTERED per run (identical fingerprints across
    # fresh-IP signups minutes apart is a trivial farm signal for the backend).
    _cores = random.choice([4, 8, 12, 16])
    _mem = random.choice([4, 8, 16])
    _plat = random.choice(["Win32", "Linux x86_64"])
    _nplug = random.randint(2, 5)
    await ctx.add_init_script(f"""() => {{
        const cfg = {{cores: {_cores}, mem: {_mem}, plat: '{_plat}', nplug: {_nplug}}};
        try {{ Object.defineProperty(navigator, 'webdriver', {{get: () => undefined}}); }} catch(e){{}}
        try {{ Object.defineProperty(navigator, 'plugins', {{get: () => Array.from({{length: cfg.nplug}}, (_, i) => ({{name: 'Plugin ' + i}}))}}); }} catch(e){{}}
        try {{ Object.defineProperty(navigator, 'hardwareConcurrency', {{get: () => cfg.cores}}); }} catch(e){{}}
        try {{ Object.defineProperty(navigator, 'deviceMemory', {{get: () => cfg.mem}}); }} catch(e){{}}
        try {{ Object.defineProperty(navigator, 'platform', {{get: () => cfg.plat}}); }} catch(e){{}}
        try {{ if(!window.chrome) window.chrome = {{runtime: {{}}}}; }} catch(e){{}}
        try {{ window.__nativeSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; }} catch(e){{}}
    }}""")
    print(f"🎭 Fingerprint jitter: cores={_cores} mem={_mem} plat={_plat} plugins={_nplug}")

    try:
        # Use pre-connect API mail if we got one — else browser-tab chain:
        # zenvex first, dispose.lol last.
        inbox = None
        zxinbox = None
        email_source = "dispose"
        email, email_id = pre_email, pre_id
        if email:
            email_source = pre_src
            print(f"{pre_src} mail {email} (skip browser-tab inboxes)")
        else:
            try:
                zxinbox = ZenvexInbox(ctx)
                email = await zxinbox.init_mailbox()
                email_source = "zenvex"
            except Exception as _zxe:
                print(f"zenvex miss ({str(_zxe)[:100]}), fallback to dispose.lol tab")
                zxinbox = None
            if not email or email_source != "zenvex":
                print("API + zenvex miss, fallback to dispose.lol Gmail tab")
                inbox = DisposeLolInbox(ctx)
                email = await inbox.init_mailbox()
                email_source = "dispose"
        password = email + "K01"  # 8+ chars
        print(f"EMAIL {email} PW {password} SRC {email_source}")

        # Open Lovable page in second tab
        page = await ctx.new_page()
        for page_attempt in range(1, 3):
            try:
                await page.goto("https://lovable.dev/signup", timeout=60000, wait_until="domcontentloaded")
                break
            except Exception as e:
                print(f"⚠️ Page load attempt {page_attempt} failed ({e}), retrying...")
                await asyncio.sleep(2)
        await page.wait_for_timeout(5000)

        # Skeleton guard (effective-script lesson): /signup sometimes renders
        # a skeleton without hydration — fallback via / then /signup once.
        try:
            _txt = await page.evaluate("() => document.body ? document.body.innerText.slice(0,500) : ''")
        except Exception:
            _txt = ""
        if len((_txt or "").strip()) < 50 or ("Create your account" not in (_txt or "") and "Créez votre compte" not in (_txt or "")):
            print("  ⚠️ /signup skeleton/white — fallback via / then /signup")
            try:
                await page.goto("https://lovable.dev/", timeout=60000, wait_until="domcontentloaded")
                await page.wait_for_timeout(1500)
                await page.goto("https://lovable.dev/signup", timeout=60000, wait_until="domcontentloaded")
                await page.wait_for_timeout(1500)
            except Exception as e:
                print(f"  skeleton fallback nav fail: {str(e)[:100]}")

        # IP check (for log)
        ip = "fail"
        for _eg in range(3):
            try:
                ip = await page.evaluate("async () => { try{ const r=await fetch('https://wtfismyip.com/json'); const j=await r.json(); return j.YourFuckingIPAddress+' '+j.YourFuckingISP }catch(e){ return 'fail' } }")
                if ip and ip != "fail":
                    break
            except: pass
            await page.wait_for_timeout(2000)
        print(f"IP {ip}")
        _isp = ip.split(" ", 1)[1].strip() if " " in (ip or "") else ""
        _log_run(email=email, src=email_source, ip=(ip or "").split(" ")[0], isp=_isp, outcome="started")
        _asn_gate(ip)  # raises ASN_GATE_BLOCKED on flagged-ASN streak → rotate

        # Dismiss cookie banner: ONE batched evaluate (reject-first). The popup
        # overlaps the form and its buttons cost CDP calls one-by-one.
        try:
            await page.evaluate("""() => {
                const labels=['reject all','rejeter tout','continuer sans accepter','accept all','accepter tout','got it'];
                for(const b of document.querySelectorAll('button')){ const t=(b.innerText||'').trim().toLowerCase();
                    if(labels.includes(t)){ b.click(); return t; } }
                const c=document.querySelector('button[aria-label*="Close" i],button[aria-label*="Fermer" i]');
                if(c){ c.click(); return 'close'; } return null; }""")
        except Exception:
            pass

        # Fill email + VERIFY it stuck (effective-script lesson: silent empty
        # field burns the run). Fallback keyboard.type on mismatch.
        email_loc = page.locator('input#email')
        await email_loc.wait_for(timeout=10000)
        await email_loc.fill(email)
        try:
            _eval = await email_loc.input_value(timeout=2000)
            if (_eval or "").strip().lower() != email.lower():
                print(f"  ⚠️ email mismatch {_eval!r} — retry keyboard.type")
                await page.keyboard.type(email, delay=40)
        except Exception:
            pass

        # Continuer with fallbacks: testid → role text (fr/en) → evaluate click
        _clicked = False
        try:
            await page.locator('[data-testid="auth-submit-button"]').click(timeout=7000)
            _clicked = True
        except Exception:
            for _name in ("Continuer", "Continue"):
                try:
                    _b = page.get_by_role("button", name=_name, exact=True).first
                    if await _b.count():
                        await _b.click(timeout=5000)
                        _clicked = True
                        break
                except Exception:
                    continue
        if not _clicked:
            try:
                await page.evaluate("""() => { const b=document.querySelector('[data-testid="auth-submit-button"]'); if(b) b.click(); }""")
                _clicked = True
            except Exception:
                pass
        if not _clicked:
            raise Exception("CONTINUER_CLICK_FAILED")
        await page.wait_for_timeout(4000)

        # Fill password: fill() FIRST (proven len 8 sticky on ZenRows GB),
        # nativeSetter+input-event only as fallback. Hard-fail if len wrong —
        # a silent empty field submits as 'Password is required' and burns the run.
        pw_input = page.locator('input#password')
        await pw_input.wait_for(timeout=10000)
        try:
            await pw_input.fill(password, timeout=8000)
        except Exception:
            try:
                await page.evaluate("(pw) => window.__nativeSetter ? window.__nativeSetter.call(document.querySelector('#password'), pw) : (document.querySelector('#password').value = pw)", password)
                await page.evaluate("el => el.dispatchEvent(new Event('input', {bubbles: true}))", await pw_input.element_handle())
            except Exception:
                await pw_input.fill(password)

        val = await page.evaluate("() => document.querySelector('#password')?.value?.length || 0")
        print(f"PW len {val} (want {len(password)})")
        if val != len(password):
            # One keyboard.type retry before giving up
            try:
                await pw_input.click(timeout=3000, force=True)
            except Exception:
                pass
            await page.keyboard.type(password, delay=40)
            val = await page.evaluate("() => document.querySelector('#password')?.value?.length || 0")
            print(f"PW len retry {val}")
        if val != len(password):
            raise Exception(f"PASSWORD_FILL_FAILED: len {val} != {len(password)} — abort before Turnstile burn")
        await page.screenshot(path="/tmp/zen_final_pw.png", full_page=True)

        # Wait Turnstile Success — single batched evaluate per tick (1 CDP call):
        # token len + widget iframe presence + Create-button state. Tells apart
        # "no challenge served" (iframes 0) from "challenge stuck" (iframes 1, tok 0).
        for i in range(15):
            try:
                st = await page.evaluate("""() => { const t=document.querySelector('input[name="cf-turnstile-response"]')?.value?.length||0;
                    const f=[...document.querySelectorAll('iframe')].filter(x=>(x.src||'').includes('challenges.cloudflare.com')).length;
                    const b=document.querySelector('[data-testid="auth-submit-button"]');
                    return {tok:t, ifr:f, dis:b?b.disabled:'nobtn'}; }""")
            except Exception as e:
                print(f"Token ? i {i} (eval fail {str(e)[:60]})")
                await page.wait_for_timeout(2000)
                continue
            token = st["tok"]
            print(f"Token {token} ifr {st['ifr']} dis {st['dis']} i {i}")
            if token > 100:
                break
            try:
                await page.evaluate("() => { if(window.turnstile && typeof window.turnstile.execute === 'function') window.turnstile.execute(); }")
            except: pass
            await page.wait_for_timeout(2000)

        token = await page.evaluate("() => document.querySelector('input[name=\"cf-turnstile-response\"]')?.value || ''")
        print(f"Final token {len(token)}")

        if len(token) == 0:
            print("⛔ Turnstile challenge failed/blocked (token 0). Killing browser...")
            _log_run(email=email, src=email_source, ip=(ip or "").split(" ")[0], isp=_isp, outcome="token0")
            raise Exception("SUSPICIOUS_BLOCK_DETECTED: Cloudflare Turnstile token missing")

        # Click Create — HUMAN HESITATION: bots click the instant the button
        # enables; humans stare at Success!, scroll, move the mouse, then click.
        # Instant-click post-token is a prime abuse-detection signal.
        btn = page.locator('[data-testid="auth-submit-button"]')
        disabled = await btn.is_disabled()
        print(f"Create disabled {disabled}")
        await page.screenshot(path="/tmp/zen_final_before.png", full_page=True)

        if not disabled:
            try:
                box = await btn.bounding_box()
                if box:
                    cx, cy = int(box["x"] + box["width"] / 2), int(box["y"] + box["height"] / 2)
                    await page.mouse.move(random.randint(300, 700), random.randint(200, 500))
                    await page.wait_for_timeout(random.randint(2500, 4500))
                    await page.mouse.wheel(0, random.randint(-120, -40))
                    await page.wait_for_timeout(random.randint(2000, 4000))
                    await page.mouse.move(cx + random.randint(-40, 40), cy + random.randint(-30, 30))
                    await page.wait_for_timeout(random.randint(1500, 3500))
                    print(f"  🖱️ human hesitation done, clicking Create at ({cx},{cy})")
                    await page.mouse.click(cx, cy, delay=random.randint(90, 180))
                else:
                    await btn.click()
            except Exception:
                await btn.click()
            await page.wait_for_timeout(8000)
            await page.screenshot(path="/tmp/zen_final_after.png", full_page=True)
            content = await page.content()
            content_lower = content.lower()

            suspicious_keywords = [
                "suspicious",
                "denied due to suspicious activity",
                "blocked due to suspicious activity",
                "requests from this device have been blocked",
                "signups from this ip address are temporarily disabled",
                "too many requests",
                "try again later"
            ]

            detected_err = None
            for kw in suspicious_keywords:
                if kw in content_lower:
                    detected_err = kw
                    break

            if not detected_err:
                try:
                    alert_el = page.locator('[role="alert"], .text-destructive, [data-invalid]').first
                    if await alert_el.is_visible(timeout=1000):
                        detected_err = (await alert_el.inner_text()).strip()
                except Exception: pass

            if detected_err:
                print(f"⛔ BLOCKED / SUSPICIOUS ERROR DETECTED: '{detected_err}'! Killing browser to rotate IP...")
                _log_run(email=email, src=email_source, ip=(ip or "").split(" ")[0], isp=_isp, outcome="suspicious", detail=detected_err)
                raise Exception(f"SUSPICIOUS_BLOCK_DETECTED: {detected_err}")

            if "Check your inbox" in content:
                print("SUCCESS Check your inbox")
            else:
                print(f"Page response snippet: {content[:500]}")

            # Wait for Lovable verify link from the matching inbox.
            # Pure-HTTP polls (tempmailhub/temp.tf) burn zero session budget.
            if email_source == "tempmailhub":
                link = await asyncio.to_thread(poll_tempmailhub_link, email_id)
            elif email_source == "22do":
                link = await poll_22do_lovable_link(ctx, email)
            elif email_source == "temptf":
                link = await poll_temptf_link(email)
            elif email_source == "zenvex":
                link = await zxinbox.wait_for_lovable_link()
            else:
                link = await inbox.wait_for_lovable_link()
            if link:
                print(f"🎯 Navigating to verify link: {link}")
                await page.goto(link, timeout=30000)
                await page.wait_for_timeout(5000)
                await page.screenshot(path="/tmp/zen_final_verified.png", full_page=True)

                # ── POST-VERIFICATION ONBOARDING FLOW ─────────────────────────────
                print("🚀 Completing onboarding flow until redirected to /dashboard...")
                display_name = email.split('@')[0].replace('.', ' ').title()

                for step_attempt in range(25):
                    await page.wait_for_timeout(1500)
                    url = page.url
                    content = await page.content()

                    if "/dashboard" in url or "/projects" in url:
                        print(f"🎯 Reached Dashboard! URL: {url}")
                        break

                    # Step 1: "Pick your style" -> Click Next
                    if "Pick your style" in content or "Step 1" in content:
                        try:
                            nxt = page.locator('button:has-text("Next"), button:has-text("Continue")').first
                            if await nxt.is_visible(timeout=1500):
                                await nxt.click()
                                print("  ✅ Step 1: Clicked Next (Style selected)")
                                await page.wait_for_timeout(2000)
                        except Exception: pass

                    # Step 2: "What's your name?" -> Fill display name
                    name_input = page.locator('input[placeholder*="name"], input#name, input[name="name"]').first
                    try:
                        if await name_input.is_visible(timeout=1500):
                            await name_input.fill(display_name)
                            print(f"  ✅ Step 2: Filled display name '{display_name}'")
                            await name_input.press("Enter")
                            await page.wait_for_timeout(2000)
                    except Exception: pass

                    # Step 3: "Which role fits you best?" -> Click "Engineer" / "Developer" / "Founder"
                    if "Which role" in content or "Step 3" in content:
                        for role in ["Engineer", "Developer", "Founder", "Other"]:
                            try:
                                r_btn = page.locator(f'button:has-text("{role}")').first
                                if await r_btn.is_visible(timeout=1000):
                                    await r_btn.click()
                                    print(f"  ✅ Step 3: Selected role '{role}'")
                                    await page.wait_for_timeout(2000)
                                    break
                            except Exception: pass

                    # Step 4: "How many people work at your company?" -> Click "Solo" / "1-5" / "2 - 20"
                    if "How many people" in content or "company" in content or "Step 4" in content:
                        for sz in ["Solo", "Just me", "1-5", "2 - 20", "200+"]:
                            try:
                                s_btn = page.locator(f'button:has-text("{sz}")').first
                                if await s_btn.is_visible(timeout=1000):
                                    await s_btn.click()
                                    print(f"  ✅ Step 4: Selected size '{sz}' (Submitting onboarding)")
                                    await page.wait_for_timeout(2500)
                                    break
                            except Exception: pass

                    # Fallback buttons (Next / Continue / Get Started / Skip)
                    for btn_text in ["Next", "Continue", "Get Started", "Skip"]:
                        try:
                            b = page.locator(f'button:has-text("{btn_text}")').first
                            if await b.is_visible(timeout=1000):
                                await b.click()
                                print(f"  ✅ Fallback: Clicked button '{btn_text}'")
                                await page.wait_for_timeout(2000)
                                break
                        except Exception: pass

                # SAVE FIRST — session often dies ~3min in, right after dashboard.
                # Any wait/screenshot before the save risks losing the account.
                # Everything here is death-proof: even with a dead browser we
                # persist email/password/verify-link for a later cookie refresh.
                try:
                    final_url = page.url
                except Exception:
                    final_url = "https://lovable.dev/dashboard (unconfirmed, session died)"
                # ── SAVE COOKIES & CONFIG TO SESSIONS DIR ──────────────────────────
                sessions_dir = Path(__file__).resolve().parents[2] / "scripts" / "sessions"
                sessions_dir.mkdir(parents=True, exist_ok=True)
                session_id_dir = f"session-{int(time.time())}"
                session_path = sessions_dir / session_id_dir
                session_path.mkdir(parents=True, exist_ok=True)

                try:
                    cookies = await ctx.cookies()
                except Exception as e:
                    print(f"  ⚠️ cookies() failed (dead session): {str(e)[:80]} — saving creds only")
                    cookies = []
                (session_path / "cookies.json").write_text(json.dumps(cookies, indent=2))
                config_data = {
                    "email": email,
                    "password": password,
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "dashboard_url": final_url,
                    "verified": True,
                    "provider": email_source,
                    "verify_link": link,
                    "cookies_saved": len(cookies) > 0,
                }
                (session_path / "config.json").write_text(json.dumps(config_data, indent=2))

                with open("/tmp/zen_final_account.txt", "w") as f:
                    f.write(f"{email}\n{password}\n{link}\n{final_url}\n")

                print(f"✅ SAVED SESSION {session_id_dir} to {session_path}")
                print(f"✅ Saved {len(cookies)} cookies & config.json for {email}")
                _log_run(email=email, src=email_source, ip=(ip or "").split(" ")[0], isp=_isp, outcome="success", session=session_id_dir)
                return True
    finally:
        if inbox:
            try: await inbox.close()
            except: pass
        try:
            if zxinbox:
                await zxinbox.close()
        except Exception:
            pass
        if browser:
            try: await browser.close()
            except: pass
        if pw:
            try: await pw.stop()
            except: pass
    return False

async def main():
    parser = argparse.ArgumentParser(description="Lovable account creation via ZenRows Cloud or Local Camoufox Stealth")
    parser.add_argument("--local", action="store_true", help="Use local Camoufox browser with stealth bypass")
    parser.add_argument("--headless", action="store_true", help="Run local browser in headless mode")
    parser.add_argument("--max-retries", type=int, default=10, help="Max retries on suspicious block")
    args = parser.parse_args()

    for attempt in range(1, args.max_retries + 1):
        try:
            print(f"\n==========================================")
            print(f"🚀 SIGNUP ATTEMPT {attempt}/{args.max_retries}")
            print(f"==========================================")
            success = await run_signup(args, run_attempt=attempt)
            if success:
                print(f"🎉 Signup completed successfully on attempt {attempt}!")
                break
        except Exception as e:
            if "SUSPICIOUS_BLOCK_DETECTED" in str(e) or "ASN_GATE_BLOCKED" in str(e):
                print(f"⛔ [Attempt {attempt}] Suspicious error encountered! Browser process killed.")
                if not args.local:
                    print(f"🔄 ZenRows mode: Changing IP / Proxy Country & Session ID for attempt {attempt + 1}...")
                else:
                    print(f"🔄 Local mode: Restarting fresh browser instance for attempt {attempt + 1}...")
                await asyncio.sleep(3)
            else:
                print(f"⚠️ Error on attempt {attempt}: {e}")
                await asyncio.sleep(2)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

