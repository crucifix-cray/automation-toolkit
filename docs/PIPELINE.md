# Pipeline quickstart (2026-09-19)

Canonical handoff: `/home/alae/Documents/repos/chimera-miner/HANDOFF.md`

| What | Where |
|---|---|
| Lovable ×36 | `scripts/sessions/` + [LOVABLE.md](LOVABLE.md) |
| Railway ×68 | `/home/alae/Documents/railways/` + [SESSIONS.md](SESSIONS.md) |
| Bridge | `wss://chimera-bridge-production-0703.up.railway.app` |
| Rescue (2FA/TOTP) | `src/lovable/session_refresh.py <N>` (cwd = repo root) |
| Script2 | `chimera-miner/script2_remix_link.py --mode template --browser kernel\|zenrows` |
| Script2 prompt | `prompts/Build a debug terminal.txt` (`/__shell` bridge) — **required**, no trivial chat |
| Script3 | `chimera-miner/script3_launch_miner.py --mode full` on Railway **service** |

Order: rescue → script2 (OnKernel/ZenRows) → script3. Parallel after one green pilot.

**DB:** GitHub `chimera-miner/data/database.json` (`CHIMERA_DB_BACKEND=github`). No Mega.

**Pilot paused:** session-2 cookies OK; script2 remixed `84633151-…` but sent trivial `say 'a'` (bug — now patched to use `Build a debug terminal.txt`). Script3 not started. See HANDOFF.
