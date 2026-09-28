#!/bin/bash
# start miner fully detached — survives the SSH session that launched it
# usage: start_miner.sh <session> <project-uuid> <logpath>
SESS=$1; PROJ=$2; LOG=$3
for p in $(ps -eo pid=,args= | awk '/[m]ine.sh|[d]aemon.py --session|[c]hrome/ {print $1}'); do
  kill -9 $p 2>/dev/null
done
sleep 2
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null
cd /app/work/chimera-miner || exit 1
setsid bash -c "nohup ./mine.sh --session $SESS --project $PROJ --log $LOG >/app/work/launcher.log 2>&1" </dev/null >/dev/null 2>&1 &
disown
exit 0
