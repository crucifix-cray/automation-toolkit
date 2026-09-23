#!/usr/bin/env python3
"""Push MADE Railway jars to GitHub (decrypt GH PAT at runtime).

Requires:
  HOLY_SECRET_KEY   — passphrase to decrypt the GitHub token
  GH_TOKEN_ENC      — optional; else finals/secrets/gh_token.enc

Optional:
  GH_REPO           — default crucifix-cray/automation-toolkit
  GH_BRANCH         — default main
  TOOLKIT_ROOT      — local checkout path (default: auto-detect / clone to /tmp/holy-toolkit)
  GH_PUSH           — set 0 to skip
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_DEFAULT = "crucifix-cray/automation-toolkit"
BRANCH_DEFAULT = "main"


def _run(cmd: list[str], cwd: Path | None = None, env: dict | None = None, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _decrypt_token() -> str:
    # allow importing when run from src/railway or repo root
    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from src.utils.secret_box import decrypt_github_token

    enc_path = root / "finals" / "secrets" / "gh_token.enc"
    return decrypt_github_token(path=enc_path if enc_path.is_file() else None)


def ensure_toolkit_repo(token: str) -> Path:
    """Return a writable git checkout of the toolkit (clone if missing)."""
    env_root = (os.environ.get("TOOLKIT_ROOT") or "").strip()
    candidates: list[Path] = []
    if env_root:
        candidates.append(Path(env_root))
    # common layouts
    here = Path(__file__).resolve()
    candidates.append(here.parents[2])  # .../automation-toolkit
    candidates.append(Path("/app/toolkit"))
    candidates.append(Path("/tmp/holy-toolkit"))

    for c in candidates:
        if (c / ".git").is_dir() and (c / "src" / "railway" / "account_creation.py").is_file():
            return c

    dest = Path(env_root) if env_root else Path("/tmp/holy-toolkit")
    if dest.exists() and not (dest / ".git").is_dir():
        shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://x-access-token:{token}@github.com/{os.environ.get('GH_REPO', REPO_DEFAULT)}.git"
    print(f"📥 Cloning toolkit → {dest}")
    r = _run(["git", "clone", "--depth", "1", "-b", os.environ.get("GH_BRANCH", BRANCH_DEFAULT), url, str(dest)], timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"git clone failed: {(r.stderr or r.stdout)[:400]}")
    # scrub token from remote URL in local config
    _run(["git", "remote", "set-url", "origin", f"https://github.com/{os.environ.get('GH_REPO', REPO_DEFAULT)}.git"], cwd=dest)
    return dest


def sync_to_github(session_dir: Path) -> None:
    """Copy MADE session jar into repo finals/sessions/ and push."""
    if os.environ.get("GH_PUSH", "1") == "0":
        print("☁️  GitHub push skipped (GH_PUSH=0)")
        return

    session_dir = Path(session_dir)
    if not session_dir.is_dir():
        print(f"⚠️  GitHub push: missing session dir {session_dir}")
        return
    if not (session_dir / "verified.json").is_file():
        print(f"⚠️  GitHub push: no verified.json in {session_dir.name}")
        return

    try:
        token = _decrypt_token()
    except Exception as e:
        print(f"⚠️  GitHub push skipped (decrypt): {e}")
        return

    if not shutil.which("git"):
        print("⚠️  GitHub push skipped: git not installed")
        return

    try:
        repo = ensure_toolkit_repo(token)
    except Exception as e:
        print(f"⚠️  GitHub push: ensure repo failed: {e}")
        return

    branch = os.environ.get("GH_BRANCH", BRANCH_DEFAULT)
    dest_name = f"farmed-{session_dir.name}"
    dest = repo / "finals" / "sessions" / dest_name
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        session_dir,
        dest,
        ignore=shutil.ignore_patterns("*.log", ".cache", "__pycache__", "node_modules"),
    )

    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    # auth via header so remote URL stays clean
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "http.https://github.com/.extraheader"
    env["GIT_CONFIG_VALUE_0"] = f"AUTHORIZATION: basic {__import__('base64').b64encode(f'x-access-token:{token}'.encode()).decode()}"

    def g(*args: str, timeout: int = 300) -> subprocess.CompletedProcess:
        return _run(["git", *args], cwd=repo, env=env, timeout=timeout)

    # refresh + commit
    g("fetch", "origin", branch)
    g("checkout", branch)
    g("pull", "--ff-only", "origin", branch)

    # force-add (some session files may match ignore rules)
    add = g("add", "-f", str(dest.relative_to(repo)))
    if add.returncode != 0:
        print(f"⚠️  git add failed: {(add.stderr or add.stdout)[:300]}")
        return

    st = g("status", "--porcelain")
    if not (st.stdout or "").strip():
        print(f"☁️  GitHub: nothing new for {dest_name}")
        return

    email = "holy-farm@local"
    try:
        email = (session_dir / "email.txt").read_text().strip() or email
    except Exception:
        pass
    msg = f"farm: add {dest_name} ({email})"
    g("config", "user.email", "holy-farm@users.noreply.github.com")
    g("config", "user.name", "holy-farm")
    c = g("commit", "-m", msg)
    if c.returncode != 0:
        print(f"⚠️  git commit failed: {(c.stderr or c.stdout)[:300]}")
        return

    p = g("push", "origin", f"HEAD:{branch}", timeout=600)
    if p.returncode != 0:
        print(f"⚠️  git push failed: {(p.stderr or p.stdout)[:400]}")
        return
    print(f"✅ Pushed {dest_name} → github.com/{os.environ.get('GH_REPO', REPO_DEFAULT)} ({branch})")
