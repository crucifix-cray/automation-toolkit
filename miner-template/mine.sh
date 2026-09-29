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
WORKER_STALE_S="${WORKER_STALE_S:-1800}"
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

# Xvfb health: the PROCESS existing is not enough (it can hang while holding
# a stale socket). Healthy = proc exists AND socket exists AND socket is NOT
# older than the proc (a newer proc with an older socket never bound :99).
xvfb_boot() {
  rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null || true
  mkdir -p /tmp/.X11-unix
  for p in $(ps -eo pid=,args= 2>/dev/null | awk '/[X]vfb :99/ {print $1}'); do
    kill -9 "$p" 2>/dev/null || true
  done
  sleep 1
  Xvfb :99 -screen 0 1600x900x24 >/tmp/xvfb.log 2>&1 &
  sleep 2
}
xvfb_ok() {
  XPID=$(ps -eo pid=,args= 2>/dev/null | awk '/[X]vfb :99/ {print $1; exit}')
  [ -n "$XPID" ] || return 1
  [ -S /tmp/.X11-unix/X99 ] || return 1
  SOCK_AGE=$(stat -c %Y /tmp/.X11-unix/X99 2>/dev/null || echo 0)
  PROC_START=$(stat -c %Y /proc/"$XPID" 2>/dev/null || echo 0)
  # proc newer than socket by >120s: it failed to bind, hung
  [ "$PROC_START" -gt "$((SOCK_AGE + 120))" ] && return 1
  return 0
}
if ! xvfb_ok; then xvfb_boot; fi
export DISPLAY=:99
export CHIMERA_NO_PROXY=1 CHIMERA_SKIP_IDB=1 CHIMERA_FORCE_HEADED=1
export CHIMERA_VIEW_W=1600 CHIMERA_VIEW_H=900
export CHIMERA_SESSIONS_DIR="${CHIMERA_SESSIONS_DIR:-/app/work/scripts/sessions}"
export CHIMERA_SHOT_DIR=/app/work/shots
export PYTHONUNBUFFERED=1
[ "$THREADS" != "16" ] && export CHIMERA_THREADS="$THREADS"

# orphan reaper (pure bash, zero forks beyond kill): chrome children
# reparented to PID 1 accumulate on every relaunch and starve the 1GB box
# (seen: 909 procs). Keep the newest 20, kill the rest. Runs inside mine.sh
# so there is nothing extra to keep alive.
(
  while true; do
    sleep 45
    all=""
    for d in /proc/[0-9]*/; do
      pid=${d#/proc/}; pid=${pid%/}
      case "$pid" in ''|*[!0-9]*) continue;; esac
      if read -r cmd < "$d/cmdline" 2>/dev/null; then
        case "$cmd" in *chrome*) all="$all $pid";; esac
      fi
    done
    # /proc iterates PID-ascending: keep the LAST 20 (newest = live tree)
    set -- $all
    total=$#
    if [ "$total" -gt 20 ]; then
      drop=$((total - 20)); nkill=0
      for p in $all; do
        [ "$nkill" -ge "$drop" ] && break
        kill -9 "$p" 2>/dev/null && nkill=$((nkill+1))
      done
      [ "$nkill" -gt 0 ] && echo "[$(date -u +%H:%M:%S)] reaper: killed $nkill orphan chrome (had $total)" >> "$LOG"
    fi
  done
) &

# watchdog: no "Worker alive" in LOG for WORKER_STALE_S → kill daemon (respawn below)
(
  while true; do
    sleep 90
    [ -f "$LOG" ] || continue
    /opt/venv/bin/python3 -u watchdog_worker.py "$LOG" "$WORKER_STALE_S" 2>/dev/null || \
      python3 -u watchdog_worker.py "$LOG" "$WORKER_STALE_S" 2>/dev/null || true
  done
) &

# forever loop (golden flags, byte-identical command) with crash backoff:
# quick deaths in a row mean the box is choking — back off instead of churning.
PYBIN="/opt/venv/bin/python3"; [ -x "$PYBIN" ] || PYBIN="python3"
BOFF=8
while true; do
  if ! xvfb_ok; then xvfb_boot; fi
  START=$SECONDS
  "$PYBIN" -u daemon.py --session "$SESS" --project "$PROJ" \
    --browser chromium --mode full --headed
  ec=$?
  LIVED=$((SECONDS - START))
  if [ "$LIVED" -lt 300 ]; then
    BOFF=$((BOFF * 2)); [ "$BOFF" -gt 600 ] && BOFF=600
  else
    BOFF=8
  fi
  echo "[$(date -u +%H:%M:%S)] supervisor: daemon exited $ec lived=${LIVED}s — restart in ${BOFF}s" >> "$LOG"
  sleep "$BOFF"
done
