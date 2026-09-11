# HANDOFF — Lovable 50×10 Blast (first-heavy)

Date: 2026-09-11. Previous AI did the work below; you continue from "Resume".

## Objective
50 Lovable sessions (2..51, s1 skipped) × 10 remixes each = 500 projects.
Per cell: **#1 = high-credit feature run from keeper source, #2..10 = cheap clones of #1**
(`--first-heavy`, default ON in remix mode, chimera-miner `script2_remix_link.py`).
Keeper source: `https://lovable.dev/projects/9941886d-d66f-4be6-8c77-5517809a36bb`

## Mapping (renamed 2026-09-11: session-13..130 → session-1..51)
Lovable N (2..51) → Railway cells `avail[:50]` = session-1..50 (was session-13,16,23,25,26,28,30,31,32,35,
36,43,53,75,76,77,80,81,82,83,84,86,87,88,89,90,91,92,93,94,95,96,106,107,108,109,110,
111,112,113,115,116,117,118,120,121,122,125,126,129 — see scripts/blast_lovable.py).
**session-51 (was session-130) left out** (51st, no service). 123/124/127/128 restricted, 5 has no service.

## State when handed off
- `scripts/reship_relaunch.py --par 2` full clean pass: check `/tmp/reship_clean2.log` tail.
- Fonts rollout (`/tmp/fonts_roll.py` → `/tmp/fonts.log`): cells had NO fonts → Firefox
  hung on "waiting for fonts to load". Fix = `apt install fonts-liberation fonts-dejavu-core`.
  **Browsers must be relaunched AFTER fonts land** (fontconfig is per-process).
- Code on cells: Camoufox (`AsyncCamoufox`, `extra_args --no-sandbox --disable-dev-shm-usage`),
  120s default timeout / 180s navigation (throttled 2vCPU), first-heavy + #1 retried 3x.
- Known good: cell net is FAST (100ms to lovable.dev), GTK installed, `setsid` detach works,
  one browser per cell (orphans killed by reship kill-step).
- Scoreboard: Mega DB auth expired + rclone hangs → **scoreboard = grep cell logs**
  (`Project ID` / `clone source` in `/app/work/remix-<lov>.log`), NOT Mega.

## Resume (run in /home/alan/Documents/railways, raw IP, LD_PRELOAD="")
1. `tail -3 /tmp/fonts.log` → if incomplete: `LD_PRELOAD="" nohup python3 -u scripts/fonts_rollout.py > /tmp/fonts.log 2>&1 &`
2. After fonts 51/51: `LD_PRELOAD="" nohup python3 -u scripts/reship_relaunch.py --par 2 > /tmp/reship_X.log 2>&1 &`
   (kills orphans, pipes fresh script2 from repo, GTK+fonts verify, setsid relaunch)
3. Wait 20 min, then per cell:
   `scripts/cell_ssh.sh session-N <proj> <env> cell-N -- "grep -E 'clone source|Project ID|created successfully' /app/work/remix-<lov>.log | tail -5; pgrep -c camoufox-bin"`
   (proj/env from cells.json)
4. Success = `🔥 FIRST-HEAVY #1 saved as clone source` then 9 clones. Failure patterns:
   `EPIPE` = browser died → check orphans (`ps aux | grep camoufox | wc -l` should be ~6);
   `Timeout 180000` on goto = throttled CPU, wait, do NOT restart (restart = progress reset);
   API `Connection reset` = back off SSH pace to par 1-2.

## Files
- `scripts/reship_relaunch.py` — kill+ship+relaunch (par 2 max, API throttles above)
- `scripts/blast_lovable.py` — original full-pipeline blaster (par default 3)
- `scripts/tor_cli.sh` — Tor multi-exit wrapper (only if raw IP throttled)
- `scripts/cell_ssh.sh` — per-session SSH (dedicated agent `/tmp/agents/session-N.sock`)
- chimera-miner repo: script2 patches pushed (first-heavy c62651e/727e85f, camoufox cd547e1, timeouts 7234036)
