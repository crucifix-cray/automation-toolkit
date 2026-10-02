#!/usr/bin/env bash
# local_mine.sh — run a miner on THIS box (Camoufox/Chrome headed, DISPLAY=:0).
# Usage: ./local_mine.sh --session <lov-N> --project <uuid> [--log NAME]
# Same golden flags as cells. One instance per session.
set -u
SESS=""; PROJ=""; LOG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --session) SESS="$2"; shift 2;;
    --project) PROJ="$2"; shift 2;;
    --log) LOG="$2"; shift 2;;
    *) echo "unknown arg $1"; exit 2;;
  esac
done
[ -n "$SESS" ] || { echo "ABORT: --session required"; exit 2; }
[ -n "$PROJ" ] || { echo "ABORT: --project required"; exit 2; }
[ -n "$LOG" ] || LOG="/home/alan/miner_$SESS.log"
export LOG
cd /home/alan/Documents/repos/chimera-miner || exit 1
me=$$
for pid in $(ps -eo pid=,args= 2>/dev/null | awk '/[d]aemon\.py --session session-'"${SESS#session-}"'/ {print $1}'); do
  if [ "$pid" != "$me" ] && [ "$pid" != "$PPID" ]; then kill -9 "$pid" 2>/dev/null || true; fi
done
if [ ! -f "/home/alan/Documents/railways/scripts/sessions/$SESS/cookies.json" ]; then
  echo "ABORT: no cookies for $SESS"; exit 3
fi
export DISPLAY=:0
export CHIMERA_NO_PROXY=1 CHIMERA_SKIP_IDB=1 CHIMERA_FORCE_HEADED=1
export CHIMERA_VIEW_W=1600 CHIMERA_VIEW_H=900
export CHIMERA_SESSIONS_DIR=/home/alan/Documents/railways/scripts/sessions
export CHIMERA_SHOT_DIR=/home/alan/Documents/railways/shots
export PYTHONUNBUFFERED=1
BOFF=8
while true; do
  START=$SECONDS
  python3 -u daemon.py --session "$SESS" --project "$PROJ" \
    --browser chromium --mode full --headed >>"$LOG" 2>&1
  ec=$?
  LIVED=$((SECONDS - START))
  if [ "$LIVED" -lt 300 ]; then
    BOFF=$((BOFF * 2)); [ "$BOFF" -gt 600 ] && BOFF=600
  else
    BOFF=8
  fi
  echo "[$(date -u +%H:%M:%S)] supervisor: daemon exited $ec lived=${LIVED}s — restart in ${BOFF}s" >>"$LOG"
  sleep "$BOFF"
done
