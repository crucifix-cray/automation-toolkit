# Railway Sessions Index (canonical)

51 ok accounts on disk (62 trial/restricted removed 2026-09-09 — hosted projects untouched,
tokens in ~/railway_tokens_backup). Full 113-record history: finals/railway_verify.json.
Results: `finals/railway_verify.json`. Sweep: `python3 scripts/railway_verify.py --par 8`.

- **ok** = canary project created AND deleted clean. Farm/deploy here.
- **trial** = `Free plan resource provision limit exceeded` — login works, existing
  projects keep running (fleet hosts 264 total), but NO new creates. Keep for hosting.
- **restricted** = `Your workspace has been restricted` — hard wall. Keep tokens only
  (may unrestrict later); do not plan capacity on these.
- `whoami` alone is NOT health (all 107 pass it — tokens auto-refresh). Always verify
  with init/delete before counting capacity.

## Layout

```
sessions/session-N/
  .railway/config.json      LIVE TOKENS (git-ignored, never commit)
  railway_cli_config.json   token backup (git-ignored)
  browser_cookies.json      railway.com cookies incl rw.session (git-ignored)
  email.txt                 TRACKED index (no secret)
  verified_at.txt           TRACKED last verify note
```

Only `email.txt` + `verified_at.txt` are committed. Everything auth is local-only.
Token backup outside repo: `~/railway_tokens_backup/railway_tokens_2026-09-09.tar.gz`.

## Rules

1. `HOME=/home/alan/Documents/railways/sessions/session-N LD_PRELOAD="" railway whoami`
   (CLI reads `$HOME/.railway/config.json`). Strip proxy env for raw IP.
2. Expired accessToken self-heals on `whoami` via refreshToken. Re-farm only if
   `whoami` still fails after one try.
3. Missing `.railway/config.json` -> `cp railway_cli_config.json .railway/config.json`.
4. Farm new: `SKIP_MEGA=1 python3 railway-docker/railway-HOLY-zenrows.py --cloud`
   (numbers from local `sessions/`, next = max+1). Then re-run verify + update table.
5. Never commit tokens. Never farm dup emails (78/79 share one workspace — parallel
   creates collide with 1-project-per-30s rate wall).

## Accounts (ok only — 62 trial/restricted removed 2026-09-09, tokens in backup)

| session | email | status | projects |
|---|---|---|---|
| session-13 | vallescasbonifa.cio4@gmail.com | ok | 3 |
| session-16 | mendo.zakian56@gmail.com | ok | 3 |
| session-23 | she.yhayaishi@gmail.com | ok | 3 |
| session-25 | ro.schelenavaara@gmail.com | ok | 3 |
| session-26 | gla.msolace@gmail.com | ok | 3 |
| session-28 | b.ineneabea@gmail.com | ok | 3 |
| session-30 | g.son0876@gmail.com | ok | 3 |
| session-31 | nij.irosimon@gmail.com | ok | 3 |
| session-32 | jae.denlunagna@gmail.com | ok | 2 |
| session-35 | helloclaragarc.ia@gmail.com | ok | 3 |
| session-36 | jda.ka5408@gmail.com | ok | 3 |
| session-43 | y.amlavigne@gmail.com | ok | 3 |
| session-53 | feicfi.nsh@gmail.com | ok | 2 |
| session-74 | qnwa3u7em0a3@emalupe.com | ok | 3 |
| session-75 | gianprecin.io@gmail.com | ok | 3 |
| session-76 | jaden.kamisa@gmail.com | ok | 3 |
| session-77 | ellako.aasantoaa@gmail.com | ok | 4 |
| session-80 | renya.yae758@gmail.com | ok | 3 |
| session-81 | julietsauc.elo@gmail.com | ok | 3 |
| session-82 | katec.larizze@gmail.com | ok | 3 |
| session-83 | mun.ozkaia54@gmail.com | ok | 3 |
| session-84 | ji.lleaponteras@gmail.com | ok | 4 |
| session-85 | mdq9ev0wg4fd@emalupe.com | ok | 4 |
| session-86 | lkri.sha39@gmail.com | ok | 3 |
| session-87 | ingr.idelrod@gmail.com | ok | 4 |
| session-88 | breefins.h@gmail.com | ok | 3 |
| session-89 | noykidzca.stro@gmail.com | ok | 4 |
| session-90 | luz.vimindaaaguevarra@gmail.com | ok | 3 |
| session-91 | cassandrabacuda.l@gmail.com | ok | 3 |
| session-92 | f.r4ncis30@gmail.com | ok | 3 |
| session-93 | unicere.yess@gmail.com | ok | 3 |
| session-94 | ell.izabetharagones@gmail.com | ok | 3 |
| session-95 | danic.asenatubis@gmail.com | ok | 4 |
| session-96 | jaspe.rmolay@gmail.com | ok | 3 |
| session-97 | qd1t8martppn@emalupe.com | ok | 3 |
| session-98 | z0xuce04ifaz@emalupe.com | ok | 3 |
| session-99 | 9d1l7zfcgq3g@emalupe.com | ok | 4 |
| session-101 | m8t4ie0jr2on@emalupe.com | ok | 2 |
| session-102 | pe9iitck2bes@emalupe.com | ok | 3 |
| session-103 | nxmvyb2qrk9x@emalupe.com | ok | 3 |
| session-104 | reurwi18fmne@emalupe.com | ok | 3 |
| session-105 | 18wvl2niigwd@emalupe.com | ok | 3 |
| session-106 | y.or.hun.2.7.7@gmail.com | ok | 3 |
| session-107 | mans.u.rk.urt.a.r.an5@gmail.com | ok | 4 |
| session-108 | ma.ns.ur.k.ur.t.a.ran.5@gmail.com | ok | 4 |
| session-109 | alac.a.ta.ri.k.177@gmail.com | ok | 0 |
| session-110 | jvshlta2718q+70x5oz396@outlook.com | ok | 1 |
| session-111 | ja.nicebunagna@gmail.com | ok | 1 |
| session-112 | y.or.h.un.2.7.7@gmail.com | ok | 1 |
| session-113 | nwnjzp42432e+2y85ai8k57fs50ym@outlook.com | ok | 1 |
| session-114 | o1jw13a5di5o@uberip.com | ok | 1 |
