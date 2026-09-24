#!/usr/bin/env python3
"""Push MADE Railway jars to GitHub (decrypt GH PAT at runtime).

Conflict-free parallel design:
  - Each MADE jar gets a unique path: farmed-{host}-{shortuuid}/
  - Each push goes to its own branch: farm/{dest_name}
  - Never force-pushes main from workers (no merge conflicts between workers)
  - Boss merges farm/* → main via src/railway/merge_farm_branches.py

Requires:
  HOLY_SECRET_KEY   — passphrase to decrypt the GitHub token
  GH_TOKEN_ENC      — optional; else finals/secrets/gh_token.enc

Optional:
  GH_REPO           — default crucifix-cray/automation-toolkit
  GH_BASE_BRANCH    — default main (branch workers fork from)
  TOOLKIT_ROOT      — local checkout path
  GH_PUSH           — set 0 to skip
  GH_FARM_HOST      — worker id baked into path/branch (e.g. sb03)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

REPO_DEFAULT = "crucifix-cray/automation-toolkit"
BASE_DEFAULT = "main"


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
    here = Path(__file__).resolve()
    candidates.append(here.parents[2])
    candidates.append(Path("/app/toolkit"))
    candidates.append(Path("/tmp/holy-toolkit"))

    for c in candidates:
        if (c / ".git").is_dir() and (c / "src" / "railway" / "account_creation.py").is_file():
            return c

    dest = Path(env_root) if env_root else Path("/tmp/holy-toolkit")
    if dest.exists() and not (dest / ".git").is_dir():
        shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    base = os.environ.get("GH_BASE_BRANCH", BASE_DEFAULT)
    url = f"https://x-access-token:{token}@github.com/{os.environ.get('GH_REPO', REPO_DEFAULT)}.git"
    print(f"📥 Cloning toolkit → {dest}")
    r = _run(["git", "clone", "--depth", "1", "-b", base, url, str(dest)], timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"git clone failed: {(r.stderr or r.stdout)[:400]}")
    _run(["git", "remote", "set-url", "origin", f"https://github.com/{os.environ.get('GH_REPO', REPO_DEFAULT)}.git"], cwd=dest)
    return dest


def sync_to_github(session_dir: Path) -> None:
    """Copy MADE jar into a unique path and push a unique farm/* branch."""
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

    base = os.environ.get("GH_BASE_BRANCH", BASE_DEFAULT)
    host = (os.environ.get("GH_FARM_HOST") or "w").strip().replace("/", "-")[:32]
    short = uuid.uuid4().hex[:10]
    dest_name = f"farmed-{host}-{short}"
    farm_branch = f"farm/{dest_name}"
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
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "http.https://github.com/.extraheader"
    env["GIT_CONFIG_VALUE_0"] = (
        "AUTHORIZATION: basic "
        + __import__("base64").b64encode(f"x-access-token:{token}".encode()).decode()
    )

    def g(*args: str, timeout: int = 300) -> subprocess.CompletedProcess:
        return _run(["git", *args], cwd=repo, env=env, timeout=timeout)

    # unique branch off latest base — workers never push the same ref
    g("fetch", "origin", base)
    co = g("checkout", "-B", farm_branch, f"origin/{base}")
    if co.returncode != 0:
        # shallow clone may lack origin/base tip naming — fall back
        g("checkout", base)
        g("pull", "--ff-only", "origin", base)
        g("checkout", "-B", farm_branch)

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

    p = g("push", "-u", "origin", f"HEAD:{farm_branch}", timeout=600)
    if p.returncode != 0:
        print(f"⚠️  git push failed: {(p.stderr or p.stdout)[:400]}")
        return
    print(
        f"✅ Pushed {dest_name} → branch {farm_branch} "
        f"(github.com/{os.environ.get('GH_REPO', REPO_DEFAULT)})"
    )
    print(f"   merge later: python3 src/railway/merge_farm_branches.py")


def sync_lovable_to_github(session_dir: Path) -> None:
    """Copy Lovable session (verified + totp) to unique lov-* path / farm/lov-* branch."""
    if os.environ.get("GH_PUSH", "1") == "0":
        print("☁️  GitHub push skipped (GH_PUSH=0)")
        return

    session_dir = Path(session_dir)
    if not session_dir.is_dir():
        print(f"⚠️  GitHub push: missing session dir {session_dir}")
        return

    cfg_path = session_dir / "config.json"
    if not cfg_path.is_file():
        print(f"⚠️  GitHub push: no config.json in {session_dir.name}")
        return
    try:
        cfg = __import__("json").loads(cfg_path.read_text())
    except Exception as e:
        print(f"⚠️  GitHub push: bad config.json: {e}")
        return
    if not cfg.get("verified", False):
        print(f"⚠️  GitHub push: not verified — skip")
        return
    # 2FA optional: verified + cookies/refresh_token is enough to keep the account
    if not cfg.get("totp_secret") and not cfg.get("2fa_done"):
        print(f"ℹ️  GitHub push: verified without 2FA (2fa_pending) — {session_dir.name}")

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

    base = os.environ.get("GH_BASE_BRANCH", BASE_DEFAULT)
    host = (os.environ.get("GH_FARM_HOST") or "lov").strip().replace("/", "-")[:32]
    short = uuid.uuid4().hex[:10]
    dest_name = f"lov-{host}-{short}"
    farm_branch = f"farm/{dest_name}"
    dest = repo / "finals" / "sessions" / dest_name
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        session_dir,
        dest,
        ignore=shutil.ignore_patterns("*.log", ".cache", "__pycache__", "node_modules", ".reserved"),
    )

    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "http.https://github.com/.extraheader"
    env["GIT_CONFIG_VALUE_0"] = (
        "AUTHORIZATION: basic "
        + __import__("base64").b64encode(f"x-access-token:{token}".encode()).decode()
    )

    def g(*args: str, timeout: int = 300) -> subprocess.CompletedProcess:
        return _run(["git", *args], cwd=repo, env=env, timeout=timeout)

    g("fetch", "origin", base)
    co = g("checkout", "-B", farm_branch, f"origin/{base}")
    if co.returncode != 0:
        g("checkout", base)
        g("pull", "--ff-only", "origin", base)
        g("checkout", "-B", farm_branch)

    add = g("add", "-f", str(dest.relative_to(repo)))
    if add.returncode != 0:
        print(f"⚠️  git add failed: {(add.stderr or add.stdout)[:300]}")
        return

    st = g("status", "--porcelain")
    if not (st.stdout or "").strip():
        print(f"☁️  GitHub: nothing new for {dest_name}")
        return

    email = cfg.get("email") or "lovable-farm@local"
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

    p = g("push", "-u", "origin", f"HEAD:{farm_branch}", timeout=600)
    if p.returncode != 0:
        print(f"⚠️  git push failed: {(p.stderr or p.stdout)[:400]}")
        return
    print(
        f"✅ Pushed {dest_name} → branch {farm_branch} "
        f"(github.com/{os.environ.get('GH_REPO', REPO_DEFAULT)})"
    )
    print(f"   merge later: python3 src/railway/merge_farm_branches.py")
