#!/usr/bin/env python3
"""Lovable 5x via ZenRows GB fresh browser each run — 6202c709..."""
import asyncio, os, json, uuid, urllib.request
ZENROWS_WSS = "wss://browser.zenrows.com?apikey=6202c7099ecb4ce32fadb8f0afddc298630eb583&proxy_country=gb"
TEMP_TF_API = "https://temp.tf/api"
def clear_proxy():
    for k in list(os.environ):
        if k.lower().endswith('_proxy') or k=='LD_PRELOAD':
            os.environ.pop(k,None)
clear_proxy()

async def get_email():
    import urllib.request, json
    for k in list(os.environ):
        if k.lower().endswith('_proxy'):
            os.environ.pop(k,None)
    with urllib.request.urlopen(TEMP_TF_API+"/account?dot=1&providers=gmail", timeout=10) as r:
        j=json.loads(r.read())
        return j['email']

async def one_run(run_idx):
    # Fresh browser per run = fresh IP via new connect (ZenRows rotates IP per new browser)
    wss = ZENROWS_WSS
    email = await get_email()
    password = email + "K01"
    print(f"\n=== Run {run_idx} {email} ===", flush=True)
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(wss, timeout=30000)
        # Fresh browser = new context + new page
        ctx = await browser.new_context()
        page = await ctx.new_page()
        # IP
        try:
            ip = await page.evaluate("async () => { try{ const r=await fetch('https://wtfismyip.com/json'); const j=await r.json(); return j.YourFuckingIPAddress+' '+j.YourFuckingISP }catch(e){ return 'fail' } }")
            print(f"Run {run_idx} IP {ip}", flush=True)
        except: pass
        for attempt in range(3):
            try:
                await page.goto("https://lovable.dev/signup", timeout=40000, wait_until="domcontentloaded")
                break
            except Exception as e:
                print(f"Run {run_idx} goto retry {attempt} {e}", flush=True)
                await page.wait_for_timeout(2000)
        else:
            print(f"Run {run_idx} goto failed", flush=True)
            await browser.close()
            return False
        await page.wait_for_timeout(4000)
        await page.locator('input#email').fill(email)
        await page.locator('[data-testid="auth-submit-button"]').click()
        await page.wait_for_timeout(4000)
        await page.locator('input#password').fill(password)
        print(f"Run {run_idx} fill ok", flush=True)
        for i in range(12):
            token = await page.evaluate("() => document.querySelector('input[name=\"cf-turnstile-response\"]')?.value?.length || 0")
            if token>100:
                print(f"Run {run_idx} Token {token} i {i}", flush=True)
                break
            if i==2:
                await page.evaluate("() => { try{ window.turnstile && window.turnstile.execute && window.turnstile.execute(); }catch(e){} }")
            await page.wait_for_timeout(1000)
        else:
            print(f"Run {run_idx} no token", flush=True)
        btn = page.locator('[data-testid="auth-submit-button"]')
        disabled = await btn.is_disabled()
        print(f"Run {run_idx} Create disabled {disabled}", flush=True)
        await page.screenshot(path=f"/tmp/zen5_run{run_idx}_before.png", full_page=True)
        if not disabled:
            await btn.click()
            await page.wait_for_timeout(8000)
            txt = await page.evaluate("() => document.body.innerText.slice(0,3000)")
            url = page.url
            print(f"Run {run_idx} URL {url}", flush=True)
            if "Check your inbox" in txt:
                print(f"Run {run_idx} SUCCESS", flush=True)
                # Poll dispose for link via same page
                # Use temp.tf poll
                import urllib.request, json, re, html, time
                link_re = re.compile(r"https?://[^\s\"'<>]*lovable\.dev[^\s\"'<>]*", re.I)
                for attempt in range(12):
                    try:
                        old_env = {k: os.environ.pop(k,None) for k in ("HTTPS_PROXY","HTTP_PROXY","https_proxy","http_proxy","ALL_PROXY","all_proxy")}
                        try:
                            data=json.dumps({"email":email}).encode()
                            req=urllib.request.Request(TEMP_TF_API+"/check", data=data, headers={"Content-Type":"application/json"}, method="POST")
                            with urllib.request.urlopen(req, timeout=10) as r:
                                j=json.loads(r.read())
                                for msg in j.get("data",[]):
                                    body=msg.get("body","")
                                    subj=msg.get("subject","")
                                    m=link_re.search(subj+" "+body)
                                    if m:
                                        link=html.unescape(m.group(0)).replace("&amp;","&")
                                        print(f"Run {run_idx} LINK {link[:300]}", flush=True)
                                        await page.goto(link, timeout=20000)
                                        await page.wait_for_timeout(4000)
                                        print(f"Run {run_idx} Verified {page.url}", flush=True)
                                        with open(f"/tmp/zen5_run{run_idx}_account.txt","w") as f:
                                            f.write(f"{email}\n{password}\n{link}\n{ip}\n")
                                        await browser.close()
                                        return True
                        finally:
                            for k,v in old_env.items():
                                if v is not None:
                                    os.environ[k]=v
                    except Exception as e:
                        print(f"Run {run_idx} poll err {e}", flush=True)
                    await asyncio.sleep(5)
                print(f"Run {run_idx} no link", flush=True)
            elif "suspicious" in txt.lower():
                print(f"Run {run_idx} BLOCKED suspicious", flush=True)
            else:
                print(f"Run {run_idx} unknown {txt[:500]}", flush=True)
        await page.screenshot(path=f"/tmp/zen5_run{run_idx}_after.png", full_page=True)
        await browser.close()
        return False

async def main():
    for i in range(1,6):
        ok = await one_run(i)
        print(f"Run {i} result {ok}", flush=True)
        # Credit check via ZenRows dashboard would be here, but we log IP instead
        await asyncio.sleep(1)
    print("All 5 done", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
