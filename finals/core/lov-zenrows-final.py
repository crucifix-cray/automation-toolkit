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


class ZenFetch:
    """Run provider HTTP APIs via fetch() INSIDE the ZenRows tab (residential
    GB egress). Local raw-IP curl gets 404/denied (tempmailhub). One page,
    one evaluate per call — minimal session burn."""
    def __init__(self):
        self.page = None

    async def open(self, ctx):
        self.page = await ctx.new_page()
        return self

    async def home(self, origin_url):
        """Navigate tab to the API's own origin first — cross-origin fetch
        dies on CORS (tempmailhub ACAO=tempmailhub.org only, 22.do/temp.tf none)."""
        try:
            await self.page.goto(origin_url, wait_until="domcontentloaded", timeout=30000)
            await self.page.wait_for_timeout(2500)
            return True
        except Exception as e:
            print(f"  zf home {origin_url} fail: {str(e)[:100]}")
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
            }""", {"method": method, "url": url, "data": data, "headers": headers or {}, "timeout_ms": timeout_ms})
        except Exception as e:
            return {"status": 0, "body": f"EVAL_ERR:{str(e)[:100]}"}

    async def close(self):
        if self.page:
            try:
                await self.page.close()
            except Exception:
                pass
        self.page = None


async def create_tempmailhub_email(zf, tries=4):
    """TempMailHub API via ZenRows tab fetch: real @gmail.com (no dots/plus),
    validated mailbox. Returns (email, email_id) or (None, None)."""
    import json as _j
    for _t in range(tries):
        try:
            _r = await zf.call("POST", f"{TEMPMAILHUB_API}/emails", {"domain": "gmail.com"},
                               {"Content-Type": "application/json", "Origin": "https://tempmailhub.org"})
            if _r["status"] != 201:
                print(f"tempmailhub try {_t+1} status {_r['status']} {str(_r['body'])[:80]}")
                continue
            _acct = _j.loads(_r["body"])
            _em, _eid = _acct.get("email", ""), str(_acct.get("email_id", ""))
            _local = _em.split("@")[0] if "@" in _em else ""
            if not (_em.lower().endswith("@gmail.com") and "." not in _local and "+" not in _local):
                print(f"tempmailhub skip {_em} (need clean gmail), retry {_t+1}/{tries}")
                continue
            _m = await zf.call("GET", f"{TEMPMAILHUB_API}/emails/messages?email_id={_eid}",
                               None, {"Origin": "https://tempmailhub.org"})
            _body = _m["body"]
            if "norecentemails" in _body.lower() or '"emails":[' in _body:
                print(f"tempmailhub Gmail {_em} (id {_eid})")
                return _em, _eid
            print(f"tempmailhub mailbox not ready for {_em}, retry {_t+1}/{tries}")
        except Exception as _e:
            print(f"tempmailhub try {_t+1} err {str(_e)[:100]}")
    return None, None
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


async def poll_tempmailhub_link(zf, email_id, timeout_seconds=180):
    """Poll TempMailHub API via ZenRows tab fetch (1 evaluate per check)."""
    import json as _j, html as _h
    deadline = time.time() + timeout_seconds
    check = 0
    while time.time() < deadline:
        check += 1
        try:
            _r = await zf.call("GET", f"{TEMPMAILHUB_API}/emails/messages?email_id={email_id}",
                               None, {"Origin": "https://tempmailhub.org"})
            _data = _j.loads(_r["body"]) if _r["status"] == 200 else []
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
        await asyncio.sleep(5)
    return None


async def _temptf_get(zf, path, data=None):
    import json as _j
    if data is not None:
        _r = await zf.call("POST", f"{TEMP_TF_API}{path}", data, {"Content-Type": "application/json"})
    else:
        _r = await zf.call("GET", f"{TEMP_TF_API}{path}")
    if _r["status"] != 200:
        raise Exception(f"temp.tf {path} status {_r['status']}: {str(_r['body'])[:100]}")
    return _j.loads(_r["body"])


async def create_temptf_email(zf, tries=10):
    """temp.tf API via ZenRows tab fetch: dot-trick @gmail.com. Returns email or None."""
    for _t in range(tries):
        try:
            _acct = await _temptf_get(zf, "/account?dot=1&providers=gmail")
            _em = _acct.get("email", "")
            await _temptf_get(zf, "/check", {"email": _em})
            print(f"temp.tf Gmail {_em}")
            return _em
        except Exception as _e:
            print(f"temp.tf try {_t+1} err {str(_e)[:100]}")
    return None


async def poll_temptf_link(zf, email, timeout_seconds=180):
    """Poll temp.tf API via ZenRows tab fetch (1 evaluate per check)."""
    import html as _h
    deadline = time.time() + timeout_seconds
    check = 0
    while time.time() < deadline:
        check += 1
        try:
            _resp = await _temptf_get(zf, "/check", {"email": email})
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
        await asyncio.sleep(5)
    return None


async def create_22do_gmail(zf, tries=40):
    """22.do fake-gmail API via ZenRows tab fetch. Returns @gmail.com or None."""
    import json as _j
    for _t in range(tries):
        try:
            _r = await zf.call("POST", "https://22.do/action/mailbox/gmail", {"type": "random"},
                {"Content-Type": "application/json",
                 "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"})
            if _r["status"] != 200:
                print(f"22.do API try {_t+1} status {_r['status']}")
                continue
            _res = _j.loads(_r["body"])
            _em = ((_res.get("data") or {}).get("email") or "").strip()
            _local = _em.split("@")[0] if "@" in _em else ""
            if _em.lower().endswith("@gmail.com") and _local.count(".") == 1 and "+" not in _em:
                return _em
            print(f"22.do skip {_em} (need @gmail.com + exactly 1 dot, no plus), retry {_t+1}/{tries}")
        except Exception as _e:
            print(f"22.do API try {_t+1} err {str(_e)[:120]}")
    return None


async def poll_22do_lovable_link(ctx, email, timeout_seconds=180, zf=None):
    """Poll 22.do inbox for the Lovable verify mail, return oobCode link or None.
    Fast path (zf given): pure tab-fetch — applyToken{email,uuid} → message{email}
    → content/{id} HTML. No DOM tab, 2-3 evaluates per check. Falls back to the
    legacy DOM tab poll when fetch path fails."""
    print(f"📥 Waiting for Lovable verify link on 22.do ({email})...")
    link_re = re.compile(r"https?://lovable\.dev/auth/action\?[^\"'\s<>]*oobCode=[^\"'\s<>]+", re.I)
    # FAST PATH: pure tab-fetch (applyToken → message → content/{id}).
    # Reverse-engineered from 22.do/inbox JS: needs Bearer from applyToken.
    if zf is not None:
        import json as _j22, html as _h22, random as _r22
        try:
            await zf.home("https://22.do/")
        except Exception:
            pass
        _uuid = "".join(_r22.choices("0123456789abcdef", k=32))
        _tok = None
        try:
            _tr = await zf.call("POST", "https://22.do/action/mailbox/applyToken",
                                {"email": email, "uuid": _uuid},
                                {"Content-Type": "application/json"})
            _tj = _j22.loads(_tr["body"]) if _tr["status"] == 200 else {}
            if _tj.get("status") and (_tj.get("data") or {}).get("token"):
                _tok = _tj["data"]["token"]
                print("  22.do fetch-path token ok")
        except Exception as _te:
            print(f"  22.do applyToken fail: {str(_te)[:80]}")
        if _tok:
            deadline = time.time() + timeout_seconds
            check = 0
            while time.time() < deadline:
                check += 1
                try:
                    _mr = await zf.call("POST", "https://22.do/action/mailbox/message",
                                        {"email": email, "lastime": 0},
                                        {"Content-Type": "application/json",
                                         "Authorization": f"Bearer {_tok}"})
                    _mj = _j22.loads(_mr["body"]) if _mr["status"] == 200 else {}
                    _items = (_mj.get("data") or []) if _mj.get("status") else []
                except Exception:
                    _items = []
                if check % 3 == 1:
                    print(f"  Check #{check}: {len(_items)} message(s) [fetch-path]")
                for _m in _items:
                    _s = str(_m.get("subject", ""))
                    _f = str(_m.get("from", ""))
                    if "lovable" in (_s + _f).lower() or "verify" in _s.lower():
                        _mid = str(_m.get("messageId", _m.get("id", "")))
                        print(f"  ✅ Found Lovable mail: {_s[:80]} / {_f[:40]}")
                        _html22 = ""
                        if _mid:
                            try:
                                _cr = await zf.call("GET", f"https://22.do/content/{_mid}")
                                _html22 = _cr["body"] if _cr["status"] == 200 else ""
                            except Exception:
                                pass
                        _m22 = link_re.search(_html22 or "")
                        if _m22:
                            link = _h22.unescape(_m22.group(0)).replace("&amp;", "&")
                            print(f"  🎯 FOUND VERIFY LINK via 22.do fetch: {link[:120]}...")
                            return link
                        print("  ⚠️ mail found but no link in content page")
                        return None
                await asyncio.sleep(5)
            return None
        print("  22.do fetch-path unavailable, DOM tab fallback")
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
            try:
                await _open.scroll_into_view_if_needed(timeout=5000)
            except Exception:
                pass
            try:
                await _open.click(timeout=8000)
            except Exception:
                await _open.evaluate("el => el.click()")
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
                rows = await self.page.evaluate("""() => {
                    const items=[...document.querySelectorAll('article.email-item')];
                    if(items.length) return items.map(a=>{
                        const s=a.querySelector('.email-sender')?.innerText||'';
                        const t=a.querySelector('.email-subject')?.innerText||'';
                        return s+' / '+t; }).join(' || ').slice(0,800);
                    const scope = document.querySelector('.email-list,.list-content,.message-list') || document;
                    return [...scope.querySelectorAll('button,li,[role="option"],tr,a')]
                    .map(e => (e.innerText||'').slice(0,150)).filter(t=>t.length>3).join(' || ').slice(0,800); }""")
            except Exception:
                rows = ""
            if check % 3 == 1:
                print(f"  Check #{check}: rows={rows[:200]}")
            low = (rows or "").lower()
            if "lovable" in low or "verify" in low:
                try:
                    cand = self.page.locator('article.email-item').filter(has_text=re.compile("lovable|verify", re.I)).first
                    if not await cand.count():
                        cand = self.page.locator('button,li').filter(has_text=re.compile("lovable|verify", re.I)).first
                    if await cand.count():
                        await cand.click(timeout=5000, force=True)
                        await self.page.wait_for_timeout(3000)
                except Exception:
                    pass
                try:
                    # viewer renders mail in iframe srcdoc — grab it directly
                    htmlzx = await self.page.evaluate("""() => {
                        const f=document.querySelector('.viewer iframe, div.viewer iframe');
                        if(f) return f.getAttribute('srcdoc')||'';
                        const v=document.querySelector('div.viewer');
                        return v ? v.innerHTML.slice(0,20000) : ''; }""")
                except Exception:
                    htmlzx = ""
                if not htmlzx or "oobCode" not in htmlzx:
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

PROVIDER_ORDER = ["tempmailhub", "22do", "temptf", "zenvex", "dispose"]


async def run_signup(args, run_attempt=1, force_src=None):
    """One full signup. force_src limits mail to a single provider (fresh
    browser+IP per call either way). Returns True on verified save."""
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
    # ZENROWS_KEYS (comma-separated) rotates per farm-loop iteration; else pool
    _keypool = [k.strip() for k in _oskey.environ.get("ZENROWS_KEYS", "").split(",") if k.strip()]
    if _keypool:
        import hashlib as _hl
        key = _keypool[int(_hl.md5(f"{run_attempt}".encode()).hexdigest(), 16) % len(_keypool)]
    else:
        key = _envkey or zenrows_keys[(run_attempt - 1) % len(zenrows_keys)]
    proxy_country = countries[(run_attempt - 1) % len(countries)]
    zenrows_wss_url = f"wss://browser.zenrows.com?apikey={key}&proxy_country={proxy_country}"
    _run_t0 = time.time()

    # 0) PROVIDER CHAIN runs AFTER connect via ZenFetch (fetch inside the
    # ZenRows tab = residential egress; local raw-IP curl gets 404/denied).
    # tempmailhub → 22.do → temp.tf (tab-fetch) → zenvex tab → dispose tab.
    pre_email, pre_src, pre_id = None, None, None
    only = [force_src] if force_src else ["tempmailhub", "22do", "temptf"]
    zf = None

    def _avail(_em, _tag):
        if _em and lovable_email_available(_em):
            print(f"{_tag} {_em} (available)")
            return True
        if _em:
            print(f"{_tag} {_em} already registered — next provider")
        return False

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
        # API providers via ZenFetch tab (residential egress, zero local curl).
        # Each provider's calls run from its own origin (CORS).
        zf = await ZenFetch().open(ctx)
        if "tempmailhub" in only:
            await zf.home("https://tempmailhub.org/")
            _th_em, _th_id = await create_tempmailhub_email(zf)
            if _avail(_th_em, "tempmailhub Gmail"):
                pre_email, pre_src, pre_id = _th_em, "tempmailhub", _th_id
        if not pre_email and "22do" in only:
            await zf.home("https://22.do/")
            _em22 = await create_22do_gmail(zf)
            if _avail(_em22, "22.do Gmail"):
                pre_email, pre_src = _em22, "22do"
        if not pre_email and "temptf" in only:
            await zf.home("https://temp.tf/")
            _emtf = await create_temptf_email(zf)
            if _avail(_emtf, "temp.tf Gmail"):
                pre_email, pre_src = _emtf, "temptf"
        if force_src in ("tempmailhub", "22do", "temptf") and not pre_email:
            print(f"forced provider {force_src} missed — aborting run (next provider gets own run)")
            return False

        # Use API mail if we got one — else browser-tab chain:
        # zenvex first, dispose.lol last (force_src limits to one tab provider).
        inbox = None
        zxinbox = None
        email_source = "dispose"
        email, email_id = pre_email, pre_id
        tab_order = [force_src] if force_src in ("zenvex", "dispose") else ["zenvex", "dispose"]
        if email:
            email_source = pre_src
            print(f"{pre_src} mail {email} (skip browser-tab inboxes)")
        else:
            if "zenvex" in tab_order:
                try:
                    zxinbox = ZenvexInbox(ctx)
                    email = await zxinbox.init_mailbox()
                    email_source = "zenvex"
                except Exception as _zxe:
                    print(f"zenvex miss ({str(_zxe)[:100]}), fallback to dispose.lol tab")
                    zxinbox = None
            if (not email or email_source != "zenvex") and "dispose" in tab_order:
                print("API + zenvex miss, fallback to dispose.lol Gmail tab")
                inbox = DisposeLolInbox(ctx)
                email = await inbox.init_mailbox()
                email_source = "dispose"
            if not email:
                print(f"forced provider {force_src} missed — aborting run")
                return False
            if email_source in ("zenvex", "dispose") and not lovable_email_available(email):
                print(f"{email_source} {email} already registered — ", end="")
                if email_source == "zenvex" and "dispose" in tab_order:
                    print("falling to dispose tab")
                    try:
                        await zxinbox.close()
                    except Exception:
                        pass
                    zxinbox = None
                    inbox = DisposeLolInbox(ctx)
                    email = await inbox.init_mailbox()
                    email_source = "dispose"
                    if not lovable_email_available(email):
                        print(f"dispose {email} also registered — aborting run")
                        return False
                else:
                    print("aborting run")
                    return False
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
        try:
            ip = await page.evaluate("async () => { try{ const r=await fetch('https://wtfismyip.com/json'); const j=await r.json(); return j.YourFuckingIPAddress+' '+j.YourFuckingISP }catch(e){ return 'fail' } }")
        except: pass
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
        # If the form never renders (slow hydration), reload once before dying.
        email_loc = page.locator('input#email')
        try:
            await email_loc.wait_for(timeout=12000)
        except Exception:
            print("  ⚠️ input#email missing — one reload then retry")
            try:
                await page.reload(wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(4000)
            except Exception:
                pass
            await email_loc.wait_for(timeout=15000)
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
        # (no screenshot here: full_page shots cost 5-10s on cloud CDP pre-Create)

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
        _token_len = len(token)
        _age_create = round(time.time() - _run_t0)

        if len(token) == 0:
            print("⛔ Turnstile challenge failed/blocked (token 0). Killing browser...")
            _log_run(email=email, src=email_source, ip=(ip or "").split(" ")[0], isp=_isp, outcome="token0")
            raise Exception("SUSPICIOUS_BLOCK_DETECTED: Cloudflare Turnstile token missing")

        # Pre-Create password re-verify: React state can desync from DOM during
        # the token wait (server then says 'Password is required' despite len ok).
        # Real keystroke at the end forces React sync.
        try:
            _pvw = await page.evaluate("() => document.querySelector('#password')?.value?.length || 0")
            if _pvw != len(password):
                print(f"  ⚠️ password desynced (dom {_pvw} != {len(password)}) — refill")
                try:
                    await page.locator('input#password').fill(password, timeout=5000)
                except Exception:
                    pass
            else:
                try:
                    await page.locator('input#password').click(timeout=2000)
                    await page.keyboard.press("End")
                    await page.keyboard.type(" ", delay=30)
                    await page.keyboard.press("Backspace")
                except Exception:
                    pass
                _pvw2 = await page.evaluate("() => document.querySelector('#password')?.value?.length || 0")
                if _pvw2 != len(password):
                    print(f"  ⚠️ password lost after sync keystroke ({_pvw2}) — refill")
                    await page.locator('input#password').fill(password, timeout=5000)
        except Exception as _pwe:
            print(f"  password re-verify err: {str(_pwe)[:80]}")

        # Click Create — HUMAN HESITATION: bots click the instant the button
        # enables; humans stare at Success!, scroll, move the mouse, then click.
        # Instant-click post-token is a prime abuse-detection signal.
        btn = page.locator('[data-testid="auth-submit-button"]')
        disabled = await btn.is_disabled()
        print(f"Create disabled {disabled}")
        # (no pre-Create screenshot: session budget)

        if not disabled:
            # NO synthetic mouse movement: single-shot mouse.move teleports
            # (superhuman) and may be the bot signal — the one success used a
            # plain element click with zero mouse trail. Keep a passive dwell.
            await page.wait_for_timeout(random.randint(4000, 7000))
            try:
                await btn.click(timeout=8000)
                print("  🖱️ Create clicked (plain element click, no mouse trail)")
            except Exception:
                await btn.click()
            await page.wait_for_timeout(8000)
            # Verdict wait: poll VISIBLE TEXT (1 evaluate/tick, max ~20s) for a
            # definitive state. Single-shot content reads catch mid-render HTML
            # (ambiguous snippet, wrong branch). Screenshot only on failure.
            content, content_lower = "", ""
            for _v in range(10):
                try:
                    _bt = await page.evaluate("() => document.body ? document.body.innerText.slice(0,3000) : ''")
                except Exception:
                    break
                content += "\n" + (_bt or "")
                content_lower = content.lower()
                if ("check your inbox" in content_lower or "verify" in content_lower
                        or "suspicious" in content_lower or "denied" in content_lower
                        or "invalid" in content_lower or "try again" in content_lower
                        or "too many" in content_lower):
                    break
                await page.wait_for_timeout(2000)
            else:
                try:
                    await page.screenshot(path="/tmp/zen_final_after.png", full_page=True)
                except Exception:
                    pass
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
                _log_run(email=email, src=email_source, ip=(ip or "").split(" ")[0], isp=_isp, outcome="suspicious", detail=detected_err, token_len=_token_len, age_create_s=_age_create)
                raise Exception(f"SUSPICIOUS_BLOCK_DETECTED: {detected_err}")

            if "Check your inbox" in content:
                print("SUCCESS Check your inbox")
            else:
                print(f"Page response snippet: {content[:500]}")

            # Wait for Lovable verify link from the matching inbox.
            # Pure-HTTP polls (tempmailhub/temp.tf) burn zero session budget.
            if email_source == "tempmailhub":
                link = await poll_tempmailhub_link(zf, email_id)
            elif email_source == "22do":
                link = await poll_22do_lovable_link(ctx, email, zf=zf)
            elif email_source == "temptf":
                link = await poll_temptf_link(zf, email)
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
                _log_run(email=email, src=email_source, ip=(ip or "").split(" ")[0], isp=_isp, outcome="success", session=session_id_dir, token_len=_token_len, age_create_s=_age_create)
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
        try:
            if zf:
                await zf.close()
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
    parser.add_argument("--loop", type=int, default=1, help="Farm loop: full fresh runs (default 1)")
    parser.add_argument("--pace-mins", type=float, default=0, help="Sleep minutes between loop runs (quota pacing)")
    parser.add_argument("--providers", default="chain",
                        help="'chain' (default first-available) or 'all' (each provider gets own fresh browser+IP run)")
    args = parser.parse_args()

    for loop_i in range(1, args.loop + 1):
        if loop_i > 1 and args.pace_mins > 0:
            print(f"⏳ Pacing {args.pace_mins} min before loop run {loop_i}/{args.loop}...", flush=True)
            await asyncio.sleep(args.pace_mins * 60)
        print(f"\n########## LOOP RUN {loop_i}/{args.loop} ##########", flush=True)
        if args.providers == "all":
            prov_list = PROVIDER_ORDER
        elif args.providers in PROVIDER_ORDER:
            prov_list = [args.providers]
        else:
            prov_list = [None]
        for prov in prov_list:
            if prov:
                print(f"\n===== PROVIDER {prov} (fresh browser+IP) =====", flush=True)
            for attempt in range(1, args.max_retries + 1):
                try:
                    print(f"\n==========================================", flush=True)
                    print(f"🚀 SIGNUP ATTEMPT {attempt}/{args.max_retries}" + (f" [{prov}]" if prov else ""), flush=True)
                    print(f"==========================================", flush=True)
                    success = await run_signup(args, run_attempt=(loop_i - 1) * args.max_retries + attempt,
                                               force_src=prov)
                    if success:
                        print(f"🎉 Signup completed successfully on attempt {attempt}!" + (f" [{prov}]" if prov else ""), flush=True)
                        break
                except Exception as e:
                    if "SUSPICIOUS_BLOCK_DETECTED" in str(e) or "ASN_GATE_BLOCKED" in str(e):
                        print(f"⛔ [Attempt {attempt}] Suspicious error encountered! Browser process killed.", flush=True)
                        if not args.local:
                            print(f"🔄 ZenRows mode: Changing IP / Proxy Country & Session ID for attempt {attempt + 1}...", flush=True)
                        else:
                            print(f"🔄 Local mode: Restarting fresh browser instance for attempt {attempt + 1}...", flush=True)
                        await asyncio.sleep(3)
                    else:
                        print(f"⚠️ Error on attempt {attempt}: {e}", flush=True)
                        await asyncio.sleep(2)
            else:
                continue
            break

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

