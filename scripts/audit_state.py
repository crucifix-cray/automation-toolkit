#!/usr/bin/env python3
"""Regenerate the canonical inventory in docs/STATE.md from live measurement.

Every count in STATE.md comes from here. Nothing is read from prior docs —
that is the whole point, they were contradicting each other.

  python3 scripts/audit_state.py            # fast: no writes to Railway
  python3 scripts/audit_state.py --census   # + real init/delete canary (slow, writes)

Outputs (all under finals/):
  railway_census.json      per-account canary verdict   [needs --census]
  lovable_inventory.json   per-session mail/pwd/totp/cookies
  lovable_summary.json     session count vs unique-account count
  onk_key_status.json      per-key working / hit-limit
  zenrows_key_status.json  per-key status + note
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FINALS = REPO / "finals"
RAILWAY = "/home/alan/.railway/bin/railway"


def clean_env(home: str) -> dict:
    e = {**os.environ, "HOME": home, "LD_PRELOAD": ""}
    for k in list(e):
        if "proxy" in k.lower():
            e.pop(k, None)
    return e


# ---------------------------------------------------------------- railway

def railway_census(write: bool) -> dict:
    sessions = [REPO / "sessions" / f"session-{n}" for n in range(1, 52)]
    jars = sorted((FINALS / "sessions").glob("farmed-*"))
    work = [(str(s), s.name) for s in sessions if s.is_dir()]
    work += [(str(j), "jar") for j in jars]

    import random
    import time

    def one(item):
        home, tag = item
        e = clean_env(home)
        cwd = f"/tmp/audit_cv/{Path(home).name[:20]}_{random.randint(1000, 99999)}"
        Path(cwd).mkdir(parents=True, exist_ok=True)
        name = f"audit-{random.randint(10000, 99999)}"
        try:
            p = subprocess.run([RAILWAY, "init", "--name", name, "--json"],
                               capture_output=True, text=True, timeout=90, env=e, cwd=cwd)
            out = (p.stdout or "") + (p.stderr or "")
            m = re.search(r'\{"id":"([0-9a-f-]{36})","name":"' + name, out)
            if m:
                subprocess.run([RAILWAY, "delete", "--project", m.group(1), "--yes", "--json"],
                               capture_output=True, text=True, timeout=60, env=e, cwd=cwd)
                return {"account": tag, "verdict": "verified"}
            low = out.lower()
            if "restricted" in low:
                return {"account": tag, "verdict": "restricted"}
            if "resource provision limit" in low:
                return {"account": tag, "verdict": "trial-wall"}
            if "one project per" in low or "rate limit" in low:
                return {"account": tag, "verdict": "rate"}
            if "select a workspace" in low or "no linked project" in low:
                return {"account": tag, "verdict": "link-fail"}
            return {"account": tag, "verdict": "inconclusive", "raw": out[:120]}
        except subprocess.TimeoutExpired:
            return {"account": tag, "verdict": "timeout"}
        except Exception as e:
            return {"account": tag, "verdict": "error", "raw": str(e)[:80]}

    print(f"census: {len(work)} accounts "
          f"({len(sessions)} sessions + {len(jars)} jars) — real writes, slow", flush=True)
    results = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for i, r in enumerate(ex.map(one, work)):
            results.append(r)
            if (i + 1) % 100 == 0:
                print(f"  {i+1}/{len(work)} {dict(Counter(x['verdict'] for x in results))}", flush=True)

    counts = dict(Counter(r["verdict"] for r in results))
    out = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "universe": len(work), "counts": counts, "results": results}
    if write:
        (FINALS / "railway_census.json").write_text(json.dumps(out, indent=1))
        print(f"wrote {FINALS / 'railway_census.json'}")
    return out


# ---------------------------------------------------------------- lovable

def lovable_inventory() -> dict:
    rows = []
    for d in sorted((REPO / "scripts" / "sessions").glob("session-*"),
                    key=lambda x: int(re.search(r"session-(\d+)", str(x)).group(1))):
        n = re.search(r"session-(\d+)", str(d)).group(1)
        cfg, ck = d / "config.json", d / "cookies.json"
        c = json.loads(cfg.read_text()) if cfg.is_file() else {}
        cookies = json.loads(ck.read_text()) if ck.is_file() else []
        rows.append({
            "session": f"session-{n}",
            "email": c.get("email"),
            "password": c.get("password"),
            "has_totp": bool(c.get("totp_secret")),
            "cookies": len(cookies) if isinstance(cookies, list) else 0,
            "status": c.get("status"),
            "project_id": c.get("project_id"),
        })
    uniq = {r["email"] for r in rows if r["email"]}
    summary = {
        "sessions": len(rows),
        "unique_accounts": len(uniq),
        "duplicate_emails": {k: v for k, v in
                             Counter(r["email"] for r in rows if r["email"]).items() if v > 1},
        "with_password": sum(1 for r in rows if r["password"]),
        "with_totp": sum(1 for r in rows if r["has_totp"]),
        "with_cookies": sum(1 for r in rows if r["cookies"]),
        "with_project_id": sum(1 for r in rows if r["project_id"]),
        "note": "session dirs != accounts; unique email is the only honest denominator",
    }
    (FINALS / "lovable_inventory.json").write_text(json.dumps(rows, indent=1))
    (FINALS / "lovable_summary.json").write_text(json.dumps(summary, indent=1))
    print(f"lovable: {summary['sessions']} sessions, {summary['unique_accounts']} unique accounts")
    return summary


# ---------------------------------------------------------------- onk / zenrows

def onk_status() -> dict:
    jars: dict[str, dict] = {}
    for f in (FINALS / "sessions").glob("onk_*.json"):
        try:
            d = json.loads(f.read_text())
            if isinstance(d, dict) and not d.get("tag") == "probe":
                k = d.get("api_key") or d.get("key")
                if k:
                    jars.setdefault(k, {"email": d.get("email"), "tag": d.get("tag"), "file": f.name})
        except Exception:
            pass
    try:
        for x in json.loads((FINALS / "zenrows_onkernel_farmed.json").read_text()):
            if x.get("api_key"):
                jars.setdefault(x["api_key"], {"email": x.get("email"), "tag": "zenvex", "file": "zenrows_onkernel_farmed"})
    except Exception:
        pass

    def probe(k):
        try:
            p = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "25",
                 "-H", f"Authorization: Bearer {k}",
                 "https://api.onkernel.com/proxies?limit=1"],
                capture_output=True, text=True, timeout=40, env=clean_env(str(REPO)))
            return k, p.stdout.strip()
        except Exception:
            return k, "000"

    out = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        for k, code in ex.map(probe, list(jars)):
            out[k] = {**jars[k], "http": code,
                      "verdict": "working" if code == "200" else "hit-limit"}
    (FINALS / "onk_key_status.json").write_text(json.dumps(out, indent=1))
    c = Counter(v["verdict"] for v in out.values())
    print(f"onk: {dict(c)}")
    return {"total": len(out), **c}


def zenrows_status() -> dict:
    keys: dict[str, dict] = {}
    for f in ("CONSOLIDATED_zenrows.json", "finals/zenrows_onkernel_farmed.json"):
        p = REPO / f
        if not p.is_file():
            continue
        d = json.loads(p.read_text())
        items = d.get("accounts", []) if isinstance(d, dict) else d
        for x in items:
            if x.get("api_key"):
                keys.setdefault(x["api_key"], {"email": x.get("email")})
    out = {k: {**v, "verdict": "unknown-needs-browser",
               "note": "curl gets a Cloudflare challenge, not an API verdict"}
           for k, v in keys.items()}
    (FINALS / "zenrows_key_status.json").write_text(json.dumps(out, indent=1))
    print(f"zenrows: {len(out)} keys (validity unknown — Cloudflare blocks curl)")
    return {"total": len(out), "verdict": "unknown-needs-browser"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--census", action="store_true",
                    help="run the real Railway init/delete canary (writes to Railway, slow)")
    a = ap.parse_args()
    if a.census:
        c = railway_census(write=True)
        print("railway census:", c["counts"])
    lovable_inventory()
    onk_status()
    zenrows_status()
    return 0


if __name__ == "__main__":
    sys.exit(main())
