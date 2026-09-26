#!/bin/bash
set -e

echo "[*] Starting Tor..."
mkdir -p /var/lib/tor /var/log/tor
chmod 700 /var/lib/tor
tor -f /etc/tor/torrc &
sleep 30

for i in {1..30}; do
    if grep -q "Bootstrapped 100%" /var/log/tor/tor.log 2>/dev/null; then
        echo "[*] Tor bootstrapped"
        break
    fi
    sleep 2
done

echo "[*] Starting WSS-Stratum bridge..."
exec /usr/local/bin/wss-bridge