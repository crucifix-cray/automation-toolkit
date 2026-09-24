#!/usr/bin/env python3
"""Lovable mail chain — locked order for farm_lovable_ultimate.

Order (per attempt, then loop):
  1. Zenvex — all domains (souss.dev → … → ofppt.edu.pl)
  2. temp.tf Gmail one-dot (?dot=1&providers=gmail)
  3. temp.tf @high.edu.pl (?domain=high.edu)
  4. 22.do one-dot Gmail
  5. dispose.lol Temporary Gmail (tab)
  6. mail.tm API
"""
from __future__ import annotations

import asyncio
import html as _h
import json as _j
import random
import re
import secrets
import string
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional

LOVABLE_VERIFY_RE = re.compile(
    r"https?://(?:[^\s'\"<>]*\.)?lovable\.dev/auth/action\?[^\s'\"<>]*oobCode=[^\s'\"<>]+",
    re.I,
)
# Firebase sometimes wraps links; also catch bare oobCode URLs with html entities
OOB_ANY_RE = re.compile(
    r"https?://[^\s'\"<>]*oobCode=[^\s'\"<>]+",
    re.I,
)
OOB_CODE_ONLY_RE = re.compile(
    r"(?:https?://(?:www\.)?lovable\.dev/auth/action\?|oobCode=)"
    r"[^\s'\"<>]*oobCode=([A-Za-z0-9_\-]+)",
    re.I,
)


def _extract_lovable_link(blob: str) -> Optional[str]:
    if not blob:
        return None
    # normalize html entities / zero-width / soft hyphens before match
    text = _h.unescape(blob or "")
    text = text.replace("\u200b", "").replace("\xad", "").replace("&amp;", "&")
    m = LOVABLE_VERIFY_RE.search(text)
    if not m:
        m = OOB_ANY_RE.search(text)
        if m and "oobCode=" not in m.group(0):
            return None
    if not m:
        return None
    link = m.group(0).replace("&amp;", "&").rstrip(").,;]'\"")
    if "lovable.dev" not in link.lower() and "oobCode=" not in link:
        return None
    # prefer full lovable.dev auth/action URL
    if "lovable.dev/auth/action" not in link.lower() and "oobCode=" in link:
        # rebuild if we only got a partial
        om = re.search(r"oobCode=([A-Za-z0-9_\-]+)", link)
        if om:
            link = (
                "https://lovable.dev/auth/action?mode=verifyEmail"
                f"&oobCode={om.group(1)}&apiKey=AIzaSyBQNjlw9Vp4tP4VVeANzyPJnqbG2wLbYPw&lang=en"
            )
    return link


TEMP_TF_API = "https://temp.tf/api"
MAIL_TM_API = "https://api.mail.tm"
TWODO_GMAIL = "https://22.do/action/mailbox/gmail"
TWODO_APPLY = "https://22.do/action/mailbox/applyToken"
TWODO_MSG = "https://22.do/action/mailbox/message"
TWODO_CONTENT = "https://22.do/content/"

ZENVEX_DOMAINS = [
    "souss.dev",
    "znvx.me",
    "zenvex.edu.pl",
    "encg.edu.pl",
    "ensam.edu.pl",
    "ofppt.edu.pl",
]


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def one_dot_gmail(em: str) -> bool:
    em = (em or "").strip()
    if not em.lower().endswith("@gmail.com") or "+" in em:
        return False
    return em.split("@")[0].count(".") == 1


def _http_json(method: str, url: str, data=None, headers=None, timeout: int = 20):
    hdrs = {"Content-Type": "application/json", "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    body = None if data is None else _j.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    # temp.tf / mail APIs hate Tor/proxy
    old = {k: __import__("os").environ.pop(k, None) for k in (
        "HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy", "ALL_PROXY", "all_proxy")}
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode(errors="replace")
            try:
                return resp.status, _j.loads(raw) if raw else {}
            except Exception:
                return resp.status, {"_raw": raw}
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            return e.code, _j.loads(raw) if raw else {"_raw": raw}
        except Exception:
            return e.code, {"_raw": raw}
    finally:
        for k, v in old.items():
            if v is not None:
                __import__("os").environ[k] = v


@dataclass
class Mailbox:
    provider: str
    address: str
    meta: dict = field(default_factory=dict)
    _page: Any = field(default=None, repr=False)
    _ctx: Any = field(default=None, repr=False)

    async def wait_for_lovable_link(self, timeout_seconds: int = 420) -> str:
        prov = self.provider
        if prov.startswith("zenvex"):
            return await _poll_zenvex(self, timeout_seconds)
        if prov == "dispose":
            return await _poll_dispose(self, timeout_seconds)
        if prov in ("temptf_gmail", "temptf_high"):
            return await _poll_temptf(self.address, timeout_seconds)
        if prov == "22do":
            return await _poll_22do(self.address, timeout_seconds, self._ctx)
        if prov == "mailtm":
            return await _poll_mailtm(self, timeout_seconds)
        raise RuntimeError(f"no poller for provider={prov}")

    async def close(self) -> None:
        if self._page:
            try:
                await self._page.close()
            except Exception:
                pass
            self._page = None


# ── Zenvex ────────────────────────────────────────────────────────────────────
async def create_zenvex(ctx, domain: str) -> Mailbox:
    page = await ctx.new_page()
    await page.goto("https://zenvex.dev", wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(3000)
    prefix = "lov" + "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    inp = page.locator('input[placeholder*="prefix"]').first
    await inp.wait_for(state="visible", timeout=12000)
    await inp.fill(prefix)
    try:
        trig = page.locator("button.domain-trigger").first
        if await trig.count():
            await trig.click(timeout=5000)
            await page.wait_for_timeout(800)
            opt = page.locator("button.domain-option").filter(has_text=domain).first
            if await opt.count():
                await opt.click(timeout=5000)
                await page.wait_for_timeout(800)
                log(f"  zenvex domain set: {domain}")
    except Exception as e:
        log(f"  zenvex domain pick fail ({str(e)[:60]}), keeping default")
    open_btn = page.get_by_role("button", name="Open Inbox").first
    try:
        await open_btn.scroll_into_view_if_needed(timeout=5000)
    except Exception:
        pass
    try:
        await open_btn.click(timeout=8000)
    except Exception:
        await open_btn.evaluate("el => el.click()")
    await page.wait_for_timeout(3500)
    try:
        disp = page.locator(".inbox-email-display").first
        await disp.wait_for(state="visible", timeout=10000)
        address = (await disp.inner_text(timeout=3000)).strip()
    except Exception:
        address = f"{prefix}@{domain}"
    log(f"✅ Mailbox ready: {address} (via zenvex/{domain})")
    return Mailbox(provider=f"zenvex:{domain}", address=address, _page=page, _ctx=ctx)


async def open_existing_zenvex(ctx, email: str) -> Mailbox:
    """Re-open an existing zenvex inbox by address (for link-detect tests / resume)."""
    email = (email or "").strip()
    if "@" not in email:
        raise ValueError(f"bad zenvex email: {email}")
    prefix, domain = email.split("@", 1)
    page = await ctx.new_page()
    await page.goto("https://zenvex.dev", wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(2500)
    inp = page.locator('input[placeholder*="prefix"]').first
    await inp.wait_for(state="visible", timeout=12000)
    await inp.fill(prefix)
    try:
        trig = page.locator("button.domain-trigger").first
        if await trig.count():
            await trig.click(timeout=5000)
            await page.wait_for_timeout(800)
            opt = page.locator("button.domain-option").filter(has_text=domain).first
            if await opt.count():
                await opt.click(timeout=5000)
                await page.wait_for_timeout(800)
    except Exception as e:
        log(f"  zenvex domain pick fail ({str(e)[:60]})")
    open_btn = page.get_by_role("button", name="Open Inbox").first
    try:
        await open_btn.click(timeout=8000)
    except Exception:
        await open_btn.evaluate("el => el.click()")
    await page.wait_for_timeout(3500)
    log(f"✅ Reopened zenvex inbox: {email}")
    return Mailbox(provider=f"zenvex:{domain}", address=email, _page=page, _ctx=ctx)


async def _zenvex_click_lovable_mail(page) -> bool:
    """Click the Lovable verify row. Prefer smallest email-item — never a page-root div."""
    try:
        clicked = await page.evaluate("""() => {
          const items = [...document.querySelectorAll(
            'article.email-item, .email-item, [class*="email-item"]'
          )];
          const hit = items
            .filter(a => /lovable|verify/i.test(a.innerText || ''))
            .sort((a,b) => (a.innerText||'').length - (b.innerText||'').length)[0];
          if (hit) {
            hit.scrollIntoView({block:'center'});
            hit.click();
            return (hit.innerText||'').replace(/\\s+/g,' ').slice(0,100);
          }
          // fallback: narrow text nodes' closest clickable, length-capped
          const all = [...document.querySelectorAll('button,li,a,[role="button"]')]
            .filter(e => {
              const t=(e.innerText||'').trim();
              return t.length > 8 && t.length < 200 && /noreply@lovable|Verify your email for Lovable/i.test(t);
            })
            .sort((a,b) => (a.innerText||'').length - (b.innerText||'').length);
          if (all[0]) { all[0].click(); return (all[0].innerText||'').replace(/\\s+/g,' ').slice(0,100); }
          return '';
        }""")
        if clicked:
            log(f"  clicked mail row: {clicked!r}")
            await page.wait_for_timeout(2800)
            return True
    except Exception as e:
        log(f"  click evaluate fail: {e}")
    try:
        cand = page.locator("article.email-item").filter(
            has_text=re.compile("lovable|verify", re.I)).first
        if await cand.count():
            await cand.click(timeout=5000, force=True)
            await page.wait_for_timeout(2800)
            log("  clicked via locator article.email-item")
            return True
    except Exception as e:
        log(f"  click locator fail: {e}")
    return False


async def _zenvex_dump_for_link(page) -> str:
    """Pull viewer text/html/hrefs where the oob link appears (keep CDP light — no frame crawl)."""
    # Prefer HTML tab — screenshot shows plain URL there
    for tab in ("HTML", "Text", "Raw"):
        try:
            await page.evaluate(
                """(name) => {
                  const b=[...document.querySelectorAll('button,a,[role="tab"]')]
                    .find(x => (x.innerText||'').trim()===name);
                  if(b) b.click();
                }""",
                tab,
            )
            await page.wait_for_timeout(350)
        except Exception:
            pass
    try:
        return await page.evaluate("""() => {
          const parts = [];
          parts.push(document.body ? document.body.innerText : '');
          parts.push(document.body ? document.body.innerHTML : '');
          for (const a of document.querySelectorAll('a[href]')) parts.push(a.href);
          for (const f of document.querySelectorAll('iframe')) {
            parts.push(f.getAttribute('srcdoc') || '');
          }
          // viewer pane specifically
          for (const sel of ['.viewer','.email-viewer','.message-body','[class*="viewer"]','pre','code']) {
            for (const el of document.querySelectorAll(sel)) {
              parts.push(el.innerText || '');
              parts.push(el.innerHTML || '');
            }
          }
          return parts.join('\\n');
        }""")
    except Exception as e:
        log(f"  dump err: {e}")
        return ""


async def _poll_zenvex(box: Mailbox, timeout_seconds: int) -> str:
    page = box._page
    log(f"📥 Waiting for Lovable verify on zenvex ({box.address})...")
    deadline = time.time() + timeout_seconds
    check = 0
    saw_mail = False
    while time.time() < deadline:
        check += 1
        # Only reload while waiting for the mail to appear — reload wipes open viewer
        if not saw_mail:
            try:
                await page.reload(wait_until="domcontentloaded")
            except Exception:
                pass
            await page.wait_for_timeout(2000)
        else:
            await page.wait_for_timeout(800)

        try:
            rows = await page.evaluate("""() => {
                const items=[...document.querySelectorAll('article.email-item, .email-item')];
                if(items.length) return items.map(a => (a.innerText||'').replace(/\\s+/g,' ').slice(0,120)).join(' || ');
                return (document.body.innerText||'').slice(0,400);
            }""")
        except Exception:
            rows = ""
        if check % 3 == 1:
            log(f"  Check #{check}: rows={(rows or '')[:180]}")

        low = (rows or "").lower()
        if "lovable" in low or "verify" in low:
            saw_mail = True
            await _zenvex_click_lovable_mail(page)
            # dump immediately + after a short settle
            for _ in range(3):
                htmlzx = await _zenvex_dump_for_link(page)
                link = _extract_lovable_link(htmlzx)
                if link:
                    log(f"  🎯 FOUND VERIFY LINK via zenvex: {link[:140]}...")
                    return link
                await page.wait_for_timeout(1200)
                await _zenvex_click_lovable_mail(page)
        await asyncio.sleep(2)
    raise TimeoutError("Lovable verify link not received on zenvex")


# ── temp.tf ───────────────────────────────────────────────────────────────────
async def create_temptf_gmail(tries: int = 12) -> Mailbox:
    for _t in range(tries):
        code, data = _http_json("GET", f"{TEMP_TF_API}/account?dot=1&providers=gmail")
        if code != 200:
            continue
        em = (data or {}).get("email", "")
        if not one_dot_gmail(em):
            log(f"  temp.tf gmail skip non-one-dot: {em}")
            continue
        c2, _ = _http_json("POST", f"{TEMP_TF_API}/check", {"email": em})
        if c2 == 200:
            log(f"✅ Mailbox ready: {em} (via temp.tf gmail one-dot)")
            return Mailbox(provider="temptf_gmail", address=em)
    raise RuntimeError("temp.tf gmail one-dot unavailable")


async def create_temptf_high(tries: int = 6) -> Mailbox:
    for _t in range(tries):
        code, data = _http_json("GET", f"{TEMP_TF_API}/account?domain=high.edu")
        if code != 200:
            continue
        em = (data or {}).get("email", "")
        if not em.lower().endswith("@high.edu.pl"):
            continue
        c2, _ = _http_json("POST", f"{TEMP_TF_API}/check", {"email": em})
        if c2 == 200:
            log(f"✅ Mailbox ready: {em} (via temp.tf high.edu.pl)")
            return Mailbox(provider="temptf_high", address=em)
    raise RuntimeError("temp.tf high.edu.pl unavailable")


async def _poll_temptf(email: str, timeout_seconds: int) -> str:
    log(f"📥 Waiting for Lovable verify on temp.tf ({email})...")
    deadline = time.time() + timeout_seconds
    check = 0
    while time.time() < deadline:
        check += 1
        code, data = _http_json("POST", f"{TEMP_TF_API}/check", {"email": email})
        items = (data or {}).get("data", []) if code == 200 else []
        if check % 4 == 1:
            log(f"  temp.tf poll #{check}: {len(items)} msgs")
        for m in items:
            blob = str(m.get("subject", "")) + " " + str(m.get("body", ""))
            link = _extract_lovable_link(blob)
            if link:
                log(f"  🎯 LINK via temp.tf: {link[:120]}...")
                return link
        await asyncio.sleep(5)
    raise TimeoutError("Lovable verify link not received on temp.tf")


# ── 22.do ─────────────────────────────────────────────────────────────────────
class _TabFetch:
    def __init__(self, ctx):
        self.ctx = ctx
        self.page = None

    async def home(self, origin_url: str) -> bool:
        try:
            if self.page is None:
                self.page = await self.ctx.new_page()
            await self.page.goto(origin_url, wait_until="domcontentloaded", timeout=30000)
            await self.page.wait_for_timeout(2000)
            return True
        except Exception as e:
            log(f"  zf home fail: {str(e)[:100]}")
            return False

    async def call(self, method, url, data=None, headers=None, timeout_ms=20000):
        try:
            return await self.page.evaluate(
                """async (p) => {
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
            }""",
                {"method": method, "url": url, "data": data,
                 "headers": headers or {}, "timeout_ms": timeout_ms},
            )
        except Exception as e:
            return {"status": 0, "body": f"EVAL_ERR:{str(e)[:100]}"}

    async def close(self):
        if self.page:
            try:
                await self.page.close()
            except Exception:
                pass
            self.page = None


async def create_22do(ctx, tries: int = 30) -> Mailbox:
    zf = _TabFetch(ctx)
    if not await zf.home("https://22.do/"):
        await zf.close()
        raise RuntimeError("22.do home failed")
    for _t in range(tries):
        r = await zf.call(
            "POST", TWODO_GMAIL, {"type": "random"},
            {"Content-Type": "application/json",
             "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        if r["status"] != 200:
            continue
        try:
            em = (((_j.loads(r["body"])).get("data") or {}).get("email") or "").strip()
        except Exception:
            continue
        if one_dot_gmail(em):
            log(f"✅ Mailbox ready: {em} (via 22.do)")
            # keep tab for poll
            return Mailbox(provider="22do", address=em, meta={"zf": zf}, _page=zf.page, _ctx=ctx)
    await zf.close()
    raise RuntimeError("22.do one-dot gmail unavailable")


async def _poll_22do(email: str, timeout_seconds: int, ctx) -> str:
    log(f"📥 Waiting for Lovable verify on 22.do ({email})...")
    zf = _TabFetch(ctx)
    if not await zf.home("https://22.do/"):
        raise RuntimeError("22.do poll home failed")
    uuid = "".join(random.choices("0123456789abcdef", k=32))
    tr = await zf.call("POST", TWODO_APPLY, {"email": email, "uuid": uuid})
    tok = None
    try:
        tj = _j.loads(tr["body"]) if tr["status"] == 200 else {}
        if tj.get("status") and (tj.get("data") or {}).get("token"):
            tok = tj["data"]["token"]
    except Exception:
        pass
    if not tok:
        await zf.close()
        raise RuntimeError("22.do applyToken failed")
    deadline = time.time() + timeout_seconds
    check = 0
    while time.time() < deadline:
        check += 1
        mr = await zf.call(
            "POST", TWODO_MSG, {"email": email, "lastime": 0},
            {"Content-Type": "application/json", "Authorization": f"Bearer {tok}"},
        )
        try:
            mj = _j.loads(mr["body"]) if mr["status"] == 200 else {}
            items = (mj.get("data") or []) if mj.get("status") else []
        except Exception:
            items = []
        if check % 3 == 1:
            log(f"  22.do poll #{check}: {len(items)} msgs")
        for m in items:
            subj = str(m.get("subject", ""))
            frm = str(m.get("from", m.get("sender", "")))
            if "lovable" not in (subj + frm).lower() and "verify" not in subj.lower():
                continue
            mid = str(m.get("messageId", m.get("id", "")))
            html22 = ""
            if mid:
                cr = await zf.call("GET", f"{TWODO_CONTENT}{mid}")
                html22 = cr["body"] if cr["status"] == 200 else ""
            link = _extract_lovable_link(html22 + " " + subj)
            if link:
                await zf.close()
                log(f"  🎯 LINK via 22.do: {link[:120]}...")
                return link
        await asyncio.sleep(5)
    await zf.close()
    raise TimeoutError("Lovable verify link not received on 22.do")


# ── dispose.lol ───────────────────────────────────────────────────────────────
async def create_dispose(ctx) -> Mailbox:
    page = await ctx.new_page()
    await page.goto("https://dispose.lol", wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(3500)
    for attempt in range(1, 6):
        email_text = await page.evaluate("""() => {
            const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT,null);
            let n; while(n=w.nextNode()){
                const t=n.textContent.trim();
                if(t.includes('@gmail.com')&&t.length<80) return t;
            }
            for(const i of document.querySelectorAll('input'))
              if(i.value&&i.value.includes('@gmail.com')) return i.value;
            return null; }""")
        if email_text and "@gmail.com" in email_text:
            em = email_text.strip()
            log(f"✅ Mailbox ready: {em} (via dispose.lol, attempt {attempt})")
            return Mailbox(provider="dispose", address=em, _page=page, _ctx=ctx)
        log(f"  dispose.lol not ready ({attempt}/5)")
        await page.wait_for_timeout(2000)
        await page.reload(wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)
    await page.close()
    raise RuntimeError("dispose.lol Gmail unavailable")


async def _poll_dispose(box: Mailbox, timeout_seconds: int) -> str:
    page = box._page
    log(f"📥 Waiting for Lovable verify on dispose.lol ({box.address})...")
    deadline = time.time() + timeout_seconds
    check = 0
    while time.time() < deadline:
        check += 1
        try:
            await page.reload(wait_until="domcontentloaded")
        except Exception:
            pass
        await page.wait_for_timeout(2200)
        try:
            buttons = await page.locator('button[aria-label^="View "]').all()
        except Exception:
            buttons = []
        if check % 4 == 1:
            log(f"  Check #{check}: {len(buttons)} message(s)")
        for btn in buttons:
            try:
                aria = (await btn.get_attribute("aria-label") or "")
            except Exception:
                aria = ""
            if "lovable" not in aria.lower() and "verify" not in aria.lower():
                continue
            try:
                await btn.click(timeout=5000, force=True)
                await page.wait_for_timeout(3000)
            except Exception:
                continue
            blob = ""
            for frame in page.frames:
                try:
                    blob += "\n" + await frame.content()
                except Exception:
                    pass
            try:
                blob += "\n" + await page.content()
            except Exception:
                pass
            link = _extract_lovable_link(blob)
            if link:
                log(f"  🎯 LINK via dispose: {link[:120]}...")
                return link
        await asyncio.sleep(3)
    raise TimeoutError("Lovable verify link not received on dispose.lol")


# ── mail.tm ───────────────────────────────────────────────────────────────────
async def create_mailtm() -> Mailbox:
    code, domains = _http_json("GET", f"{MAIL_TM_API}/domains")
    if code != 200:
        raise RuntimeError(f"mail.tm domains {code}")
    dom_list = [d["domain"] for d in (domains or {}).get("hydra:member", [])]
    if not dom_list:
        raise RuntimeError("No mail.tm domains")
    dom = random.choice(dom_list)
    local = "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
    addr = f"{local}@{dom}"
    pwd = secrets.token_hex(16)
    c2, _ = _http_json("POST", f"{MAIL_TM_API}/accounts", {"address": addr, "password": pwd})
    if c2 not in (200, 201):
        raise RuntimeError(f"mail.tm create {c2}")
    c3, tok = _http_json("POST", f"{MAIL_TM_API}/token", {"address": addr, "password": pwd})
    if c3 != 200 or not (tok or {}).get("token"):
        raise RuntimeError("mail.tm token fail")
    log(f"✅ Mailbox ready: {addr} (via mail.tm)")
    return Mailbox(provider="mailtm", address=addr, meta={"token": tok["token"], "password": pwd})


async def _poll_mailtm(box: Mailbox, timeout_seconds: int) -> str:
    token = box.meta.get("token")
    log(f"📥 Waiting for Lovable verify on mail.tm ({box.address})...")
    deadline = time.time() + timeout_seconds
    check = 0
    while time.time() < deadline:
        check += 1
        code, msgs = _http_json(
            "GET", f"{MAIL_TM_API}/messages",
            headers={"Authorization": f"Bearer {token}"},
        )
        items = (msgs or {}).get("hydra:member", []) if code == 200 else []
        if check % 5 == 1:
            log(f"  mail.tm poll #{check}: {len(items)} msgs")
        for msg in items:
            subj = msg.get("subject", "")
            intro = msg.get("intro", "")
            if "lovable" not in (subj + intro).lower() and "verify" not in subj.lower():
                continue
            mid = msg.get("id")
            full_blob = subj + " " + intro
            if mid:
                _, full = _http_json(
                    "GET", f"{MAIL_TM_API}/messages/{mid}",
                    headers={"Authorization": f"Bearer {token}"},
                )
                full_blob += " " + str((full or {}).get("text") or "")
                html = (full or {}).get("html") or ""
                if isinstance(html, list):
                    html = " ".join(html)
                full_blob += " " + str(html)
            link = _extract_lovable_link(full_blob)
            if link:
                log(f"  🎯 LINK via mail.tm: {link[:120]}...")
                return link
        await asyncio.sleep(4)
    raise TimeoutError("Lovable verify link not received on mail.tm")


# ── Chain ─────────────────────────────────────────────────────────────────────
async def acquire_mailbox(
    ctx,
    used: Optional[set] = None,
    skip_zenvex: bool = False,
    zenvex_offset: int = 0,
) -> Mailbox:
    """Walk mail chain once; raise if every provider fails.

    Zenvex domains are shuffled each acquire (spread reputation heat).
    zenvex_offset still biases retries away from the first failed domain.
    """
    used = used or set()

    # 1. Zenvex — random domain order each attempt
    if not skip_zenvex:
        order = list(ZENVEX_DOMAINS)
        random.shuffle(order)
        if zenvex_offset and order:
            # move previously preferred start out of bit-0 for retries
            n = len(order)
            pivot = order[zenvex_offset % n]
            order = [pivot] + [d for d in order if d != pivot]
            random.shuffle(order[1:])  # keep pivot first, reshuffle rest
        log(f"  zenvex domain order: {' → '.join(order)}")
        for dom in order:
            try:
                box = await create_zenvex(ctx, dom)
                if box.address.lower() not in used:
                    return box
                await box.close()
            except Exception as e:
                log(f"  zenvex/{dom} miss: {str(e)[:120]}")
    else:
        log("  zenvex skipped (--skip-zenvex)")

    # 2. temp.tf gmail one-dot
    try:
        box = await create_temptf_gmail()
        if box.address.lower() not in used:
            return box
    except Exception as e:
        log(f"  temptf_gmail miss: {str(e)[:120]}")

    # 3. temp.tf high.edu.pl
    try:
        box = await create_temptf_high()
        if box.address.lower() not in used:
            return box
    except Exception as e:
        log(f"  temptf_high miss: {str(e)[:120]}")

    # 4. 22.do
    try:
        box = await create_22do(ctx)
        if box.address.lower() not in used:
            return box
        await box.close()
    except Exception as e:
        log(f"  22do miss: {str(e)[:120]}")

    # 5. dispose
    try:
        box = await create_dispose(ctx)
        if box.address.lower() not in used:
            return box
        await box.close()
    except Exception as e:
        log(f"  dispose miss: {str(e)[:120]}")

    # 6. mail.tm
    try:
        box = await create_mailtm()
        if box.address.lower() not in used:
            return box
    except Exception as e:
        log(f"  mailtm miss: {str(e)[:120]}")

    raise RuntimeError("mail chain exhausted — all providers failed")
