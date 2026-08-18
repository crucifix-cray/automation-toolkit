#!/bin/bash
# WARP Multi-Instance Manager
# Creates isolated WARP instances with unique IPs using network namespaces

set -e

INSTANCE_ID=$1
ACTION=$2

if [ -z "$INSTANCE_ID" ] || [ -z "$ACTION" ]; then
    echo "Usage: $0 <instance_id> <start|stop|ip>"
    exit 1
fi

NETNS="warp-${INSTANCE_ID}"
VETH_HOST="vwarp${INSTANCE_ID}h"
VETH_NS="vwarp${INSTANCE_ID}n"
CONFIG_DIR="/tmp/wgcf-${INSTANCE_ID}"
WG_INTERFACE="wg-${INSTANCE_ID}"

start_instance() {
    echo "🚀 Starting WARP instance ${INSTANCE_ID}..."
    
    # 1. Create network namespace
    echo "   📦 Creating network namespace: ${NETNS}"
    sudo ip netns add ${NETNS} 2>/dev/null || true
    
    # 2. Create veth pair
    echo "   🔗 Creating veth pair..."
    sudo ip link add ${VETH_HOST} type veth peer name ${VETH_NS} 2>/dev/null || true
    sudo ip link set ${VETH_NS} netns ${NETNS}
    
    # 3. Configure host side
    sudo ip addr add 10.200.${INSTANCE_ID}.1/24 dev ${VETH_HOST}
    sudo ip link set ${VETH_HOST} up
    
    # 4. Configure namespace side
    sudo ip netns exec ${NETNS} ip addr add 10.200.${INSTANCE_ID}.2/24 dev ${VETH_NS}
    sudo ip netns exec ${NETNS} ip link set ${VETH_NS} up
    sudo ip netns exec ${NETNS} ip link set lo up
    sudo ip netns exec ${NETNS} ip route add default via 10.200.${INSTANCE_ID}.1
    
    # 5. Enable IP forwarding and NAT
    sudo sysctl -w net.ipv4.ip_forward=1 >/dev/null
    sudo iptables -t nat -A POSTROUTING -s 10.200.${INSTANCE_ID}.0/24 -j MASQUERADE 2>/dev/null || true
    
    # 5c. Allow FORWARD for this instance's veth (Docker hosts drop non-docker forwarding)
    sudo iptables -I FORWARD -i ${VETH_HOST} -j ACCEPT 2>/dev/null || true
    sudo iptables -I FORWARD -o ${VETH_HOST} -j ACCEPT 2>/dev/null || true
    
    # 6. Create wgcf config if not exists
    mkdir -p ${CONFIG_DIR}
    
    if [ ! -f "${CONFIG_DIR}/wgcf-account.toml" ]; then
        if [ -n "${WG_PROFILE_DIR}" ] && [ -f "${WG_PROFILE_DIR}/wgcf-account.toml" ] && [ -f "${WG_PROFILE_DIR}/wgcf-profile.conf" ]; then
            echo "   📦 Using pre-registered WARP profile from pool"
            cp ${WG_PROFILE_DIR}/wgcf-account.toml ${CONFIG_DIR}/
            cp ${WG_PROFILE_DIR}/wgcf-profile.conf ${CONFIG_DIR}/
        else
            echo "   📝 Registering new WARP account..."
            cd ${CONFIG_DIR}
            wgcf register --accept-tos --config wgcf-account.toml
            wgcf generate --config wgcf-account.toml
        fi
        
        # Remove DNS lines from config (we'll set manually)
        sed -i '/^DNS = /d' ${CONFIG_DIR}/wgcf-profile.conf
        
        # 6b. NAT for WARP tunnel traffic too (wgcf Address subnet, e.g. 172.16.0.2/32)
        WG_SUBNET=$(grep -oP 'Address = \K[0-9.]+/[0-9]+' ${CONFIG_DIR}/wgcf-profile.conf | head -1)
        if [ -n "$WG_SUBNET" ]; then
            echo "   🔀 NAT for tunnel subnet ${WG_SUBNET}"
            sudo iptables -t nat -A POSTROUTING -s ${WG_SUBNET} -j MASQUERADE 2>/dev/null || true
        fi
    fi
    
    # 7. Setup DNS in namespace (manual, since resolvconf doesn't work)
    #    Use host resolver if it is external (GH Actions: Azure DNS), else 1.1.1.1
    echo "   🌐 Setting up DNS in namespace..."
    sudo mkdir -p /etc/netns/${NETNS}
    HOST_NS=$(awk '/^nameserver/{print $2; exit}' /etc/resolv.conf 2>/dev/null)
    if [ -n "$HOST_NS" ] && [ "$HOST_NS" != "127.0.0.1" ] && [ "$HOST_NS" != "127.0.0.53" ]; then
        echo "nameserver ${HOST_NS}" | sudo tee /etc/netns/${NETNS}/resolv.conf > /dev/null
    else
        echo "nameserver 1.1.1.1" | sudo tee /etc/netns/${NETNS}/resolv.conf > /dev/null
        echo "nameserver 1.0.0.1" | sudo tee -a /etc/netns/${NETNS}/resolv.conf > /dev/null
    fi
    
    # 7b. Resolve WireGuard endpoint on host (namespace DNS may be unreachable pre-tunnel)
    ENDPOINT=$(grep '^Endpoint = ' ${CONFIG_DIR}/wgcf-profile.conf | sed 's/^Endpoint = //')
    ENDPOINT_HOST=$(echo "$ENDPOINT" | sed 's/:.*//')
    ENDPOINT_PORT=$(echo "$ENDPOINT" | grep -oP ':\K[0-9]+$')
    ENDPOINT_IP=$(getent ahostsv4 "$ENDPOINT_HOST" | awk '{print $1; exit}')
    if [ -n "$ENDPOINT_IP" ]; then
        echo "   🔗 Endpoint ${ENDPOINT_HOST}:${ENDPOINT_PORT} -> ${ENDPOINT_IP}:${ENDPOINT_PORT}"
        sed -i "s|^Endpoint = .*|Endpoint = ${ENDPOINT_IP}:${ENDPOINT_PORT}|" ${CONFIG_DIR}/wgcf-profile.conf
    fi
    
    # 8. Start WireGuard inside namespace
    echo "   🔧 Starting WireGuard in namespace..."
    sudo ip netns exec ${NETNS} wg-quick up ${CONFIG_DIR}/wgcf-profile.conf
    
    # 8b. Ensure endpoint route exists so handshake packets escape the tunnel
    #     MUST go via the veth gateway (10.200.X.1) - dev-only route causes
    #     on-link ARP for the remote endpoint and kills the handshake
    if [ -n "$ENDPOINT_IP" ]; then
        sudo ip netns exec ${NETNS} ip route add ${ENDPOINT_IP} via 10.200.${INSTANCE_ID}.1 dev ${VETH_NS} 2>/dev/null || true
        sudo ip netns exec ${NETNS} ip route add ${ENDPOINT_IP} via 10.200.${INSTANCE_ID}.1 dev ${VETH_NS} table 51820 2>/dev/null || true
    fi
    
    # 9. Start SOCKS proxy on HOST routing through namespace
    echo "   🔌 Starting SOCKS proxy on port $((40000 + INSTANCE_ID))..."
    
    # Check if microsocks is installed
    if ! command -v microsocks &> /dev/null; then
        echo "   📦 Installing microsocks..."
        git clone https://github.com/rofl0r/microsocks /tmp/microsocks-build
        cd /tmp/microsocks-build
        make
        sudo cp microsocks /usr/local/bin/
        cd -
        rm -rf /tmp/microsocks-build
    fi
    
    # Run microsocks on HOST but route its traffic through the namespace
    # Use ip netns exec to run it WITH the namespace network
    sudo ip netns exec ${NETNS} microsocks -i 0.0.0.0 -p $((40000 + INSTANCE_ID)) > /dev/null 2>&1 &
    sleep 1
    
    # 9b. DNAT host 127.0.0.1:PORT -> netns microsocks (host-side access to the proxy)
    sudo iptables -t nat -A PREROUTING -p tcp --dport $((40000 + INSTANCE_ID)) -j DNAT --to-destination 10.200.${INSTANCE_ID}.2:$((40000 + INSTANCE_ID)) 2>/dev/null || true
    sudo iptables -t nat -A OUTPUT -p tcp -d 127.0.0.1 --dport $((40000 + INSTANCE_ID)) -j DNAT --to-destination 10.200.${INSTANCE_ID}.2:$((40000 + INSTANCE_ID)) 2>/dev/null || true
    
    # 9c. MASQUERADE traffic to the netns proxy so replies return via the veth
    #     (source stays 127.0.0.1 otherwise and the reply is lost in the netns loopback)
    sudo iptables -t nat -A POSTROUTING -p tcp -d 10.200.${INSTANCE_ID}.2 --dport $((40000 + INSTANCE_ID)) -j MASQUERADE 2>/dev/null || true
    
    echo "✅ WARP instance ${INSTANCE_ID} started"
    echo "   Namespace: ${NETNS}"
    echo "   SOCKS proxy: 127.0.0.1:$((40000 + INSTANCE_ID))"
}

stop_instance() {
    echo "🔴 Stopping WARP instance ${INSTANCE_ID}..."
    
    # Stop WireGuard
    sudo ip netns exec ${NETNS} wg-quick down ${CONFIG_DIR}/wgcf-profile.conf 2>/dev/null || true
    
    # Kill microsocks
    sudo pkill -f "microsocks.*$((40000 + INSTANCE_ID))" 2>/dev/null || true
    
    # Remove iptables rules
    sudo iptables -t nat -D PREROUTING -p tcp --dport $((40000 + INSTANCE_ID)) -j DNAT --to-destination 10.200.${INSTANCE_ID}.2:$((40000 + INSTANCE_ID)) 2>/dev/null || true
    sudo iptables -t nat -D OUTPUT -p tcp -d 127.0.0.1 --dport $((40000 + INSTANCE_ID)) -j DNAT --to-destination 10.200.${INSTANCE_ID}.2:$((40000 + INSTANCE_ID)) 2>/dev/null || true
    sudo iptables -t nat -D POSTROUTING -p tcp -d 10.200.${INSTANCE_ID}.2 --dport $((40000 + INSTANCE_ID)) -j MASQUERADE 2>/dev/null || true
    
    # Remove veth
    sudo ip link del ${VETH_HOST} 2>/dev/null || true
    
    # Remove FORWARD accepts
    sudo iptables -D FORWARD -i ${VETH_HOST} -j ACCEPT 2>/dev/null || true
    sudo iptables -D FORWARD -o ${VETH_HOST} -j ACCEPT 2>/dev/null || true
    
    # Remove namespace
    sudo ip netns del ${NETNS} 2>/dev/null || true
    
    # Remove iptables NAT rule
    sudo iptables -t nat -D POSTROUTING -s 10.200.${INSTANCE_ID}.0/24 -j MASQUERADE 2>/dev/null || true
    sudo iptables -t nat -D POSTROUTING -s $(grep -oP 'Address = \K[0-9.]+/[0-9]+' ${CONFIG_DIR}/wgcf-profile.conf 2>/dev/null | head -1) -j MASQUERADE 2>/dev/null || true
    
    echo "✅ WARP instance ${INSTANCE_ID} stopped"
}

get_ip() {
    # Get IP from namespace
    sudo ip netns exec ${NETNS} curl -s --max-time 5 https://www.cloudflare.com/cdn-cgi/trace | grep '^ip=' | cut -d= -f2
}

case $ACTION in
    start)
        start_instance
        ;;
    stop)
        stop_instance
        ;;
    ip)
        get_ip
        ;;
    *)
        echo "Unknown action: $ACTION"
        exit 1
        ;;
esac
