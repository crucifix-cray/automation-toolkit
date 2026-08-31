# Architecture — BD Browser Stream

## How It Works

### Server (`bd_stream.py`)

**Startup flow:**
1. Connect to BD Browser API via Playwright CDP (`connect_over_cdp`)
2. Open first page, navigate to `ipify.org` to get current IP
3. Start threaded HTTP server on `:8888`
4. Enter screenshot loop — poll page every 100ms, serve JPEG

**Command queue:**
- HTTP POST endpoints (`/click`, `/type`, `/key`, `/goto`, `/scroll`) push to a `queue.Queue`
- Main async loop drains queue and executes commands via Playwright
- After each command: immediate screenshot capture + URL/title update

**Screenshot streaming:**
- `page.screenshot(type="jpeg", quality=40)` — compressed for speed
- Served at `/screenshot` endpoint, no-cache headers
- Client polls at ~10fps via XMLHttpRequest blob loading

**Cross-domain navigation:**
- BD Browser API has `navigate_domains_limit` (1 domain per session)
- When domain changes → close old browser → open fresh BD session → navigate
- New session = new `?sessionId` = new residential IP (~3-5s reconnect)

**Reconnect on death:**
- If screenshot fails → call `reconnect(url)` with fresh BD session
- Crash guard: `while True: try: asyncio.run(main())` restarts on any unhandled exception

### Client (`bd_stream.html`)

**Canvas rendering:**
- `<canvas>` element, `createImageBitmap(blob)` for fast rendering
- `ctx.drawImage(bmp)` — no img tag src swapping (avoids event listener destruction)
- `bmp.close()` — explicit memory cleanup

**Click handling:**
- `mousedown` event on canvas (not `click` — faster, no double-click ambiguity)
- `toRemote(e)` — maps client coordinates to remote viewport coordinates
  - Uses `cv.getBoundingClientRect()` for canvas position
  - `sx = cv.width / rect.width` — scale factor from CSS to actual pixels
  - Clamps to viewport bounds

**Keyboard forwarding:**
- `keydown` on `document` (not on canvas — captures globally)
- Skipped when URL bar is focused (`urlFocused` state)
- Special keys mapped: Enter, Backspace, Tab, Escape, arrows, Space, Delete, Home, End
- Single chars → `post('/type', {text})` → `page.keyboard.type(text, delay=30)`
- Multi-char keys → `post('/key', {key})` → `page.keyboard.press(key)`

**Scroll forwarding:**
- `wheel` event on `wrap` div
- `deltaY` sent to `/scroll` → `page.mouse.wheel(0, dy)`
- `{passive: false}` — allows `preventDefault()`

**URL bar:**
- Enter key → `go()` function
- Sets `paused = true` for 5s (prevents status poll from overwriting URL bar during nav)
- `post('/goto', {url})` → server handles cross-domain detection

**Status polling:**
- Every 2s, fetch `/status` → update info text + URL bar (if not focused)
- Includes IP, page title, URL

## Coordinate Mapping

```
Remote viewport:  1280 x 720 (set at BD session creation)
CSS canvas:       fills #wrap div (responsive)
Click mapping:    clientX → canvas pixel = (clientX - rect.left) * (cv.width / rect.width)
                  clamp to [0, viewport.w] x [0, viewport.h]
```

## Session Management

```
BD WSS URL: wss://brd-customer-hl_{API_KEY}-zone-scraping_browser1:{TOKEN}@brd.superproxy.io:9222
                 ↓
         ?sessionId={random12}    ← fresh IP per session
                 ↓
     Playwright connect_over_cdp()
                 ↓
     browser.contexts[0].pages[0] ← use existing page if available
```

## systemd Service

```
~/.config/systemd/user/bdstream.service
```

- `ALL_PROXY=` — bypasses Tor proxy (system-wide proxy would break CDP WebSocket)
- `Restart=on-failure` + `RestartSec=3s` — auto-restart on crash
- `KillMode=process` — clean kill
- `WorkingDirectory=/home/alae/Documents/repos/automation-toolkit/railway-docker`
