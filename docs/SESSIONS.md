# Railway Sessions Index (canonical)

107 live Railway accounts. Verified 2026-09-09 via raw-IP `railway whoami` P20: **107/107 OK**.
Raw egress that day: `160.177.74.223 MA warp=off`, no proxy env, `railway 5.43.4`.

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
Token backup outside repo: `~/railway_tokens_backup/railway_tokens_2026-09-09.tar.gz` (+/tmp/railbk).

## Rules (proven 2026-09-09)

1. `HOME=/home/alan/Documents/railways/sessions/session-N LD_PRELOAD="" railway whoami` — CLI reads
   `$HOME/.railway/config.json`. No other setup. Strip proxy env for raw IP.
2. Expired accessToken is FINE: `whoami` auto-refreshes via refreshToken in place
   (e.g. session-10 `1788026029 Aug29 -> 1788967396 Sep09`). Do NOT re-farm on `Unauthorized`
   before trying one `whoami` (it self-heals).
3. If `.railway/config.json` goes missing (CLI auto-update wiped them once):
   `cp railway_cli_config.json .railway/config.json` then `whoami`.
4. Bulk: `ls -d sessions/session-* | xargs -P20 ... railway whoami` or `python3 scripts/railway_audit.py`.
5. Never commit tokens. Never farm duplicates of these emails.

## Notes

- `session-14` does not exist (numbering gap). `session-78` + `session-79` share
  `moonto.rres350@gmail.com` (dup); `session-12`/`session-96` similar j.molay variants.
- Old notes moved to `docs/archive/`. Old scripts/railways (5 tracked live tokens) +
  scripts/sessions (43 empty) removed 2026-09-09 — single source is `sessions/`.

## Accounts

| session | email |
|---|---|
| session-1 | 904x1b2h4avw@emalupe.com |
| session-2 | st.odezgdvkp+odytn8e1il@gmail.com |
| session-3 | jzwvvhj4934m+vla1ycoqmow59@outlook.com |
| session-4 | bsu.ejjrue.kis8.0.9+bxbqr9ff@gmail.com |
| session-5 | nlvnod39153u+jm7mu6cj9m01hh5@outlook.com |
| session-6 | tha.t.huchoem0.1.8@gmail.com |
| session-7 | s2d6bjrla38o@emalupe.com |
| session-8 | f1ygzor9x8pa@emalupe.com |
| session-9 | 0ybiva47sesh@emalupe.com |
| session-10 | harp.ergestrice@gmail.com |
| session-11 | ammyymore.noo@gmail.com |
| session-12 | jasper.molay@gmail.com |
| session-13 | vallescasbonifa.cio4@gmail.com |
| session-15 | abbigailvorcabu.no@gmail.com |
| session-16 | mendo.zakian56@gmail.com |
| session-17 | lo.peracamie@gmail.com |
| session-18 | vian.nabartolome@gmail.com |
| session-19 | velvetkiss08.2@gmail.com |
| session-20 | adis.wuechl@gmail.com |
| session-21 | l.ilacelrod@gmail.com |
| session-22 | na.tanhielriverra@gmail.com |
| session-23 | she.yhayaishi@gmail.com |
| session-24 | er99114.34@gmail.com |
| session-25 | ro.schelenavaara@gmail.com |
| session-26 | gla.msolace@gmail.com |
| session-27 | jean.netteejavier@gmail.com |
| session-28 | b.ineneabea@gmail.com |
| session-29 | jeni.sisfajardo@gmail.com |
| session-30 | g.son0876@gmail.com |
| session-31 | nij.irosimon@gmail.com |
| session-32 | jae.denlunagna@gmail.com |
| session-33 | tyraf.uega@gmail.com |
| session-34 | jinshd.os@gmail.com |
| session-35 | helloclaragarc.ia@gmail.com |
| session-36 | jda.ka5408@gmail.com |
| session-37 | r.ouvlachtandy@gmail.com |
| session-38 | milkyb.abes982@gmail.com |
| session-39 | ron.aeagomez@gmail.com |
| session-40 | ech.oelrod@gmail.com |
| session-41 | m.kszae@gmail.com |
| session-42 | b9oc66m4ij97@emalupe.com |
| session-43 | y.amlavigne@gmail.com |
| session-44 | hazeller.enabucas@gmail.com |
| session-45 | samyvv.asquez@gmail.com |
| session-46 | 1gqvpidgelqn@emalupe.com |
| session-47 | en.chatneddwasjjeksjs@gmail.com |
| session-48 | kalilar.eigns@gmail.com |
| session-49 | lauraesave.lina@gmail.com |
| session-50 | karensapi.ntara@gmail.com |
| session-51 | katehamada30.4@gmail.com |
| session-52 | qdchs1l98p4a@emalupe.com |
| session-53 | feicfi.nsh@gmail.com |
| session-54 | k.atefajerfoa@gmail.com |
| session-55 | amyca.cayurana@gmail.com |
| session-56 | kp7dpi0d6f3r@emalupe.com |
| session-57 | umwytpbr1k1f@emalupe.com |
| session-58 | yavb6qtxbrqv@emalupe.com |
| session-59 | 685hiph17p3r@emalupe.com |
| session-60 | ieaiylv10xrc@emalupe.com |
| session-61 | 5lzxp9xpiw2z@emalupe.com |
| session-62 | 9dlrziirqqar@emalupe.com |
| session-63 | 2lxgxxitnxep@emalupe.com |
| session-64 | aq9vx0h9c842@emalupe.com |
| session-65 | mtasfrmd5r39@emalupe.com |
| session-66 | uacq5zbv3r9y@emalupe.com |
| session-67 | q601heanlz8i@emalupe.com |
| session-68 | ks411c582koa@emalupe.com |
| session-69 | 3nzcgcvt01hs@emalupe.com |
| session-70 | fubh63zoueqj@emalupe.com |
| session-71 | hadcjbp2sn8x@emalupe.com |
| session-72 | f12xgp0gq881@emalupe.com |
| session-73 | q65vl7fsl85l@emalupe.com |
| session-74 | qnwa3u7em0a3@emalupe.com |
| session-75 | gianprecin.io@gmail.com |
| session-76 | jaden.kamisa@gmail.com |
| session-77 | ellako.aasantoaa@gmail.com |
| session-78 | moonto.rres350@gmail.com |
| session-79 | moonto.rres350@gmail.com |
| session-80 | renya.yae758@gmail.com |
| session-81 | julietsauc.elo@gmail.com |
| session-82 | katec.larizze@gmail.com |
| session-83 | mun.ozkaia54@gmail.com |
| session-84 | ji.lleaponteras@gmail.com |
| session-85 | mdq9ev0wg4fd@emalupe.com |
| session-86 | lkri.sha39@gmail.com |
| session-87 | ingr.idelrod@gmail.com |
| session-88 | breefins.h@gmail.com |
| session-89 | noykidzca.stro@gmail.com |
| session-90 | luz.vimindaaaguevarra@gmail.com |
| session-91 | cassandrabacuda.l@gmail.com |
| session-92 | f.r4ncis30@gmail.com |
| session-93 | unicere.yess@gmail.com |
| session-94 | ell.izabetharagones@gmail.com |
| session-95 | danic.asenatubis@gmail.com |
| session-96 | jaspe.rmolay@gmail.com |
| session-97 | qd1t8martppn@emalupe.com |
| session-98 | z0xuce04ifaz@emalupe.com |
| session-99 | 9d1l7zfcgq3g@emalupe.com |
| session-100 | 63i21v6mmp0f@emalupe.com |
| session-101 | m8t4ie0jr2on@emalupe.com |
| session-102 | pe9iitck2bes@emalupe.com |
| session-103 | nxmvyb2qrk9x@emalupe.com |
| session-104 | reurwi18fmne@emalupe.com |
| session-105 | 18wvl2niigwd@emalupe.com |
| session-106 | y.or.hun.2.7.7@gmail.com |
| session-107 | mans.u.rk.urt.a.r.an5@gmail.com |
| session-108 | ma.ns.ur.k.ur.t.a.ran.5@gmail.com |
