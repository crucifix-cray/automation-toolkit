#!/usr/bin/env python3
"""BD Browser API → Local Interactive Stream. http://127.0.0.1:8888"""
import asyncio, json, os, queue, sys, time, uuid
from playwright.async_api import async_playwright
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from threading import Thread
from urllib.parse import urlparse

BRD_WSS = os.environ.get("BRD_WSS",
    "wss://brd-customer-hl_7357e514-zone-scraping_browser1:vuln37v8nbfh@brd.superproxy.io:9222")
PORT = int(os.environ.get("PORT", "8888"))

_HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bd_stream.html")
with open(_HTML_PATH) as f:
    HTML = f.read()

S = {"pw": None, "browser": None, "page": None, "ctx": None,
     "screenshot": b"", "ip": "", "url": "", "title": "",
     "width": 1280, "height": 720, "ready": False, "cmds": queue.Queue()}

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class H(StreamHandler if False else SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200); self.send_header("Content-Type","text/html"); self.end_headers()
            self.wfile.write(HTML.encode())
        elif self.path.startswith("/screenshot"):
            self.send_response(200); self.send_header("Content-Type","image/jpeg")
            self.send_header("Cache-Control","no-cache"); self.end_headers()
            self.wfile.write(S["screenshot"])
        elif self.path.startswith("/status"):
            self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers()
            self.wfile.write(json.dumps({"ip":S["ip"],"url":S["url"],"title":S["title"],
                "ready":S["ready"],"width":S["width"],"height":S["height"]}).encode())
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        cl = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(cl) if cl else b""
        d = json.loads(body) if body else {}
        routes = {
            "/click": lambda: S["cmds"].put(("click", d.get("x",0), d.get("y",0))),
            "/type": lambda: S["cmds"].put(("type", d.get("text",""))),
            "/key": lambda: S["cmds"].put(("key", d.get("key",""))),
            "/goto": lambda: S["cmds"].put(("goto", d.get("url",""))),
            "/scroll": lambda: S["cmds"].put(("scroll", d.get("dy",0))),
        }
        action = routes.get(self.path)
        if action: action()
        self.send_response(200); self.end_headers()

    def log_message(self, *a): pass

async def reconnect(url):
    """Close old browser, open fresh BD session, navigate to url."""
    S["page"] = None
    try:
        if S["browser"]: await S["browser"].close()
    except: pass

    sid = str(uuid.uuid4())[:12]
    wss = BRD_WSS.split("?")[0] + f"?sessionId={sid}"
    print(f"[*] New session → {url} (sid={sid})", flush=True)

    browser = await S["pw"].chromium.connect_over_cdp(wss)
    ctx = browser.contexts[0] if browser.contexts else await browser.new_context(
        viewport={"width": S["width"], "height": S["height"]})
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    S["browser"], S["page"], S["ctx"] = browser, page, ctx

    try:
        await page.goto(url, wait_until="commit", timeout=20000)
        S["url"] = page.url
        S["title"] = await page.title()
        print(f"[+] Opened: {page.url}", flush=True)
    except Exception as e:
        print(f"[-] {e}", flush=True)
        S["url"] = url

async def run_cmd(cmd):
    p = S["page"]
    if not p: return
    try:
        if cmd[0] == "click":
            await p.mouse.click(cmd[1], cmd[2])
        elif cmd[0] == "type":
            await p.keyboard.type(cmd[1], delay=30)
        elif cmd[0] == "key":
            await p.keyboard.press(cmd[1])
        elif cmd[0] == "scroll":
            await p.mouse.wheel(0, cmd[1])
        elif cmd[0] == "goto":
            url = cmd[1].strip()
            if not url.startswith("http") and not url.startswith("about:"): url = "https://" + url
            new_domain = urlparse(url).netloc
            cur_domain = urlparse(S.get("url","")).netloc
            S["url"] = url
            if new_domain and new_domain != cur_domain:
                await reconnect(url)
            else:
                await p.goto(url, wait_until="commit", timeout=20000)
                S["url"] = p.url
                S["title"] = await p.title()
    except Exception as e:
        print(f"[-] {cmd[0]}: {e}", flush=True)

async def main():
    async with async_playwright() as pw:
        S["pw"] = pw
        try:
            browser = await pw.chromium.connect_over_cdp(BRD_WSS)
            print(f"[+] CDP connected", flush=True)
        except Exception as e:
            print(f"[-] CDP connect failed: {e}", flush=True)
            return
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context(
            viewport={"width": S["width"], "height": S["height"]})
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        S["browser"], S["page"], S["ctx"] = browser, page, ctx

        try:
            await page.goto("https://api.ipify.org?format=json", wait_until="commit", timeout=15000)
            S["ip"] = json.loads(await page.inner_text("body"))["ip"]
        except Exception as e:
            print(f"[-] ipify failed: {e}", flush=True)
            S["ip"] = "unknown"
        S["url"] = page.url
        S["ready"] = True

        try:
            srv = ThreadedHTTPServer(("0.0.0.0", PORT), H)
            t = Thread(target=srv.serve_forever, daemon=False)
            t.start()
            print(f"[+] HTTP server started on :{PORT}", flush=True)
        except Exception as e:
            print(f"[-] HTTP server failed: {e}", flush=True)

        print(f"\n{'='*55}\n  BD BROWSER STREAM LIVE\n{'='*55}")
        print(f"  IP:  {S['ip']}\n  URL: http://127.0.0.1:{PORT}\n{'='*55}\n", flush=True)

        url = S["url"] or "https://railway.com"
        while True:
            while not S["cmds"].empty():
                try:
                    await run_cmd(S["cmds"].get_nowait())
                except: break
                # take immediate screenshot after command
                if S["page"]:
                    try:
                        S["screenshot"] = await S["page"].screenshot(type="jpeg", quality=40)
                        S["url"] = S["page"].url
                        S["title"] = await S["page"].title()
                    except: pass
            if S["page"]:
                try:
                    S["screenshot"] = await S["page"].screenshot(type="jpeg", quality=40)
                    S["url"] = S["page"].url
                    S["title"] = await S["page"].title()
                except Exception as e:
                    print(f"[-] screenshot died: {e}, reconnecting...", flush=True)
                    try: await reconnect(url)
                    except Exception as e2:
                        print(f"[-] reconnect failed: {e2}", flush=True)
                        await asyncio.sleep(2)
            else:
                S["screenshot"] = b""
            await asyncio.sleep(0.1)

if __name__ == "__main__":
    while True:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[!] CRASH: {e}, restarting in 3s...", flush=True)
            time.sleep(3)
