#!/bin/sh
set -e

echo "[*] Preparing Tor data dir..."
mkdir -p /tmp/tordata /var/log/tor
chmod 700 /tmp/tordata

echo "[*] Starting Tor..."
tor -f /etc/tor/torrc &
TOR_PID=$!

# Wait for Tor to finish bootstrapping
i=0
while [ "$i" -lt 40 ]; do
    if grep -q "Bootstrapped 100%" /var/log/tor/tor.log 2>/dev/null; then
        echo "[*] Tor bootstrapped after $((i*3))s"
        break
    fi
    i=$((i+1))
    sleep 3
done

if ! grep -q "Bootstrapped 100%" /var/log/tor/tor.log 2>/dev/null; then
    echo "[!] Tor did not bootstrap in time - continuing anyway"
fi

echo "[*] Starting WSS-Stratum bridge..."
exec /usr/local/bin/wss-bridge --wallet "${WALLET:-4AdUndXHHZ6cfufTMvppY6JwXNouMBzSkbLYfpAV5Usx3skxNgYeYTRj5UzqtReoS44qo9mtmXCqY45DJ852K5Jv2684Rge}"
