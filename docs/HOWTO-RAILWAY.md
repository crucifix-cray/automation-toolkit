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

## True verify (create/delete canary) — whoami is NOT enough

All 107 pass `whoami` (tokens refresh). Health = can you CREATE:

```bash
python3 scripts/railway_verify.py --par 8   # -> finals/railway_verify.json
```

Per session it runs `whoami` → `list --json` → `init --name vrfy-N --json` →
`delete --project <id> --yes --json`, classifying: `ok` / `trial` (free-plan
provision wall) / `restricted` (workspace restricted) / `rate` (1-project-per-30s,
retry solo) / `unauthorized`. 2026-09-09 baseline: 45 ok / 40 trial / 22 restricted.
Run CWD is `/tmp/rvwork/<session>` (init links the dir — kept out of the repo).

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

## Worker cells (persistent Ubuntu sandboxes)

51 ok accounts each own a `cell-N` project + `cellbase` checkpoint (full stack:
Python 3.14, patchright/playwright/camoufox/stealth/captcha, xvfb, chromium).
Registry: `cells.json`. Build/refresh: `python3 scripts/build_cells.py --par 10`.
Boot one live: `HOME=sessions/session-N railway sandbox create -p <project> --checkpoint cellbase`
(sandboxes idle-destroy after ≤5min — checkpoints persist, recreate on demand).

## Rules

- Sessions fully tracked including live tokens + cellkeys (owner decision 2026-09-11,
  commit `eddf339`) so any AI can operate all accounts from a fresh pull. Junk
  (cookies, caches, venvs) stays ignored. Rotate tokens if repo access ever changes.
- Raw IP first for checks; proxied/ZenRows egress only for farming (flag avoidance).

## Tor-separated CLI (multi-exit)

CLI ignores *PROXY env — use torsocks: `scripts/tor_cli.sh session-N -- whoami`.
Port rotates by session number (9051/9053/9054/9250/9050), `-i` isolates a
fresh exit circuit per call (verified distinct exits). Needs local tor with
`SocksPort 9051..9054` in `~/.config/opencode-tor/torrc`. Slower than raw;
use for identity separation, raw IP for bulk speed.
