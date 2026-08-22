#!/bin/bash
set -e

TUNNEL_DIR="/home/alae/.vpn-tunnel"
NS_NAME="vpnns"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[+]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[-]${NC} $1"; }

if [[ $EUID -ne 0 ]]; then
    err "Run as root: sudo bash $0"
    exit 1
fi

log "=== Isolated VPN Tunnel Setup ==="
log "Chain: OpenVPN -> WARP -> Chrome + Waydroid (network namespace)"

# Check prerequisites
if ! command -v google-chrome-stable &>/dev/null; then
    err "Google Chrome not found"
    exit 1
fi

if ! command -v wg &>/dev/null; then
    err "WireGuard tools not found. Install: sudo pacman -S wireguard-tools"
    exit 1
fi

if ! command -v curl &>/dev/null; then
    err "curl not found"
    exit 1
fi

# Clean up any previous state
log "Cleaning up previous state..."
ip netns del "$NS_NAME" 2>/dev/null || true
ip link del veth-host 2>/dev/null || true
sleep 1

# Create network namespace
log "Creating network namespace: $NS_NAME"
ip netns add "$NS_NAME"

# Create veth pair
log "Creating veth pair..."
ip link add veth-host type veth peer name veth-ns
ip link set veth-ns netns "$NS_NAME"

# Configure host side
ip addr add 10.200.0.1/30 dev veth-host
ip link set veth-host up

# Configure namespace side
ip netns exec "$NS_NAME" ip addr add 10.200.0.2/30 dev veth-ns
ip netns exec "$NS_NAME" ip link set veth-ns up
ip netns exec "$NS_NAME" ip link set lo up
ip netns exec "$NS_NAME" ip route add default via 10.200.0.1

# NAT: namespace -> host internet
log "Setting up NAT..."
echo 1 > /proc/sys/net/ipv4/ip_forward
iptables -t nat -C POSTROUTING -s 10.200.0.0/30 -o wlan0 -j MASQUERADE 2>/dev/null || \
    iptables -t nat -A POSTROUTING -s 10.200.0.0/30 -o wlan0 -j MASQUERADE
iptables -t nat -C POSTROUTING -s 172.16.0.0/12 -o wlan0 -j MASQUERADE 2>/dev/null || \
    iptables -t nat -A POSTROUTING -s 172.16.0.0/12 -o wlan0 -j MASQUERADE
iptables -C FORWARD -i veth-host -o wlan0 -j ACCEPT 2>/dev/null || \
    iptables -A FORWARD -i veth-host -o wlan0 -j ACCEPT
iptables -C FORWARD -i wlan0 -o veth-host -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || \
    iptables -A FORWARD -i wlan0 -o veth-host -m state --state RELATED,ESTABLISHED -j ACCEPT

# DNS for namespace
mkdir -p "/etc/netns/$NS_NAME"
echo "nameserver 1.1.1.1" > "/etc/netns/$NS_NAME/resolv.conf"
echo "nameserver 1.0.0.1" >> "/etc/netns/$NS_NAME/resolv.conf"

# Verify namespace has internet
log "Verifying namespace connectivity..."
if ip netns exec "$NS_NAME" ping -c 1 -W 5 1.1.1.1 &>/dev/null; then
    log "Namespace has internet access!"
else
    err "Namespace cannot reach internet"
    exit 1
fi

# Create Chrome profile
mkdir -p "$TUNNEL_DIR/chrome-profile"

# Create launcher wrapper script
mkdir -p /home/alae/.local/share/applications
cat > /home/alae/.vpn-tunnel/vpn-launcher.sh << 'WRAPPER'
#!/bin/bash
exec /usr/bin/kitty -1 -T "VPN Tunnel" sudo /home/alae/.vpn-tunnel/start-tunnel.sh
WRAPPER
chmod +x /home/alae/.vpn-tunnel/vpn-launcher.sh

# Create app launcher
cat > /home/alae/.local/share/applications/warp-tunnel.desktop << DESKTOP
[Desktop Entry]
Name=WARP Tunnel Browser
Comment=Chrome through OpenVPN + WARP isolated tunnel
Exec=/home/alae/.vpn-tunnel/vpn-launcher.sh
Icon=google-chrome
Terminal=false
Type=Application
Categories=Network;WebBrowser;
StartupNotify=true
DESKTOP

# Remove old broken desktop file
rm -f /home/alae/.local/share/applications/vpn-tunnel-chrome.desktop

log ""
log "============================================"
log "  Setup complete!"
log ""
log "  To launch: sudo bash $TUNNEL_DIR/start-tunnel.sh"
log "  Or find 'VPN Tunnel Browser' in app launcher"
log "  To stop:   sudo bash $TUNNEL_DIR/stop-tunnel.sh"
log "============================================"
