# Limitations — BD Browser Stream

## BD Free Tier

- **5,000 credits/month** per account
- **5 credits/MB** for Browser API → ~1GB free per account
- 12 accounts total, 3 alive → 3 parallel sessions max
- Credits drain fast with screenshot streaming (~50-100KB per JPEG × 10fps = ~500KB/s)

## navigate_domains_limit

- **1 domain per BD session** — cannot navigate cross-domain without reconnecting
- Cross-domain = close old browser → open fresh BD session → navigate (~3-5s)
- Same-domain navigation works fine (no reconnect)
- This is a BD API limitation, not fixable

## Cloudflare Turnstile

- **ISP proxy IPs blocked**: ASN 213541 (WS Telecom) classified as datacenter
- Turnstile requires residential IPs → only BD Browser API works
- BD Browser API uses real Chrome sessions → Turnstile passes
- But: BD robots.txt blocks Railway auth pages (`/auth/signin`, `/auth/github`)

## BD Robots.txt Blocks

- `railway.com/auth/signin` — blocked
- `railway.com/auth/github` — blocked
- `22.do` — blocked (Email/Chat classification)
- Other Railway pages work fine

## Click Latency

- **Same-domain**: ~1-2s (CDP round-trip)
- **Cross-domain**: ~3-5s (new BD session + navigation)
- Clicks work server-side (curl test passes) but UI may feel slow

## Canvas Rendering

- JPEG quality 40% — compressed for speed, not sharp
- ~10fps polling — not real-time, sufficient for navigation
- Canvas `mousedown` not `click` — faster but no double-click detection
- Keyboard forwarded globally (except URL bar focus)

## Sandboxing

- Railway sandbox: 953MB RAM / 2 CPU / no `memory.swap.max` / no `CAP_NET_ADMIN`
- No kernel VPN support → only user-space solutions (wireproxy, BD Browser API)
- `/dev/net/tun` not available → WireGuard impossible

## Tor Proxy Conflict

- System-wide `ALL_PROXY` interferes with BD CDP WebSocket
- Service runs with `ALL_PROXY=` to bypass
- Manual runs must also unset `ALL_PROXY`

## Session Persistence

- BD sessions are ephemeral — no persistence across reconnects
- Page state lost on reconnect (cookies, form data, etc.)
- Must re-authenticate after each cross-domain navigation
