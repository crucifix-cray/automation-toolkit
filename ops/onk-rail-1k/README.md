# ops/onk-rail-1k — farm ops scripts (mirrored)

Live copies live in `/home/alae/onk-rail-1k/` — these are the repo mirrors so
the scripts travel with the code. Ops runs from `/home/alae/onk-rail-1k/`
because the supervisor tick's `git checkout main` + farm-branch merges rewrite
in-repo files (this bit us: patched tools silently reverted mid-run).

| Script | Role |
|---|---|
| `mail_rotate.py` | mailbox provider rotation + per-IP signup pacing (the 2026-09-25 fix) |
| `refill_all.py` | per-host worker refill: restart stale, destroy dead, top up to 8. **Pause switch = rename to `.PAUSED`** |
| `materialize_jars.py` | merged jars (`finals/sessions/farmed-*`) → `session-N` dirs, dedup by email |
| `verify_up_down.py` | the UP_GOOD gate: link → `railway up -d` → build → mark GOOD/BAD → down |
| `count_ready.py` | the only truth on progress (UP_GOOD count) |
| `org_reset_fixed.py` | OnK org-reset via remote CDP browser; restore over `src/onkernel/org_reset.py` if `--host-key` disappears |

See `docs/FARM-1K.md` for the full runbook.
