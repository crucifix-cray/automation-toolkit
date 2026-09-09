# HOWTO — Railway sessions

Single source: `sessions/session-N/`. Index: `docs/SESSIONS.md`. Audit: `scripts/railway_audit.py`.

## Check one (raw IP)

```bash
HOME=/home/alan/Documents/railways/sessions/session-10 LD_PRELOAD="" \
  env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
  railway whoami
# Logged in as harp.ergestrice@gmail.com
```

`HOME=` is the whole trick — the CLI reads `$HOME/.railway/config.json`.
`LD_PRELOAD=""` clears any preload hacks. Unset proxies = raw egress IP.

## Check all (P20)

```bash
ls -1d sessions/session-* | xargs -P 20 -I{} bash -c \
  'n=$(basename {}); out=$(HOME=$PWD/{} LD_PRELOAD="" railway whoami 2>&1); echo "$n :: $out"'
```

Or `python3 scripts/railway_audit.py` (writes `finals/railway_audit.json` with project counts).

## Self-healing refresh

Expired `accessToken` is normal. `whoami` refreshes it via `refreshToken` and rewrites
`.railway/config.json` in place. Only re-farm if `whoami` still says Unauthorized
after one try (means refreshToken itself died).

## Restore a wiped config

The CLI auto-update once deleted all `.railway/config.json` except session-1.
Fix per session:

```bash
cp sessions/session-N/railway_cli_config.json sessions/session-N/.railway/config.json
# then whoami (auto-refreshes)
```

Nuclear backup: `~/railway_tokens_backup/railway_tokens_2026-09-09.tar.gz`.

## Farm a new one

```bash
LD_PRELOAD="" python3 railway-docker/railway-HOLY-zenrows.py --cloud
```

Takes next free number, verifies `whoami`, writes `email.txt`. Then add row to `docs/SESSIONS.md`.

## Rules

- Never commit anything under `sessions/*/` except `email.txt` / `verified_at.txt` (enforced by `.gitignore`).
- Never `git add -f` a token file. History already contains old tokens (see `docs/CLEANUP.md`).
- Raw IP first for checks; proxied/ZenRows egress only for farming (flag avoidance).
