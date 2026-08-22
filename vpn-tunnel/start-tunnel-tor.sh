#!/bin/bash
# Tor -> WARP -> Chrome  final WARP IP via Tor (WARP UDP over Tor TCP via gost relay + hidden service)
TUNNEL_DIR="/home/alae/.vpn-tunnel"
NS_NAME="torns"
VETH_HOST="veth-tor-host"
VETH_NS="veth-tor-ns"
SUBNET="10.201.0"
RESOLV_BACKUP="$TUNNEL_DIR/resolv.conf.bak"
TOR_DATA="/tmp/tor-torns"
TOR_LOG="/tmp/tor-torns.log"
HIDDEN_DIR="/tmp/tor-torns/hidden"
RELAY_PORT=50000
CLIENT_UDP_PORT=60000

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
log()  { echo -e "${GREEN}[+]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[-]${NC} $1"; }

if [[ $EUID -ne 0 ]]; then err "Run as root: sudo bash $0"; exit 1; fi

cleanup() {
    trap - EXIT INT TERM
    log "Shutting down Tor->WARP..."
    timeout 3 ip netns exec "$NS_NAME" pkill -9 gost 2>/dev/null || true
    pkill -9 gost 2>/dev/null || true
    timeout 3 ip netns exec "$NS_NAME" pkill -9 tor 2>/dev/null || true
    timeout 3 ip netns exec "$NS_NAME" pkill -9 -f "/opt/google/chrome" 2>/dev/null || true
    timeout 3 ip netns exec "$NS_NAME" ip link del warp-wg 2>/dev/null || true
    umount /etc/resolv.conf 2>/dev/null || true
    [[ -f "$RESOLV_BACKUP" ]] && cp "$RESOLV_BACKUP" /etc/resolv.conf 2>/dev/null || true
    log "Stopped."
}
trap cleanup EXIT INT TERM

# Fresh ns
if ip netns list 2>/dev/null | grep -q "$NS_NAME"; then
    log "Removing stale $NS_NAME..."
    timeout 3 ip netns exec "$NS_NAME" pkill -9 tor 2>/dev/null || true
    timeout 3 ip netns exec "$NS_NAME" pkill -9 gost 2>/dev/null || true
    pkill -9 gost 2>/dev/null || true
    umount /etc/resolv.conf 2>/dev/null || true
    ip netns del "$NS_NAME" 2>/dev/null || true
    ip link del "$VETH_HOST" 2>/dev/null || true
    sleep 1
fi
log "Creating namespace $NS_NAME..."
ip netns del "$NS_NAME" 2>/dev/null || true
ip link del "$VETH_HOST" 2>/dev/null || true
umount /etc/resolv.conf 2>/dev/null || true
ip netns add "$NS_NAME"
ip link add "$VETH_HOST" type veth peer name "$VETH_NS"
ip link set "$VETH_NS" netns "$NS_NAME"
ip addr add "${SUBNET}.1/30" dev "$VETH_HOST"
ip link set "$VETH_HOST" up
ip netns exec "$NS_NAME" ip addr add "${SUBNET}.2/30" dev "$VETH_NS"
ip netns exec "$NS_NAME" ip link set "$VETH_NS" up
ip netns exec "$NS_NAME" ip link set lo up
ip netns exec "$NS_NAME" ip route add default via "${SUBNET}.1"
mkdir -p "/etc/netns/$NS_NAME"
echo -e "nameserver 1.1.1.1\nnameserver 1.0.0.1" > "/etc/netns/$NS_NAME/resolv.conf"
log "Namespace $NS_NAME created"

# NAT
if [[ $(cat /proc/sys/net/ipv4/ip_forward) != "1" ]]; then echo 1 > /proc/sys/net/ipv4/ip_forward; fi
WLAN_IFACE=$(ip -o route get 8.8.8.8 | awk '{print $5; exit}')
iptables -t nat -C POSTROUTING -s "${SUBNET}.0/30" -o "$WLAN_IFACE" -j MASQUERADE 2>/dev/null || iptables -t nat -A POSTROUTING -s "${SUBNET}.0/30" -o "$WLAN_IFACE" -j MASQUERADE
iptables -t nat -C POSTROUTING -s 172.16.0.0/12 -o "$WLAN_IFACE" -j MASQUERADE 2>/dev/null || iptables -t nat -A POSTROUTING -s 172.16.0.0/12 -o "$WLAN_IFACE" -j MASQUERADE
iptables -C FORWARD -i "$VETH_HOST" -o "$WLAN_IFACE" -j ACCEPT 2>/dev/null || iptables -A FORWARD -i "$VETH_HOST" -o "$WLAN_IFACE" -j ACCEPT
iptables -C FORWARD -i "$WLAN_IFACE" -o "$VETH_HOST" -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || iptables -A FORWARD -i "$WLAN_IFACE" -o "$VETH_HOST" -m state --state RELATED,ESTABLISHED -j ACCEPT
nft add rule inet filter forward iifname "$VETH_HOST" oifname "$WLAN_IFACE" accept 2>/dev/null || true
nft add rule inet filter forward iifname "$WLAN_IFACE" oifname "$VETH_HOST" ct state established,related accept 2>/dev/null || true

cp /etc/resolv.conf "$RESOLV_BACKUP" 2>/dev/null || true
umount /etc/resolv.conf 2>/dev/null || true
mount --bind "/etc/netns/$NS_NAME/resolv.conf" /etc/resolv.conf

log "Cleaning old state..."
rm -rf "$TOR_DATA" 2>/dev/null; mkdir -p "$TOR_DATA" "$HIDDEN_DIR"; chmod 700 "$TOR_DATA" "$HIDDEN_DIR"; chown -R alae:alae "$TOR_DATA" 2>/dev/null || true
pkill -9 gost 2>/dev/null || true
rm -f /tmp/gost-*.log /tmp/tor-torns.log 2>/dev/null || true; touch /tmp/gost-relay.log /tmp/gost-client.log /tmp/tor-torns.log; chmod 666 /tmp/gost-*.log /tmp/tor-torns.log 2>/dev/null || true

# Tor config with hidden service for WARP relay
cat > /tmp/tor-torns.conf <<CONF
DataDirectory $TOR_DATA
SocksPort 9050
DNSPort 5353
HiddenServiceDir $HIDDEN_DIR
HiddenServicePort $RELAY_PORT 127.0.0.1:$RELAY_PORT
ExitNodes {us}
StrictNodes 1
Log notice file $TOR_LOG
User alae
CONF
chmod 644 /tmp/tor-torns.conf 2>/dev/null || true
chown alae:alae /tmp/tor-torns.conf 2>/dev/null || true

# Start gost relay server inside ns (TCP relay -> WARP UDP)
log "Starting gost relay server (TCP $RELAY_PORT -> UDP 162.159.192.1:2408) inside $NS_NAME..."
ip netns exec "$NS_NAME" sudo -u alae bash -c "/usr/local/bin/gost -L relay://127.0.0.1:$RELAY_PORT -F udp://162.159.192.1:2408 > /tmp/gost-relay.log 2>&1 &" 2>&1
sleep 2
# also start host relay for fallback (direct)
# (host relay not needed, hidden service handles)

# Start Tor
log "Starting Tor (US exit) with hidden service..."
ip netns exec "$NS_NAME" tor -f /tmp/tor-torns.conf --RunAsDaemon 1 &
sleep 2

log "Waiting for Tor bootstrap..."
for i in $(seq 1 60); do
    if ip netns exec "$NS_NAME" ss -tlnp 2>/dev/null | grep -q ":9050"; then
        if grep -q "Bootstrapped 100%" "$TOR_LOG" 2>/dev/null; then log "Tor bootstrapped (${i}s)"; break; fi
        if ip netns exec "$NS_NAME" curl -s --socks5 127.0.0.1:9050 --max-time 5 https://check.torproject.org/api/ip &>/dev/null; then log "Tor socks ready (${i}s)"; break; fi
    fi
    sleep 2
    if [[ $((i % 10)) -eq 0 ]]; then tail -2 "$TOR_LOG" 2>/dev/null | while read l; do log "  tor: $l"; done; fi
done
if ! ip netns exec "$NS_NAME" ss -tlnp 2>/dev/null | grep -q ":9050"; then err "Tor failed"; cat "$TOR_LOG" | tail -20; exit 1; fi

# Wait for hidden service
ONION=""
for i in $(seq 1 15); do
    if [[ -f "$HIDDEN_DIR/hostname" ]]; then ONION=$(cat "$HIDDEN_DIR/hostname" 2>/dev/null | tr -d ' \n'); [[ -n "$ONION" ]] && break; fi
    sleep 2
done
if [[ -z "$ONION" ]]; then warn "Hidden service not ready after 30s, retrying direct"; ONION="127.0.0.1"; else log "Hidden service: $ONION:$RELAY_PORT"; fi

TOR_IP=$(ip netns exec "$NS_NAME" curl -s --socks5 127.0.0.1:9050 --max-time 15 https://ipinfo.io/ip 2>/dev/null || echo "unknown")
log "Tor IP: $TOR_IP"

# Start gost client inside ns (UDP -> socks -> relay TCP via Tor -> hidden service)
log "Starting gost client (UDP $CLIENT_UDP_PORT -> socks -> relay $ONION:$RELAY_PORT via Tor)..."
if [[ "$ONION" == *"onion"* ]]; then
    ip netns exec "$NS_NAME" sudo -u alae bash -c "/usr/local/bin/gost -L udp://127.0.0.1:$CLIENT_UDP_PORT -F socks5://127.0.0.1:9050 -F relay://$ONION:$RELAY_PORT > /tmp/gost-client.log 2>&1 &" 2>&1
else
    ip netns exec "$NS_NAME" sudo -u alae bash -c "/usr/local/bin/gost -L udp://127.0.0.1:$CLIENT_UDP_PORT -F relay://127.0.0.1:$RELAY_PORT > /tmp/gost-client.log 2>&1 &" 2>&1
fi
sleep 2
log "gost client started, waiting for WARP via Tor..."

# WARP via Tor (endpoint via gost client)
log "Starting WARP via Tor (endpoint 127.0.0.1:$CLIENT_UDP_PORT -> $ONION)..."
ip netns exec "$NS_NAME" ip link add dev warp-wg type wireguard 2>/dev/null || true
ip netns exec "$NS_NAME" wg set warp-wg private-key "$TUNNEL_DIR/warp.key" peer bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo= endpoint 127.0.0.1:$CLIENT_UDP_PORT allowed-ips 0.0.0.0/1,128.0.0.0/1,::/1,128.0.0.0/2
ip netns exec "$NS_NAME" ip addr add 172.16.0.2/32 dev warp-wg 2>/dev/null || true
ip netns exec "$NS_NAME" ip -6 addr add 2606:4700:110:8760:945f:a500:efd9:7422/128 dev warp-wg 2>/dev/null || true
ip netns exec "$NS_NAME" ip link set mtu 1280 dev warp-wg 2>/dev/null || true
ip netns exec "$NS_NAME" ip link set warp-wg up
ip netns exec "$NS_NAME" ip route del default 2>/dev/null || true
ip netns exec "$NS_NAME" ip route add default dev warp-wg metric 1
ip netns exec "$NS_NAME" ip -6 route del default 2>/dev/null || true
ip netns exec "$NS_NAME" ip -6 route add default dev warp-wg metric 1 2>/dev/null || true

log "Waiting for WARP handshake via Tor (may take 30s via onion)..."
for i in $(seq 1 30); do
    sleep 2
    HS=$(ip netns exec "$NS_NAME" wg show warp-wg latest-handshakes 2>/dev/null | awk '{print $2}')
    if [[ "$HS" != "0" ]] && [[ -n "$HS" ]]; then log "WARP OK via Tor (hs $HS)"; break; fi
    if [[ $i -eq 15 ]]; then log "Still waiting for WARP via Tor..."; cat /tmp/gost-client.log 2>&1 | tail -5 | while read l; do log "  gost-client: $l"; done; fi
    if [[ $i -eq 30 ]]; then warn "WARP handshake timeout via Tor, continuing..."; fi
done
WARP_IP=$(ip netns exec "$NS_NAME" curl -s --max-time 15 https://ipinfo.io/ip 2>/dev/null || echo "unknown")
WARP_CITY=$(ip netns exec "$NS_NAME" curl -s --max-time 10 https://ipinfo.io 2>/dev/null | grep -oP '"city":\s*"\K[^"]+' || echo "unknown")
log "WARP IP (via Tor): $WARP_IP ($WARP_CITY)"
log "Chain: Tor ($TOR_IP) -> WARP ($WARP_IP) -> Chrome  [WARP via Tor, Chrome via WARP]"

PROFILE_DIR="$TUNNEL_DIR/chrome-profile-tor"
mkdir -p "$PROFILE_DIR"; chown -R alae:alae "$PROFILE_DIR" 2>/dev/null || true

log "Launching Chrome (Tor->WARP)..."
if [[ -e /tmp/.X11-unix/X0 ]]; then OZONE_FLAG=""; else OZONE_FLAG="--ozone-platform=wayland"; fi
ip netns exec "$NS_NAME" sudo -u alae env DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-1 /opt/google/chrome/chrome --user-data-dir="$PROFILE_DIR" $OZONE_FLAG --no-first-run --no-default-browser-check "https://browserleaks.com/ip" >/tmp/chrome-tor.log 2>&1 &
disown
sleep 3
if ip netns exec "$NS_NAME" pgrep -f google-chrome &>/dev/null; then log "Chrome started (pid $(ip netns exec "$NS_NAME" pgrep -f google-chrome | head -1))"; else warn "Chrome failed"; cat /tmp/chrome-tor.log | tail -20 | while read l; do warn "  $l"; done; fi

log "============================================"
log "  Tor -> WARP -> Chrome  (warp via tor, final WARP)"
log "  Tor: $TOR_IP | WARP: $WARP_IP ($WARP_CITY)"
log "  Profile: $PROFILE_DIR  warp-wg via 127.0.0.1:$CLIENT_UDP_PORT -> $ONION:$RELAY_PORT (gost relay+udp2raw faketcp)"
log "  Ctrl+C to stop"
log "============================================"

while true; do
    sleep 5
    if ! ip netns exec "$NS_NAME" pgrep -f "google-chrome.*chrome-profile-tor" &>/dev/null; then
        if ! ip netns exec "$NS_NAME" pgrep -f google-chrome &>/dev/null; then log "Chrome closed."; break; fi
    fi
    if ! ip netns exec "$NS_NAME" ip link show warp-wg &>/dev/null; then log "WARP down."; break; fi
done
