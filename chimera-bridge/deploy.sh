#!/bin/bash
# Deploy Chimera bridge server to VPS

set -e

echo "=== Chimera Bridge Deployment ==="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: Must run as root"
    exit 1
fi

# Variables
BRIDGE_USER="chimera"
BRIDGE_DIR="/opt/chimera-bridge"
DOMAIN="bridge.example.com"

echo "--- Creating user ---"
if ! id "$BRIDGE_USER" &>/dev/null; then
    useradd -r -s /bin/false -d "$BRIDGE_DIR" "$BRIDGE_USER"
    echo "✓ User created: $BRIDGE_USER"
else
    echo "✓ User exists: $BRIDGE_USER"
fi

echo ""
echo "--- Installing dependencies ---"
apt-get update
apt-get install -y python3 python3-pip certbot

pip3 install -r requirements.txt
echo "✓ Dependencies installed"

echo ""
echo "--- Setting up directories ---"
mkdir -p "$BRIDGE_DIR"
cp bridge.py config.json "$BRIDGE_DIR/"
chown -R "$BRIDGE_USER:$BRIDGE_USER" "$BRIDGE_DIR"
chmod 750 "$BRIDGE_DIR"
chmod 640 "$BRIDGE_DIR/config.json"
echo "✓ Files deployed to $BRIDGE_DIR"

echo ""
echo "--- SSL certificates ---"
if [ ! -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
    echo "Getting SSL certificate for $DOMAIN..."
    certbot certonly --standalone -d "$DOMAIN" --non-interactive --agree-tos --email admin@example.com
    echo "✓ SSL certificate obtained"
else
    echo "✓ SSL certificate exists"
fi

# Allow bridge user to read certs
setfacl -R -m u:$BRIDGE_USER:rX /etc/letsencrypt/live/
setfacl -R -m u:$BRIDGE_USER:rX /etc/letsencrypt/archive/

echo ""
echo "--- Installing systemd service ---"
cp systemd/chimera-bridge.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable chimera-bridge
echo "✓ Service installed"

echo ""
echo "--- Firewall ---"
ufw allow 8443/tcp comment "Chimera Bridge"
echo "✓ Firewall configured"

echo ""
echo "--- Starting service ---"
systemctl restart chimera-bridge
sleep 2
systemctl status chimera-bridge --no-pager
echo ""

echo "=== Deployment Complete ==="
echo ""
echo "Bridge URL: wss://$DOMAIN:8443"
echo "Status: systemctl status chimera-bridge"
echo "Logs: journalctl -u chimera-bridge -f"
echo ""
