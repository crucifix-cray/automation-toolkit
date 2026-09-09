# OVPN + WARP Persistent Setup (No TUN)

`Ubuntu 24.04` `railway` `persistent` `test-ubuntu-6` `2e7ef06d-660e-4da2-87e3-1cc37693889b` `jzwvvhj4934m+vla1ycoqmow59@outlook.com` `cc45a970-...` `RuSufgc...`

## Why no TUN
`railway` `container` `no /dev/net/tun` `openvpn` `TUN/TAP No such file` `even` `socks-proxy 127.0.0.1:40000` `still` `TUN` `fail` `wireproxy` `userspace` `gVisor` `ok`.

## Build
```bash
apt-get update -qq; apt-get install -y -qq build-essential autoconf automake libtool libssl-dev liblzo2-dev libpam0g-dev liblz4-dev pkg-config libevent-dev unzip
# openvpn-tunpipe
cd /tmp; rm -rf openvpn-tunpipe; git clone https://github.com/ValdikSS/openvpn-tunpipe.git
cd /tmp/openvpn-tunpipe; autoreconf -i; ./configure; make -j4 # src/openvpn/openvpn 4.0M
# tunsocks
cd /tmp; rm -rf tunsocks; git clone https://github.com/russdill/tunsocks.git
cd /tmp/tunsocks; rm -rf lwip*; git submodule update --init --recursive
apt-get install -y -qq libevent-dev; make -j4 LIBS='-levent -levent_core -levent_extra' # tunsocks 850K
# wireproxy
go install github.com/windtf/wireproxy/cmd/wireproxy@latest # ~/go/bin/wireproxy go1.26.7
# wgcf
# 245 valid wgcf-profile.conf from /home/alan/Documents/mega_dumps/chimera/wgcf-pool (1378 total, shuf)
# proton
rclone copy mega:protonvpn /tmp/proton --mega-use-https # 97 ovpn, credentials.txt 0yqflkJmsb5Xr6Rz / Z1zZ...
printf '0yqflkJmsb5Xr6Rz\nZ1zZ0ikBbZJ5IE5imnJwbWFvOneuYINO\n' > /tmp/auth.txt
```

## Run
```bash
# warp
POOL=$(ls /tmp/wgcf-pool/*/wgcf-profile.conf | shuf -n1 | xargs dirname)
printf "WGConfig = $POOL/wgcf-profile.conf\n[Socks5]\nBindAddress = 127.0.0.1:40000\n" > /tmp/warp.conf
nohup ~/go/bin/wireproxy -c /tmp/warp.conf > /tmp/wireproxy.log 2>&1 &
curl --socks5 127.0.0.1:40000 -s https://www.cloudflare.com/cdn-cgi/trace | grep warp # warp=on ip=104.28.251.147

# ovpn via tunsocks (no TUN)
OVPN=$(ls /tmp/proton/*.ovpn | shuf -n1); REMOTE_IP=$(grep -m1 "^remote " "$OVPN" | awk "{print $2}")
sed "s/^proto udp/proto tcp/; s/^remote .*/remote $REMOTE_IP 443/" "$OVPN" > /tmp/proton_tun.ovpn
timeout 30 /tmp/openvpn-tunpipe/src/openvpn/openvpn --config /tmp/proton_tun.ovpn --auth-user-pass /tmp/auth.txt --verb 1 --script-security 2 --dev "|/tmp/tunsocks/tunsocks -D 127.0.0.1:1080" > /tmp/ovpn_tun.log 2>&1 &
sleep 10
curl --socks5 127.0.0.1:1080 -s https://ifconfig.me # 185.177.125.53 NL warp=off
curl --socks5 127.0.0.1:1080 -s https://www.cloudflare.com/cdn-cgi/trace | grep -E "ip|warp|loc"

# ovpn via warp (chain)
# add to ovpn: socks-proxy 127.0.0.1 40000  (makes ovpn TCP via warp socks)
# or make wireproxy use ovpn socks as upstream (not needed, separate per run shuf is human)

# holy
# bypass railway.com,22.do for direct, warp for Turnstile
# proxy_settings = {"server": "socks5://127.0.0.1:40000", "bypass": "127.0.0.1,localhost,22.do,*.22.do,railway.com,*.railway.com,*.railway.app,backboard.railway.com"}
# playwright-captcha 0.1.5 + playwright 1.62.0 + patchright chromium-1234 chrome 151.0.7922.173 xvfb
timeout 300 xvfb-run -a --server-args='-screen 0 1280x720x24' python3 -u /root/automation-toolkit/railway-docker/railway-HOLY-22do-full.py --domain "@gmail.com"
# OTP 722355 poll1 iframe Logged in
```

## Persistent
`rclone config` `mega` `emilypeterson30@mail.findmeghana.org` `--mega-use-https` `counter 2` `session-1 eyx1...@usdtbeta.com session-2 st.ode...@gmail.com` `good` `jzw` `session-3` restored `counter 3` `jzwvvhj...@outlook.com` `RuSufgc...`
`railway ssh --service "Ubuntu 24.04" -- "ps aux; cat /tmp/holy_*.log"` `test-ubuntu-6` `running:1` `ams` `https://ubuntu-railway-production-c797.up.railway.app` `admin/admin123`
