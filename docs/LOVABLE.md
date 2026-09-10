# Lovable accounts (canonical)

51 accounts, all TOTP. Farmed by Script 1 track (other machine).

## Sessions

`scripts/sessions/session-N/` (N = 1..51) + `scripts/sessions/invites.json`.
Per session `config.json`: `email`, `password`, `totp_secret`,
`totp_secret_backup`, `2fa_live_id`, `cookies.json` alongside.
Status fields (`verified`, `status`, `last_revived_at`) maintained by Script 1 —
do not hand-edit, read only.

## Pipeline (chimera-miner repo)

- Script 2 `script2_remix_link.py` (project creator): 10 remixes per account,
  one account per Railway cell (`sessions/session-N` Railway CLI session feeds
  cell N). `SKIP_FEATURE=1` on 0-credit accounts. Invites → Mega DB.
- Script 3 `script3_launch_miner.py` (miner): injects worker via window.doc
  bridge into `*.lovableproject.com` previews. Honors `MINER_CMD` override.
- Shared DB: `mega:chimera/database.json` (Mega lock on all writes).

## Remix flow (NEW Lovable UI — only working flow)

Deep-link `{project}?view=more&subview=settings-general` → wait
`button[name=General]` → pill Remix inside `section#preview-panel`
(`get_by_role(button, name="Remix", exact=True)`, plain click) → dialog
`form[data-testid="remix-dialog-content"]` (prefilled name, submit directly,
45s wait) → new `/projects/<id>` → Share invite → Mega DB.
Never match `base-ui-*` ids; verify dialog title (Remix/Move/Transfer pills
look identical); never accept source URL as success.

## Login/TOTP

Cookies first; fallback email → Continue → password →
`pyotp.TOTP(totp_secret)` → Verify, else `totp_secret_backup`.
Secrets local-only. Mark red only on proven-bad credentials, never infra flakes.

## Run envs

`CHIMERA_SESSIONS_DIR`, `HEADLESS=1` (script3), `SKIP_FEATURE=1` (script2),
`MINER_CMD`, `PROXY_PORT=9` forces direct. Proxy env unset + `LD_PRELOAD=''`.
