#!/usr/bin/env python3
"""Expand farm: use MADE farmed-* Railway CLI jars as additional sandbox hosts.

Each farmed jar already has tokens + project + hlth service. We:
  1. bootstrap holy-ready checkpoint on that account
  2. continuous-refill sandboxes (10/host) like session-1..44
  3. workers still push farm/* → main (GitHub DB, no Mega)

Usage:
  # bootstrap checkpoints on farmed jars (parallel)
  python3 src/railway/farmed_host_farm.py --bootstrap --parallel 16 --limit 80

  # continuous refill on whatever already has checkpoints
  python3 src/railway/farmed_host_farm.py --continuous --target 1200 --slots 10 --parallel 16
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FARMED_ROOT = REPO / "finals" / "sessions"
STATE_ROOT = Path(os.environ.get("HOLY_FARMED_STATE", "/home/alae/onk-rail-fleet-farmed"))
FLEET = REPO / "src" / "railway" / "fleet_sandbox_farm.py"
MERGE = REPO / "src" / "railway" / "merge_farm_branches.py"
CHECKPOINT = os.environ.get("HOLY_CHECKPOINT", "holy-ready-v1")


def run(cmd: list[str], env: dict | None = None, timeout: int = 600) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    if env:
        e.update(env)
    e.setdefault("LD_PRELOAD", "")
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        e.pop(k, None)
    return subprocess.run(cmd, cwd=str(REPO), env=e, capture_output=True, text=True, timeout=timeout)


def list_farmed_homes() -> list[Path]:
    out = []
    for d in sorted(FARMED_ROOT.glob("farmed-*")):
        if not d.is_dir():
            continue
        v = d / "verified.json"
        cfg = d / ".railway" / "config.json"
        if not v.is_file() or not cfg.is_file():
            continue
        try:
            meta = json.loads(v.read_text())
        except Exception:
            continue
        if meta.get("verified") and (meta.get("service_id") or meta.get("service_name")):
            out.append(d)
    return out


def state_dir(home: Path) -> Path:
    return STATE_ROOT / home.name


def rail_env(home: Path) -> dict:
    e = os.environ.copy()
    e["HOME"] = str(home)
    e["LD_PRELOAD"] = ""
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        e.pop(k, None)
    return e


def railway(home: Path, *args: str, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["railway", *args],
        env=rail_env(home),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def link_home(home: Path) -> tuple[str, str | None]:
    meta = json.loads((home / "verified.json").read_text())
    proj = meta.get("project_name")
    svc = meta.get("service_name")
    if not proj:
        raise RuntimeError(f"no project_name in {home}")
    args = ["link", "-p", proj, "-e", "production"]
    if svc:
        args += ["-s", svc]
    r = railway(home, *args, timeout=120)
    return proj, svc


def bootstrap_one(home: Path) -> dict:
    name = home.name
    st = state_dir(home)
    st.mkdir(parents=True, exist_ok=True)
    marker = st / "checkpoint.json"
    if marker.is_file():
        return {"host": name, "status": "already"}

    lock = st / ".bootstrapping"
    if lock.is_file():
        age = time.time() - lock.stat().st_mtime
        if age < 1200:
            return {"host": name, "status": "busy"}
    lock.write_text(str(time.time()))

    try:
        return _bootstrap_one_locked(home, name, st, marker)
    except subprocess.TimeoutExpired as e:
        return {"host": name, "status": "timeout", "err": str(e)[:200]}
    except Exception as e:
        return {"host": name, "status": "error", "err": f"{type(e).__name__}: {e}"[:250]}
    finally:
        try:
            lock.unlink(missing_ok=True)
        except Exception:
            pass


def _bootstrap_one_locked(home: Path, name: str, st: Path, marker: Path) -> dict:
    try:
        proj, svc = link_home(home)
    except Exception as e:
        return {"host": name, "status": "link_fail", "err": str(e)[:200]}

    r = railway(home, "sandbox", "create", "--idle-timeout-minutes", "5", "--json", timeout=180)
    text = (r.stdout or "") + (r.stderr or "")
    if "{" not in text:
        return {"host": name, "status": "create_fail", "err": text[-250:]}
    try:
        meta = json.loads(text[text.find("{") : text.rfind("}") + 1])
    except Exception as e:
        return {"host": name, "status": "parse_fail", "err": str(e)}
    sb = meta["id"]
    print(f"[{name}] golden {sb[:8]}… proj={proj} svc={svc}")

    railway(
        home,
        "sandbox", "exec", "--id", sb, "--detach", "--",
        "bash", "-lc", "while true; do date -u >> /tmp/keepalive.log; sleep 25; done",
        timeout=60,
    )
    time.sleep(2)

    # Resilient bootstrap: install mise if missing, fall back to system python
    bootstrap = r'''
set -e
export PATH="$HOME/.local/bin:/root/.local/bin:/root/.local/share/mise/shims:$PATH"
if ! command -v mise >/dev/null 2>&1; then
  curl -fsSL https://mise.run | sh || true
  export PATH="$HOME/.local/bin:$PATH"
fi
if command -v mise >/dev/null 2>&1; then
  mise install python@3.12.10 || true
  mise use -g python@3.12.10 || true
  hash -r
fi
python3 --version
pip3 install -q cryptography playwright httpx || pip install -q cryptography playwright httpx
python3 -m playwright install-deps chromium || true
python3 -m playwright install chromium
npm install -g @onkernel/cli --silent || true
command -v railway >/dev/null || curl -fsSL https://railway.com/install.sh | sh
export PATH="$HOME/.railway/bin:/root/.local/share/mise/shims:$HOME/.local/bin:$PATH"
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
    r = railway(home, "sandbox", "exec", "--id", sb, "--", "bash", "-lc", bootstrap, timeout=900)
    out = (r.stdout or "") + (r.stderr or "")
    if "BOOTSTRAP_OK" not in out:
        # cleanup golden so slot frees
        railway(home, "sandbox", "destroy", sb, timeout=90)
        return {"host": name, "status": "bootstrap_fail", "err": out[-400:], "golden": sb}

    railway(home, "sandbox", "checkpoint", "create", CHECKPOINT, timeout=300)
    marker.write_text(
        json.dumps({"name": CHECKPOINT, "golden_sb": sb, "host": name, "home": str(home)}, indent=2)
    )
    railway(home, "sandbox", "destroy", sb, timeout=90)
    print(f"[{name}] ✅ checkpoint ready")
    return {"host": name, "status": "ready", "golden": sb}


def ready_homes() -> list[Path]:
    homes = []
    for d in list_farmed_homes():
        if (state_dir(d) / "checkpoint.json").is_file():
            homes.append(d)
    return homes


def refill_one(home: Path, slots: int, wave_tag: str) -> dict:
    name = home.name
    # short stable prefix from jar name
    short = name.replace("farmed-", "f-")[:28]
    env = {
        "HOLY_HOST_HOME": str(home),
        "HOLY_FARM_STATE": str(state_dir(home)),
        "HOLY_HOST_PREFIX": f"{wave_tag}{short}-",
        "HOLY_SKIP_LINK": "1",
        "HOLY_CHECKPOINT": CHECKPOINT,
        "HOME": str(home),
        "LD_PRELOAD": "",
    }
    # re-link quietly (project may need refresh)
    try:
        link_home(home)
    except Exception:
        pass
    r = run(
        [sys.executable, "-u", str(FLEET), "--refill", "--slots", str(slots)],
        env=env,
        timeout=1200,
    )
    tail = (r.stdout or "")[-220:].replace("\n", " | ")
    print(f"[{name}] {tail}")
    return {"host": name, "rc": r.returncode}


def merge_farms() -> int:
    key = (REPO / "finals" / "secrets" / "holy_secret_key.local").read_text().strip()
    e = os.environ.copy()
    e["HOLY_SECRET_KEY"] = key
    e["LD_PRELOAD"] = ""
    r = run([sys.executable, "-u", str(MERGE)], env=e, timeout=900)
    print((r.stdout or "")[-500:])
    m = re.search(r"merged (\d+)", r.stdout or "")
    return int(m.group(1)) if m else 0


def count_jars() -> int:
    sys.path.insert(0, str(REPO))
    from src.utils.secret_box import decrypt_github_token
    import base64

    token = decrypt_github_token(path=REPO / "finals" / "secrets" / "gh_token.enc")
    e = os.environ.copy()
    e["GIT_TERMINAL_PROMPT"] = "0"
    e["GIT_CONFIG_COUNT"] = "1"
    e["GIT_CONFIG_KEY_0"] = "http.https://github.com/.extraheader"
    e["GIT_CONFIG_VALUE_0"] = "AUTHORIZATION: basic " + base64.b64encode(
        f"x-access-token:{token}".encode()
    ).decode()
    e["LD_PRELOAD"] = ""
    run(["git", "fetch", "origin", "--prune"], env=e, timeout=120)
    r = run(["git", "ls-tree", "-d", "-r", "--name-only", "origin/main"], env=e, timeout=120)
    return sum(
        1
        for line in (r.stdout or "").splitlines()
        if line.startswith("finals/sessions/farmed-") and line.count("/") == 2
    )


def bootstrap(parallel: int, limit: int | None) -> None:
    homes = list_farmed_homes()
    todo = [h for h in homes if not (state_dir(h) / "checkpoint.json").is_file()]
    if limit:
        todo = todo[:limit]
    print(f"bootstrap todo={len(todo)} already={len(homes) - len(todo)} parallel={parallel}")
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    ok = fail = 0
    with ThreadPoolExecutor(max_workers=parallel) as ex:
        futs = {ex.submit(bootstrap_one, h): h for h in todo}
        for fut in as_completed(futs):
            res = fut.result()
            print(json.dumps(res))
            if res.get("status") in ("ready", "already"):
                ok += 1
            else:
                fail += 1
    print(f"bootstrap done ok={ok} fail={fail}")


def continuous(slots: int, parallel: int, target: int, wave_tag: str, also_bootstrap: bool) -> int:
    tick = 0
    while True:
        try:
            tick += 1
            jars = count_jars()
            ready = ready_homes()
            print(f"\n===== FARMED tick={tick} jars={jars}/{target} ready_hosts={len(ready)} =====")
            if jars >= target:
                merge_farms()
                print(f"TARGET REACHED: {jars}")
                return 0

            if also_bootstrap:
                pending = [h for h in list_farmed_homes() if not (state_dir(h) / "checkpoint.json").is_file()]
                batch = pending[:parallel]
                if batch:
                    print(f"  bootstrapping batch={len(batch)}")
                    with ThreadPoolExecutor(max_workers=min(parallel, len(batch))) as ex:
                        futs = [ex.submit(bootstrap_one, h) for h in batch]
                        for fut in as_completed(futs):
                            try:
                                print(json.dumps(fut.result()))
                            except Exception as e:
                                print(json.dumps({"status": "future_err", "err": str(e)[:200]}))
                    ready = ready_homes()

            if ready:
                with ThreadPoolExecutor(max_workers=parallel) as ex:
                    futs = [ex.submit(refill_one, h, slots, wave_tag) for h in ready]
                    for fut in as_completed(futs):
                        try:
                            fut.result()
                        except Exception as e:
                            print(f"refill_err: {e}")

            merged = merge_farms()
            jars2 = count_jars()
            print(f"  tick done jars={jars2} (+{jars2 - jars}) merged={merged} hosts={len(ready)}")
        except Exception as e:
            print(f"continuous_tick_error: {type(e).__name__}: {e}")
        time.sleep(40)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bootstrap", action="store_true")
    ap.add_argument("--continuous", action="store_true")
    ap.add_argument("--parallel", type=int, default=16)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--slots", type=int, default=10)
    ap.add_argument("--target", type=int, default=1200)
    ap.add_argument("--wave-tag", default="fx")
    ap.add_argument("--also-bootstrap", action="store_true", help="with --continuous, keep bootstrapping")
    args = ap.parse_args()

    if args.bootstrap:
        bootstrap(args.parallel, args.limit or None)
        return 0
    if args.continuous:
        return continuous(args.slots, args.parallel, args.target, args.wave_tag, args.also_bootstrap)
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
