#!/usr/bin/env python3
"""ZenRows account creation via Kernel Browser Cloud — deterministic, no AI, no opencode.
Uses Kernel stealth browser (fresh IP per run) + dispose.lol Gmail + iframe srcdoc verify extraction.

Flow proven 2026-09-02 on rprb81jbgg2gt6uyd0l6ozps (prod-jfk-hypeman-7, live 5a79zRDd8ZLd):
  dispose.lol cyn.thiabayaletan@gmail.com → app.zenrows.com/register (CF reload fix) → email/verify → dispose poll → url4722 Verify email → overview → API e7e88777223864ab0252b6983c98a8927c60cf8b
Also verified: s.ofiareeyesa@gmail.com → 3f7d260bab1d75874f8992d28eb536b575eb9a28

Usage:
  KERNEL_API_KEY=sk_729ff0c8-8973-8dcb-9c53-7288178dbc13.jO62-M4NtqELqARSxGY1Ar7BPyjSIU6OhdoHMjdt0Ow python3 finals/core/zenrows-kernel-final.py
"""
import asyncio, os, json, re, subprocess, sys, time, random

KERNEL_API_KEY = os.environ.get("KERNEL_API_KEY", "sk_729ff0c8-8973-8dcb-9c53-7288178dbc13.jO62-M4NtqELqARSxGY1Ar7BPyjSIU6OhdoHMjdt0Ow")
os.environ["PATH"] = os.environ.get("PATH","") + f":{os.path.expanduser('~')}/.local/bin"

def create_kernel_browser():
    if os.environ.get("KERNEL_CDP_WS"):
        wss = os.environ["KERNEL_CDP_WS"]
        return wss, os.environ.get("KERNEL_LIVE_URL",""), os.environ.get("KERNEL_SESSION_ID","")
    cmd = "kernel browsers create --stealth --timeout 600 --start-url https://dispose.lol -o json"
    env = {**os.environ, "KERNEL_API_KEY": KERNEL_API_KEY}
    out = subprocess.check_output(cmd, shell=True, env=env, text=True)
    data = json.loads(out)
    print(f"LIVE: {data['browser_live_view_url']} | SID: {data['session_id']}", file=sys.stderr)
    return data["cdp_ws_url"], data["browser_live_view_url"], data["session_id"]

def cleanup_kernel(session_id):
    try:
        subprocess.run(f"kernel browsers delete {session_id}", shell=True, env={**os.environ, "KERNEL_API_KEY": KERNEL_API_KEY}, timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except: pass

async def run_once():
    cdp_ws, live_url, session_id = create_kernel_browser()
    print(f"Connecting to {cdp_ws[:60]}... | LIVE {live_url}", file=sys.stderr)
    from playwright.async_api import async_playwright
    for k in list(os.environ):
        if k.lower().endswith('_proxy'):
            os.environ.pop(k, None)

    browser = None
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(cdp_ws, timeout=30000)
            ctx = browser.contexts[0]
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            if "dispose.lol" not in page.url:
                await page.goto("https://dispose.lol", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(5000)
            body = await page.evaluate("() => document.body.innerText")
            # User requested temp.tf Gmail with fresh IP each run
            try:
                import urllib.request, json as _json
                for k in list(__import__('os').environ):
                    if k.lower().endswith('_proxy'):
                        __import__('os').environ.pop(k,None)
                with urllib.request.urlopen("https://temp.tf/api/account?dot=1&providers=gmail", timeout=10) as r:
                    email = _json.loads(r.read())['email']
                print(f"TEMP.TF Gmail {email}", file=sys.stderr)
            except Exception as e:
                print(f"temp.tf fail {e}, fallback to Gmail from dispose", file=sys.stderr)
                m = re.search(r"[a-z0-9._%+-]+@gmail\.com", body, re.I)
                if not m:
                    print("No email found", body[:1000], file=sys.stderr)
                    await page.screenshot(path="/tmp/zen_no_email_found.png", full_page=True)
                    await browser.close()
                    cleanup_kernel(session_id)
                    sys.exit(1)
                email = m.group(0)
            password = "Test1234!AbcZ2026"
            print(f"EMAIL: {email} | PASS: {password}", file=sys.stderr)

            await page.goto("https://app.zenrows.com/register", wait_until="domcontentloaded", timeout=30000)
            solved = False
            # Let captcha solver take its time: wait 5min total, checking every 5s, refresh every 30s
            for i in range(60):  # 60 *5s = 300s = 5min
                await page.wait_for_timeout(5000)
                title = await page.title()
                body_snip = await page.evaluate("() => document.body.innerText.substring(0,1200)")
                if "Sign Up" in title and "Create a ZenRows account" in body_snip:
                    solved = True
                    print(f"CF solved attempt {i} title={title}", file=sys.stderr)
                    break
                if i % 6 == 5 and "Just a moment" in title:
                    print(f"CF still Just a moment at {i*5}s, refresh...", file=sys.stderr)
                    await page.reload(wait_until="domcontentloaded")
            if not solved:
                print("CF not solved", file=sys.stderr)
                await browser.close()
                cleanup_kernel(session_id)
                sys.exit(1)

            await page.wait_for_selector("#email", timeout=15000)
            await page.fill("#email", email)
            await page.wait_for_timeout(800)
            await page.fill("#password", password)
            await page.wait_for_timeout(800)
            await page.click('button:has-text("Create account")')
            await page.wait_for_timeout(9000)
            url = page.url
            print(f"After Create URL: {url}", file=sys.stderr)
            content = await page.content()
            if "email/verify" not in url and "verify" not in content.lower():
                print(f"Register failed, url={url} {content[:2000]}", file=sys.stderr)
                await page.screenshot(path="/tmp/zen_register_failed.png", full_page=True)
                await browser.close()
                cleanup_kernel(session_id)
                sys.exit(1)
            print(f"Registered {email} → email/verify, polling inbox...", file=sys.stderr)
            # Poll correct inbox: temp.tf for @gmail.com, dispose.lol for custom astroai.eu.cc
            is_gmail = email.lower().endswith("@gmail.com")
            if is_gmail:
                # Poll temp.tf directly (no browser needed)
                import urllib.request, json as _json2, re as _re, html as _html2, time as _time2
                link_re2 = _re.compile(r"https://[^\s]+zenrows\.com[^\s]+", _re.I)
                found = False
                for i in range(20):
                    try:
                        old_env2 = {k: __import__('os').environ.pop(k,None) for k in ("HTTPS_PROXY","HTTP_PROXY","https_proxy","http_proxy","ALL_PROXY","all_proxy")}
                        try:
                            data2=_json2.dumps({"email":email}).encode()
                            req2=urllib.request.Request("https://temp.tf/api/check", data=data2, headers={"Content-Type":"application/json"}, method="POST")
                            with urllib.request.urlopen(req2, timeout=10) as r2:
                                j2=_json2.loads(r2.read())
                                items2=j2.get("data",[])
                                print(f"Poll temp.tf {i}: {len(items2)} msgs", file=sys.stderr)
                                for msg2 in items2:
                                    body2=msg2.get("body","")
                                    subj2=msg2.get("subject","")
                                    m2=link_re2.search(subj2+" "+body2)
                                    if m2:
                                        # Save link for later use via page
                                        verify_url2=_html2.unescape(m2.group(0)).replace("&amp;","&")
                                        print(f"FOUND LINK via temp.tf {verify_url2[:200]}", file=sys.stderr)
                                        # Store in page for later
                                        await page.evaluate("(url) => { window.__verifyUrl = url; }", verify_url2)
                                        found = True
                                        break
                                if found:
                                    break
                        finally:
                            for k,v in old_env2.items():
                                if v is not None:
                                    __import__('os').environ[k]=v
                    except Exception as e:
                        print(f"Poll temp.tf err {e}", file=sys.stderr)
                    await page.wait_for_timeout(5000)
                    if i == 8 and not found:
                        print("No email after 8 polls, trying Resend...", file=sys.stderr)
                        await page.goto("https://app.zenrows.com/email/verify", wait_until="domcontentloaded", timeout=30000)
                        await page.wait_for_timeout(3000)
                        await page.evaluate("() => { const b=[...document.querySelectorAll('button')].find(x=>x.innerText.includes('Resend')); if(b) b.click(); }")
                        await page.wait_for_timeout(5000)
                        print("Resent", file=sys.stderr)
                # For Gmail, we already have verify_url via window.__verifyUrl, skip dispose polling
                if found and email.lower().endswith("@gmail.com"):
                    # Skip dispose polling, use the found link
                    pass
                else:
                    # For custom domain, poll dispose.lol via browser
                    await page.goto("https://dispose.lol", wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_timeout(4000)
                    for i in range(20):
                        body = await page.evaluate("() => document.body.innerText")
                        if "verify@e.zenrows.com" in body or "Verify your email to activate" in body:
                            await page.evaluate("() => { const b=[...document.querySelectorAll('button')].find(x=>x.getAttribute('aria-label')?.includes('Verify your email')); if(b) b.click(); }")
                            await page.wait_for_timeout(3000)
                            found = True
                            break
                        await page.evaluate("() => { const r=[...document.querySelectorAll('button')].find(x=>x.innerText.includes('Refresh')); if(r) r.click(); }")
                        await page.wait_for_timeout(3000)
                        print(f"Poll dispose {i} waiting...", file=sys.stderr)
                        if i == 8 and not found:
                            print("No email after 8 polls, trying Resend...", file=sys.stderr)
                            await page.goto("https://app.zenrows.com/email/verify", wait_until="domcontentloaded", timeout=30000)
                            await page.wait_for_timeout(3000)
                            await page.evaluate("() => { const b=[...document.querySelectorAll('button')].find(x=>x.innerText.includes('Resend')); if(b) b.click(); }")
                            await page.wait_for_timeout(5000)
                            print("Resent, back to dispose", file=sys.stderr)
                            await page.goto("https://dispose.lol", wait_until="domcontentloaded", timeout=30000)
                            await page.wait_for_timeout(4000)
            if not found:
                print("No verification email after 20 polls", file=sys.stderr)
                await page.screenshot(path="/tmp/zen_no_email.png", full_page=True)
                await browser.close()
                cleanup_kernel(session_id)
                sys.exit(1)

            # For Gmail via temp.tf, verify_url already in window.__verifyUrl
            verify_url = await page.evaluate("() => window.__verifyUrl || ''")
            if verify_url:
                print(f"Using window.__verifyUrl {verify_url[:80]}", file=sys.stderr)
                verify_links = []
            else:
                # Try iframe srcdoc first, then fallback to direct link in dispose UI
                srcdoc = await page.evaluate("() => document.querySelector('iframe')?.getAttribute('srcdoc') || ''")
                verify_links = []
                if srcdoc:
                    verify_links = await page.evaluate("""(sd) => {
                    const p = new DOMParser();
                    const d = p.parseFromString(sd, "text/html");
                    return Array.from(d.querySelectorAll("a")).map(a=> ({ href: a.getAttribute("href"), text: (a.innerText||"").trim() }));
                }""", srcdoc)
                print(f"Links in srcdoc: {verify_links}", file=sys.stderr)
            if not verify_links:
                # Fallback: look for Verification link directly in dispose UI
                verify_links = await page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('a')).map(a=> ({ href: a.getAttribute('href') || a.href, text: (a.innerText||"").trim() })).filter(x=>x.href && (x.href.includes('zenrows') || x.href.includes('url4722') || x.text.includes('Verification')));
                }""")
                print(f"Links in dispose UI: {verify_links}", file=sys.stderr)
                # Also try to find the Verify email button's link
                btn_link = await page.evaluate("""() => {
                    const btn=[...document.querySelectorAll('a','button')].find(b=>b.innerText && b.innerText.includes('Verify email'));
                    if(btn && btn.href) return btn.href;
                    const a=[...document.querySelectorAll('a')].find(x=>x.innerText.includes('Verification link'));
                    return a ? (a.href || a.getAttribute('href')) : '';
                }""")
                if btn_link and "http" in btn_link:
                    verify_links.append({"href": btn_link, "text": "Verify email"})
            if not verify_url:
                verify_url = None
            for link in verify_links:
                if link["text"] == "Verify email" or "Verify" in link["text"]:
                    if link["href"] and ("url4722" in link["href"] or "zenrows" in link["href"]):
                        verify_url = link["href"]
                        break
            if not verify_url:
                for link in verify_links:
                    if link["href"] and ("url4722" in link["href"] or "zenrows" in link["href"]):
                        verify_url = link["href"]
                        break
            if not verify_url:
                # Last resort: click the Verify email button directly
                print(f"No verify_url found, trying to click Verify email button", file=sys.stderr)
                clicked = await page.evaluate("""() => {
                    const btn=[...document.querySelectorAll('button')].find(b=>b.innerText.includes('Verify email'));
                    if(btn){ btn.click(); return 'clicked button'; }
                    const a=[...document.querySelectorAll('a')].find(x=>x.innerText.includes('Verify email'));
                    if(a){ a.click(); return 'clicked a '+a.href.slice(0,80); }
                    return 'not found';
                }""")
                print(f"Click result {clicked}", file=sys.stderr)
                await page.wait_for_timeout(4000)
                # Check if navigated to verification
                if "zenrows" in page.url and "verify" in page.url:
                    verify_url = page.url
                    print(f"Got verify_url via click: {verify_url[:120]}", file=sys.stderr)
                else:
                    print(f"No verify_url found links={verify_links}", file=sys.stderr)
                    await browser.close()
                    cleanup_kernel(session_id)
                    sys.exit(1)
            print(f"VERIFY_URL: {verify_url[:120]}...", file=sys.stderr)

            await page.goto(verify_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(8000)
            url = page.url
            print(f"After verify URL: {url}", file=sys.stderr)
            if "overview" not in url:
                print(f"Not overview, trying alternative verification link", file=sys.stderr)
                alt = None
                for link in verify_links:
                    if link["href"] != verify_url and "url4722" in (link["href"] or ""):
                        alt = link["href"]
                        break
                if alt:
                    print(f"ALT {alt[:120]}", file=sys.stderr)
                    await page.goto(alt, wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_timeout(8000)
                    url = page.url
                    print(f"After alt URL: {url}", file=sys.stderr)

            if "app.zenrows.com/overview" not in url and "overview" not in url:
                await page.goto("https://app.zenrows.com/overview", wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(5000)
                url = page.url
                print(f"After overview goto URL: {url}", file=sys.stderr)

            content = await page.content()
            body_text = await page.evaluate("() => document.body.innerText")
            m = re.search(r"zenrows login --api-key ([a-f0-9]{32,})", content) or re.search(r"zenrows login --api-key ([a-f0-9]{32,})", body_text) or re.search(r"[a-f0-9]{32,}", content)
            if not m:
                print(f"No API key found at {url} body={body_text[:2000]}", file=sys.stderr)
                await page.screenshot(path="/tmp/zen_no_apikey.png", full_page=True)
                await browser.close()
                cleanup_kernel(session_id)
                sys.exit(1)
            api_key = m.group(1) if m.groups() else m.group(0)
            print(f"SUCCESS {email} / {password} / {api_key} → {url}", file=sys.stderr)
            result = {"email": email, "password": password, "api_key": api_key, "url": url, "live_url": live_url, "session_id": session_id}
            print(json.dumps(result, indent=2))
            with open("/tmp/zen_kernel_account.txt","w") as f:
                f.write(f"EMAIL={email}\nPASSWORD={password}\nAPI_KEY={api_key}\nURL={url}\nLIVE={live_url}\nSID={session_id}\n")
            await page.screenshot(path="/tmp/zen_verified.png", full_page=True)
            print(f"Saved /tmp/zen_kernel_account.txt and /tmp/zen_verified.png", file=sys.stderr)
            await browser.close()
            cleanup_kernel(session_id)
            return result
    except SystemExit:
        # already cleaned, re-raise
        raise
    except Exception as e:
        print(f"run_once exception {e}", file=sys.stderr)
        import traceback; traceback.print_exc()
        try:
            if browser:
                await browser.close()
        except: pass
        cleanup_kernel(session_id)
        raise

async def main():
    for attempt in range(5):
        try:
            result = await run_once()
            print(f"SUCCESS on attempt {attempt+1}", file=sys.stderr)
            return
        except SystemExit as e:
            if e.code != 0:
                print(f"Attempt {attempt+1} failed with exit {e.code}, retrying with fresh browser...", file=sys.stderr)
                await asyncio.sleep(5)
                continue
            else:
                return
        except Exception as e:
            print(f"Attempt {attempt+1} exception {e}, retrying...", file=sys.stderr)
            await asyncio.sleep(5)
            continue
    print("All 5 attempts failed", file=sys.stderr)
    sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())