#!/bin/bash
# tor_cli.sh <session> -- <railway args...>
# Run railway CLI through a dedicated Tor circuit (fresh exit per call via -i).
# Port rotates by session number: 9051/9053/9054/9250/9050.
# NOTE: CLI ignores *PROXY env — torsocks (LD_PRELOAD) is the only way.
USAGE="usage: tor_cli.sh <session-N> -- <railway args>"
SESS="${1:?}"; shift
[ "$1" = "--" ] && shift
REPO=/home/alan/Documents/railways
N=${SESS#session-}
PORTS=(9051 9053 9054 9250 9050)
PORT=${PORTS[$((10#$N % 5))]}
CONF=/tmp/torsocks$PORT.conf
[ -f "$CONF" ] || printf 'server = 127.0.0.1\nserver_port = %s\n' "$PORT" > "$CONF"
export TORSOCKS_CONF_FILE="$CONF" HOME="$REPO/sessions/$SESS"
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy
exec torsocks -i /home/alan/.railway/bin/railway "$@"
