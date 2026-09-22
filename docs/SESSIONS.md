# Railway sessions (canonical live path)

Live verified tokens: `/home/alae/Documents/railways/session-*` (**44**, renumbered
2026-09-22 after create-service verify; 61 trial/bad culled).

OnKernel browser pool for farming: **Batch B only** — see [ONKERNEL.md](ONKERNEL.md)
(10 `tag=unlocked` keys, cookies + `__refresh_*`). Host-safe farm width: **`--par 20`**.

Use: `HOME=/home/alae/Documents/railways/session-N LD_PRELOAD='' railway whoami`

| session | email | project | service |
|---|---|---|---|
| session-1 | janic.ebunagna@gmail.com | - | - |
| session-2 | ghian.sean5@gmail.com | - | - |
| session-3 | ysmaelli.gaya@gmail.com | - | - |
| session-4 | jae.denlunagna@gmail.com | - | - |
| session-5 | helloclaragarc.ia@gmail.com | - | - |
| session-6 | jda.ka5408@gmail.com | - | - |
| session-7 | y.amlavigne@gmail.com | - | - |
| session-8 | feicfi.nsh@gmail.com | - | - |
| session-9 | m.an.s.u.rk.urt.a.r.an.5@gmail.com | cell-130-7c52d9 | hlth-130 |
| session-10 | ma.nsur.kur.tara.n.5@gmail.com | cell-131-9423bf | hlth-131 |
| session-11 | b.a.l.a.t.c.em.re@gmail.com | cell-132-b7d5ce | hlth-132 |
| session-12 | m.an.s.u.rk.ur.t.a.r.a.n.5@gmail.com | cell-133-8b416f | hlth-133 |
| session-13 | y.ava.s.h.use.y.in15@gmail.com | cell-134-47e4b8 | hlth-134 |
| session-14 | a.l.a.cat.a.rik.1.77@gmail.com | cell-135-61aa50 | hlth-135 |
| session-15 | al.a.cata.r.ik.17.7@gmail.com | cell-136-b0a3a5 | hlth-136 |
| session-16 | y.or.h.u.n27.7@gmail.com | cell-138-2f6a3c | hlth-138 |
| session-17 | 5homilvghwol@uberip.com | cell-139-7224c0 | hlth-139 |
| session-18 | woobnbzu336h@uberip.com | - | - |
| session-19 | k0tzc7luh0j1@uberip.com | - | - |
| session-20 | d8bkpdjljr6n@uberip.com | - | - |
| session-21 | ev76ca5ergz6@uberip.com | cell-143-04933d | hlth-143 |
| session-22 | w8dl0k13fivw@uberip.com | cell-144-ae536d | hlth-144 |
| session-23 | gd2sw0lxnbho@uberip.com | cell-145-74aaab | hlth-145 |
| session-24 | csgx4ahoqfgg@uberip.com | cell-146-287713 | hlth-146 |
| session-25 | abydo5vs0vhw@uberip.com | cell-147-9258d9 | hlth-147 |
| session-26 | 6dkc98lg6own@uberip.com | cell-148-31ccd4 | hlth-148 |
| session-27 | i0e10sl8jr3f@uberip.com | cell-149-28ee0a | hlth-149 |
| session-28 | w39iacmwjcys@uberip.com | cell-150-988f45 | hlth-150 |
| session-29 | ia90hox40a5l@uberip.com | cell-151-05eb6e | hlth-151 |
| session-30 | 1o5jtkn93zd7@uberip.com | cell-152-cb8f3a | hlth-152 |
| session-31 | vux6cwus91tc@uberip.com | cell-153-62c622 | hlth-153 |
| session-32 | ufm63lhmg4p7@uberip.com | cell-154-028ec2 | hlth-154 |
| session-33 | rxaien458q3u@uberip.com | cell-155-5134c8 | hlth-155 |
| session-34 | 6iuc4kooiyfh@uberip.com | cell-156-427955 | hlth-156 |
| session-35 | fuaa7hzk08tf@uberip.com | cell-157-8b1b3e | hlth-157 |
| session-36 | 57d5lnzrpkfk@uberip.com | cell-158-fa286f | hlth-158 |
| session-37 | 818idrf8u1dm@uberip.com | cell-159-24eee0 | hlth-159 |
| session-38 | pwxvwn6o2o1s@uberip.com | cell-160-21b670 | hlth-160 |
| session-39 | vykyr7mbtcjm@uberip.com | cell-161-0cc240 | hlth-161 |
| session-40 | atjm8h2rjdbi@uberip.com | cell-162-959326 | hlth-162 |
| session-41 | 063lsic3v9vr@uberip.com | cell-163-a07ca8 | hlth-163 |
| session-42 | 5sipc4ydq3du@uberip.com | cell-164-97821f | hlth-164 |
| session-43 | 3sw5equic9p4@uberip.com | cell-165-67eb45 | hlth-165 |
| session-44 | 70hhruuyjwdk@uberip.com | cell-166-443d50 | hlth-166 |

## Farm next

```bash
# host-safe width on 15Gi box (par 40/100 OOM'd)
LD_PRELOAD="" python3 src/railway/farm_onk_1k.py --target 1000 --par 20
```

See [ONKERNEL.md](ONKERNEL.md). Tokens stay local under `Documents/railways/` (not this
repo’s `sessions/` tree). Index emails above are safe to commit; CLI tokens are not.
