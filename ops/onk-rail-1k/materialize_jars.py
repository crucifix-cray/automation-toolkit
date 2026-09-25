#!/usr/bin/env python3
"""Materialize merged MADE jars (finals/sessions/farmed-w-*) into
/home/alae/Documents/railways/session-N dirs for the verify gate.

Skips jars whose email already exists in any session dir. Assigns fresh IDs
from max(existing)+1. Idempotent: reruns only add new jars.

Usage: python3 /home/alae/onk-rail-1k/materialize_jars.py [--limit N]
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO = Path("/home/alae/Documents/repos/automation-toolkit/finals/sessions")
DEST = Path("/home/alae/Documents/railways")


def main() -> None:
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 0
    sess_emails: dict[str, str] = {}
    for f in DEST.glob("session-*/email.txt"):
        try:
            sess_emails[f.read_text().strip().split()[0]] = f.parent.name
        except Exception:
            pass
    used_ids = [int(p.name.split("-")[1]) for p in DEST.glob("session-*")
                if p.name.split("-")[1].isdigit()]
    nxt = (max(used_ids) + 1) if used_ids else 200
    added = 0
    for jar in sorted(REPO.glob("farmed-*")):
        if not jar.is_dir():
            continue
        if limit and added >= limit:
            break
        try:
            em = (jar / "email.txt").read_text().strip().split()[0]
        except Exception:
            continue
        if em in sess_emails or not (jar / "verified.json").is_file():
            continue
        while (DEST / f"session-{nxt}").exists():
            nxt += 1
        shutil.copytree(jar, DEST / f"session-{nxt}")
        print(f"jar {jar.name} -> session-{nxt} ({em})", flush=True)
        sess_emails[em] = f"session-{nxt}"
        nxt += 1
        added += 1
    print(f"MATERIALIZED={added}")


if __name__ == "__main__":
    main()
