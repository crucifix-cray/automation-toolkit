# WARP Proxy Setup

> ⚠️ **OUTDATED BELOW (pre-2026-08-24).** The "SOCKS4 for API" note is wrong: the
> TempMailHub API host (`api.tempmailhub.org`) is **IPv6-only** and is reachable **only via
> Tor** (`127.0.0.1:9050` / `9251`), not via WARP at all. The current architecture is a
> `warp-1` netns with microsocks at `10.200.1.2:40001` (see "Current reality" at the bottom).
> Also: WARP egress IPs are **Cloudflare-flagged** → Lovable signup button stays disabled; use
> ProtonVPN egress (netns `default dev tun0`) instead. See `opencode backups/SESSION.md`.

The browser automation routes its traffic through Cloudflare WARP as a SOCKS proxy so requests egress from a Cloudflare WARP IP **without affecting your system's network**.

## CRITICAL: SOCKS4 vs SOCKS5

**Use SOCKS4 for TempMail API compatibility:**

```python
WARP_PROXY = "socks4://127.0.0.1:40000"  # ✅ Works
# NOT: "socks5://127.0.0.1:40000"        # ❌ Blocks api.tempmailhub.org
```

**Why SOCKS4?**
- WARP SOCKS5 returns error code 4 (host unreachable) for `api.tempmailhub.org`
- WARP SOCKS4 works perfectly for the same endpoint
- Both work for browser automation
- Deep diagnosis confirmed SOCKS5 specifically blocks TempMail API

**Test command:**
```bash
# SOCKS5 - FAILS
curl --proxy socks5://127.0.0.1:40000 -X POST https://api.tempmailhub.org/emails \
  -H "Content-Type: application/json" -d '{}'
# Error: (97) cannot complete SOCKS5 connection. (4)

# SOCKS4 - WORKS
curl --proxy socks4://127.0.0.1:40000 -X POST https://api.tempmailhub.org/emails \
  -H "Content-Type: application/json" -d '{}'
# Response: {"email":"example@gmail.com","email_id":39}
```

## Installation (Arch Linux)

```bash
yay -S cloudflare-warp-bin
```

For other distributions, see [official documentation](https://developers.cloudflare.com/warp-client/get-started/linux/).

## Configuration (Proxy Mode - Browser Only)

**IMPORTANT**: This setup uses WARP in **proxy mode**, which only affects applications configured to use it (like our browser script). Your system's network remains unaffected.

```bash
# 1. Register the client
warp-cli registration new

# 2. Set to proxy mode (this is KEY - only affects apps using the proxy)
warp-cli mode proxy

# 3. Set the proxy port
warp-cli proxy port 40000

# 4. (Optional) Add WARP+ license for better performance
warp-cli registration license <your-license-key>

# 5. Connect
warp-cli connect

# 6. Verify it's running
warp-cli status
```

**Note:** The proxy runs as **SOCKS5** server, but we use **SOCKS4** protocol for API calls (see above).

## Dual Proxy Strategy

**Best practice:** Use WARP for browser, direct connection for API:

```python
# Browser - use WARP SOCKS4
proxy_settings = {
    "server": "socks4://127.0.0.1:40000",
    "bypass": "22.do,127.0.0.1,localhost"
}

# API - bypass proxy entirely
no_proxy_handler = urllib.request.ProxyHandler({})
opener = urllib.request.build_opener(no_proxy_handler)
urllib.request.install_opener(opener)
```

This gives:
- ✅ Browser uses WARP IP (for rate limit evasion)
- ✅ API uses direct connection (for reliability)
- ✅ No proxy compatibility issues

## How the proxy is wired

- WARP runs as a SOCKS5 proxy on `127.0.0.1:40000` (only affects configured apps).
- Your system network is NOT affected - only the browser uses WARP.
- The Playwright browser context gets:
  `{"server": "socks5://127.0.0.1:40000"}`
- Cookie loading happens before navigation to preserve sessions.

## IP Rotation

To get a new IP address between account creations:

```bash
warp-cli disconnect && sleep 2 && warp-cli connect && sleep 3
```

The script automatically does this after each successful account creation.

## Why the bypass list exists

Some HTTPS API backends fail through the WARP route:

- `api.tempmailhub.org` – **CRITICAL:** SOCKS5 blocked (error 4), SOCKS4 works but unstable. 
  **Solution:** Use direct connection (bypass proxy) for API calls.
- `api.lovable.dev` – caused the **white screen** bug: Lovable's SPA
  crashed on `Failed to fetch consent policy` / `Error checking auth
  provider` because its own API was unreachable through WARP.

**Current strategy:** Bypass WARP entirely for API calls, use only for browser.

Everything else keeps the WARP IP. `127.0.0.1`/`localhost` are always
bypassed so local callback servers (Railway OAuth) work.

## Verifying the egress

Check your IP through WARP:

```bash
# SOCKS5 protocol (default)
curl -x socks5://127.0.0.1:40000 https://www.cloudflare.com/cdn-cgi/trace

# SOCKS4 protocol (for TempMail compatibility)
curl -x socks4://127.0.0.1:40000 https://www.cloudflare.com/cdn-cgi/trace
```

Expected output:
```
ip=2a09:bac1:...:3b6:46
warp=on
colo=MRS
```

- `warp=on` – traffic is going through WARP
- `ip=2a09:...` – WARP IPv6 address (healthy)

## Cookie Loading

The script loads cookies from `/home/alae/Downloads/tu-cookies.txt` (Netscape format) before starting:

1. WARP connects
2. Cookies load into browser context
3. Browser navigates to TempMail
4. Session is preserved across account creations

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `warp-cli: command not found` | Install cloudflare-warp-bin package |
| `ERR_SOCKS_CONNECTION_FAILED` | WARP not connected - run `warp-cli connect` |
| System network affected | You're using wgcf/system-wide mode - switch to `warp-cli mode proxy` |
| IP not rotating | Check `warp-cli status` shows Connected, then disconnect/reconnect |
| Cookie file not found | Place cookies in `/home/alae/Downloads/tu-cookies.txt` |
| `curl: (97) error code 4` | Using SOCKS5 for blocked endpoint - switch to SOCKS4 or direct |
| TempMail API timeout | Use direct connection (bypass proxy) instead of WARP |
| API returns 0 bytes | Mailbox died or WARP unstable - use direct connection for monitoring |

## Performance Comparison

| Connection | TempMail Create | TempMail Check | Notes |
|-----------|----------------|----------------|-------|
| Direct | 0.5s | 4-30s | ✅ Most reliable |
| WARP SOCKS4 | 1.0s | Unstable | ⚠️ Use for creation only |
| WARP SOCKS5 | ❌ Blocked | ❌ Blocked | Don't use with TempMail |
| TOR | 1.4s | 10-40s | ⚠️ Slow but works |

**Recommendation:** Use WARP for browser, direct for API.

---

## Current reality (2026-08-24 session)

The setup above (`warp-cli mode proxy` on `127.0.0.1:40000`) no longer matches the running
architecture. What is actually deployed now:

### Netns `warp-1` chain (no `warp-cli`)
- veth pair `10.200.1.1` (host) ⇄ `10.200.1.2` (netns `warp-1`); host NATs `10.200.1.0/30`
  out `wlan0`.
- Inside netns: `openvpn` → ProtonVPN NL (`tun0`, egress e.g. `41.92.x` / `169.150.x`); then a
  **real kernel `wg0`** WARP interface (profile from `/home/alan/Documents/mega_dumps/chimera/wgcf-pool/`,
  endpoint `162.159.192.1:2408`, route `162.159.192.1/32 via 10.96.0.1 dev tun0`, `default dev wg0`).
- `microsocks -i 10.200.1.2 -p 40001` runs **inside** the netns. Host reaches it directly at
  `10.200.1.2:40001` — **do NOT put socat in front of it**: the `socat 127.0.0.1:40000 →
  10.200.1.2:40001` hop works for `curl` but **stalls Firefox's SOCKS stream** (button/timeout).
- Rebuild script: `opencode backups/rebuild_warp_chain.sh`.

### Proxy routing in `lov-api.py` (commit `e787d13`)
- **API (TempMailHub):** Tor only — `[9050, 9251]`. Host is IPv6-only-reachable solely via Tor.
  (The old "SOCKS4 for API" advice is obsolete; WARP cannot reach the API at all.)
- **Browser:** currently forced **direct** in `proxy_settings(for_api=False)` because WARP egress
  is Cloudflare-flagged (Lovable "Create your account" button disabled). On this Tor-wrapped host
  "direct" = Tor, so the real unflagged path is to point the browser at `10.200.1.2:40001` with the
  netns default route set to `dev tun0` (ProtonVPN egress), not `dev wg0` (WARP). Flip the browser
  candidate back to the netns IP when using ProtonVPN egress.

### Required out-of-repo patch
`invisible_core/_geo.py` must use `socks5` (not `socks5h`) and cloudflare/ipify echo endpoints,
or the browser launch's egress-discovery hangs. Details in `opencode backups/SESSION.md` §4.

---

## Persistent Railway Sandbox approach (2026-08-24, session with Alan)

### Key finding: Browser must go DIRECT for22.do + Turnstile
- **WARP blocks22.do**: Cloudflare 403 from `104.28.219.140` (all wgcf profiles give same AMS colo)
- **Turnstile fails through WARP SOCKS5**: `challenges.cloudflare.com` unreachable; Chromium's
  SOCKS5 handling stalls the TLS handshake
- **22.do works direct** from sandbox IP (`152.55.184.157`)
- **Solution**: `proxy_settings = None` (browser goes direct) + mail.tm API as email fallback

### Fallback chain (22.do → dispose.lol → mail.tm)
When 22.do is unreachable or blocked:
1. **22.do** (browser-based, primary) — works direct, blocked via WARP
2. **dispose.lol** (browser-based, fallback) — sometimes returns `ERR_CONNECTION_CLOSED` through WARP
3. **mail.tm API** (no browser, last resort) — works through any proxy, API-based email creation

### Gost HTTP proxy (SOCKS5 → HTTP conversion for Chromium)
Chromium has broken SOCKS5 handling in Playwright. Solution: use `gost` to convert:
```bash
# Install gost
curl -sL https://github.com/ginuerzh/gost/releases/download/v2.12.0/gost_2.12.0_linux_amd64.tar.gz | tar xz -C /usr/local/bin/

# Run: HTTP proxy on 40001 forwarding to WARP SOCKS5 on 40000
gost -L http://127.0.0.1:40001 -F socks5://127.0.0.1:40000

# Browser proxy setting
proxy_settings = {"server": "http://127.0.0.1:40001"}
```
This works with curl but **still times out with Playwright/patchright** — unverified.

### WARP on persistent sandbox (no systemd)
- `warp-cli 2026.6.880.0` installed but daemon won't start (no systemd in container)
- **wireproxy** works: `wireproxy -c /tmp/warp.conf` → SOCKS5 on 40000, WARP IP `104.28.219.140`
- WARP IP is **always the same** regardless of wgcf profile (colocation determined at registration)
- ProtonVPN OVPN tunsocks chain works but not needed for browser (direct is better for 22.do)

### Railway SSH access
```bash
railway ssh -s "Ubuntu 24.04" "command"  # uses jzw2 key
```
Persistent sandbox service: `d1970e69` on project `test-ubuntu-6` (`2e7ef06d-660e-4da2-87e3-1cc37693889b`)

