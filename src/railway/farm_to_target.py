#!/usr/bin/env python3
"""Continuous Holy farm until N MADE jars on GitHub main.

Loop:
  1. count farmed-* on origin/main
  2. wipe all sandboxes on hosts 1-44 (free 10-slot cap)
  3. launch --per-host workers on every host (wave-tagged)
  4. wait / poll until mostly done or timeout
  5. merge farm/* → main
  6. repeat until target

Usage:
  python3 src/railway/farm_to_target.py --target 1200 --per-host 10
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
MULTI = REPO / "src" / "railway" / "multihost_farm.py"
FLEET = REPO / "src" / "railway" / "fleet_sandbox_farm.py"
MERGE = REPO / "src" / "railway" / "merge_farm_branches.py"
RAIL_ROOT = Path("/home/alae/Documents/railways")


def run(cmd: list[str], env: dict | None = None, timeout: int = 600) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    if env:
        e.update(env)
    e.setdefault("LD_PRELOAD", "")
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        e.pop(k, None)
    return subprocess.run(cmd, cwd=str(REPO), env=e, capture_output=True, text=True, timeout=timeout)


def git_token_env() -> dict:
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
    return e


def count_jars() -> int:
    e = git_token_env()
    run(["git", "fetch", "origin", "--prune"], env=e, timeout=120)
    r = run(["git", "ls-tree", "-d", "-r", "--name-only", "origin/main"], env=e, timeout=120)
    n = 0
    for line in (r.stdout or "").splitlines():
        if line.startswith("finals/sessions/farmed-") and line.count("/") == 2:
            n += 1
    return n


def rail_env(n: int) -> dict:
    home = RAIL_ROOT / f"session-{n}"
    e = os.environ.copy()
    e["HOME"] = str(home)
    e["LD_PRELOAD"] = ""
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        e.pop(k, None)
    return e


def wipe_host(n: int) -> int:
    e = rail_env(n)
    if not (RAIL_ROOT / f"session-{n}" / ".railway" / "config.json").exists():
        return 0
    r = subprocess.run(
        ["railway", "sandbox", "list", "--json"], env=e, capture_output=True, text=True, timeout=90
    )
    text = (r.stdout or "") + "\n" + (r.stderr or "")
    m = re.search(r"\[.*\]", text, re.S)
    items = []
    if m:
        try:
            items = json.loads(m.group(0))
        except Exception:
            items = []
    killed = 0
    for it in items:
        sid = it.get("id")
        if not sid:
            continue
        subprocess.run(
            ["railway", "sandbox", "destroy", sid], env=e, capture_output=True, text=True, timeout=90
        )
        killed += 1
    # clear workers state
    if n == 1:
        p = Path("/home/alae/onk-rail-fleet/workers.json")
        if p.exists():
            p.write_text("[]")
    else:
        p = Path(f"/home/alae/onk-rail-fleet-multi/session-{n}/workers.json")
        p.unlink(missing_ok=True)
    return killed


def wipe_all(sessions: list[int]) -> int:
    total = 0
    with ThreadPoolExecutor(max_workers=12) as ex:
        for k in ex.map(wipe_host, sessions):
            total += k
    return total


def merge_farms() -> int:
    key = (REPO / "finals" / "secrets" / "holy_secret_key.local").read_text().strip()
    e = os.environ.copy()
    e["HOLY_SECRET_KEY"] = key
    e["LD_PRELOAD"] = ""
    r = run([sys.executable, "-u", str(MERGE)], env=e, timeout=900)
    print((r.stdout or "")[-800:])
    if r.returncode != 0:
        print((r.stderr or "")[-400:])
    m = re.search(r"merged (\d+)", r.stdout or "")
    return int(m.group(1)) if m else 0


def launch_wave(sessions: list[int], per_host: int, wave_tag: str, parallel: int) -> None:
    # s1 special state path
    if 1 in sessions:
        env = os.environ.copy()
        env.update(
            {
                "HOLY_HOST_HOME": str(RAIL_ROOT / "session-1"),
                "HOLY_FARM_STATE": "/home/alae/onk-rail-fleet",
                "HOLY_HOST_PREFIX": f"{wave_tag}s1-",
                "HOLY_SKIP_LINK": "1",
                "HOLY_CHECKPOINT": "holy-ready-v1",
                "LD_PRELOAD": "",
                "HOME": str(RAIL_ROOT / "session-1"),
            }
        )
        print(f"[s1] launch {per_host}")
        r = run(
            [sys.executable, "-u", str(FLEET), "--launch", "--count", str(per_host)],
            env=env,
            timeout=1800,
        )
        print((r.stdout or "")[-500:])

    others = [n for n in sessions if n != 1]
    if not others:
        return
    spec = ",".join(str(n) for n in others)
    env = os.environ.copy()
    env["HOLY_WAVE_TAG"] = wave_tag
    env["LD_PRELOAD"] = ""
    print(f"[multi] launch sessions={spec} per_host={per_host}")
    r = run(
        [
            sys.executable,
            "-u",
            str(MULTI),
            "--launch",
            "--sessions",
            spec,
            "--per-host",
            str(per_host),
            "--parallel",
            str(parallel),
        ],
        env=env,
        timeout=3600,
    )
    print((r.stdout or "")[-800:])
    if r.returncode != 0:
        print((r.stderr or "")[-400:])


def wait_wave(minutes: int, poll_s: int = 90) -> None:
    """Wait while merging opportunistically; don't block forever."""
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        merged = merge_farms()
        jars = count_jars()
        print(f"  … jars={jars} merged_this_tick={merged}")
        time.sleep(poll_s)


def continuous(sessions: list[int], slots: int, parallel: int, target: int, wave_tag: str) -> int:
    """Keep every host topped up to `slots` until jar target hit. No batch wait."""
    tick = 0
    while True:
        tick += 1
        jars = count_jars()
        print(f"\n===== CONTINUOUS tick={tick} jars={jars} target={target} =====")
        if jars >= target:
            merge_farms()
            print(f"TARGET REACHED: {jars}")
            return 0

        def refill_host(n: int) -> dict:
            if n == 1:
                env = {
                    "HOLY_HOST_HOME": str(RAIL_ROOT / "session-1"),
                    "HOLY_FARM_STATE": "/home/alae/onk-rail-fleet",
                    "HOLY_HOST_PREFIX": f"{wave_tag}s1-",
                    "HOLY_SKIP_LINK": "1",
                    "HOLY_CHECKPOINT": "holy-ready-v1",
                    "HOME": str(RAIL_ROOT / "session-1"),
                    "LD_PRELOAD": "",
                }
            else:
                env = {
                    "HOLY_HOST_HOME": str(RAIL_ROOT / f"session-{n}"),
                    "HOLY_FARM_STATE": f"/home/alae/onk-rail-fleet-multi/session-{n}",
                    "HOLY_HOST_PREFIX": f"{wave_tag}s{n}-",
                    "HOLY_SKIP_LINK": "1",
                    "HOLY_CHECKPOINT": "holy-ready-v1",
                    "HOME": str(RAIL_ROOT / f"session-{n}"),
                    "LD_PRELOAD": "",
                }
                cp = Path(f"/home/alae/onk-rail-fleet-multi/session-{n}/checkpoint.json")
                if not cp.is_file():
                    return {"session": n, "status": "no_checkpoint"}
            r = run(
                [sys.executable, "-u", str(FLEET), "--refill", "--slots", str(slots)],
                env=env,
                timeout=1200,
            )
            tail = (r.stdout or "")[-280:].replace("\n", " | ")
            print(f"[s{n}] {tail}")
            return {"session": n, "rc": r.returncode}

        with ThreadPoolExecutor(max_workers=parallel) as ex:
            list(ex.map(refill_host, sessions))

        merged = merge_farms()
        jars2 = count_jars()
        print(f"  tick done jars={jars2} (+{jars2 - jars}) merged={merged}")
        time.sleep(45)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=1200)
    ap.add_argument("--per-host", type=int, default=10)
    ap.add_argument("--sessions", default="1-44")
    ap.add_argument("--parallel", type=int, default=10)
    ap.add_argument("--wait-minutes", type=int, default=25)
    ap.add_argument("--max-waves", type=int, default=40)
    ap.add_argument("--continuous", action="store_true", help="refill loop (faster)")
    ap.add_argument("--wave-tag", default="cx")
    args = ap.parse_args()

    sessions: list[int] = []
    for part in args.sessions.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            sessions.extend(range(int(a), int(b) + 1))
        else:
            sessions.append(int(part))
    sessions = sorted(set(sessions))

    if args.continuous:
        return continuous(sessions, args.per_host, args.parallel, args.target, args.wave_tag)

    wave = 0
    while wave < args.max_waves:
        jars = count_jars()
        print(f"\n===== WAVE check jars={jars} target={args.target} =====")
        if jars >= args.target:
            print(f"TARGET REACHED: {jars}")
            merge_farms()
            return 0

        wave += 1
        tag = f"w{wave + 2}"
        print(f"→ WAVE {wave} tag={tag} need={args.target - jars}")

        killed = wipe_all(sessions)
        print(f"  wiped sandboxes={killed}")

        launch_wave(sessions, args.per_host, tag, args.parallel)
        print(f"  launched; waiting up to {args.wait_minutes}m")
        wait_wave(args.wait_minutes, poll_s=90)

        merged = merge_farms()
        jars2 = count_jars()
        print(f"  wave done: jars {jars} → {jars2} (+{jars2 - jars}) merged_last={merged}")

    print("max waves hit; jars=", count_jars())
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
