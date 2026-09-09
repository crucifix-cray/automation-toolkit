# Game Warp Isolation Study

**Game:** `script2` 3-mode heavy - only this game, separated  
**Date:** 2026-08-21  
**Branch:** `fix/script2-3mode`

---

## What We Are Playing

Make `script2` perfect without breaking other apps - only browser tunnels via WARP, system stays direct.

---

## Warp Setup For Game

**Before:** `wg-quick up wgcf` system-wide → all apps `warp=on` → `api.lovable.dev` fails `ERR_SOCKS_CONNECTION_FAILED` → `Target folder` pulse forever.

**Now:** `warp-cli mode proxy` `WarProxy on port 40000` isolated.

```bash
warp-cli status # Connected
warp-cli settings | grep Mode # (user set) Mode: WarpProxy on port 40000
ss -tlnp | grep 40000 # LISTEN 127.0.0.1:40000
warp-svc pid 594
```

**Proxy for browser only:**
```python
proxy = {"server": "socks5://127.0.0.1:40000", "bypass": "api.tempmailhub.org,api.lovable.dev,127.0.0.1,localhost"}
# InvisiblePlaywright(headless, proxy=proxy)
# page.set_viewport_size({1440,900})
```

**Bypass fixes white-screen:** `api.lovable.dev` was in `bypass` per `WARP_PROXY.md:73` + `ARCHITECTURE.md:32` - without it `Failed to fetch (api.lovable.dev) vendor-sentry` loops.

---

## Verification - Isolated

```bash
# Browser via proxy
curl -s --socks5 127.0.0.1:40000 https://cloudflare.com/cdn-cgi/trace | grep -E "warp=|ip="
# ip=2a09:bac1:46a0:28::6b:84 warp=on colo=LIS

# Direct (system, other apps)
curl -s https://cloudflare.com/cdn-cgi/trace | grep -E "warp=|ip="
# ip=201.3.225.28 warp=off colo=WAW

# In browser (playwright)
await page.goto("https://cloudflare.com/cdn-cgi/trace") # warp=on
# vs outside browser warp=off
```

**Browser test:** `warp_session_fixed2` session 19 `Home | Lovable` `✅ no ERR_SOCKS - bypass works` `warp=on` isolated.

**Script2 test:** `log: Using warp proxy 127.0.0.1:40000 for browser (isolated, bypass api.lovable.dev/api.tempmailhub.org)` → `Found 35 templates` → `Menu dropdown visible` → `Dialog appeared` → `Target folder loaded`.

---

## Credentials For Warp Game

- **WARP:** `socks5://127.0.0.1:40000` `warp-cli` `cloudflare-warp-bin`
- **Railway VPN acc:** `g.runsts.wain36+jywh3i0b@gmail.com` token `[REDACTED-RAILWAY-TOKEN - see railway-token.txt]` sandbox `6d37bdd4` project `ubuntu-sbx` egress `152.55.177.190` split `tun0`
- **Lovable sessions:** `session-19 Josephgrant651@gmail.com` / `session-21 mariepeterson749@gmail.com` (52 cookies, `active`)
- **Git:** `crucifix-cray` token `[REDACTED-GH-TOKEN - see local]` branch `fix/script2-3mode`

---

## How To Keep Isolated

- Never `wg-quick up` system-wide - use `warp-cli proxy` only.
- Never `stop_warp` disconnect in proxy mode - keep alive (`stop_warp` now no-op if proxy alive).
- All `rclone` via `env -u HTTP_PROXY` (Tor `127.0.0.1:9251` breaks it).
- Browser `bypass` must include `api.lovable.dev` - else `ERR_SOCKS` returns.

```bash
# keep browser with session until kill
setsid xvfb-run -a python3 -u /tmp/warp_session_fixed2.py >> /tmp/warp_session_fixed2.log 2>&1 & disown
# kill
pkill -f warp_session_fixed2
```
