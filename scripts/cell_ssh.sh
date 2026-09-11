#!/bin/bash
# cell_ssh.sh <railway-session> <project> <env> <service> -- <cmd...>
# Runs `railway ssh` with a DEDICATED agent holding only that session's key.
# (Multi-key agents mis-resolve to the wrong Railway account.)
# Raw IP: proxies stripped, LD_PRELOAD cleared.
USAGE="usage: cell_ssh.sh <session> <project> <env> <service> -- <cmd...>"
SESS="${1:?}"; PROJ="${2:?}"; ENV="${3:?}"; SVC="${4:?}"; shift 4
[ "$1" = "--" ] && shift
REPO=/home/alan/Documents/railways
SOCKDIR=/tmp/agents
mkdir -p "$SOCKDIR"
SOCK="$SOCKDIR/$SESS.sock"
if ! SSH_AUTH_SOCK="$SOCK" ssh-add -l >/dev/null 2>&1; then
  rm -f "$SOCK"
  ssh-agent -a "$SOCK" >/dev/null 2>&1
  SSH_AUTH_SOCK="$SOCK" ssh-add -q "$REPO/sessions/$SESS/.ssh/cellkey" || exit 7
fi
export SSH_AUTH_SOCK="$SOCK" HOME="$REPO/sessions/$SESS" LD_PRELOAD=""
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
exec /home/alan/.railway/bin/railway ssh -p "$PROJ" -e "$ENV" -s "$SVC" -- "$@"
