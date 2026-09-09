# Railway Sessions Registry

All session configs live in `mega:railway_sessions/` (local mirror: `Documents/railways/`).

| # | Session dir | User ID | Email | Project | Token |
|---|---|---|---|---|---|
| 1 | `session-3/` | (implicit) | dispose `cruzjanet87.5@gmail.com` | `scraper-svc` (d3846bbd) | rw.session cookie + browser_cookies.json |
| 2 | `session-4/` | (implicit) | dispose `ae.lexclement@gmail.com` | `test-session-1787133751` (03ecfc9e) | rw.session cookie + browser_cookies.json |
| 3 | `session-test/` | `dd8c8dd2-a0f6-43ac-b0aa-1fd445e98e2c` | `ha.nseltw.edt99@gmail.com` (*discovered 2026-08-19 via config-swap whoami*) | `zonal-motivation` (default) + sandbox 1c06dae0 us-west2 | accessToken `c9Gpx6Fu...` — refreshable, HAS CREDIT (fresh trial) |
| 4 | `session-test2/` | `6ae03701-a9e5-4960-a335-ec4f77f7d68e` | `katrinawat.sonlaos@gmail.com` | `test-session-1787133751` (03ecfc9e) | token `ymUHxsES` |
| 5 | `credit_accounts/gabrielgreen14/` | `c8f24b60...` | `gabrielgreen14@web.sytchamptoncc.co.uk` | (ssh/ keys present) | — |

Mailboxes:

- session-3, session-4 → dispose.lol (`mailboxKey` inside `browser_cookies.json` `dispose_mailbox` cookie). Mail check = open `https://dispose.lol/mailbox/<address>/` in a browser (page is JS-rendered; plain curl gets nothing).
- session-test → ha.nseltw.edt99@gmail.com (dispose service, mailbox not yet inspected).
- session-test2 → real gmail (katrinawat.sonlaos@gmail.com).
- gabrielgreen14 → temp-mail domain web.sytchamptoncc.co.uk (MX: mail.cleantempmail.com).

Notes:

- 4 unique emails across 5 sessions; session-test was previously marked "no email" but is actually `ha.nseltw.edt99@gmail.com`.
- 3 of the sessions link to project `03ecfc9e` (test-session-1787133751). session-3 links to scraper-svc.
- `mega:railway_sessions` = railway CLI configs only. `mega:lovable_sessions/` = Lovable cookies. `mega:chimera/database.json` = Lovable miner DB. Do not touch the wrong one.