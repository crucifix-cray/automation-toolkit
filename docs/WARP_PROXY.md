# WARP Proxy Setup

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
