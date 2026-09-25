#!/usr/bin/env python3
"""Refill all farm hosts back up to SLOTS running sandbox workers.

SELF-CONTAINED (lives outside the toolkit repo on purpose): the supervisor
tick's `git checkout main` + farm-branch merges rewrite in-repo tool files,
so this intentionally duplicates fleet_sandbox_farm.py's create/inject logic
instead of calling `--refill` (which does not exist in the repo copy).

Per host:
  1. (Re)starts sandboxes that exist but never started (status=created) in place.
  2. Destroys dead/finished sandboxes (frees the 10-sandbox env quota).
  3. Creates fresh sandboxes for the shortfall (from CHECKPOINT) and starts them.
Trusts status=running (periodic --status tick corrects it).

Same env contract as before (set by supervisor or manually):
  HOLY_HOST_HOME, HOLY_FARM_STATE (per-host below), HOLY_CHECKPOINT,
  HOME (per-host below), LD_PRELOAD='', HOLY_SECRET_KEY,
  HOLY_ONK_KEYS_FILE (per-host host_keys/session-N.json)
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, "/home/alae/onk-rail-1k")
from mail_rotate import pick as pick_provider  # noqa: E402

REPO = Path("/home/alae/Documents/repos/automation-toolkit")
RAIL = Path("/home/alae/Documents/railways")
SESS = [int(x) for x in open("/tmp/rail-ok-hosts.txt").read().split(",") if x.strip()]
SLOTS = 8
API = "https://api.onkernel.com"
HOLY = os.environ.get("HOLY_SECRET_KEY") or (REPO / "finals/secrets/holy_secret_key.local").read_text().strip()
os.environ["HOLY_SECRET_KEY"] = HOLY

sys.path.insert(0, str(REPO))
from src.utils.secret_box import decrypt_github_token

GH_TOKEN = decrypt_github_token(path=REPO / "finals/secrets/gh_token.enc")


def rail(home: Path, *args: str, timeout: int = 600) -> subprocess.CompletedProcess:
    e = {**os.environ, "HOME": str(home), "LD_PRELOAD": "",
         "BROWSER": "/home/alae/bin/no-browser",
         "PATH": "/home/alae/bin:" + os.environ.get("PATH", "/usr/bin")}
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        e.pop(k, None)
    # NOTE: railway links are directory-scoped — always run from REPO where
    # each host HOME has its project link, regardless of caller CWD.
    return subprocess.run(["railway", *args], cwd=str(REPO), env=e,
                          capture_output=True, text=True, timeout=timeout)


def load_keys(n: int) -> list[dict]:
    kf = Path(f"/home/alae/onk-rail-1k/host_keys/session-{n}.json")
    if kf.is_file():
        rows = json.loads(kf.read_text())
    else:
        rows = []
    keys, seen = [], set()
    for r in rows:
        k = (r.get("api_key") or "").strip()
        if k.startswith("sk_") and k not in seen:
            seen.add(k)
            keys.append({"email": r.get("email"), "api_key": k})
    return keys


def create_proxy(api_key: str) -> str:
    import uuid
    name = f"mobi-refill-{uuid.uuid4().hex[:10]}"
    body = json.dumps({"name": name, "type": "mobile", "config": {"country": "us"}}).encode()
    req = urllib.request.Request(API + "/proxies", data=body, method="POST",
                                 headers={"Authorization": f"Bearer {api_key}",
                                          "Accept": "application/json",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        if resp.status in (200, 201):
            return name
    raise RuntimeError("proxy create failed")


def sb_exec(home: Path, sb_id: str, script: str, detach: bool = False, timeout: int = 900):
    args = ["sandbox", "exec", "--id", sb_id]
    if detach:
        args.append("--detach")
    return rail(home, *args, "--", "bash", "-lc", script, timeout=timeout)


def start_single(home: Path, w: dict) -> dict:
    """Inject + start one EXISTING sandbox (same as launch's start_one, hardened).

    Mailbox provider is chosen by mail_rotate.pick() (weighted rotation, not
    pure random) and baked into the worker as an explicit --domain, so the
    fleet spreads across providers instead of collapsing onto one. 2026-09-25
    lesson: 100% one provider + ~10 egress IPs = instant Railway restriction.
    """
    try:
        sb = w["id"]
        provider = pick_provider(w.get("host", "sb"))
        try:
            sb_exec(home, sb, "while true; do date -u >> /tmp/keepalive.log; sleep 20; done",
                    detach=True, timeout=120)
        except Exception as e:
            print(f"  keepalive warn [{w.get('host')}]: {str(e)[:120]}", flush=True)
        b64 = lambda s: base64.b64encode(s.encode()).decode()  # noqa: E731
        inject = f'''
set -e
mkdir -p /root/secrets /root/Documents/railways /app
echo {b64(HOLY)} | base64 -d > /root/secrets/holy_secret_key
echo {b64(GH_TOKEN)} | base64 -d > /root/secrets/gh_token
echo {b64(w["onk_key"])} | base64 -d > /root/secrets/onk_key
printf '%s' '{w["proxy"]}' > /root/secrets/proxy_name
chmod 600 /root/secrets/*
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
export HOLY_SKIP_MAILTM=1
export TOOLKIT_ROOT=/app/toolkit
export HOLY_SECRET_KEY="$(cat /root/secrets/holy_secret_key)"
export KERNEL_API_KEY="$(cat /root/secrets/onk_key)"
export GH_PUSH=1
export GH_REPO=crucifix-cray/automation-toolkit
export GH_BASE_BRANCH=main
export GH_FARM_HOST={w["host"]}
PROXY=$(cat /root/secrets/proxy_name)
while IFS= read -r line; do
  case "$line" in RAILWAY_*=*) unset "${{line%%=*}}" ;; esac
done < <(env | grep -E '^RAILWAY_' || true)
mkdir -p /root/Documents/railways
cd /app/toolkit
echo "START $(date -u +%FT%TZ) host=$GH_FARM_HOST proxy=$PROXY provider={provider['name']} domain={provider['domain']}" | tee /tmp/holy-run.log
exec python3 -u src/railway/account_creation.py --kernel --kernel-proxy "$PROXY" --once --no-warp --domain "{provider['domain']}" >> /tmp/holy-run.log 2>&1
EOS
chmod +x /root/run_holy.sh
echo INJECT_OK
'''
        r = sb_exec(home, sb, inject, timeout=600)
        if "INJECT_OK" not in (r.stdout or ""):
            w["status"] = "inject_fail"
            w["err"] = (r.stderr or r.stdout or "")[-300:]
            return w
        sb_exec(home, sb, "/root/run_holy.sh", detach=True)
        w["status"] = "running"
        return w
    except Exception as e:
        w["status"] = "start_fail"
        w["err"] = str(e)[-300:]
        return w


def refill(n: int) -> str:
    home = RAIL / f"session-{n}"
    state = Path(f"/home/alae/onk-rail-fleet-multi/session-{n}")
    if n == 1:
        state = Path("/home/alae/onk-rail-fleet")
    if not (state / "checkpoint.json").is_file():
        return f"s{n}:no_cp"
    keys = load_keys(n)
    if not keys:
        return f"s{n}:no_keys"
    path = state / "workers.json"
    workers = json.loads(path.read_text()) if path.is_file() else []

    out_lines = []
    pending = [w for w in workers if w.get("status") == "created" and w.get("id")]
    if pending:
        with ThreadPoolExecutor(max_workers=min(12, len(pending))) as ex:
            for w in ex.map(lambda w: start_single(home, w), pending):
                out_lines.append(f"{w['host']}->{w['status']}")

    by_host = {w["host"]: w for w in workers}
    for w in list(by_host.values()):
        if w.get("status") != "running":
            if w.get("id"):
                try:
                    rail(home, "sandbox", "destroy", w["id"], timeout=90)
                except Exception:
                    pass
            del by_host[w["host"]]

    running = [w for w in by_host.values() if w.get("status") == "running"]
    need = max(0, SLOTS - len(running))
    fresh: list[dict] = []
    if need:
        used = [int(h[2:]) for h in by_host if h.startswith("sb") and h[2:].isdigit()]
        idx = (max(used) + 1) if used else 0
        for i in range(need):
            r = rail(home, "sandbox", "create", "--idle-timeout-minutes", "5",
                     "--checkpoint", os.environ.get("HOLY_CHECKPOINT", "holy-ready-v1"),
                     "--json", timeout=300)
            text = r.stdout + r.stderr
            if "{" not in text:
                out_lines.append(f"create_fail:{(r.stderr or r.stdout)[:80]}")
                continue
            try:
                meta = json.loads(text[text.find("{"): text.rfind("}") + 1])
            except Exception:
                out_lines.append("parse_fail")
                continue
            key = keys[(idx + i) % len(keys)]
            try:
                proxy = create_proxy(key["api_key"])
            except Exception as e:
                try:
                    rail(home, "sandbox", "destroy", meta["id"], timeout=90)
                except Exception:
                    pass
                out_lines.append(f"proxy_fail:{str(e)[:60]}")
                continue
            fresh.append({"id": meta["id"], "host": f"sb{idx + i:02d}",
                          "onk_email": key["email"], "onk_key": key["api_key"],
                          "proxy": proxy, "status": "created"})
            time.sleep(0.4)
        if fresh:
            with ThreadPoolExecutor(max_workers=min(12, len(fresh))) as ex:
                fresh = list(ex.map(lambda w: start_single(home, w), fresh))
            for w in fresh:
                out_lines.append(f"{w['host']}->{w['status']}")
    out = list(by_host.values()) + fresh
    path.write_text(json.dumps(out, indent=2))
    running_n = sum(1 for w in out if w.get("status") == "running")
    return f"s{n}:running={running_n}/{len(out)} {' '.join(out_lines[:6])}"


if __name__ == "__main__":
    only = [int(x) for x in sys.argv[1:] if x.strip().isdigit()]
    targets = only or SESS
    with ThreadPoolExecutor(max_workers=12) as ex:
        for line in ex.map(refill, targets):
            print(line, flush=True)
