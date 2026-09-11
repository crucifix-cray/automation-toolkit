#!/bin/bash
# cell_ssh.sh <railway-session> <project> <env> <service> -- <cmd...>
# Runs `railway ssh` with a DEDICATED agent holding only that session's key.
# (Multi-key agents mis-resolve to the wrong Railway account.)
# Raw IP: proxies stripped, LD_PRELOAD cleared.
USAGE="usage: cell_ssh.sh <session> <project> <env> <service> -- <cmd...>"
SESS="${1:?}"; PROJ="${2:?}"; ENV="${3:?}"; SVC="${4:?}"; shift 4
[ "$1" = "--" ] && shift
REPO=/home/alae/Documents/repos/automation-toolkit
# ponytail: handle both layouts — new repo sessions/ and old /home/alan/Documents/railways/sessions
if [ -f "$REPO/sessions/$SESS/.ssh/cellkey" ]; then
  CELLKEY="$REPO/sessions/$SESS/.ssh/cellkey"
  HOMEDIR="$REPO/sessions/$SESS"
elif [ -f "/home/alae/Documents/railways/$SESS/.ssh/cellkey" ]; then
  CELLKEY="/home/alae/Documents/railways/$SESS/.ssh/cellkey"
  HOMEDIR="/home/alae/Documents/railways/$SESS"
else
  CELLKEY="/home/alan/Documents/railways/sessions/$SESS/.ssh/cellkey"
  HOMEDIR="/home/alan/Documents/railways/sessions/$SESS"
fi
SOCKDIR=/tmp/agents
mkdir -p "$SOCKDIR"
SOCK="$SOCKDIR/$SESS.sock"
if ! SSH_AUTH_SOCK="$SOCK" ssh-add -l >/dev/null 2>&1; then
  rm -f "$SOCK"
  ssh-agent -a "$SOCK" >/dev/null 2>&1
  SSH_AUTH_SOCK="$SOCK" ssh-add -q "$CELLKEY" || exit 7
fi
export SSH_AUTH_SOCK="$SOCK" HOME="$HOMEDIR" LD_PRELOAD=""
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
exec /home/alan/.railway/bin/railway ssh -p "$PROJ" -e "$ENV" -s "$SVC" -- "$@"
