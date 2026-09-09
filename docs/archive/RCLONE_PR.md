# rclone-pr — Proton OVPN isolated rclone for MEGA

`~/.local/bin/rclone-pr` ensures `Mega` always runs via **Proton OVPN** `149.40.62.31` `tun1` inside `vpnns` netns, fixing `suspicious activity` / `ban` on raw `105.156.62.152` Fes / `tor` `41.142.27.203` Quintex exit. Based on `~/.vpn-tunnel/start-tunnel.sh` `196` lines.

## Why

- `opencode` runs Tor-wrapped (`LD_PRELOAD` + `127.0.0.1:9251` `204.8.96.85` Quintex) → `MEGA` `g.api.mega.co.nz` `ban` (`login with previous auth keys failed: unexpected end of JSON`, `suspicious activity` on Lovable even with `Token 837`).
- Raw `105.156.62.152` `ADSL Maroc` Fes residential also flagged after `Mega!Str0ng-Pw_2026xZ` update.
- `mega:chimera/zenrows` `ls` worked but `cat`/`copy` on `gfs*.userstorage.mega.co.nz` hit `EOF` `TLS_RSA_WITH_AES_128_GCM_SHA256` (Go1.22+, `rclone#8565`) → needs `GODEBUG=tlsrsakex=1`.

## OVPN

`rclone copy mega:protonvpn /tmp/proton --mega-use-https` → `97` `*.ovpn` `ch-free-2` etc. + `credentials.txt` `0yqflkJmsb5Xr6Rz / Z1zZ...` (`/tmp/auth.txt`). From `docs/OVPN_WARP_PERSISTENT.md:23-42`.

```bash
OVPN=$(ls /tmp/proton/*.ovpn | shuf -n1); REMOTE_IP=$(grep -m1 "^remote " "$OVPN" | awk "{print \$2}")
sed "s/^proto udp/proto tcp/; s/^remote .*/remote $REMOTE_IP 443/" "$OVPN" > /tmp/proton_tun.ovpn
timeout 30 /tmp/openvpn-tunpipe/src/openvpn/openvpn --config /tmp/proton_tun.ovpn --auth-user-pass /tmp/auth.txt --verb 1 --script-security 2 --dev "|/tmp/tunsocks/tunsocks -D 127.0.0.1:1080"
# or via netns: start-tunnel.sh --no-warp -> tun1 149.40.62.31/149.40.62.35 US Proton, no WARP
```

`start-tunnel.sh` (`--no-warp`): `openvpn --config /tmp/ovpn-fixed.conf --dev tun1 --daemon` (`<ca>`+`<tls-crypt>` from `protonvpn-isolated.ovpn` `149.40.62.31 1194` `AES-256-GCM`, `auth-user-pass /home/alae/.vpn-tunnel/credentials.txt`) → `tun1` inside `vpnns` `10.200.0.0/30` `veth` NAT, `OVPN_IP` via `ip netns exec vpnns curl -s https://ipinfo.io/ip` → `149.40.62.34/35`.

App launcher: `~/.vpn-tunnel/start-tunnel.sh` `196` lines — `ovpn-fixed.conf` `/tmp/ovpn-fixed.conf`, `warp.key` `/home/alae/.vpn-tunnel/warp.key` `bmXOC+...` `162.159.192.1:2408` `warp-wg`, `chrome-profile` `~/.vpn-tunnel/chrome-profile` (`--no-warp` → `chrome-profile-ovpn`).

## rclone-pr

`~/.local/bin/rclone-pr` (`chmod +x`):
```bash
#!/bin/bash
set -e
NS="vpnns"
if ! sudo ip netns exec "$NS" ip link show tun1 >/dev/null 2>&1; then
  sudo bash /home/alae/.vpn-tunnel/start-tunnel.sh --no-warp >/tmp/rclone-pr-ovpn.log 2>&1 &
  for i in $(seq 1 30); do sudo ip netns exec "$NS" ip link show tun1 >/dev/null 2>&1 && break; sleep 1; done
fi
exec sudo ip netns exec "$NS" sudo -u alae env GODEBUG=tlsrsakex=1 LD_PRELOAD='' rclone "$@"
```

- Auto-starts `ovpn` if `tun1` down (`--no-warp` so only `149.40.62.31` Proton, not `warp` `172.16.0.2`).
- Always runs `rclone` **inside** `vpnns` as `alae` with `GODEBUG=tlsrsakex=1` (fixes `rclone#8565` `TLS_RSA` `EOF` on `gfs302n125` etc.) + `LD_PRELOAD=''` (bypass `opencode-tor` wrapper).

## Sync Mega → Local

```bash
# Full Mega (needs fresh login after Mega!Str0ng-Pw_2026xZ)
rclone config update mega session_id "" master_key ""  # force MultiFactorLogin via ovpn IP
~/.local/bin/rclone-pr ls mega:chimera/zenrows --retries 1 # should show 4 keys
~/.local/bin/rclone-pr sync mega: /tmp/mega_full --retries 1 --transfers 4
ls /tmp/mega_full/railway_sessions/session-1/email.txt && cat $_
# Or specific
~/.local/bin/rclone-pr sync mega:chimera/zenrows /tmp/zenrows_sync
~/.local/bin/rclone-pr sync mega:railway_sessions /tmp/railway_sync
~/.local/bin/rclone-pr sync mega:brightdata /tmp/brightdata_sync
```

Raw `41.142.27.203` `g.api`/`gfs` + `105.156.62.152` `Fes` both **banned**, `tor` `204.8.96.85` also `suspicious` — **only `vpnns` `149.40.62.34` Proton `US` residential currently lets `rclone ls` work** (before `pass` update `MPyPxJUBre...` was created via `Fes` raw, now need fresh login via `vpnns`).

## Verify

```bash
sudo ip netns exec vpnns curl -s https://ipinfo.io/ip # should be 149.40.62.34
/home/alae/.local/bin/rclone-pr ls mega:chimera/zenrows
cat /tmp/zenrows_sync/zenrows_new_key.txt
```

If `login with previous auth keys failed: unexpected end of JSON` persists, `mega-login` via `vpnns` `RDP` residential `86.141` `BT` as you saw web login works there.
