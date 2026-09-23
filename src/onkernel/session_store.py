"""Crash-safe local storage for OnKernel account credentials and browser state."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any


SESSION_SUFFIXES = (".json", ".cookies.json", ".storage.json")


def atomic_write_json(path: str | Path, value: Any) -> None:
    """Write JSON through a same-directory temporary file, then atomically replace."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(value, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, target)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def session_bundle_paths(session_file: str | Path) -> tuple[Path, Path, Path]:
    account = Path(session_file)
    if not account.name.endswith(".json"):
        raise ValueError(f"Session path must end in .json: {account}")
    base = str(account)[:-5]
    return account, Path(base + ".cookies.json"), Path(base + ".storage.json")


def backup_session_bundle(session_file: str | Path, reason: str) -> Path:
    """Copy every existing session artifact to an immutable timestamped directory."""
    account, cookies, storage = session_bundle_paths(session_file)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    safe_reason = "".join(c if c.isalnum() or c in "-_" else "_" for c in reason)
    backup_dir = account.parent / "backups" / account.stem / f"{stamp}-{safe_reason}"
    serial = 1
    while backup_dir.exists():
        backup_dir = backup_dir.with_name(f"{backup_dir.name}-{serial}")
        serial += 1
    backup_dir.mkdir(parents=True, mode=0o700)

    manifest: dict[str, Any] = {
        "created_at": stamp,
        "reason": reason,
        "source": str(account.resolve()),
        "files": {},
    }
    for source in (account, cookies, storage):
        if not source.exists():
            continue
        destination = backup_dir / source.name
        shutil.copy2(source, destination)
        os.chmod(destination, 0o600)
        manifest["files"][source.name] = {
            "bytes": destination.stat().st_size,
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        }
    atomic_write_json(backup_dir / "manifest.json", manifest)
    return backup_dir


async def save_session_bundle(
    session_file: str | Path,
    account_data: dict[str, Any],
    context: Any,
) -> None:
    """Snapshot browser state first, then atomically publish all three artifacts."""
    account, cookies_file, storage_file = session_bundle_paths(session_file)
    cookies = await context.cookies()
    storage = await context.storage_state()

    atomic_write_json(account, account_data)
    atomic_write_json(cookies_file, cookies)
    atomic_write_json(storage_file, storage)


def save_latest_pointer(session_file: str | Path, account_data: dict[str, Any]) -> None:
    """Update latest_onk.json without replacing the canonical account record."""
    account = Path(session_file).resolve()
    pointer = {
        "session_file": str(account),
        "email": account_data.get("email"),
        "api_key": account_data.get("api_key"),
        "org": account_data.get("org"),
        "org_slug": account_data.get("org_slug"),
        "status": account_data.get("status"),
        "updated_at": account_data.get("updated_at")
        or account_data.get("reset_at")
        or account_data.get("created_at"),
    }
    atomic_write_json(account.parent / "latest_onk.json", pointer)
