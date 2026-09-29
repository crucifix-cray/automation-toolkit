#!/bin/bash
# Lovable farm job — runs ON the Railway VPS worker.
# Identity comes from Railway's injected RAILWAY_PROJECT_ID, so one generic
# script works on every box with no per-service env plumbing.
#
#   1. clone the repo (payload lives in code, not in the image)
#   2. pick this box's OnK key deterministically from the project id
#   3. farm one Lovable account (shuffled mail providers)
#   4. push the result to GitHub
set -u
JID="${LOV_JID:-0}"
LOG=/tmp/lov_job.log
exec >>"$LOG" 2>&1
echo "===== LOV JOB START $(date -u) jid=$JID project=${RAILWAY_PROJECT_ID:-none} ====="

REPO_DIR=/app/work
rm -rf "$REPO_DIR"
mkdir -p "$REPO_DIR"
if ! git clone --depth 1 https://github.com/crucifix-cray/automation-toolkit "$REPO_DIR"; then
  echo "CLONE FAILED"; exit 10
fi
cd "$REPO_DIR"
echo "cloned: $(git rev-parse --short HEAD)"

# own OnK key — deterministic from project id, so 5 workers/key max (OnK's cap)
KEY=$(python3 - "$JID" <<'PY'
import glob, json, sys
jid = int(sys.argv[1])
fps = sorted(glob.glob("finals/sessions/onk-*/session.json"))
keys = []
for fp in fps:
    try:
        d = json.load(open(fp))
    except Exception:
        continue
    k = d.get("api_key") or ""
    if isinstance(k, str) and k.startswith("sk_"):
        keys.append((d.get("email"), k))
keys.sort(key=lambda t: t[0] or "")
row = keys[jid % len(keys)]
print(row[1])
PY
)
if [ -z "${KEY:-}" ]; then echo "NO ONK KEY FOUND"; exit 11; fi
echo "onk key: ${KEY:0:12}..."

DOMAIN_IDX=""
[ -n "${LOV_DOMAIN_INDEX:-}" ] && DOMAIN_IDX="--domain-index ${LOV_DOMAIN_INDEX}"

export KERNEL_API_KEY="$KEY"
export LD_PRELOAD=""
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy
export PYTHONPATH="$REPO_DIR"
export PYTHONUNBUFFERED=1

python3 src/lovable/farm_lovable_ultimate.py \
  --once \
  --host-key "$KEY" \
  --proxy-country none \
  --zenvex-rounds 2 \
  --shuffle-providers \
  $DOMAIN_IDX
RC=$?
echo "farm exit=$RC"

# report
if [ -d "$REPO_DIR/scripts/sessions" ]; then
  LATEST=$(ls -1dt "$REPO_DIR"/scripts/sessions/session-* 2>/dev/null | head -1)
  [ -n "${LATEST:-}" ] && echo "session dir: $LATEST" && cat "$LATEST/config.json" 2>/dev/null | head -20
fi
echo "===== LOV JOB END $(date -u) rc=$RC ====="
exit $RC
