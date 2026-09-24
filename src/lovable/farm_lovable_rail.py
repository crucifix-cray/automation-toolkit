#!/usr/bin/env python3
"""Railway-parallel Lovable ultimate farm (warm-up / preflight / scale).

Spreads OnK keys across Railway sandboxes. Each sandbox runs one
`farm_lovable_ultimate.py --once` (mobile-GB → mail chain → signup → 2FA → farm/lov-* push).

Local scripts are injected as a tarball (main may not have ultimate yet).

Usage:
  # wipe leftover sandboxes on the linked host
  python3 src/lovable/farm_lovable_rail.py --destroy-all

  # preflight 10 (warm the fleet)
  python3 src/lovable/farm_lovable_rail.py --launch --count 10

  # watch
  python3 src/lovable/farm_lovable_rail.py --status

  # later dial up (still per-host sandbox cap ~10)
  python3 src/lovable/farm_lovable_rail.py --launch --count 10
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE = Path(os.environ.get("LOV_FARM_STATE", "/home/alae/lov-rail-preflight"))
HOST_HOME = Path(os.environ.get("HOLY_HOST_HOME", "/home/alae/Documents/railways/session-1"))
CHECKPOINT = os.environ.get("HOLY_CHECKPOINT", "holy-ready-v1")
PROXY_COUNTRY = os.environ.get("LOV_PROXY_COUNTRY", "gb")
# One distinct OnK mobile country per worker (avoid US — Firebase suspicious).
# Rotates if --count > len(list).
MOBILE_COUNTRIES = [
    c.strip().lower()
    for c in os.environ.get(
        "LOV_MOBILE_COUNTRIES",
        "gb,de,fr,nl,ie,es,it,be,at,se",
    ).split(",")
    if c.strip()
]

# files not necessarily on origin/main yet — packed into each sandbox
# Keep overlay SMALL: Railway sandbox exec caps ~32KB stdout/cmd payload.
# account_creation.py (~85KB) stays on git clone main; critical farm fixes are below.
INJECT_FILES = [
    "src/lovable/farm_lovable_ultimate.py",
    "src/lovable/mail_chain.py",
    "src/lovable/session_state.py",
    "src/railway/gh_push.py",
]


def run(cmd: list[str], env: dict | None = None, timeout: int = 600) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    if env:
        e.update(env)
    e["HOME"] = str(HOST_HOME)
    e["LD_PRELOAD"] = ""
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        e.pop(k, None)
    return subprocess.run(cmd, env=e, capture_output=True, text=True, timeout=timeout)


def railway(*args: str, timeout: int = 600) -> subprocess.CompletedProcess:
    return run(["railway", *args], timeout=timeout)


def ensure_linked() -> None:
    if os.environ.get("HOLY_SKIP_LINK") == "1":
        return
    railway("link", "-p", "talented-celebration", "-e", "production", "-s", "brilliant-determination")


def sb_exec(sb_id: str, script: str, detach: bool = False, timeout: int = 900) -> subprocess.CompletedProcess:
    args = ["sandbox", "exec", "--id", sb_id]
    if detach:
        args.append("--detach")
    args += ["--", "bash", "-lc", script]
    return railway(*args, timeout=timeout)


def load_onk_keys() -> list[dict]:
    """Unlocked OnK keys, sorted by filename. Prefer taking from the *end*
    at launch time — early keys were burned on prior waves; last ones keep credit.
    """
    keys, seen = [], set()
    for fp in sorted((REPO / "finals" / "sessions").glob("onk_*.json")):
        if fp.name.endswith((".cookies.json", ".storage.json")):
            continue
        try:
            d = json.loads(fp.read_text())
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        k = d.get("api_key") or ""
        if d.get("tag") != "unlocked" or not isinstance(k, str) or not k.startswith("sk_") or k in seen:
            continue
        seen.add(k)
        keys.append({"email": d.get("email"), "api_key": k, "file": str(fp)})
    return keys


def pick_onk_keys(count: int) -> list[dict]:
    """One distinct api_key per worker, from the *last* unlocked keys.

    Skips individual api_keys marked unhealthy by /tmp/onk-credit-probe.json
    (match on onk_*.json file path — same email can have multiple orgs/keys).
    """
    keys = load_onk_keys()
    bad_files = set()
    probe = Path("/tmp/onk-credit-probe.json")
    if probe.is_file():
        try:
            for r in json.loads(probe.read_text()).get("results") or []:
                if r.get("status") not in ("OK", "LIMIT") and r.get("file"):
                    bad_files.add(str(Path(r["file"]).resolve()))
        except Exception:
            pass
    if bad_files:
        before = len(keys)
        keys = [k for k in keys if str(Path(k["file"]).resolve()) not in bad_files]
        print(f"→ OnK keys: skipped {before - len(keys)} unhealthy api_key(s) from probe")
    if len(keys) < count:
        raise SystemExit(f"need {count} healthy unlocked OnK keys, have {len(keys)}")
    chosen = keys[-count:]  # healthy / least-used end of pack
    print(f"→ OnK keys: using LAST {count}/{len(keys)} unlocked (distinct api_key each)")
    for i, k in enumerate(chosen):
        print(f"   [{i}] {k.get('email')}")
    return chosen


def pack_inject_b64() -> str:
    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for rel in INJECT_FILES:
            path = REPO / rel
            if not path.is_file():
                raise SystemExit(f"missing inject file: {rel}")
            tf.add(path, arcname=rel)
    return base64.b64encode(buf.getvalue()).decode()


def list_sandboxes() -> list[dict]:
    r = railway("sandbox", "list", "--json")
    text = r.stdout + r.stderr
    i = text.find("[")
    if i < 0:
        return []
    try:
        data, _ = json.JSONDecoder().raw_decode(text[i:])
        return data if isinstance(data, list) else []
    except Exception:
        return []


def destroy_all() -> None:
    ensure_linked()
    for it in list_sandboxes():
        sid = it["id"]
        print("destroy", sid[:8], it.get("status"))
        railway("sandbox", "destroy", sid, timeout=120)


def launch(count: int) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    ensure_linked()
    keys = pick_onk_keys(count)

    passphrase = (REPO / "finals" / "secrets" / "holy_secret_key.local").read_text().strip()
    sys.path.insert(0, str(REPO))
    from src.utils.secret_box import decrypt_github_token
    token = decrypt_github_token(path=REPO / "finals" / "secrets" / "gh_token.enc")
    tarball_b64 = pack_inject_b64()

    workers = []
    countries = MOBILE_COUNTRIES or [PROXY_COUNTRY]
    print(
        f"→ creating {count} sandboxes from checkpoint={CHECKPOINT} "
        f"mobile_countries={countries[:count]} (1 distinct country / worker)"
    )
    for i in range(count):
        r = railway(
            "sandbox", "create",
            "--idle-timeout-minutes", "5",
            "--checkpoint", CHECKPOINT,
            "--json",
            timeout=180,
        )
        text = r.stdout + r.stderr
        if "{" not in text:
            print(f"  create fail [{i}]: {(r.stderr or r.stdout)[:240]}")
            continue
        j = text[text.find("{") : text.rfind("}") + 1]
        try:
            meta = json.loads(j)
        except Exception as e:
            print(f"  parse fail [{i}]: {e} {text[:200]}")
            continue
        key = keys[i]  # distinct key per worker for preflight
        wid = f"lov{i:02d}"
        country = countries[i % len(countries)]
        workers.append({
            "id": meta["id"],
            "host": wid,
            "onk_email": key["email"],
            "onk_key": key["api_key"],
            "status": "created",
            "proxy_country": country,
        })
        print(f"  {wid} sb={meta['id'][:8]}… country={country} key={str(key['email'])[:28]}")
        time.sleep(0.3)

    (STATE / "workers.json").write_text(json.dumps(workers, indent=2))
    print(f"→ injecting + starting {len(workers)} workers")

    def start_one(w: dict) -> dict:
        sb = w["id"]
        sb_exec(sb, "while true; do date -u >> /tmp/keepalive.log; sleep 20; done", detach=True)
        b64_pass = base64.b64encode(passphrase.encode()).decode()
        b64_tok = base64.b64encode(token.encode()).decode()
        b64_key = base64.b64encode(w["onk_key"].encode()).decode()
        host = w["host"]
        country = w["proxy_country"]
        # tarball is large — write via python from env chunk? Keep inline; ~100KB ok
        inject = f'''
set -e
mkdir -p /root/secrets /app
echo {b64_pass} | base64 -d > /root/secrets/holy_secret_key
echo {b64_tok} | base64 -d > /root/secrets/gh_token
echo {b64_key} | base64 -d > /root/secrets/onk_key
chmod 600 /root/secrets/*
TOK=$(cat /root/secrets/gh_token)
rm -rf /app/toolkit
git clone --depth 1 -b main "https://x-access-token:${{TOK}}@github.com/crucifix-cray/automation-toolkit.git" /app/toolkit
git -C /app/toolkit remote set-url origin https://github.com/crucifix-cray/automation-toolkit.git
# overlay local ultimate scripts (may not be on main yet)
python3 - <<'PY'
import base64, tarfile, io
b = base64.b64decode("""{tarball_b64}""")
with tarfile.open(fileobj=io.BytesIO(b), mode="r:gz") as tf:
    tf.extractall("/app/toolkit", filter="data")
print("OVERLAY_OK")
PY
test -f /app/toolkit/src/lovable/farm_lovable_ultimate.py
cat > /root/run_lov.sh << 'EOS'
#!/bin/bash
set -euo pipefail
export PATH="/root/.railway/bin:/root/.local/share/mise/shims:/usr/bin:$PATH"
export HOME=/root
export LD_PRELOAD=
export SKIP_MEGA=1
export CHIMERA_SKIP_MEGA_SYNC=1
export PYTHONUNBUFFERED=1
export TOOLKIT_ROOT=/app/toolkit
export HOLY_SECRET_KEY="$(cat /root/secrets/holy_secret_key)"
export KERNEL_API_KEY="$(cat /root/secrets/onk_key)"
export GH_PUSH=1
export GH_REPO=crucifix-cray/automation-toolkit
export GH_BASE_BRANCH=main
export GH_FARM_HOST=HOST_PLACEHOLDER
export CHIMERA_SESSIONS_DIR=/root/lov-sessions
mkdir -p "$CHIMERA_SESSIONS_DIR"
while IFS= read -r line; do
  case "$line" in RAILWAY_*=*) unset "${{line%%=*}}" ;; esac
done < <(env | grep -E '^RAILWAY_' || true)
cd /app/toolkit
pip3 install -q pyotp cryptography 2>/dev/null || true
echo "START $(date -u +%FT%TZ) host=$GH_FARM_HOST country=COUNTRY_PLACEHOLDER" | tee /tmp/lov-run.log
exec python3 -u src/lovable/farm_lovable_ultimate.py --once --proxy-country COUNTRY_PLACEHOLDER >> /tmp/lov-run.log 2>&1
EOS
sed -i "s/HOST_PLACEHOLDER/{host}/; s/COUNTRY_PLACEHOLDER/{country}/g" /root/run_lov.sh
chmod +x /root/run_lov.sh
echo INJECT_OK
'''
        # sandboxes need a few seconds after create before exec works
        time.sleep(3 + (int(host.replace("lov", "") or "0") % 5))
        out = ""
        for attempt in range(1, 4):
            r = sb_exec(sb, inject, timeout=600)
            out = (r.stdout or "") + (r.stderr or "")
            if "INJECT_OK" in out:
                break
            time.sleep(5 * attempt)
        if "INJECT_OK" not in out:
            w["status"] = "inject_fail"
            w["err"] = out[-400:]
            return w
        sb_exec(sb, "/root/run_lov.sh", detach=True)
        w["status"] = "running"
        return w

    if not workers:
        print("❌ no sandboxes created — free slots with --destroy-all then retry")
        return

    with ThreadPoolExecutor(max_workers=min(10, len(workers))) as ex:
        futs = [ex.submit(start_one, w) for w in workers]
        out = []
        for fut in as_completed(futs):
            w = fut.result()
            out.append(w)
            print(f"  start {w['host']} → {w['status']}")
    (STATE / "workers.json").write_text(json.dumps(out, indent=2))
    running = sum(1 for w in out if w["status"] == "running")
    print(f"🏁 launched running={running}/{len(out)}")
    print(f"   state: {STATE}/workers.json")
    print(f"   watch: python3 src/lovable/farm_lovable_rail.py --status")


def status() -> None:
    path = STATE / "workers.json"
    if not path.is_file():
        print("no workers.json")
        return
    workers = json.loads(path.read_text())
    ensure_linked()

    def check(w: dict) -> dict:
        sb = w["id"]
        r = sb_exec(
            sb,
            'echo PROCS=$(pgrep -c -f "farm_lovable_ultimate" || echo 0); '
            'rg -n "SUCCESS|Pushed lov-|FAIL:|totp_secret|Verified:|suspicious|Traceback|Mailbox ready|2FA enabled|2FA not set|2fa_pending|refresh_token" /tmp/lov-run.log 2>/dev/null | tail -14; '
            'echo "---"; tail -8 /tmp/lov-run.log 2>/dev/null',
            timeout=120,
        )
        out = r.stdout or ""
        w["log_tail"] = out[-1200:]
        if "Pushed lov-" in out or '"ok": true' in out or "2FA enabled" in out or "2FA not set" in out:
            w["status"] = "ok"
        elif "FAIL:" in out or "Traceback" in out or "suspicious" in out:
            w["status"] = "fail"
        elif "PROCS=0" in out and "START " in out:
            w["status"] = "done_unknown"
        elif "PROCS=" in out and "PROCS=0" not in out:
            w["status"] = "running"
        return w

    with ThreadPoolExecutor(max_workers=min(10, len(workers))) as ex:
        updated = list(ex.map(check, workers))
    (STATE / "workers.json").write_text(json.dumps(updated, indent=2))
    from collections import Counter
    c = Counter(w.get("status") for w in updated)
    print(dict(c))
    for w in updated:
        print(f"\n=== {w['host']} {w.get('status')} {str(w.get('onk_email',''))[:28]} ===")
        print((w.get("log_tail") or "")[-500:])


def main() -> int:
    ap = argparse.ArgumentParser(description="Railway parallel Lovable ultimate")
    ap.add_argument("--launch", action="store_true")
    ap.add_argument("--count", type=int, default=10, help="parallel sandboxes (default 10 preflight)")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--destroy-all", action="store_true")
    ap.add_argument("--proxy-country", default=None)
    args = ap.parse_args()
    if args.proxy_country:
        global PROXY_COUNTRY
        PROXY_COUNTRY = args.proxy_country

    if args.destroy_all:
        destroy_all()
        return 0
    if args.launch:
        launch(args.count)
        return 0
    if args.status:
        status()
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
