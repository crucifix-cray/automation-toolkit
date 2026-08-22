#!/bin/bash
TUNNEL_DIR="/home/alae/.vpn-tunnel"
NS_NAME="vpnns"
RESOLV_BACKUP="$TUNNEL_DIR/resolv.conf.bak"
MITM_PORT=8080  # unused, kept for reference
OVPN_ONLY=""
[[ "$1" == "--no-warp" ]] && OVPN_ONLY=1

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'
log()  { echo -e "${GREEN}[+]${NC} $1"; }
err()  { echo -e "${RED}[-]${NC} $1"; }

if [[ $EUID -ne 0 ]]; then err "Run as root: sudo bash $0"; exit 1; fi

cleanup() {
    log "Shutting down..."
    ip netns exec "$NS_NAME" pkill openvpn 2>/dev/null || true
    ip netns exec "$NS_NAME" ip link del warp-wg 2>/dev/null || true
    ip netns exec "$NS_NAME" ip link del tun1 2>/dev/null || true
    ip netns exec "$NS_NAME" pkill -f "/opt/google/chrome" 2>/dev/null || true
    ip netns exec "$NS_NAME" iptables -F OUTPUT 2>/dev/null || true
    ip netns exec "$NS_NAME" ip6tables -F OUTPUT 2>/dev/null || true
    ip route del 149.40.62.31/32 via 192.168.100.1 dev wlan0 2>/dev/null || true
    umount /etc/resolv.conf 2>/dev/null || true
    [[ -f "$RESOLV_BACKUP" ]] && cp "$RESOLV_BACKUP" /etc/resolv.conf 2>/dev/null
    log "Stopped."
}
trap cleanup EXIT INT TERM

if ! ip netns list | grep -q "$NS_NAME"; then
    log "Namespace not found. Running auto-setup..."
    bash "$TUNNEL_DIR/setup.sh" 2>&1 | while read line; do log "  $line"; done
    if ! ip netns list | grep -q "$NS_NAME"; then
        err "Setup failed. Run: sudo bash $TUNNEL_DIR/setup.sh"
        exit 1
    fi
fi

# Ensure IP forwarding and NAT are active (may be lost after reboot)
if [[ $(cat /proc/sys/net/ipv4/ip_forward) != "1" ]]; then
    log "Enabling IP forwarding..."
    echo 1 > /proc/sys/net/ipv4/ip_forward
fi
WLAN_IFACE=$(ip -o route get 8.8.8.8 | awk '{print $5; exit}')
iptables -t nat -C POSTROUTING -s 10.200.0.0/30 -o "$WLAN_IFACE" -j MASQUERADE 2>/dev/null || \
    iptables -t nat -A POSTROUTING -s 10.200.0.0/30 -o "$WLAN_IFACE" -j MASQUERADE
iptables -t nat -C POSTROUTING -s 172.16.0.0/12 -o "$WLAN_IFACE" -j MASQUERADE 2>/dev/null || \
    iptables -t nat -A POSTROUTING -s 172.16.0.0/12 -o "$WLAN_IFACE" -j MASQUERADE
iptables -C FORWARD -i veth-host -o "$WLAN_IFACE" -j ACCEPT 2>/dev/null || \
    iptables -A FORWARD -i veth-host -o "$WLAN_IFACE" -j ACCEPT
iptables -C FORWARD -i "$WLAN_IFACE" -o veth-host -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || \
    iptables -A FORWARD -i "$WLAN_IFACE" -o veth-host -m state --state RELATED,ESTABLISHED -j ACCEPT
# ponytail: firewalld's inet filter forward chain has policy drop (docker policy artifact) - accept tunnel flows in nft directly
nft add rule inet filter forward iifname "veth-host" oifname "$WLAN_IFACE" accept 2>/dev/null || true
nft add rule inet filter forward iifname "$WLAN_IFACE" oifname "veth-host" ct state established,related accept 2>/dev/null || true

cp /etc/resolv.conf "$RESOLV_BACKUP" 2>/dev/null
mount --bind /etc/netns/vpns/resolv.conf /etc/resolv.conf

log "Cleaning..."
ip netns exec "$NS_NAME" pkill openvpn 2>/dev/null || true
ip netns exec "$NS_NAME" pkill mitmdump 2>/dev/null || true
ip netns exec "$NS_NAME" ip link del warp-wg 2>/dev/null || true
ip netns exec "$NS_NAME" ip link del tun1 2>/dev/null || true
ip route add 149.40.62.31/32 via 192.168.100.1 dev wlan0 2>/dev/null || true
ip netns exec "$NS_NAME" ip route flush all 2>/dev/null || true
ip netns exec "$NS_NAME" ip route add 10.200.0.0/30 dev veth-ns proto kernel scope link src 10.200.0.2 2>/dev/null
ip netns exec "$NS_NAME" ip route add 149.40.62.31/32 via 10.200.0.1 dev veth-ns onlink 2>/dev/null || true
ip netns exec "$NS_NAME" ip route add default via 10.200.0.1 dev veth-ns 2>/dev/null
sleep 1

# Block WebRTC: allow only essential UDP (OpenVPN, WARP, DNS), block everything else
ip netns exec "$NS_NAME" iptables -A OUTPUT -p udp --dport 1194 -d 149.40.62.31 -j ACCEPT 2>/dev/null || true
ip netns exec "$NS_NAME" iptables -A OUTPUT -p udp --dport 2408 -d 162.159.192.1 -j ACCEPT 2>/dev/null || true
ip netns exec "$NS_NAME" iptables -A OUTPUT -p udp --dport 53 -j ACCEPT 2>/dev/null || true
ip netns exec "$NS_NAME" iptables -A OUTPUT -p udp -j DROP 2>/dev/null || true
ip netns exec "$NS_NAME" ip6tables -A OUTPUT -p udp --dport 53 -j ACCEPT 2>/dev/null || true
ip netns exec "$NS_NAME" ip6tables -A OUTPUT -p udp -j DROP 2>/dev/null || true

# Generate ovpn-fixed.conf (lost on reboot since /tmp is tmpfs)
if [[ ! -f /tmp/ovpn-fixed.conf ]]; then
    log "Generating OpenVPN config..."
    cat > /tmp/ovpn-fixed.conf << 'OVPN'
client
dev tun1
proto udp
remote 149.40.62.31 1194
resolv-retry infinite
nobind
cipher AES-256-GCM
setenv CLIENT_CERT 0
tun-mtu 1500
mssfix 0
persist-key
persist-tun
reneg-sec 0
remote-cert-tls server
auth-user-pass /home/alae/.vpn-tunnel/credentials.txt
disable-dco
pull-filter ignore "redirect-gateway"
pull-filter ignore "dhcp-option"
verb 4
OVPN
    cat /home/alae/.vpn-tunnel/protonvpn-isolated.ovpn | sed -n '/<ca>/,/<\/ca>/p' >> /tmp/ovpn-fixed.conf
    cat /home/alae/.vpn-tunnel/protonvpn-isolated.ovpn | sed -n '/<tls-crypt>/,/<\/tls-crypt>/p' >> /tmp/ovpn-fixed.conf
    chmod 600 /tmp/ovpn-fixed.conf
fi

log "Starting OpenVPN (ProtonVPN US)..."
ip netns exec "$NS_NAME" openvpn --config /tmp/ovpn-fixed.conf --dev tun1 --daemon --writepid /tmp/ovpn-ns.pid --log /tmp/ovpn-ns.log

for i in $(seq 1 60); do
    if ip netns exec "$NS_NAME" ip link show tun1 &>/dev/null; then log "OpenVPN UP (${i}s)"; break; fi
    sleep 1
done
sleep 3

ip netns exec "$NS_NAME" ip route del default 2>/dev/null || true
ip netns exec "$NS_NAME" ip route add default dev tun1

OVPN_IP=$(ip netns exec "$NS_NAME" curl -s --max-time 10 https://ipinfo.io/ip 2>/dev/null || echo "unknown")
log "OpenVPN IP: $OVPN_IP"

if [[ -n "$OVPN_ONLY" ]]; then
    log "OpenVPN-only mode, skipping WARP..."
    FINAL_IP="$OVPN_IP"
    FINAL_CITY=$(ip netns exec "$NS_NAME" curl -s --max-time 10 https://ipinfo.io 2>/dev/null | grep -oP '"city":\s*"\K[^"]+' || echo "unknown")
else
log "Starting WARP..."
ip netns exec "$NS_NAME" ip link add dev warp-wg type wireguard
ip netns exec "$NS_NAME" wg set warp-wg \
    private-key "$TUNNEL_DIR/warp.key" \
    peer bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo= \
    endpoint 162.159.192.1:2408 \
    allowed-ips 0.0.0.0/1,128.0.0.0/1,::/1,128.0.0.0/2
ip netns exec "$NS_NAME" ip addr add 172.16.0.2/32 dev warp-wg
ip netns exec "$NS_NAME" ip -6 addr add 2606:4700:110:8760:945f:a500:efd9:7422/128 dev warp-wg 2>/dev/null || true
ip netns exec "$NS_NAME" ip link set mtu 1280 dev warp-wg
ip netns exec "$NS_NAME" ip link set warp-wg up

ip netns exec "$NS_NAME" ip route add 162.159.192.1/32 via 10.96.0.1 dev tun1 2>/dev/null || true
ip netns exec "$NS_NAME" ip route del default 2>/dev/null || true
ip netns exec "$NS_NAME" ip route add default dev warp-wg metric 1
ip netns exec "$NS_NAME" ip -6 route del default 2>/dev/null || true
ip netns exec "$NS_NAME" ip -6 route add default dev warp-wg metric 1 2>/dev/null || true

log "Waiting for WARP..."
for i in $(seq 1 20); do
    sleep 2
    HS=$(ip netns exec "$NS_NAME" wg show warp-wg latest-handshakes 2>/dev/null | awk '{print $2}')
    if [[ "$HS" != "0" ]] && [[ -n "$HS" ]]; then log "WARP OK"; break; fi
done

FINAL_IP=$(ip netns exec "$NS_NAME" curl -s --max-time 15 https://ipinfo.io/ip 2>/dev/null || echo "unknown")
FINAL_CITY=$(ip netns exec "$NS_NAME" curl -s --max-time 10 https://ipinfo.io 2>/dev/null | grep -oP '"city":\s*"\K[^"]+' || echo "unknown")
log "WARP IP: $FINAL_IP ($FINAL_CITY)"
fi

CHAIN_LABEL="OpenVPN -> WARP"
PROFILE_DIR="$TUNNEL_DIR/chrome-profile"
if [[ -n "$OVPN_ONLY" ]]; then
    CHAIN_LABEL="OpenVPN only"
    PROFILE_DIR="$TUNNEL_DIR/chrome-profile-ovpn"
fi

log "Launching Chrome ($CHAIN_LABEL)..."
# Auto-detect display platform: use X11 if socket exists, else Wayland
if [[ -e /tmp/.X11-unix/X0 ]]; then
    OZONE_FLAG=""
else
    OZONE_FLAG="--ozone-platform=wayland"
fi
ip netns exec "$NS_NAME" sudo -u alae \
    env DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-1 \
    /opt/google/chrome/chrome --user-data-dir="$PROFILE_DIR" \
    $OZONE_FLAG \
    "https://browserleaks.com/ip" >/tmp/chrome.log 2>&1 &
disown

log "============================================"
log "  $CHAIN_LABEL -> Chrome"
log "  IP: $FINAL_IP ($FINAL_CITY)"
log "  Ctrl+C to stop"
log "============================================"

while true; do
    sleep 5
    if ! ip netns exec "$NS_NAME" pgrep -f "/opt/google/chrome/chrome" &>/dev/null; then
        log "Chrome closed."; break
    fi
done
