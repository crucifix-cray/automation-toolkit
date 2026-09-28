#!/usr/bin/env python3
"""cell_ssh2.py — SSH to a Railway cell by SERVICE INSTANCE ID (works with no domain).

`railway ssh -s <name>` needs a domain. Services we create from a plain public
image have no domain, so we address them by service instance id instead
(docs: "a deployment instance ID works as the username too").

Also knows the "drop a first line" quirk: railway ssh eats the first stdout
line, so every script starts with a throwaway echo and we verify a sentinel.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

RW = "/home/alan/Documents/repos/chimera-miner/ops"
import sys
sys.path.insert(0, RW)
from cell_ops import rw_env, linked_cwd  # noqa: E402


def run(railway_session: int, instance: str, script: str, sentinel: str,
        *, service: str | None = None, timeout: int = 240, tries: int = 3):
    home = Path(f"/home/alan/Documents/railways/sessions/session-{railway_session}")
    env = rw_env(home)
    cwd = linked_cwd(home, service) if service else home
    script = "echo\n" + script
    last = ""
    for _ in range(tries):
        # instance id is globally unique: pass ONLY -d (adding -s makes the
        # CLI print account JSON instead of running the command).
        cmd = ["railway", "ssh", "-d", instance, "--", "bash", "-lc", script]
        try:
            r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True,
                               timeout=timeout)
        except subprocess.TimeoutExpired:
            last = "timeout"
            time.sleep(5)
            continue
        out = (r.stdout or b"").decode("utf-8", "replace")
        if sentinel in out:
            return True, out
        err = (r.stderr or b"").decode("utf-8", "replace")
        last = (out.strip()[-250:] + " | " + err[-160:]) if (out.strip() or err) else f"rc={r.returncode}"
        time.sleep(6)
    return False, last


def upload(railway_session: int, instance: str, local: Path, remote: str,
           *, service: str | None = None, timeout: int = 240):
    """Ship a file with base64 over one-shot SSH (no scp, no stdin)."""
    import base64
    b64 = base64.b64encode(local.read_bytes()).decode()
    chunks = [b64[i:i + 3000] for i in range(0, len(b64), 3000)]
    parts = ["mkdir -p $(dirname %s) 2>/dev/null || true" % remote]
    for i, ch in enumerate(chunks):
        op = ">" if i == 0 else ">>"
        parts.append(f"printf '%s' '{ch}' {op} /tmp/.up.b64")
    script = ("echo\n: > /tmp/.up.b64\n" + "\n".join(parts) +
              f"\nbase64 -d /tmp/.up.b64 > {remote} && echo MARK-END")
    ok, out = run(railway_session, instance, script, "MARK-END",
                  service=service, timeout=timeout)
    if not ok:
        return ok, out
    script2 = f"echo\nwc -c < {remote}; md5sum {remote} | cut -d' ' -f1; echo MARK-END"
    return run(railway_session, instance, script2, "MARK-END",
               service=service, timeout=timeout)


def upload_big(railway_session, instance, local, remote, *, service=None,
               chunk=45000, timeout=280, gunzip=True):
    """Ship a large file: gzip+base64 streamed in several SSH calls.

    One SSH command cannot hold a 182KB file, so we append it in order.
    Returns (ok, "md5=... want=... match=bool").
    """
    import base64, gzip, hashlib

    raw = Path(local).read_bytes()
    want = hashlib.md5(raw).hexdigest()
    blob = gzip.compress(raw, 6) if gunzip else raw
    b64 = base64.b64encode(blob).decode()
    chunks = [b64[i:i + chunk] for i in range(0, len(b64), chunk)]

    ok, out = run(railway_session, instance,
                  "echo\nmkdir -p $(dirname %s) 2>/dev/null || true; "
                  ": > /tmp/.stream.b64; rm -f /tmp/.updone; echo MARK-END" % remote,
                  "MARK-END", service=service, timeout=timeout)
    if not ok:
        return False, "init failed: %s" % out[:150]

    for i, c in enumerate(chunks):
        op = ">" if i == 0 else ">>"
        script = ("echo\nprintf '%%s' '%s' %s /tmp/.stream.b64; "
                  "wc -c < /tmp/.stream.b64; echo MARK-END" % (c, op))
        good, o = run(railway_session, instance, script, "MARK-END",
                      service=service, timeout=timeout, tries=3)
        if not good:
            return False, "chunk %d/%d failed: %s" % (i + 1, len(chunks), o[:150])
        print("    chunk %d/%d ok" % (i + 1, len(chunks)), flush=True)

    dec = ("base64 -d /tmp/.stream.b64 | gunzip -c > %s" % remote) if gunzip else \
          ("base64 -d /tmp/.stream.b64 > %s" % remote)
    good, o = run(railway_session, instance,
                  "echo\n%s && touch /tmp/.updone; md5sum %s | cut -d' ' -f1; echo MARK-END" % (dec, remote),
                  "MARK-END", service=service, timeout=timeout, tries=3)
    got = ""
    for line in (o or "").splitlines():
        s = line.strip()
        if len(s) == 32 and all(ch in "0123456789abcdef" for ch in s):
            got = s
    return good, "md5=%s want=%s match=%s" % (got, want, got == want)
