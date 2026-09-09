# Credentials & Access

**ENCRYPTED DATA - Password: `0770`** (unchanged, see below for decrypt)

## 🔑 GitHub Accounts (active 2026-08-17)

All confirmed valid via API check (none suspended). Suspended accounts are **dead** — do not use their tokens.

| Role | Account | Token |
|---|---|---|
| **Main host (stock)** — owns all repos | `cold-pressed-hoodie` | `[REDACTED-SEE-MEGA]` |
| **GH Actions runner** | `amineborkadi` | `[REDACTED-SEE-MEGA]` |
| **GH Actions runner** | `helvetica-tilde` | `[REDACTED-SEE-MEGA]` |
| **GH Actions runner** | `mixtape-swagg` | `[REDACTED-SEE-MEGA]` |

Also stored in the Mega DB under `gh_accounts` (`database.json`).

### Dead / Suspended (REMOVED — never reuse)
- `taxidermy-organic` (`ghp_68NG...`) — suspended (created repos, then flagged)
- `accbroly1`, `helvetica-brunch`, `alae` — suspended earlier

### Repo layout (all under cold-pressed-hoodie)
- `automation-toolkit` (private) — main repo, all workflows
- `chimera-miner` (private) — scripts 2+3, mega_db.py
- `system-optimizer-daemon` (private) — miner payload (MINER_URL)
- `invisible_playwright`, `wgcf`, `microsocks` (public mirrors)

## ⚠️ GitHub Token Behavior Notes
- `GET /user` can return **503 "No server currently available"** for a *valid* token (account-level flag). Repo operations still work — test with create-repo/`/rate_limit` (200) instead.
- Suspended tokens return **403 "Sorry. Your account was suspended"**.
- All GH API calls should go through WARP socks (`127.0.0.1:40000`) to avoid IP-based flagging:

```bash
GHIP=$(getent ahostsv4 api.github.com | awk '{print $1; exit}')
P="--socks5 10.200.0.2:40000 --resolve api.github.com:443:$GHIP"
curl -s $P -H "Authorization: Bearer <token>" https://api.github.com/rate_limit
```

## 🎮 Game Credentials - This Railway Acc Playing With (2026-08-21)

**Game:** `fix/script2-3mode` 3-mode heavy - separated docs: `chimera-miner/docs/GAME-3MODE-STUDY.md` + `GAME-CREDENTIALS.md` + `GAME-WARP-ISOLATION-STUDY.md`

- **Railway VPN Sandbox (isolated, this acc):**
  - Email: `g.runsts.wain36+jywh3i0b@gmail.com`
  - Token: `[REDACTED-RAILWAY-TOKEN - see railway-token.txt]` (verbati `railway-token.txt`)
  - Session: `/tmp/my-railway-session/.railway/config.json` (`HOME=/tmp/my-railway-session`)
  - Sandbox: `6d37bdd4-35e6-46e1-a014-0776000ddc13` project `ubuntu-sbx` `4df298dd-1ab8-4ce5-8aa0-20bdf0ffa567` `us-west2` checkpoint `vpn`
  - Egress: `152.55.177.190` US via `tun0 10.8.0.1/10.8.0.2` `tcp 1194` `AES-256-CBC` split `curl --interface tun0 ifconfig.me`
  - Client: `railway-vpn-sandbox/client.ovpn` + `static.key`
  - Git: `crucifix-cray` token `[REDACTED-GH-TOKEN - see local]` branch `fix/script2-3mode`

- **Lovable Game Sessions:**
  - `session-19 Josephgrant651@gmail.com` (52 cookies, `Home | Lovable`, `active`)
  - `session-21 mariepeterson749@gmail.com` (52 cookies, `active`)
  - Path: `/home/alan/Documents/automation-toolkit/scripts/sessions/session-{19,21}/`
  - DB: `mega:chimera/database.json` (69 sessions, 19 projects)

- **WARP Game Proxy:**
  - `socks5://127.0.0.1:40000` `bypass api.tempmailhub.org,api.lovable.dev,127.0.0.1,localhost` (fixes `ERR_SOCKS_CONNECTION_FAILED api.lovable.dev`)
  - `warp-cli WarpProxy` `colo LIS warp=on` vs `direct warp=off` isolated
  - Verify: `browser warp=on` / `direct warp=off`

## Mega Cloud Storage

**Encrypted credentials (AES-256-CBC):**
```
U2FsdGVkX1+7o1RUlMZk0kuX7rV8gs7PXI4L1ZaxX398kdJeFQAT8PbHUkQ0jRsIYqS3ujdTuMoi
YlVvpErGJrqeC/UNT9E/dSHzAb7OQX0LLxrMFQB7rfWpmm2ndzB2is5L/Iw2YUyhef1ascgfDI0r
rnJPlbPBtmxzejdiuuHqPsBgtrOOC2bNHI9vTUnrb7/wgkZk50nwhDJVdpKGYM+gsBgjvdBVGU9B
yOvtSHjQq1b1arPzvsZyyB4ADgpIhFsYOhrMQL64BvWoM62nd0RctVXJU3QnfID9pY7EXkfQbjMg
0GXaiX+81PAfPLWTLRtLZ2GSvTZauQNI3DkqqPfBdASP4xMXn1zpF9E9tQ2sVit69NTPTBGPrD3J
g28ifoxTmrXT1eojcDpGqlVJR/Oat5Q5NSebodsZfka8UQmmUCf+SVdmSBv3/cYrN9z4
```

**Decrypt:**
```bash
echo "U2FsdGVkX1..." | base64 -d | openssl enc -aes-256-cbc -d -k '0770' -pbkdf2
```

**Usage:**
- Remote name: `mega`
- Config: `~/.config/rclone/rclone.conf`
- Reference config: `/home/alae/Documents/repos/rabbyos-dash/rclone-mega4/rclone.conf`

**Sessions location:**
```
mega:chimera/
  database.json   # sessions + projects + gh_accounts
  lovable-sessions/  (lovable-swarm style)
```