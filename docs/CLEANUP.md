# CLEANUP 2026-09-09 — what was removed and why

Repo had 3 session truths, 1.7GB browser profiles, 22 revive logs, 40 conflicting docs.
Fresh AI kept tripping on stale claims (e.g. `docs/USAGE.md` said `HOME=` override doesn't
work and all tokens are dead — both disproven same day: 107/107 raw `whoami` OK).

## Deleted (tracked → gone from HEAD, still in git history)

- `scripts/sessions/` (43 empty `config.json` + moved `invites.json` → `finals/lovable_invites.json`)
- `scripts/railways/` (5 sessions **with live tokens** — secrets do not belong in git)
- `scripts/sessions_backup_dead/`, `scripts/__pycache__`, `railway-docker/__pycache__`
- `finals/core/lov-api-BACKUP.py`, `lov-api.BAK-no-dispose.py`,
  `scripts/lovable-script2-FIXED.py.backup`, `scripts/railway-mailtm.py.backup`
- `railway-docker-backup/` (stale copy of `railway-docker/`)
- Root `revive_*.log`, `kernel_revive_results.log`, `revive_results.log`,
  `session_check_*.log`, `railway-docker/lol-integration-final.log`
- `docs/*.md` → `docs/archive/` except keepers:
  `README, SESSIONS (rewritten), RAILWAY_AUTOMATION, ARCHITECTURE,
  RAILWAY_ZENROWS_2026-09-02, ZENROWS_ADVANCEMENTS_2026-09-01` + new `HOWTO-RAILWAY`
  (archived: CREDENTIALS, ACCOUNTS, USAGE, AI_HANDOFF_PROMPT, CURRENT-STATUS, etc.)

## Deleted (untracked → gone from disk)

- `browser_profile_*` ×29 (~1.7GB), `scripts/railway_profile/` (~101MB)
- `_bridge_recovery/`, `opencode-sessions/`, `counter.txt`
- Per session: `.cache/` (~441MB), `.local/` (~140MB), `.config/`,
  `.railway/staged-update` (18MB CLI binary copy), `.railway/sessions` (agent PIDs),
  `railway_cli_sessions/` (agent PIDs), `*.log/*.lock/__pycache__`
  (600MB → ~100KB per session)

## Moved

- Root `session-*` (107) → `sessions/session-*` — one address for everything.
- `scripts/railway_audit.py` rewritten: old path `repos/automation-toolkit/scripts/railways`
  → `sessions/`, direct `HOME=` (no temp-copy), P20.
- `scripts/check_sessions_dashboard.py` default `scripts/sessions` → `finals/core/sessions`
  (Lovable cookies; Railway CLI sessions are separate).

## ⚠️ Secret-history warning

Git history still contains: `scripts/railways/*/config.json` (5 live Railway tokens),
`docs/archive/CREDENTIALS.md`, `docs/archive/bd-browser/CREDENTIALS.md` (BD keys),
`railway-docker/rclone.conf`, README ZenRows key. If this repo ever goes public:
rotate Railway refreshTokens (or purge history), BD/ZenRows keys, Mega password.
Local-only stance from here: `.gitignore` blocks `sessions/*` auth + `*.session` + `rclone.conf`.
