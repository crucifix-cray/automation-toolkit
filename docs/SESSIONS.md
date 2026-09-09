# Railway Sessions Index (canonical)

108 accounts (session-109 farmed 2026-09-09 ~17:00 UTC), true-verified via CLI
create/delete canary (`railway init vrfy-N` -> `railway delete --yes`):
**46 ok / 40 trial / 22 restricted**.
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

## Accounts (status 2026-09-09)

| session | email | status | projects |
|---|---|---|---|
| session-1 | 904x1b2h4avw@emalupe.com | restricted | 1 |
| session-2 | st.odezgdvkp+odytn8e1il@gmail.com | trial | 2 |
| session-3 | jzwvvhj4934m+vla1ycoqmow59@outlook.com | trial | 2 |
| session-4 | bsu.ejjrue.kis8.0.9+bxbqr9ff@gmail.com | trial | 2 |
| session-5 | nlvnod39153u+jm7mu6cj9m01hh5@outlook.com | trial | 2 |
| session-6 | tha.t.huchoem0.1.8@gmail.com | trial | 2 |
| session-7 | s2d6bjrla38o@emalupe.com | trial | 2 |
| session-8 | f1ygzor9x8pa@emalupe.com | trial | 2 |
| session-9 | 0ybiva47sesh@emalupe.com | trial | 2 |
| session-10 | harp.ergestrice@gmail.com | trial | 2 |
| session-11 | ammyymore.noo@gmail.com | trial | 2 |
| session-12 | jasper.molay@gmail.com | trial | 2 |
| session-13 | vallescasbonifa.cio4@gmail.com | ok | 3 |
| session-15 | abbigailvorcabu.no@gmail.com | trial | 2 |
| session-16 | mendo.zakian56@gmail.com | ok | 3 |
| session-17 | lo.peracamie@gmail.com | trial | 2 |
| session-18 | vian.nabartolome@gmail.com | trial | 2 |
| session-19 | velvetkiss08.2@gmail.com | trial | 2 |
| session-20 | adis.wuechl@gmail.com | trial | 2 |
| session-21 | l.ilacelrod@gmail.com | trial | 2 |
| session-22 | na.tanhielriverra@gmail.com | trial | 2 |
| session-23 | she.yhayaishi@gmail.com | ok | 3 |
| session-24 | er99114.34@gmail.com | trial | 2 |
| session-25 | ro.schelenavaara@gmail.com | ok | 3 |
| session-26 | gla.msolace@gmail.com | ok | 3 |
| session-27 | jean.netteejavier@gmail.com | trial | 2 |
| session-28 | b.ineneabea@gmail.com | ok | 3 |
| session-29 | jeni.sisfajardo@gmail.com | trial | 2 |
| session-30 | g.son0876@gmail.com | ok | 3 |
| session-31 | nij.irosimon@gmail.com | ok | 3 |
| session-32 | jae.denlunagna@gmail.com | ok | 2 |
| session-33 | tyraf.uega@gmail.com | trial | 2 |
| session-34 | jinshd.os@gmail.com | trial | 2 |
| session-35 | helloclaragarc.ia@gmail.com | ok | 3 |
| session-36 | jda.ka5408@gmail.com | ok | 3 |
| session-37 | r.ouvlachtandy@gmail.com | trial | 2 |
| session-38 | milkyb.abes982@gmail.com | trial | 2 |
| session-39 | ron.aeagomez@gmail.com | trial | 2 |
| session-40 | ech.oelrod@gmail.com | trial | 2 |
| session-41 | m.kszae@gmail.com | trial | 2 |
| session-42 | b9oc66m4ij97@emalupe.com | restricted | 2 |
| session-43 | y.amlavigne@gmail.com | ok | 3 |
| session-44 | hazeller.enabucas@gmail.com | trial | 2 |
| session-45 | samyvv.asquez@gmail.com | trial | 2 |
| session-46 | 1gqvpidgelqn@emalupe.com | restricted | 2 |
| session-47 | en.chatneddwasjjeksjs@gmail.com | trial | 2 |
| session-48 | kalilar.eigns@gmail.com | trial | 2 |
| session-49 | lauraesave.lina@gmail.com | trial | 2 |
| session-50 | karensapi.ntara@gmail.com | trial | 2 |
| session-51 | katehamada30.4@gmail.com | trial | 2 |
| session-52 | qdchs1l98p4a@emalupe.com | restricted | 2 |
| session-53 | feicfi.nsh@gmail.com | ok | 2 |
| session-54 | k.atefajerfoa@gmail.com | trial | 2 |
| session-55 | amyca.cayurana@gmail.com | trial | 2 |
| session-56 | kp7dpi0d6f3r@emalupe.com | restricted | 2 |
| session-57 | umwytpbr1k1f@emalupe.com | restricted | 2 |
| session-58 | yavb6qtxbrqv@emalupe.com | restricted | 2 |
| session-59 | 685hiph17p3r@emalupe.com | restricted | 2 |
| session-60 | ieaiylv10xrc@emalupe.com | restricted | 2 |
| session-61 | 5lzxp9xpiw2z@emalupe.com | restricted | 2 |
| session-62 | 9dlrziirqqar@emalupe.com | restricted | 2 |
| session-63 | 2lxgxxitnxep@emalupe.com | restricted | 2 |
| session-64 | aq9vx0h9c842@emalupe.com | restricted | 2 |
| session-65 | mtasfrmd5r39@emalupe.com | restricted | 2 |
| session-66 | uacq5zbv3r9y@emalupe.com | restricted | 2 |
| session-67 | q601heanlz8i@emalupe.com | restricted | 2 |
| session-68 | ks411c582koa@emalupe.com | restricted | 2 |
| session-69 | 3nzcgcvt01hs@emalupe.com | restricted | 2 |
| session-70 | fubh63zoueqj@emalupe.com | restricted | 2 |
| session-71 | hadcjbp2sn8x@emalupe.com | restricted | 2 |
| session-72 | f12xgp0gq881@emalupe.com | restricted | 2 |
| session-73 | q65vl7fsl85l@emalupe.com | restricted | 2 |
| session-74 | qnwa3u7em0a3@emalupe.com | ok | 3 |
| session-75 | gianprecin.io@gmail.com | ok | 3 |
| session-76 | jaden.kamisa@gmail.com | ok | 3 |
| session-77 | ellako.aasantoaa@gmail.com | ok | 4 |
| session-78 | moonto.rres350@gmail.com | trial | 2 |
| session-79 | moonto.rres350@gmail.com | trial | 2 |
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
| session-100 | 63i21v6mmp0f@emalupe.com | trial | 2 |
| session-101 | m8t4ie0jr2on@emalupe.com | ok | 2 |
| session-102 | pe9iitck2bes@emalupe.com | ok | 3 |
| session-103 | nxmvyb2qrk9x@emalupe.com | ok | 3 |
| session-104 | reurwi18fmne@emalupe.com | ok | 3 |
| session-105 | 18wvl2niigwd@emalupe.com | ok | 3 |
| session-106 | y.or.hun.2.7.7@gmail.com | ok | 3 |
| session-107 | mans.u.rk.urt.a.r.an5@gmail.com | ok | 4 |
| session-108 | ma.ns.ur.k.ur.t.a.ran.5@gmail.com | ok | 4 |
| session-109 | alac.a.ta.ri.k.177@gmail.com | ok | 2 |
