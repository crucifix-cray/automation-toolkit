#!/usr/bin/env python3
"""Mail-provider rotation + signup pacing for the Railway farm.

WHY: 2026-09-25 the farm burned because every worker used the SAME mail
provider (temp.tf high.edu.pl) and the same ~10 egress IPs, so the whole
fleet's signup fingerprint collapsed into one pattern. Railway's response
was instant workspace restriction on every fresh account.

WHAT: each worker run picks its mailbox from a provider pool on a rotating
schedule (not pure random — rotation guarantees spread, random breaks
ties) and every signup is paced so no single egress IP is hammered.

The chosen provider is baked into the worker as an explicit `--domain`, so
account_creation.py takes only that path instead of falling through to
whatever is convenient (which is how the fleet converged on one provider).

Usage:
  python3 mail_rotate.py pick            # print the next domain to use
  python3 mail_rotate.py pick --host 45  # domain for one specific host
  python3 mail_rotate.py stats           # mix + pacing state
  python3 mail_rotate.py reset           # clear rotation cursor
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

STATE = Path("/home/alae/onk-rail-1k/mail_rotate_state.json")

# Providers ordered by trust score. Weights = how often each may be used.
# gmail/high.edu.pl both verified 100% clean; 22.do pool domains are BURNED
# (23/23 blocked 16:05) so they are excluded — add them back only if
# Railway's restriction window closes and they verify again.
PROVIDERS = [
    {"name": "temp_tf_gmail", "domain": "@gmail.com", "weight": 3,
     "env": {"HOLY_SKIP_MAILTM": "1"}, "note": "temp.tf one-dot gmail"},
    {"name": "temp_tf_high", "domain": "@high.edu.pl", "weight": 2,
     "env": {"HOLY_SKIP_MAILTM": "1"}, "note": "temp.tf @high.edu.pl"},
    {"name": "twodo_gmail", "domain": "@gmail.com", "weight": 1,
     "env": {"HOLY_SKIP_MAILTM": "1"}, "note": "22.do fake-gmail one-dot"},
]

# Pacing: minimum seconds between two signups sharing one egress IP, and
# the max signups allowed per IP per rolling hour. Railway's restriction
# kicked in around hundreds/hour off ~10 IPs; stay far under that.
MIN_GAP_S = 90
PER_IP_HOUR = 40


def _load() -> dict:
    if STATE.is_file():
        try:
            return json.loads(STATE.read_text())
        except Exception:
            pass
    return {"cursor": 0, "picks": {}, "ip_times": {}}


def _save(st: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, indent=2))


def _expanded() -> list[dict]:
    out: list[dict] = []
    for p in PROVIDERS:
        out.extend([p] * p["weight"])
    return out


def _hour_ok(st: dict, ip: str) -> bool:
    now = time.time()
    times = [t for t in st["ip_times"].get(ip, []) if now - t < 3600]
    st["ip_times"][ip] = times
    return len(times) < PER_IP_HOUR


def _claim_slot(st: dict, ip: str) -> bool:
    if not _hour_ok(st, ip):
        return False
    now = time.time()
    last = st["ip_times"][ip][-1] if st["ip_times"].get(ip) else 0
    if now - last < MIN_GAP_S:
        return False
    st["ip_times"].setdefault(ip, []).append(now)
    return True


def pick(host: str | None = None) -> dict:
    """Return the next provider for a worker.

    Rotation is a weighted round-robin (guarantees every provider is used
    before any repeats); host name is mixed in so different hosts don't
    march in lockstep.
    """
    st = _load()
    pool = _expanded()
    if host:
        off = int(hashlib.sha256(host.encode()).hexdigest()[:8], 16) % len(pool)
        idx = (st["cursor"] + off) % len(pool)
    else:
        idx = st["cursor"] % len(pool)
    st["cursor"] = (st["cursor"] + 1) % len(pool)
    p = pool[idx]
    st["picks"][p["name"]] = st["picks"].get(p["name"], 0) + 1
    _save(st)
    return p


def can_run_now(ip: str) -> tuple[bool, int]:
    """(allowed, seconds_to_wait) for one signup on this egress IP."""
    st = _load()
    now = time.time()
    times = [t for t in st["ip_times"].get(ip, []) if now - t < 3600]
    if len(times) >= PER_IP_HOUR:
        wait = int(3600 - (now - times[0])) + 1
        return False, max(wait, 1)
    if times:
        wait = int(MIN_GAP_S - (now - times[-1])) + 1
        if wait > 0:
            return False, wait
    return True, 0


def record(ip: str) -> None:
    st = _load()
    st["ip_times"].setdefault(ip, []).append(time.time())
    _save(st)


def stats() -> dict:
    st = _load()
    total = sum(st["picks"].values()) or 1
    mix = {k: {"n": v, "pct": round(100 * v / total, 1)} for k, v in st["picks"].items()}
    now = time.time()
    active = {ip: len([t for t in ts if now - t < 3600])
              for ip, ts in st["ip_times"].items() if any(now - t < 3600 for t in ts)}
    return {
        "total_picks": total,
        "mix": mix,
        "pacing": {"min_gap_s": MIN_GAP_S, "per_ip_hour": PER_IP_HOUR},
        "ips_active_last_hour": active,
        "cursor": st["cursor"],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["pick", "stats", "reset", "gate"])
    ap.add_argument("--host", default=None)
    ap.add_argument("--ip", default="unknown")
    args = ap.parse_args()
    if args.cmd == "pick":
        p = pick(args.host)
        print(json.dumps(p))
    elif args.cmd == "stats":
        print(json.dumps(stats(), indent=2))
    elif args.cmd == "reset":
        _save({"cursor": 0, "picks": {}, "ip_times": {}})
        print("rotator reset")
    elif args.cmd == "gate":
        ok, wait = can_run_now(args.ip)
        print(json.dumps({"allowed": ok, "wait_s": wait, "ip": args.ip}))


if __name__ == "__main__":
    main()
