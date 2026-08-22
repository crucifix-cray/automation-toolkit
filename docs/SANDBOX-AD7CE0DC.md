# Sandbox ad7ce0dc — 22.do Pool + Proton → Warp Stack

**Created:** 2026-08-22 10:46 UTC  
**Project:** `sb-test-s3` `7c6dbd19-f6be-4ca0-81ee-7b788a940782` `production` `c8a9d7b2-492c-4d47-9c80-47cbc5488384` `My Projects` `d04eb052`  
**Account:** `869fcf30` `s.hie.ldsleon.ardo.27.7@gmail.com` (session-3, token refreshed `D-tWA6...` expires 1787399321)  
**Region:** `us-west2` `5m idle` `2vcpu 1GB + 8G swap`

## Inside (live)

- `/root/repos/automation-toolkit` + `chimera-miner` cloned via `crucifix-cray` token `ghp_5uZN...`
- `rclone v1.75` configured (`mega` emilypeterson30) — `mega:protonvpn` → `/tmp/proton` (96 ovpn + `credentials.txt` → `/tmp/auth.txt` 2-line fix), `mega:chimera/wgcf-pool` → `/tmp/wgcf-pool`
- `apt: unzip openvpn wireguard-tools iproute2` + `wgcf 2.2.22` + `wireproxy 1.0.9`

## Network Stack — Proton → Warp

- **Proton OpenVPN:** `/tmp/proton_tcp.ovpn` (converted `proto udp` → `tcp`, remote `151.243.141.162:443` `node-us-417`) via `--auth-user-pass /tmp/auth.txt` (fixed header bug) → `tun0 10.98.0.6/16` `redirect-gateway def1` `PUSH_REPLY` `Initialization Sequence Completed`
- **Verify proton:** `curl --interface tun0 ifconfig.me` → `155.117.189.75` `loc US warp=off`
- **Warp (above proton):** `wireproxy` with `wgcf-profile.conf` `oAclmSIH...` + `[Socks5] 127.0.0.1:40000` → `LISTEN 127.0.0.1:40000` `104.28.202.184 EWR warp=on` via `tun0` (pro usa)
- **Stack:** `browser socks5://127.0.0.1:40000 bypass 127.0.0.1,localhost` → `warp 104.28.202.184` → `proton 155.117.189.75` → `eth0 10.250.12.114`
- **Previous bug:** `credentials.txt` had `Username: / Password:` header → auth failed (no PUSH_REPLY), fixed to 2-line `auth.txt`; UDP 1194 stuck `PUSH_REQUEST x5`, TCP 443 works.

## Usage

```bash
# pick random ovpn then warp above it (per-run different country)
OVPN=$(ls /tmp/proton/*.ovpn | shuf -n1); sed 's/proto udp/proto tcp/; s/remote .*/remote $(grep remote $OVPN | awk "{print \$2}") 443/' $OVPN > /tmp/proton_tcp.ovpn
openvpn --config /tmp/proton_tcp.ovpn --auth-user-pass /tmp/auth.txt --verb 3 --log /tmp/ovpn.log --daemon
# warp already running on 40000 above tun0
xvfb-run -a python3 /root/repos/automation-toolkit/railway-docker/railway-HOLY-22do-full.py --domain @linshiyou.com
xvfb-run -a python3 -u /root/repos/automation-toolkit/test_22do.py --recov "g92w@colabeta.com"
```

## Next

- Keepalive `while true; curl --socks5 ... ifconfig.me; sleep 240` to avoid 5m idle kill.
- Per-run: `shuf` different `*.ovpn` (ca/ch/jp/us) + `random.choice(HANDLERS)` 10 handlers + warp above.

## Status 2026-08-22 11:05 — Paused

- Test `railway-HOLY-22do-full.py --domain @linshiyou.com` halted at `patchright install` (needed `patchright install` not `playwright install`, branch mismatch). Dependencies: `apt xvfb` + `pip patchright playwright` + `patchright install` + `playwright install-deps firefox` done, next run ready via `xvfb-run -a`.
- Sandbox still RUNNING `ad7ce0dc` — pool + warp stack verified, ready for next test. Stopped per user request before full Railway account creation attempt.
- Next: `xvfb-run -a python3 -u /root/repos/automation-toolkit/railway-docker/railway-HOLY-22do-full.py` (random pool) after `patchright install` completes.
