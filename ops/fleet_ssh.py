#!/usr/bin/env python3
"""One-command fan-out to the Railway VPS fleet over `railway ssh`.

Each jar gets a DEDICATED ssh-agent (shared agents mis-resolve to the wrong
Railway account), a linked cwd, raw-IP env. Output is marker-first because
`railway ssh` drops the first stdout line — bare rc=0/empty is never trusted.

Usage:
  # fire-and-forget start on all 500 (returns in seconds per box):
  python3 ops/fleet_ssh.py --cmd-file ops/payloads/start_job.sh --par 25 --target 500
  # blocking run with output:
  python3 ops/fleet_ssh.py --cmd "cat /tmp/lov_job.log | tail -5" --par 25 --only farmed-cxs33
  # resume skips jars already marked done in the registry
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path("/home/alan/Documents/railways")
RAILWAY = "/home/alan/.railway/bin/railway"
AGENTS = Path("/tmp/agents")
REG = REPO / "finals" / "fleet_ssh_registry.json"
MARKER = "FLEET-MARK-OK"


def base_env() -> dict:
    e = dict(os.environ, LD_PRELOAD="")
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
              "ALL_PROXY", "all_proxy"):
        e.pop(k, None)
    return e


def load_jars(only: str = "") -> list[Path]:
    jars = sorted(Path(REPO / "finals" / "sessions").glob("farmed-*/"))
    # the 5 new session-N dirs live at repo root (no "s")
    for d in sorted(Path(REPO).glob("session-[0-9]*")):
        if d.is_dir() and (d / "verified.json").is_file():
            jars.append(d)
    if only:
        jars = [j for j in jars if only in j.name]
    out = []
    for j in jars:
        if (j / ".railway" / "config.json").is_file() and (j / "verified.json").is_file():
            out.append(j)
    return out


def jar_ids(jar: Path) -> tuple[str, str, str] | None:
    try:
        d = json.loads((jar / "verified.json").read_text())
        return (d["railway_project_id"], d["environment_id"],
                d.get("service_name") or d.get("service_id"))
    except Exception:
        return None


def ensure_key(jar: Path) -> Path:
    """Unique ed25519 per jar (Railway rejects a key used on 2 accounts)."""
    sshdir = jar / ".ssh"
    sshdir.mkdir(parents=True, exist_ok=True)
    priv, pub = sshdir / "cellkey", sshdir / "cellkey.pub"
    if not priv.is_file():
        subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "",
                        "-C", f"fleet-{jar.name[:24]}", "-f", str(priv)],
                       check=True, capture_output=True, timeout=60)
        os.chmod(priv, 0o600)
    return priv


def agent_for(jar: Path, priv: Path) -> str:
    AGENTS.mkdir(parents=True, exist_ok=True)
    sock = str(AGENTS / f"{jar.name[:40]}.sock")
    env = dict(base_env(), SSH_AUTH_SOCK=sock)
    try:
        r = subprocess.run(["ssh-add", "-l"], env=env, capture_output=True,
                           text=True, timeout=15)
        if r.returncode == 0 and "cellkey" not in r.stdout:
            subprocess.run(["ssh-add", "-q", str(priv)], env=env, timeout=15)
            return sock
        if r.returncode == 0:
            return sock
    except Exception:
        pass
    subprocess.run(["rm", "-f", sock], timeout=10)
    subprocess.run(["ssh-agent", "-a", sock], capture_output=True, timeout=15)
    subprocess.run(["ssh-add", "-q", str(priv)], env={**env, "SSH_AUTH_SOCK": sock},
                   timeout=15)
    return sock


def registered(jar: Path, sock: str) -> bool:
    env = dict(base_env(), HOME=str(jar), SSH_AUTH_SOCK=sock)
    r = subprocess.run([RAILWAY, "ssh", "keys", "list"], env=env,
                       capture_output=True, text=True, timeout=60)
    return "Fingerprint" in (r.stdout or "")


def register_key(jar: Path, sock: str) -> bool:
    """No -k flag: the dedicated agent holds exactly this jar's key, so
    auto-detect picks the right one. (-k <path> is buggy: 'Key not found'
    on valid files.)"""
    env = dict(base_env(), HOME=str(jar), SSH_AUTH_SOCK=sock)
    r = subprocess.run([RAILWAY, "ssh", "keys", "add",
                        "-n", f"fleet-{jar.name[:20]}"],
                       env=env, capture_output=True, text=True, timeout=90)
    out = (r.stdout or "") + (r.stderr or "")
    return "registered successfully" in out or registered(jar, sock)


def run_remote(jar: Path, sock: str, proj: str, envid: str, svc: str,
               cmd: str, timeout: int) -> tuple[int, str]:
    """Marker-first exec. Returns (rc, output-after-marker)."""
    wrapped = f"echo {MARKER}; {cmd}"
    env = dict(base_env(), HOME=str(jar), SSH_AUTH_SOCK=sock)
    try:
        r = subprocess.run(
            [RAILWAY, "ssh", "-p", proj, "-e", envid, "-s", svc,
             "--", "bash", "-lc", wrapped],
            env=env, capture_output=True, text=True, timeout=timeout)
        out = r.stdout or ""
        if MARKER in out:
            return r.returncode, out.split(MARKER, 1)[1].strip()
        return -10, f"NO-MARKER rc={r.returncode} out={out[:150]} err={(r.stderr or '')[:150]}"
    except subprocess.TimeoutExpired:
        return -11, "TIMEOUT"
    except Exception as e:
        return -12, f"ERR:{str(e)[:120]}"


def load_registry() -> dict:
    try:
        return json.loads(REG.read_text())
    except Exception:
        return {}


def save_registry(reg: dict) -> None:
    tmp = str(REG) + ".tmp"
    json.dump(reg, open(tmp, "w"), indent=1)
    os.replace(tmp, str(REG))


def one(jar: Path, cmd: str, timeout: int, fire_and_forget: bool, jid: int) -> dict:
    rec = {"jar": jar.name, "jid": jid}
    cmd = cmd.replace("{{JID}}", str(jid))
    ids = jar_ids(jar)
    if not ids:
        return {**rec, "status": "no-ids"}
    proj, envid, svc = ids
    try:
        priv = ensure_key(jar)
        sock = agent_for(jar, priv)
        if not registered(jar, sock):
            if not register_key(jar, sock):
                return {**rec, "status": "key-register-fail"}
        if fire_and_forget:
            cmd = f"nohup bash -lc {cmd!r} >/dev/null 2>&1 & disown; echo STARTED"
        rc, out = run_remote(jar, sock, proj, envid, svc, cmd, timeout)
        ok = rc == 0 and out and not out.startswith("NO-MARKER")
        return {**rec, "status": "ok" if ok else "fail", "rc": rc,
                "out": out[:400]}
    except Exception as e:
        return {**rec, "status": f"harness:{str(e)[:80]}"}


def main() -> None:
    ap = argparse.ArgumentParser(description="One-command fan-out to the VPS fleet")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--cmd", default="", help="Remote command string")
    g.add_argument("--cmd-file", default="", help="File whose content is the remote command")
    ap.add_argument("--par", type=int, default=25)
    ap.add_argument("--target", type=int, default=0, help="max jars (0 = all)")
    ap.add_argument("--only", default="", help="substring filter on jar name")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--fire-and-forget", action="store_true",
                    help="nohup the command remotely; SSH returns in seconds")
    ap.add_argument("--resume", action="store_true", default=True)
    ap.add_argument("--no-resume", dest="resume", action="store_false")
    a = ap.parse_args()

    cmd = a.cmd or Path(a.cmd_file).read_text()
    jars = load_jars(a.only)
    if a.target:
        jars = jars[:a.target]
    print(f"jars={len(jars)} par={a.par} faf={a.fire_and_forget}", flush=True)

    reg = load_registry()
    todo = [j for j in jars if not (a.resume and reg.get(j.name, {}).get("status") == "ok")]
    print(f"todo={len(todo)} (skipped {len(jars) - len(todo)} done)", flush=True)

    ok = fail = 0
    with ThreadPoolExecutor(max_workers=a.par) as ex:
        futs = {ex.submit(one, j, cmd, a.timeout, a.fire_and_forget, wi): j
                for wi, j in enumerate(todo)}
        for i, f in enumerate(as_completed(futs), 1):
            try:
                r = f.result()
            except Exception as e:
                r = {"jar": futs[f].name, "status": f"harness:{str(e)[:70]}"}
            reg[r["jar"]] = {**r, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            if r.get("status") == "ok":
                ok += 1
            else:
                fail += 1
            if i % 10 == 0 or i == len(todo):
                save_registry(reg)
                print(f"[{i}/{len(todo)}] ok={ok} fail={fail} last={r['jar']}:{r['status']}",
                      flush=True)
    save_registry(reg)
    print(f"FINAL ok={ok} fail={fail}", flush=True)


if __name__ == "__main__":
    main()
