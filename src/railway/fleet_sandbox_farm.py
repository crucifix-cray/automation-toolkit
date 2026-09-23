#!/usr/bin/env python3
"""Parallel Holy farm on Railway sandboxes (one compute project).

Spreads Batch-B OnKernel keys + unique mobile proxies across N sandboxes.
Each worker pushes MADE jars to a unique farm/* branch (no main conflicts).

Usage:
  # build checkpoint once (deps baked)
  python3 src/railway/fleet_sandbox_farm.py --build-checkpoint

  # blast N workers (default: min(40, 4*num_onk_keys))
  python3 src/railway/fleet_sandbox_farm.py --launch --count 40

  # monitor
  python3 src/railway/fleet_sandbox_farm.py --status

  # after wave: merge farm branches
  python3 src/railway/merge_farm_branches.py
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
API = "https://api.onkernel.com"
STATE = Path(os.environ.get("HOLY_FARM_STATE", "/home/alae/onk-rail-fleet"))
HOST_HOME = Path(os.environ.get("HOLY_HOST_HOME", "/home/alae/Documents/railways/session-1"))
CHECKPOINT = os.environ.get("HOLY_CHECKPOINT", "holy-ready-v1")


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


def load_onk_keys() -> list[dict]:
    keys = []
    seen = set()
    for fp in sorted((REPO / "finals" / "sessions").glob("onk_*.json")):
        if fp.name.endswith((".cookies.json", ".storage.json")):
            continue
        d = json.loads(fp.read_text())
        k = d.get("api_key") or ""
        if d.get("tag") != "unlocked" or not k.startswith("sk_") or k in seen:
            continue
        seen.add(k)
        keys.append({"email": d.get("email"), "api_key": k, "file": str(fp)})
    return keys


def create_mobile_proxy(api_key: str) -> str:
    name = f"mobi-fleet-{uuid.uuid4().hex[:10]}"
    body = json.dumps({"name": name, "type": "mobile", "config": {"country": "us"}}).encode()
    req = urllib.request.Request(
        API + "/proxies",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            if resp.status in (200, 201):
                return name
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"proxy create {e.code}: {e.read()[:200]}") from e
    raise RuntimeError("proxy create failed")


def sb_exec(sb_id: str, script: str, detach: bool = False, timeout: int = 900) -> subprocess.CompletedProcess:
    args = ["sandbox", "exec", "--id", sb_id]
    if detach:
        args.append("--detach")
    args += ["--", "bash", "-lc", script]
    return railway(*args, timeout=timeout)


def ensure_linked() -> None:
    # talented-celebration proven for session-1 host
    r = railway("link", "-p", "talented-celebration", "-e", "production", "-s", "brilliant-determination")
    if r.returncode != 0 and "linked" not in (r.stdout + r.stderr).lower():
        # non-interactive may still succeed with prompts swallowed
        pass


def build_checkpoint() -> str:
    STATE.mkdir(parents=True, exist_ok=True)
    ensure_linked()
    print("→ create golden sandbox")
    r = railway("sandbox", "create", "--idle-timeout-minutes", "5", "--json")
    text = r.stdout + r.stderr
    j = text[text.find("{") : text.rfind("}") + 1]
    meta = json.loads(j)
    sb = meta["id"]
    print("  sb", sb)
    # keepalive
    sb_exec(sb, "while true; do date -u >> /tmp/keepalive.log; sleep 25; done", detach=True)
    time.sleep(2)
    bootstrap = r'''
set -e
export PATH="/root/.local/share/mise/shims:$PATH"
mise install python@3.12.10
mise use -g python@3.12.10
hash -r
python3 --version
pip3 install -q cryptography playwright httpx
python3 -m playwright install-deps chromium
python3 -m playwright install chromium
npm install -g @onkernel/cli --silent
command -v railway >/dev/null || curl -fsSL https://railway.com/install.sh | sh
export PATH="$HOME/.railway/bin:/root/.local/share/mise/shims:$PATH"
which python3 kernel railway git
python3 - <<PY
import asyncio
from playwright.async_api import async_playwright
async def main():
  async with async_playwright() as p:
    b=await p.chromium.launch(headless=True)
    page=await b.new_page()
    await page.goto('https://example.com', timeout=60000)
    print('LAUNCH_OK', await page.title())
    await b.close()
asyncio.run(main())
PY
echo BOOTSTRAP_OK
'''
    print("→ bootstrap deps (long)")
    r = sb_exec(sb, bootstrap, timeout=900)
    print(r.stdout[-800:] if r.stdout else "")
    print(r.stderr[-400:] if r.stderr else "")
    if "BOOTSTRAP_OK" not in (r.stdout or ""):
        raise SystemExit("bootstrap failed")
    print("→ checkpoint", CHECKPOINT)
    r = railway("sandbox", "checkpoint", "create", CHECKPOINT)
    print(r.stdout, r.stderr)
    (STATE / "checkpoint.json").write_text(json.dumps({"name": CHECKPOINT, "golden_sb": sb}, indent=2))
    print("✅ checkpoint ready:", CHECKPOINT)
    return sb


def launch(count: int) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    ensure_linked()
    keys = load_onk_keys()
    if not keys:
        raise SystemExit("no unlocked OnK keys")
    passphrase = (REPO / "finals" / "secrets" / "holy_secret_key.local").read_text().strip()
    token = None
    sys.path.insert(0, str(REPO))
    from src.utils.secret_box import decrypt_github_token
    token = decrypt_github_token(path=REPO / "finals" / "secrets" / "gh_token.enc")

    # create sandboxes from checkpoint
    workers = []
    print(f"→ creating {count} sandboxes from checkpoint={CHECKPOINT}")
    for i in range(count):
        r = railway(
            "sandbox", "create",
            "--idle-timeout-minutes", "5",
            "--checkpoint", CHECKPOINT,
            "--json",
        )
        text = r.stdout + r.stderr
        if "{" not in text:
            print(f"  create fail [{i}]: {(r.stderr or r.stdout)[:200]}")
            continue
        j = text[text.find("{") : text.rfind("}") + 1]
        try:
            meta = json.loads(j)
        except Exception as e:
            print(f"  parse fail [{i}]: {e} {text[:200]}")
            continue
        wid = f"sb{i:02d}"
        key = keys[i % len(keys)]
        try:
            proxy = create_mobile_proxy(key["api_key"])
        except Exception as e:
            print(f"  proxy fail [{wid}]: {e}")
            continue
        workers.append({
            "id": meta["id"],
            "host": wid,
            "onk_email": key["email"],
            "onk_key": key["api_key"],
            "proxy": proxy,
            "status": "created",
        })
        print(f"  {wid} sb={meta['id'][:8]}… key={key['email'][:20]}… proxy={proxy}")
        time.sleep(0.4)

    (STATE / "workers.json").write_text(json.dumps(workers, indent=2))
    print(f"→ injecting + starting {len(workers)} workers")

    def start_one(w: dict) -> dict:
        sb = w["id"]
        # keepalive
        sb_exec(sb, "while true; do date -u >> /tmp/keepalive.log; sleep 20; done", detach=True)
        b64_pass = base64.b64encode(passphrase.encode()).decode()
        b64_tok = base64.b64encode(token.encode()).decode()
        b64_key = base64.b64encode(w["onk_key"].encode()).decode()
        proxy = w["proxy"]
        host = w["host"]
        inject = f'''
set -e
mkdir -p /root/secrets /root/Documents/railways /app
echo {b64_pass} | base64 -d > /root/secrets/holy_secret_key
echo {b64_tok} | base64 -d > /root/secrets/gh_token
echo {b64_key} | base64 -d > /root/secrets/onk_key
printf '%s' '{proxy}' > /root/secrets/proxy_name
chmod 600 /root/secrets/*
# clone toolkit fresh (has conflict-free gh_push)
TOK=$(cat /root/secrets/gh_token)
rm -rf /app/toolkit
git clone --depth 1 -b main "https://x-access-token:${{TOK}}@github.com/crucifix-cray/automation-toolkit.git" /app/toolkit
git -C /app/toolkit remote set-url origin https://github.com/crucifix-cray/automation-toolkit.git
cat > /root/run_holy.sh << 'EOS'
#!/bin/bash
set -euo pipefail
export PATH="/root/.railway/bin:/root/.local/share/mise/shims:/usr/bin:$PATH"
export HOME=/root
export LD_PRELOAD=
export SKIP_MEGA=1
export PYTHONUNBUFFERED=1
export TOOLKIT_ROOT=/app/toolkit
export HOLY_SECRET_KEY="$(cat /root/secrets/holy_secret_key)"
export KERNEL_API_KEY="$(cat /root/secrets/onk_key)"
export GH_PUSH=1
export GH_REPO=crucifix-cray/automation-toolkit
export GH_BASE_BRANCH=main
export GH_FARM_HOST=HOST_PLACEHOLDER
PROXY=$(cat /root/secrets/proxy_name)
while IFS= read -r line; do
  case "$line" in RAILWAY_*=*) unset "${{line%%=*}}" ;; esac
done < <(env | grep -E '^RAILWAY_' || true)
mkdir -p /root/Documents/railways
cd /app/toolkit
echo "START $(date -u +%FT%TZ) host=$GH_FARM_HOST proxy=$PROXY" | tee /tmp/holy-run.log
exec python3 -u src/railway/account_creation.py --kernel --kernel-proxy "$PROXY" --once --no-warp >> /tmp/holy-run.log 2>&1
EOS
sed -i "s/HOST_PLACEHOLDER/{host}/" /root/run_holy.sh
chmod +x /root/run_holy.sh
echo INJECT_OK
'''
        r = sb_exec(sb, inject, timeout=600)
        if "INJECT_OK" not in (r.stdout or ""):
            w["status"] = "inject_fail"
            w["err"] = (r.stderr or r.stdout or "")[-300:]
            return w
        sb_exec(sb, "/root/run_holy.sh", detach=True)
        w["status"] = "running"
        return w

    # parallel inject/start (sandbox API can take it)
    with ThreadPoolExecutor(max_workers=min(12, len(workers))) as ex:
        futs = [ex.submit(start_one, w) for w in workers]
        out = []
        for fut in as_completed(futs):
            w = fut.result()
            out.append(w)
            print(f"  start {w['host']} → {w['status']}")
    (STATE / "workers.json").write_text(json.dumps(out, indent=2))
    print(f"🏁 launched running={sum(1 for w in out if w['status']=='running')}/{len(out)}")
    print(f"   state: {STATE}/workers.json")


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
            'echo PROCS=$(pgrep -c -f "account_creation.py --kernel" || echo 0); '
            'rg -n "MADE account|Pushed farmed-|No new verified|Traceback|SERVICE OK|git push failed" /tmp/holy-run.log 2>/dev/null | tail -8; '
            'tail -5 /tmp/holy-run.log 2>/dev/null',
            timeout=120,
        )
        out = r.stdout or ""
        w["log_tail"] = out[-800:]
        if "SERVICE OK" in out or "MADE account" in out:
            w["status"] = "made"
        elif "Pushed farmed-" in out:
            w["status"] = "pushed"
        elif "PROCS=0" in out.replace(" ", ""):
            w["status"] = "done_or_dead"
        return w

    with ThreadPoolExecutor(max_workers=10) as ex:
        workers = list(ex.map(check, workers))
    (STATE / "workers.json").write_text(json.dumps(workers, indent=2))
    from collections import Counter
    c = Counter(w.get("status") for w in workers)
    print(dict(c))
    for w in workers:
        print(f"{w['host']} {w.get('status')} {w.get('onk_email','')[:24]}")


def destroy_all() -> None:
    ensure_linked()
    r = railway("sandbox", "list", "--json")
    text = r.stdout + r.stderr
    text = text[text.find("[") :]
    try:
        items = json.loads(text)
    except Exception:
        print("list parse fail", (r.stdout or r.stderr)[:300])
        return
    for it in items:
        sid = it["id"]
        print("destroy", sid[:8])
        railway("sandbox", "destroy", sid)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-checkpoint", action="store_true")
    ap.add_argument("--launch", action="store_true")
    ap.add_argument("--count", type=int, default=0)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--destroy-all", action="store_true")
    args = ap.parse_args()

    if args.build_checkpoint:
        build_checkpoint()
        return 0
    if args.launch:
        keys = load_onk_keys()
        n = args.count or min(40, max(10, len(keys) * 4))
        launch(n)
        return 0
    if args.status:
        status()
        return 0
    if args.destroy_all:
        destroy_all()
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
