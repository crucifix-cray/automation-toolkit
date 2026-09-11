# PROMPT FOR NEXT AI — full context in one paste

You are continuing the Railway × Lovable blast operation. Repo: `crucifix-cray/automation-toolkit`,
branch `main` (just pushed, pull first). Work dir: `/home/alan/Documents/railways`.
Rules: raw IP only (strip all *PROXY env, `LD_PRELOAD=""`), max `--par 2` on Railway SSH
(API throttles above), never mass-deploy/create projects (restriction waves), one browser per cell.

First read: `docs/HANDOFF-BLAST.md` (resume steps), `docs/SESSIONS.md` (accounts),
`docs/HOWTO-RAILWAY.md` (Tor wrapper, true-verify), `docs/LOVABLE.md` (pipeline).

Situation: 51 Railway Ubuntu services live, 50 in the blast (session-130 excluded),
Lovable sessions 2..51 mapped 1:1 to cells. script2 (`chimera-miner` repo,
`script2_remix_link.py`) runs first-heavy: project #1 high-credit feature from keeper
`9941886d-d66f-4be6-8c77-5517809a36bb`, #2..10 cheap clones of #1. Camoufox browser,
120s/180s timeouts (throttled CPUs), fonts required (`scripts/fonts_rollout.py`).
Scoreboard = `grep 'clone source\|Project ID' /app/work/remix-<lov>.log` per cell —
Mega DB auth is expired, ignore Mega/rclone entirely.

Session index (`sessions/session-N/email.txt`) is tracked; tokens/keys stay LOCAL
(git-ignored, never commit). Restricted 123/124/127/128 removed 2026-09-11
(backup: `~/railway_tokens_backup/restricted_123-124-127-128_2026-09-11.tar.gz`).

Resume command sequence is in HANDOFF-BLAST.md. Verify with evidence (cell logs),
do not restart cells with a live `camoufox-bin` process.
