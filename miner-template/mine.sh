#!/usr/bin/env bash
# mine.sh — ONE script. Clone it, run it, the cell mines forever.
# Usage: ./mine.sh --session <lov-session> --project <lovable-uuid> [--threads N] [--log NAME]
# Faithful copy of golden cell-28. Args are the ONLY per-cell differences.
set -u
SESS=""; PROJ=""; THREADS="16"; LOG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --session) SESS="$2"; shift 2;;
    --project) PROJ="$2"; shift 2;;
    --threads) THREADS="$2"; shift 2;;
    --log) LOG="$2"; shift 2;;
    *) echo "unknown arg $1"; exit 2;;
  esac
done
[ -n "$SESS" ] || { echo "ABORT: --session required"; exit 2; }
[ -n "$PROJ" ] || { echo "ABORT: --project required"; exit 2; }
CELLN="$(echo "$LOG" | grep -oE '[0-9]+' | head -1)"
[ -n "$LOG" ] || LOG="/app/work/daemon.log"
export LOG SESS PROJ
WORKER_STALE_S="${WORKER_STALE_S:-600}"
cd /app/work/chimera-miner 2>/dev/null || cd "$(dirname "$0")" || exit 1

# single instance (exact-PID discipline: only other mine.sh copies)
me=$$
for pid in $(ps -eo pid=,args= 2>/dev/null | awk '/[m]ine\.sh/ {print $1}'); do
  if [ "$pid" != "$me" ] && [ "$pid" != "$PPID" ]; then kill -9 "$pid" 2>/dev/null || true; fi
done

# trio must exist — fail fast, never mine blind
if [ ! -f "${CHIMERA_SESSIONS_DIR:-/app/work/scripts/sessions}/$SESS/cookies.json" ]; then
  echo "ABORT: no cookies for $SESS (trio missing)"; exit 3
fi

# Xvfb (golden: :99, 1600x900x24)
if ! pgrep -f "Xvfb :99" >/dev/null 2>&1; then
  rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null || true
  mkdir -p /tmp/.X11-unix
  Xvfb :99 -screen 0 1600x900x24 >/tmp/xvfb.log 2>&1 &
  sleep 1
fi
export DISPLAY=:99
export CHIMERA_NO_PROXY=1 CHIMERA_SKIP_IDB=1 CHIMERA_FORCE_HEADED=1
export CHIMERA_VIEW_W=1600 CHIMERA_VIEW_H=900
export CHIMERA_SESSIONS_DIR="${CHIMERA_SESSIONS_DIR:-/app/work/scripts/sessions}"
export CHIMERA_SHOT_DIR=/app/work/shots
export PYTHONUNBUFFERED=1
[ "$THREADS" != "16" ] && export CHIMERA_THREADS="$THREADS"

# watchdog: no "Worker alive" in LOG for WORKER_STALE_S → kill daemon (respawn below)
(
  while true; do
    sleep 90
    [ -f "$LOG" ] || continue
    /opt/venv/bin/python3 -u watchdog_worker.py "$LOG" "$WORKER_STALE_S" 2>/dev/null || \
      python3 -u watchdog_worker.py "$LOG" "$WORKER_STALE_S" 2>/dev/null || true
  done
) &

# forever loop (golden flags, byte-identical command)
PYBIN="/opt/venv/bin/python3"; [ -x "$PYBIN" ] || PYBIN="python3"
while true; do
  if ! pgrep -f "Xvfb :99" >/dev/null 2>&1; then
    rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null || true
    mkdir -p /tmp/.X11-unix
    Xvfb :99 -screen 0 1600x900x24 >/tmp/xvfb.log 2>&1 &
    sleep 1
  fi
  "$PYBIN" -u daemon.py --session "$SESS" --project "$PROJ" \
    --browser chromium --mode full --headed
  ec=$?
  echo "[$(date -u +%H:%M:%S)] supervisor: daemon exited $ec — restart in 8s" >> "$LOG"
  sleep 8
done
