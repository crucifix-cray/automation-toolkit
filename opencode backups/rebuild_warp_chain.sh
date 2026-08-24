#!/bin/bash
NS="warp-1"
log(){ echo "[$(date +%T)] $1" >> /tmp/rebuild_status.log; }
echo "" > /tmp/rebuild_status.log
log "start"
# tear down
sudo pkill -f "openvpn.*ovpn" 2>/dev/null; sudo pkill -f microsocks 2>/dev/null; sudo pkill -f "socat.*40000" 2>/dev/null
sleep 2
sudo ip netns exec "$NS" ip link del wg0 2>/dev/null
# netns default MUST be via veth so ovpn can reach its server
sudo ip netns exec "$NS" ip route replace default via 10.200.1.1 dev veth-w1n
# fresh ovpn
cd /tmp/proton
OVPN=$(ls *.ovpn | grep -i "nl-free" | shuf -n1)
log "OVPN=$OVPN"
sudo ip netns exec "$NS" openvpn --config "/tmp/proton/$OVPN" --auth-user-pass /tmp/auth.txt --daemon --log /tmp/ovpnR.log --writepid /tmp/ovpnR.pid
# wait for tun0
for i in $(seq 1 25); do
  if sudo ip netns exec "$NS" ip link show tun0 >/dev/null 2>&1; then log "tun0 up after ${i}s"; break; fi
  sleep 1
done
if ! sudo ip netns exec "$NS" ip link show tun0 >/dev/null 2>&1; then log "ERROR: tun0 never came up"; tail -5 /tmp/ovpnR.log >> /tmp/rebuild_status.log; exit 1; fi
# fresh wgcf
POOL=/home/alan/Documents/mega_dumps/chimera/wgcf-pool
SRC=$(find "$POOL" -name wgcf-profile.conf 2>/dev/null | shuf -n1)
log "WGCF=$SRC"
cp "$SRC" /tmp/wgR.conf
sed -i -E 's/^Endpoint\s*=.*/Endpoint = 162.159.192.1:2408/' /tmp/wgR.conf
PK=$(grep -i "^PrivateKey" /tmp/wgR.conf | awk '{print $3}')
PUB=$(grep -i "^PublicKey" /tmp/wgR.conf | awk '{print $3}')
ADDR=$(grep -i "^Address" /tmp/wgR.conf | head -1 | awk '{print $3}')
ADDR6=$(grep -i "^Address" /tmp/wgR.conf | grep ":" | awk '{print $3}' | head -1)
echo "$PK" | sudo tee /root/wgR.key >/dev/null
sudo ip netns exec "$NS" ip link add wg0 type wireguard
sudo ip netns exec "$NS" wg set wg0 private-key /root/wgR.key peer "$PUB" endpoint 162.159.192.1:2408 allowed-ips 0.0.0.0/0,::/0 persistent-keepalive 25
sudo ip netns exec "$NS" ip addr add "$ADDR" dev wg0
sudo ip netns exec "$NS" ip addr add "$ADDR6" dev wg0 2>/dev/null
sudo ip netns exec "$NS" ip link set wg0 up
# endpoint via tun0 (ovpn), then wg0 default
sudo ip netns exec "$NS" ip route add 162.159.192.1/32 via 10.96.0.1 dev tun0 2>/dev/null
sudo ip netns exec "$NS" ip route del 0.0.0.0/1 2>/dev/null; sudo ip netns exec "$NS" ip route del 128.0.0.0/1 2>/dev/null
sudo ip netns exec "$NS" ip route replace default dev wg0
sudo ip netns exec "$NS" ip -6 route add default dev wg0 2>/dev/null
sleep 3
# proxies
sudo setsid ip netns exec "$NS" microsocks -i 10.200.1.2 -p 40001 >/tmp/microsocksR.log 2>&1 </dev/null &
sudo setsid socat TCP-LISTEN:40000,fork,reuseaddr,bind=127.0.0.1 TCP:10.200.1.2:40001 >/tmp/socatR.log 2>&1 </dev/null &
sleep 2
log "DONE proxies up"
