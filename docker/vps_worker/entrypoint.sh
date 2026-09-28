#!/bin/bash
# Long-lived VPS worker. Boots sshd and idles — work arrives via `railway ssh`.
set -u
echo "=== vps_worker boot $(date -u) ==="
swapon -a 2>/dev/null && echo "SWAP: on" || echo "SWAP: platform-default"
free -m | head -2
mkdir -p /var/run/sshd /root/.ssh /app/work
chmod 700 /root/.ssh
# Railway injects these; the job reads RAILWAY_PROJECT_ID to pick its own work.
echo "PROJECT=${RAILWAY_PROJECT_ID:-none} SERVICE=${RAILWAY_SERVICE_NAME:-none} ENV=${RAILWAY_ENVIRONMENT_NAME:-none}"
python3 -c 'import playwright; print("PLAYWRIGHT CLIENT OK")' 2>&1 | tail -1
kernel --version 2>&1 | head -1 | sed 's/^/ONK CLI: /'
/usr/sbin/sshd -D -e
