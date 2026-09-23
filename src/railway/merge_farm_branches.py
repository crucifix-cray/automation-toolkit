#!/usr/bin/env python3
"""Merge remote farm/* branches into main (conflict-free worker pushes).

Workers push each MADE jar to farm/farmed-<host>-<uuid>. This script:
  1. fetches farm/* refs
  2. merges each into main sequentially (paths are unique → no content conflicts)
  3. pushes main
  4. deletes merged farm branches

Usage:
  HOLY_SECRET_KEY=… python3 src/railway/merge_farm_branches.py
  python3 src/railway/merge_farm_branches.py --dry-run
"""
from __future__ import annotations

import argparse
import base64
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def run(cmd: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(REPO), env=env, capture_output=True, text=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--base", default=os.environ.get("GH_BASE_BRANCH", "main"))
    ap.add_argument("--keep-branches", action="store_true")
    args = ap.parse_args()

    sys.path.insert(0, str(REPO))
    from src.utils.secret_box import decrypt_github_token

    token = decrypt_github_token(path=REPO / "finals" / "secrets" / "gh_token.enc")
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "http.https://github.com/.extraheader"
    env["GIT_CONFIG_VALUE_0"] = "AUTHORIZATION: basic " + base64.b64encode(
        f"x-access-token:{token}".encode()
    ).decode()

    def g(*cmd: str) -> subprocess.CompletedProcess:
        return run(["git", *cmd], env=env)

    g("fetch", "origin", "--prune")
    ls = g("branch", "-r", "--list", "origin/farm/*")
    branches = []
    for line in (ls.stdout or "").splitlines():
        ref = line.strip()
        if ref.startswith("origin/farm/"):
            branches.append(ref[len("origin/"):])
    branches = sorted(set(branches))
    print(f"farm branches: {len(branches)}")
    if not branches:
        return 0

    if args.dry_run:
        for b in branches:
            print(" ", b)
        return 0

    g("checkout", args.base)
    g("pull", "--ff-only", "origin", args.base)

    merged = []
    failed = []
    for b in branches:
        print(f"→ merge {b}")
        m = g("merge", "--no-ff", "--no-edit", f"origin/{b}", "-m", f"merge {b}")
        if m.returncode != 0:
            print(f"  FAIL: {(m.stderr or m.stdout)[:300]}")
            g("merge", "--abort")
            failed.append(b)
            continue
        merged.append(b)

    if merged:
        p = g("push", "origin", args.base)
        if p.returncode != 0:
            print(f"push main failed: {(p.stderr or p.stdout)[:400]}")
            return 2
        print(f"✅ merged {len(merged)} → {args.base}")

    if not args.keep_branches:
        for b in merged:
            g("push", "origin", "--delete", b)

    if failed:
        print(f"⚠️  failed merges: {failed}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
