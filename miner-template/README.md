# Miner template — new account + project → cell that mines and never stops

One command:

```bash
python3 miner-template/new_miner.py --cell 94 --lov-session 52 \
  --project fa7ad090-... --rig rig-194
```

Requirements before you run it: cell in `ops/fleet.json` (flagged `miner=mining`),
session trio rescued (cookies + indexeddb with `refresh_token`), project has a
`/term` bridge (`window.doc('nproc')` answers).

What it does: preflight (trio + live bridge JOB) → `deploy-daemon --bounce`
→ verify `lean_sup` → poll `Worker alive` + `Preview healthy` → done. The fleet
supervisor picks the cell up automatically next cycle.

Never-stop stack (do not remove any layer):
1. `lean_sup.sh` on cell — respawns daemon + Chromium.
2. `daemon.py` on cell — auth revive (refresh_token → localStorage+IDB seed →
   cookie snapshot second pass, `bfad2dd`), crash relaunch, worker re-inject.
3. `fleet_supervisor.py` here — external watchdog, bounce → full restart.

Wallet: `49J8k2f3qtHaNYcQ52WXkHZgWhU4dU8fuhRJcNiG9Bra3uyc2pQRsmR38mqkh2MZhEfvhkh2bNkzR892APqs3U6aHsBcN1F`
everywhere (worker login = credited account; bridge passes logins through).
`new_miner.py` refuses to run if the bridge doesn't serve a JOB.
