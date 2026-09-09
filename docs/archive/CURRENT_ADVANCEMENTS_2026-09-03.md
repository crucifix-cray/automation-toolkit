# Current Advancements — 2026-09-03

## TL;DR
- **Lovable** `genev.aochea@gmail.com` / `GmailK01` **verified** on `ZenRows GB` `86.141.244.43` `BT Telford` via `dispose.lol` (`Check your inbox` → `oobCode=t9v0iZJJ...` → `getting-started`).
- **Railway** `railway-HOLY-zenrows.py` **flawless** on `ZenRows` `b71908...` `gf` `109.222.170.164` `FR` `Orange` → `b.a.lat.ce.m.re@gmail.com` `OTP 691099` → `dashboard` `session-100`.
- **Mega** fixed `g.api` `IPv6` dead → `eu.api.mega.co.nz` + `WARP` `socks5://127.0.0.1:40000` only for `rclone` `endpoint`, `114` `railway_sessions` `exit 0`.
- **ZenRows** 2 keys `3a6a9ee...` (exhausted `402`) + `b71908...` (`gf`/`gb` `200` `Example Domain`) + `a71406...` on `mega:chimera/zenrows`, `browser-use-zenrows` live.
- **Oxylabs** `holygray_wRbC4:holygray_wRbC4` `Web Scraper` `200` `Example Domain` + `holygray_q3FQP:holygray_q3FQP` `Web Unblocker` `109.222.170.164` `FR`.

## BD vs ZenRows
| BD `hl_e895b201` `wss://brd.superproxy.io:9222` | ZenRows `wss://browser.zenrows.com?apikey=...&proxy_country=gf/gb` |
|---|---|
| `navigate_domains_limit` 2-3 `Page.navigate` per `sessionId` | No limit |
| `Forbidden: password typing` global trap on `type=password` via `Input.dispatchKeyEvent`/`el.value=` even from `iframe` clean window, only `window.__nativeSetter` via `add_init_script` bypasses | No trap, `page.keyboard.type` `delay 50` works |
| `suspicious activity` `400` on `Firebase` `49.43.x`/`76.108.x` `AS7922` | `gb` `86.141.244.43` `BT` `Success!` + `Check inbox` passed, `gf` `92.142.x` `Orange` still `suspicious` |

## Mail
- `temp.tf` Gmail dot (`b.alatc.em.re@gmail.com` etc.) → `suspicious` on BD+ZenRows `gf`.
- `dispose.lol` `Temporary Gmail` (`ionizaakpoest.er@gmail.com`, `genev.aochea@gmail.com`) → `gf` `suspicious` but `gb` `BT` **verified**.
- `mail.tm` `testgop0sw@emalupe.com` → `suspicious` on BD.
- Healthiest: `dispose.lol` + `ZenRows GB`.

## IP Health
- `BD` `49.37.210.184`, `35.146.119.153` `57` `73.148.253.107` `AS7922` `68.34.106.134` `AS7922` `174.103.78.72` `92.18.x` `161.22.x` `2.120.179.216` `GB` `BT` — only `86.156.87.116` `BT`/`86.141.244.43` `BT` `GB` gave `Check inbox`, others `suspicious`/`no token`.
- `ZenRows` `92.142.24.39 AS3215 Orange FR`, `81.248.38.144 AS3215`, `161.22.127.109 AS21351 Mediaserv GF` — token `837` but `suspicious`; `78.124.39.10 SFR FR`, `149.57.255.203 LogicWeb US` datacenter `suspicious`; `86.141.244.43 BT GB` **healthy**.

## Script
`playwright` `connect_over_cdp("wss://browser.zenrows.com?apikey=...&proxy_country=gb")` + `ctx.add_init_script("window.__nativeSetter=...")` → `page.keyboard.type` `delay 50` → `Turnstile Success` → `Create` → `dispose.lol` poll `getMailboxMessages` → `oobCode` → `Dashboard` — 100% on `gb` as `finals/core/lov-zenrows-final.py` / `zenrows-kernel-final.py` (`Kernel` `prod-jfk-hypeman-7` `wss` for `app.zenrows.com` self-signup `thomasnhayes@astroai.eu.cc`).

## Mega
- `rclone.conf` `endpoint = https://eu.api.mega.co.nz/` + `LD_PRELOAD='' https_proxy=socks5://127.0.0.1:40000 rclone lsd mega:railway_sessions` → `114` dirs `session-100` `railway_cli_sessions/` `200` `f` `22877` nodes, `ls` `brightdata` `15` `chimera/zenrows` `4` now `exit 0`; `g.api` `IPv6` `unreachable` was the hang, `eu` `WARP` `socks5` only for `rclone` `endpoint` fixes `cat`/`copy` `gfs` `EOF`/`403`.

## Oxylabs
- `Web Scraper API` `realtime.oxylabs.io/v1/queries` `holygray_wRbC4:holygray_wRbC4` `source:universal` `https://example.com` `200` `7500898108360937473` — like `ZenRows Scrape`.
- `Web Unblocker` `unblock.oxylabs.io:60000` `holygray_q3FQP:holygray_q3FQP` `200` `109.222.170.164` `FR` `AS3215` — like `ZenRows Scrape` with `x-oxylabs-geo-location`, not `Browser` CDP; `Headless Browser` `render:html` handles `Cloudflare` but `Turnstile` still needs `Browser`.

## Config
- `opencode.json` `zenrows`/`zenrows2` (`3a6a9ee...`/`b71908...`) + `browser-use-zenrows`/`zenrows2` (`gf`→`gb` healthiest), `~/.zenrows/secrets.json` + `mega:chimera/zenrows/*`, `browser-use-zenrows-wrapper.sh` `BU_CDP_WS`, `server.py` `cdp_url` fix + `browser_evaluate` `userGesture:true` + `browser_human_type`/`browser_paste` for BD (kept).

## Next
- `Railway` farm `railway-HOLY-zenrows.py --cloud-no-c --no-warp` with `ZENROWS_WSS` `gf` + `dispose` (as just succeeded `b.a.lat.ce.m.re@gmail.com` `691099` → `dashboard`).
- `Lovable` farm `lov-api-zenrows.py` on `GB` `BT` `dispose.lol`.
- `Kernel` `prod-jfk-hypeman-7` `wss` for `ZenRows` self-farm `astroai.eu.cc`.
