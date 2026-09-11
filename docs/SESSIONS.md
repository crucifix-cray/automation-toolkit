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

## Accounts (ok on disk — deploys restricted on touched accounts, writes frozen)

| session | email | status | projects |
|---|---|---|---|
| session-1 | vallescasbonifa.cio4@gmail.com | ok | 3 |
| session-2 | mendo.zakian56@gmail.com | ok | 3 |
| session-3 | she.yhayaishi@gmail.com | ok | 3 |
| session-4 | ro.schelenavaara@gmail.com | ok | 3 |
| session-5 | gla.msolace@gmail.com | ok | 3 |
| session-6 | b.ineneabea@gmail.com | ok | 3 |
| session-7 | g.son0876@gmail.com | ok | 3 |
| session-8 | nij.irosimon@gmail.com | ok | 3 |
| session-9 | jae.denlunagna@gmail.com | ok | 2 |
| session-10 | helloclaragarc.ia@gmail.com | ok | 3 |
| session-11 | jda.ka5408@gmail.com | ok | 3 |
| session-12 | y.amlavigne@gmail.com | ok | 3 |
| session-13 | feicfi.nsh@gmail.com | ok | 2 |
| session-14 | gianprecin.io@gmail.com | ok | 3 |
| session-15 | jaden.kamisa@gmail.com | ok | 3 |
| session-16 | ellako.aasantoaa@gmail.com | ok | 4 |
| session-17 | renya.yae758@gmail.com | ok | 3 |
| session-18 | julietsauc.elo@gmail.com | ok | 3 |
| session-19 | katec.larizze@gmail.com | ok | 3 |
| session-20 | mun.ozkaia54@gmail.com | ok | 3 |
| session-21 | ji.lleaponteras@gmail.com | ok | 4 |
| session-22 | lkri.sha39@gmail.com | ok | 3 |
| session-23 | ingr.idelrod@gmail.com | ok | 4 |
| session-24 | breefins.h@gmail.com | ok | 3 |
| session-25 | noykidzca.stro@gmail.com | ok | 4 |
| session-26 | luz.vimindaaaguevarra@gmail.com | ok | 3 |
| session-27 | cassandrabacuda.l@gmail.com | ok | 3 |
| session-28 | f.r4ncis30@gmail.com | ok | 3 |
| session-29 | unicere.yess@gmail.com | ok | 3 |
| session-30 | ell.izabetharagones@gmail.com | ok | 3 |
| session-31 | danic.asenatubis@gmail.com | ok | 4 |
| session-32 | jaspe.rmolay@gmail.com | ok | 3 |
| session-33 | y.or.hun.2.7.7@gmail.com | ok | 3 |
| session-34 | mans.u.rk.urt.a.r.an5@gmail.com | ok | 4 |
| session-35 | ma.ns.ur.k.ur.t.a.ran.5@gmail.com | ok | 4 |
| session-36 | alac.a.ta.ri.k.177@gmail.com | ok | 0 |
| session-37 | jvshlta2718q+70x5oz396@outlook.com | ok |  |
| session-38 | ja.nicebunagna@gmail.com | ok |  |
| session-39 | y.or.h.un.2.7.7@gmail.com | ok | 1 |
| session-40 | nwnjzp42432e+2y85ai8k57fs50ym@outlook.com | ok |  |
| session-41 | y.a.v.as.h.u.seyi.n15@gmail.com | ok | 1 |
| session-42 | pexxg885ejrgb+ntaflt9@outlook.com | ok | 1 |
| session-43 | jelai.merope@gmail.com | ok | 1 |
| session-44 | balat.ce.mr.e@gmail.com | ok | 1 |
| session-45 | y.av.a.shu.s.ey.i.n15@gmail.com | ok | 1 |
| session-46 | hamadasa.ji94@gmail.com | ok | 1 |
| session-47 | tanfu686574+ogcwrplnac79fkqn8@outlook.com | ok | 1 |
| session-48 | ki.ttysantosna@gmail.com | ok | 1 |
| session-49 | nnkowkw2861b+r7bhet10@hotmail.com | ok | 1 |
| session-50 | sha.neoadjaron@gmail.com | ok | 1 |
| session-51 | y.a.va.shus.eyin15@gmail.com | ok | 1 |
