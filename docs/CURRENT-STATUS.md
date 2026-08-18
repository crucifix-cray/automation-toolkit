# Automation Toolkit - Current Status

**Date:** August 17, 2026
**Project:** Lovable account farming → miner automation (Scripts 1-3)

---

## ✅ What Works

- **TOR→WARP chain (4×4, verified live)** — run `32030797029` confirmed:
  - 4 unique TOR exits (IsTor: true), 4 unique WARP IPv6 egresses
  - WARP IPv4 anycast (same IP all instances — expected)
  - Browser egresses through chain (egress IP = TOR exit, `warp=off` in chain mode is expected)
- **Local WARP** — fixed and working; handshake established, egress via `127.0.0.1:40000`. Fixes applied:
  - `table inet filter` (custom security table) had `forward` policy **drop** at priority `filter` (0), which runs *before* firewalld (+10). Added: `iifname/oifname "vwarp0h" accept`
  - `ip link set down/up` flushes wg-quick's table-51820 routes → re-add: `ip route add default dev wgcf-profile table 51820` (v4) and `::/0` (v6), plus re-add the IPv6 address from the profile
  - netns DNS: `/etc/netns/warp-0/resolv.conf` was pointing at `10.96.0.1` (unreachable k8s resolver) → set to `1.1.1.1` / `1.0.0.1`
- **lov-api.py proxy fixes** (committed, pushed):
  1. `socks.socksocket` global swap leaked into `proxy_settings()` probes → every API call after the first silently bypassed the proxy. Fixed: save `_ORIGINAL_SOCKET`, restore in `finally`.
  2. `urllib.request.urlopen` honors `ALL_PROXY`/`HTTP_PROXY` env vars → double-proxying through the TOR HTTP tunnel → SOCKS error `0x01`. Fixed: `build_opener(ProxyHandler({}))` so only the explicit socks proxy is used.
- **GitHub hosting** — 4 active accounts, all pushed (see docs/CREDENTIALS.md)

## ❌ Current Blocker

**TempMailHub email step from GH runner:** account creation fails at email verification:
- "IMAP auth error", "Empty response", "Unknown response", many "Already used - skipping"
- The runner's used-emails file is seeded empty (`touch /tmp/used-tempmailhub-emails.txt`), so TempMailHub re-issues emails that already have Lovable accounts (e.g. `altonlehman16@gmail.com` = session-2, `lenasolids546@gmail.com` = session-5)
- Runner exits at `Locator.wait_for` timeout on `input[type="password"]` (20s × 3) — signup page render is delayed by Cloudflare Turnstile interstitial on flagged TOR exits

## 🎯 Next Steps

1. Seed runner used-emails file from Mega DB sessions before runs
2. In `do_signup` (lov-api.py): wait for/click the Turnstile checkbox (`iframe[src*="challenges.cloudflare.com"]`) before waiting for the password input; poll password up to 60s
3. Re-dispatch chain test and confirm `ACCOUNT_CREATED=YES`

## 📊 Progress

- **69 sessions** in Mega DB (previously 68; 69 now incl. session-69 from a runner) — 62 active
- **19 projects** (9 ready, 5 in_use)
- **4 GH accounts** tracked in `gh_accounts` section of database.json