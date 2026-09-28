#!/usr/bin/env python3
"""Reap orphaned Chrome processes on a 1GB cell.

Playwright hard-kills leave chrome children reparented to PID 1. A few dozen
of those starve the page: the Lovable composer never renders, health probes
time out, and the OOM killer follows. Keep only the largest browser tree (the
live one), kill the rest. Measured: 166 procs/953MB -> 40 procs/536MB.
"""
import os
import time


def chrome_procs():
    out = {}
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            stat = open(f"/proc/{pid}/stat").read()
            ppid = int(stat.rsplit(")", 1)[1].split()[1])
            cmd = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\0", b" ").decode()
        except Exception:
            continue
        if "chrome" in cmd or "chromium" in cmd:
            out[int(pid)] = ppid
    return out


def trees(procs):
    roots = {p for p, pp in procs.items() if pp not in procs}
    groups = {r: [r] for r in roots}
    for pid, ppid in procs.items():
        if ppid in procs:
            for r, members in groups.items():
                if pid in _descend(procs, r, set()):
                    members.append(pid)
                    break
    return groups


def _descend(procs, root, seen):
    out, stack = set(), [root]
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        out.add(n)
        for c, pp in procs.items():
            if pp == n:
                stack.append(c)
    return out


def main():
    while True:
        time.sleep(20)
        p = chrome_procs()
        if len(p) <= 12:
            continue
        groups = trees(p)
        best = max(groups.values(), key=len) if groups else []
        keep = set(best)
        dead = [pid for pid in p if pid not in keep]
        for pid in dead:
            try:
                os.kill(pid, 9)
            except Exception:
                pass
        if dead:
            print(f"reaped {len(dead)}, kept {len(keep)}", flush=True)


if __name__ == "__main__":
    main()
