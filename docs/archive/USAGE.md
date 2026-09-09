# Railway CLI — How To Use These Sessions

## Golden rule: auth comes ONLY from ~/.railway/config.json

The CLI reads the global config at `/home/alae/.railway/config.json` for auth.
Per-directory `.railway/config.json` only holds project links. `RAILWAY_TOKEN`
and `RAILWAY_CONFIG_DIR` are IGNORED. All 5 sessions' accessTokens are expired
→ "Unauthorized". Without a swap you are ALWAYS katrinawat.sonlaos@gmail.com.

## Acting as a different account (config swap)

```bash
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY   # TOR-wrapped shell breaks calls

cp ~/.railway/config.json /tmp/railway-config.bak
cp Documents/railways/credit_accounts/session-test/config.json ~/.railway/config.json
railway whoami          # now ha.nseltw.edt99@gmail.com
railway status          # project comes from CWD .railway/config.json
cp /tmp/railway-config.bak ~/.railway/config.json   # restore BEFORE doing anything else
```

- Everything is `railway whoami`/`status`-verified per session.
- `session-test/config.json` is the one with an alive refreshable token (worked 2026-08-19).
- A broken config produces "Unable to parse config file, regenerating".

## Other commands seen working

- `railway status` → project id + name for the session (from the session dir).
- `railway link --project <name>` inside a session dir → binds it to that project.
- `railway sandbox create/fork/template/checkpoint/list/ssh/exec/forward/destroy`.
- `railway sandbox template build` MUST run from a directory already linked to
  a project (it fails otherwise: "No project selected").

## rclone (MEGA sync)

- Always: `env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy bash -c 'rclone ...'`
- Flags: `--transfers 1 --tpslimit 4` (avoid hangs).
- `rclone lsl mega:...` — `lsl` has no `-R` flag.
- Local mirror: `/home/alae/Documents/railways/` ↔ `mega:railway_sessions/`.

## Mail checks

- dispose.lol mailboxes: open `https://dispose.lol/mailbox/<address>/` in a real
  browser. It's a SvelteKit app (JS-rendered) — curl gives you the shell only
  and `__data.json` currently 404s.
- Real gmail (katrinawat): only DNS/MX checks without account access.
- temp-mail (web.sytchamptoncc.co.uk): MX = mail.cleantempmail.com.

## Context mapping (do not confuse)

| Thing | Location |
|---|---|
| railway CLI configs | `mega:railway_sessions/` |
| Lovable cookies | `mega:lovable_sessions/` |
| Lovable miner DB | `mega:chimera/database.json` |
| Lovable API script | `Documents/repos/automation-toolkit/finals/core/lov-api.py` |
| Sandbox template staging | `/tmp/opencode/tpl/` |