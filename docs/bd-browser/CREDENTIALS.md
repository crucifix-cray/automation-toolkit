# Credentials — BD Browser API

## Primary BD Account (Browser API)

```
API Key:       hl_7357e514
WSS Token:     vuln37v8nbfh
Zone:          scraping_browser1
Endpoint:      wss://brd-customer-hl_7357e514-zone-scraping_browser1:vuln37v8nbfh@brd.superproxy.io:9222
```

## ISP Proxy Account

```
API Key:       hl_7357e514
Proxy User:    brd-customer-hl_7357e514-zone-isp_proxy1
Proxy Pass:    n7pq7twhpas9
Proxy:         brd.superproxy.io:44445
Protocol:      HTTP/HTTPS
Known IP:      158.46.218.92 (ASN 213541 WS Telecom)
```

> **WARNING**: ISP proxy IPs are flagged by Cloudflare as datacenter → Turnstile blocks them. Only Browser API (residential Chrome) works for CF-protected sites.

## BD Browser API Pool — 12 Accounts

| Account | API Key | Status | Notes |
|---------|---------|--------|-------|
| acc1 | hl_89e05c71 | SUSPENDED | Credit drained |
| acc2 | hl_a511e8a7 | SUSPENDED | Credit drained |
| acc3 | hl_eb0ee1fc | SUSPENDED | Credit drained |
| acc4 | hl_3a6f3a6f | SUSPENDED | Credit drained |
| acc5 | hl_fcc5c3c7 | SUSPENDED | Credit drained |
| acc6 | hl_25ef2832 | SUSPENDED | Credit drained |
| acc7 | hl_33454e4d | SUSPENDED | Credit drained |
| acc8 | hl_34b2f8c2 | SUSPENDED | Credit drained |
| acc9 | hl_21f2f021 | SUSPENDED | Rate limited |
| **acc10** | **hl_e895b201** | **ALIVE** | Active |
| **acc11** | **hl_7e8d5d40** | **ALIVE** | Active |
| **acc12** | **hl_76276a19** | **ALIVE** | Active |

### Alive Account Tokens

```
acc10: wss://brd-customer-hl_e895b201-zone-scraping_browser1:{TOKEN}@brd.superproxy.io:9222
acc11: wss://brd-customer-hl_7e8d5d40-zone-scraping_browser1:{TOKEN}@brd.superproxy.io:9222
acc12: wss://brd-customer-hl_76276a19-zone-scraping_browser1:{TOKEN}@brd.superproxy.io:9222
```

> Tokens redacted — retrieve from BD dashboard or encrypted creds vault.

## Free Tier Limits

- **5,000 credits/month** per account
- **5 credits/MB** for Browser API
- ~1GB free browsing per account per month
- `navigate_domains_limit`: **1 domain per session** (must reconnect for cross-domain)
- 12 accounts alive = 3 → 3 parallel browser sessions possible

## BD Dashboard

```
https://dashboard.brightdata.com
```

Login required. Account ID visible in dashboard (no copy button — must manually extract).

## SSH / Railway

```
SSH Key:     /home/alae/.ssh/jzw_vnc.pub (jzw-vnc-2026-08-24)
GH Token:    see encrypted creds vault (docs/CREDENTIALS.md in repo root)
Remote Box:  Railway "Ubuntu 24.04" (test-ubuntu-6)
```

## Cloudflare Account

```
Account ID:  452f29fa3dc7e3e4eebce890ea87... (partial — no copy button in dashboard)
```
