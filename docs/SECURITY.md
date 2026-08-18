# Security

This repository is public. Read this before committing anything.

## Hard rule

Never commit live credentials: API tokens, OAuth access/refresh tokens,
session cookies, auth keys, or password-derived material.

## Known-secret file locations (local, git-ignored)

| Path | Contains |
|---|---|
| `session-1/`, `session-3/` | Railway CLI config + session files with live tokens |
| `session-2/.railway/`, `session-3/.railway/` | Railway CLI state incl. `accessToken` |
| `session-*/browser_cookies.json` | Live browser cookies |
| `chimera-bridge/config.json` (local only) | Real bridge `auth_keys` |
| `chimera-bridge/.git/config` | Historical embedded GitHub tokens |

The bridge repo was previously pushed with a token embedded in its remote
URL; **rotate that token** – it is visible in `.git/config` of clones.

## What the repo contains instead

- `chimera-bridge/config.example.json` – template with placeholder keys.
- `docs/` – explanations only; no secret values in any example output.

## Hygiene checklist

1. `git status` before committing – look for `config.json`, `*.session`,
   `*_config.json`, `cookies*`.
2. `grep -rnE "ghp_|Bearer |accessToken|auth_keys" .` in a fresh clone.
3. If a secret leaks, assume compromise: revoke/rotate immediately, then
   purge from history (or delete and recreate the repo if it is public).
4. Env vars / Railway variables for anything the runtime needs.

## Token handling in automation

- GitHub pushes use a personal access token only in the git remote URL
  (never in files).
- Railway tokens are written by the automation into CLI session files
  outside the repo.
- Bridge `auth_keys` live only in the host's `config.json`.
