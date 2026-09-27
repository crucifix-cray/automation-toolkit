#!/usr/bin/env bash
# install.sh — clone + run, the cell is mining. Run INSIDE the cell as root.
# Usage: git clone <this-repo> && cd miner-template && ./install.sh --session <S> --project <P>
# What it does: system stack -> python stack -> golden files (md5-pinned) ->
# dirs -> mine.sh launch -> worker-alive proof (or ABORT reason).
set -u
SESS=""; PROJ=""; THREADS="16"; TRIO=""
while [ $# -gt 0 ]; do
  case "$1" in
    --session) SESS="$2"; shift 2;;
    --project) PROJ="$2"; shift 2;;
    --threads) THREADS="$2"; shift 2;;
    --trio) TRIO="$2"; shift 2;;
    *) echo "unknown arg $1"; exit 2;;
  esac
done
[ -n "$SESS" ] || { echo "ABORT: --session required"; exit 2; }
[ -n "$PROJ" ] || { echo "ABORT: --project required"; exit 2; }

GOLD_DAEMON_MD5="cb9305f50b6f1cee90fbbe74c0a2f009"
GOLD_INJECTOR_MD5="e9e158a76419522f635ebcdcd3b82590"
RAW_TOOLKIT="https://raw.githubusercontent.com/crucifix-cray/automation-toolkit/main/miner-template"
RAW_MINER="https://raw.githubusercontent.com/crucifix-cray/chimera-miner/master"
export DEBIAN_FRONTEND=noninteractive

echo "=== [1/7] system stack ==="
apt-get update -qq
apt-get install -y -qq xvfb curl git unzip ca-certificates python3 python3-pip \
  fonts-liberation fonts-dejavu-core libgtk-3-0 libdbus-glib-1-2 libxt6 \
  libasound2t64 libatk-bridge2.0-0 libatk1.0-0 libatspi2.0-0 libcups2 libdbus-1-3 \
  libdrm2 libgbm1 libnspr4 libnss3 libxcomposite1 libxdamage1 libxfixes3 \
  libxkbcommon0 libxrandr2 xdg-utils >/dev/null 2>&1 || apt-get install -y \
  xvfb curl git python3 python3-pip fonts-liberation libgtk-3-0
# uv + python 3.14 (golden: 3.14.7)
if ! [ -x /opt/venv/bin/python3 ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  uv python install 3.14
  uv venv --python 3.14 /opt/venv
fi
echo "=== [2/7] python stack ==="
/opt/venv/bin/pip install -q --break-system-packages patchright playwright camoufox \
  websockets psutil requests playwright-captcha
/opt/venv/bin/python -m patchright install chromium
/opt/venv/bin/python -m patchright install-deps || true

echo "=== [3/7] golden files (md5-pinned) ==="
mkdir -p /app/work/chimera-miner /app/work/scripts/sessions /app/work/shots /data/work
[ -e /app/work ] && [ ! -L /data/work ] && ln -sfn /data/work /app/work 2>/dev/null || true
cd /app/work/chimera-miner
curl -fsSL "$RAW_TOOLKIT/golden-cell/daemon.golden.py" -o daemon.py
curl -fsSL "$RAW_MINER/miner_injector.py" -o miner_injector.py
curl -fsSL "$RAW_MINER/watchdog_worker.py" -o watchdog_worker.py
curl -fsSL "$RAW_TOOLKIT/mine.sh" -o mine.sh && chmod +x mine.sh
[ "$(md5sum daemon.py | cut -d' ' -f1)" = "$GOLD_DAEMON_MD5" ] || { echo "ABORT: daemon md5 mismatch"; exit 4; }
[ "$(md5sum miner_injector.py | cut -d' ' -f1)" = "$GOLD_INJECTOR_MD5" ] || { echo "ABORT: injector md5 mismatch"; exit 4; }
echo "golden bytes verified"

echo "=== [4/7] trio ==="
if [ -n "$TRIO" ]; then cp -r "$TRIO" "/app/work/scripts/sessions/$SESS"; fi
[ -f "/app/work/scripts/sessions/$SESS/cookies.json" ] || { echo "ABORT: trio for $SESS missing (pass --trio <dir>)"; exit 3; }

echo "=== [5/7] launch ==="
setsid nohup ./mine.sh --session "$SESS" --project "$PROJ" --threads "$THREADS" \
  >>"/app/work/install_$SESS.log" 2>&1 < /dev/null &
echo "=== [6/7] waiting for worker (up to 12 min) ==="
for i in $(seq 1 24); do
  sleep 30
  if grep -q "Worker alive" /app/work/daemon*.log 2>/dev/null; then
    echo "=== [7/7] MINING ==="
    grep -h "Worker alive" /app/work/daemon*.log 2>/dev/null | tail -2
    exit 0
  fi
done
echo "ABORT: no worker in 12 min — check /app/work/daemon*.log"; exit 5
