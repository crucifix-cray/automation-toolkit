#!/usr/bin/env python3
"""Launch Holy farm workers across many Railway host accounts in parallel.

Each host: own HOME token, own project link, own checkpoint, own state dir.
Workers push unique farm/* branches (no main merge conflicts).

Usage:
  # bootstrap checkpoint on hosts 2-6 (parallel)
  python3 src/railway/multihost_farm.py --bootstrap --sessions 2-6

  # launch N workers per ready host
  python3 src/railway/multihost_farm.py --launch --sessions 2-6 --per-host 10

  # status across hosts
  python3 src/railway/multihost_farm.py --status --sessions 1-6
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RAIL_ROOT = Path("/home/alae/Documents/railways")
FLEET = REPO / "src" / "railway" / "fleet_sandbox_farm.py"
STATE_ROOT = Path(os.environ.get("HOLY_MULTI_STATE", "/home/alae/onk-rail-fleet-multi"))
CHECKPOINT = os.environ.get("HOLY_CHECKPOINT", "holy-ready-v1")


def parse_sessions(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return sorted(set(out))


def host_home(n: int) -> Path:
    return RAIL_ROOT / f"session-{n}"


def host_state(n: int) -> Path:
    return STATE_ROOT / f"session-{n}"


def rail_env(n: int) -> dict:
    home = host_home(n)
    e = os.environ.copy()
    e["HOME"] = str(home)
    e["LD_PRELOAD"] = ""
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        e.pop(k, None)
    e["HOLY_HOST_HOME"] = str(home)
    e["HOLY_FARM_STATE"] = str(host_state(n))
    e["HOLY_CHECKPOINT"] = CHECKPOINT
    e["HOLY_HOST_PREFIX"] = os.environ.get("HOLY_WAVE_TAG", "") + f"s{n}-"
    e["HOLY_SKIP_LINK"] = "1"
    return e


def railway(n: int, *args: str, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["railway", *args],
        env=rail_env(n),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def project_name(n: int) -> str | None:
    """Prefer live cell-* / named projects over ephemeral vrfy-* links."""
    home = host_home(n)
    cfg = home / ".railway" / "config.json"
    # Prefer railway list (live) over stale config links
    try:
        r = railway(n, "list", "--json", timeout=90)
        items = json.loads(r.stdout or "[]")
        live = [it for it in items if not it.get("deletedAt")]
        scored = []
        for it in live:
            name = it.get("name") or ""
            svcs = ((it.get("services") or {}).get("edges") or [])
            score = 0
            if name.startswith("cell-") or "ubuntu" in name or "celebration" in name or name.startswith("holy-"):
                score += 10
            if svcs:
                score += 5
            if name.startswith("vrfy-"):
                score -= 20
            scored.append((score, name))
        scored.sort(reverse=True)
        if scored and scored[0][0] > 0:
            return scored[0][1]
        if scored:
            return scored[0][1]
    except Exception:
        pass
    if not cfg.is_file():
        return None
    data = json.loads(cfg.read_text())
    projects = data.get("projects") or {}
    for path, p in projects.items():
        if "automation-toolkit" in path:
            return p.get("name")
    for p in projects.values():
        name = p.get("name") or ""
        if name and not name.startswith("vrfy-"):
            return name
    for p in projects.values():
        if p.get("name"):
            return p.get("name")
    return None


def pick_service(n: int, project: str) -> str | None:
    try:
        r = railway(n, "list", "--json", timeout=90)
        items = json.loads(r.stdout or "[]")
        for it in items:
            if it.get("name") != project or it.get("deletedAt"):
                continue
            edges = ((it.get("services") or {}).get("edges") or [])
            names = [e["node"]["name"] for e in edges if e.get("node", {}).get("name")]
            # prefer hlth-* sandbox-capable services
            for nm in names:
                if nm.startswith("hlth-"):
                    return nm
            return names[0] if names else None
    except Exception:
        return None
    return None


def bootstrap_one(n: int) -> dict:
    """Create golden + bake deps + checkpoint on one host."""
    home = host_home(n)
    state = host_state(n)
    state.mkdir(parents=True, exist_ok=True)
    marker = state / "checkpoint.json"
    if marker.is_file():
        return {"session": n, "status": "already", "checkpoint": CHECKPOINT}

    if not (home / ".railway" / "config.json").is_file():
        return {"session": n, "status": "no_railway_config"}

    name = project_name(n)
    if not name:
        return {"session": n, "status": "unlinked"}

    svc = pick_service(n, name)
    link_args = ["link", "-p", name, "-e", "production"]
    if svc:
        link_args += ["-s", svc]
    r = railway(n, *link_args, timeout=120)
    print(f"[s{n}] link {name} svc={svc}: rc={r.returncode} {(r.stderr or '')[:120]}")

    r = railway(n, "sandbox", "create", "--idle-timeout-minutes", "5", "--json", timeout=180)
    text = r.stdout + r.stderr
    if "{" not in text:
        return {"session": n, "status": "create_fail", "err": text[-300:]}
    meta = json.loads(text[text.find("{") : text.rfind("}") + 1])
    sb = meta["id"]
    print(f"[s{n}] golden {sb}")

    railway(
        n,
        "sandbox", "exec", "--id", sb, "--detach", "--",
        "bash", "-lc", "while true; do date -u >> /tmp/keepalive.log; sleep 25; done",
        timeout=60,
    )
    time.sleep(2)

    bootstrap = r'''
set -e
export PATH="/root/.local/share/mise/shims:$PATH"
mise install python@3.12.10
mise use -g python@3.12.10
hash -r
pip3 install -q cryptography playwright httpx
python3 -m playwright install-deps chromium
python3 -m playwright install chromium
npm install -g @onkernel/cli --silent
command -v railway >/dev/null || curl -fsSL https://railway.com/install.sh | sh
export PATH="$HOME/.railway/bin:/root/.local/share/mise/shims:$PATH"
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
    r = railway(
        n, "sandbox", "exec", "--id", sb, "--", "bash", "-lc", bootstrap, timeout=900
    )
    out = (r.stdout or "") + (r.stderr or "")
    if "BOOTSTRAP_OK" not in out:
        return {"session": n, "status": "bootstrap_fail", "err": out[-400:], "golden": sb}

    r = railway(n, "sandbox", "checkpoint", "create", CHECKPOINT, timeout=300)
    marker.write_text(json.dumps({"name": CHECKPOINT, "golden_sb": sb, "host": f"session-{n}"}, indent=2))
    # free the 10-sandbox slot — checkpoint is enough
    railway(n, "sandbox", "destroy", sb, timeout=90)
    print(f"[s{n}] ✅ checkpoint {CHECKPOINT} (golden destroyed)")
    return {"session": n, "status": "ready", "golden": sb}


def launch_one(n: int, count: int) -> dict:
    state = host_state(n)
    if not (state / "checkpoint.json").is_file() and n != 1:
        # session-1 uses legacy state path
        legacy = Path("/home/alae/onk-rail-fleet/checkpoint.json")
        if n == 1 and legacy.is_file():
            pass
        else:
            return {"session": n, "status": "no_checkpoint"}
    env = rail_env(n)
    if n == 1:
        env["HOLY_FARM_STATE"] = "/home/alae/onk-rail-fleet"
        env["HOLY_HOST_PREFIX"] = "s1-"
    cmd = [sys.executable, "-u", str(FLEET), "--launch", "--count", str(count)]
    print(f"[s{n}] launch count={count}")
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=1800)
    print((r.stdout or "")[-600:])
    if r.returncode != 0:
        print((r.stderr or "")[-400:])
    return {"session": n, "status": "launched" if r.returncode == 0 else "launch_fail", "rc": r.returncode}


def status_one(n: int) -> dict:
    env = rail_env(n)
    if n == 1:
        env["HOLY_FARM_STATE"] = "/home/alae/onk-rail-fleet"
    r = subprocess.run(
        [sys.executable, "-u", str(FLEET), "--status"],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    print(f"=== session-{n} ===")
    print((r.stdout or r.stderr or "").strip() or "(empty)")
    return {"session": n, "rc": r.returncode}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", default="1-5")
    ap.add_argument("--bootstrap", action="store_true")
    ap.add_argument("--launch", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--per-host", type=int, default=10)
    ap.add_argument("--parallel", type=int, default=6)
    args = ap.parse_args()
    sessions = parse_sessions(args.sessions)
    STATE_ROOT.mkdir(parents=True, exist_ok=True)

    if args.bootstrap:
        with ThreadPoolExecutor(max_workers=args.parallel) as ex:
            futs = {ex.submit(bootstrap_one, n): n for n in sessions}
            for fut in as_completed(futs):
                print(json.dumps(fut.result()))
        return 0
    if args.launch:
        # launch hosts sequentially per host API, but hosts can be parallel
        with ThreadPoolExecutor(max_workers=min(args.parallel, len(sessions))) as ex:
            futs = [ex.submit(launch_one, n, args.per_host) for n in sessions]
            for fut in as_completed(futs):
                print(json.dumps(fut.result()))
        return 0
    if args.status:
        for n in sessions:
            status_one(n)
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
