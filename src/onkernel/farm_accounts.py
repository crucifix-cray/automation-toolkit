#!/usr/bin/env python3
"""Create OnKernel accounts through a round-robin pool of existing orgs.

Each provider gets at most one active signup at a time. Provider API keys and
CDP URLs stay in process environment variables and are never printed or saved
in the new account records.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SESSIONS = ROOT / "finals" / "sessions"
CREATOR = Path(__file__).with_name("account_creation.py")
DEFAULT_PROVIDERS = (
    "onk_1788991878.json",
    "onk_1788993960.json",
    "onk_1788994087.json",
)


def clean_env() -> dict[str, str]:
    env = dict(os.environ)
    env["LD_PRELOAD"] = ""
    for key in (
        "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
        "ALL_PROXY", "all_proxy", "PLAYWRIGHT_PROXY_URL",
    ):
        env.pop(key, None)
    return env


def parse_json_output(text: str) -> Any:
    for opener in ("{", "["):
        start = text.find(opener)
        if start >= 0:
            try:
                return json.loads(text[start:])
            except json.JSONDecodeError:
                continue
    raise RuntimeError(f"No JSON object in command output: {text[:200]!r}")


def load_provider(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    missing = [key for key in ("email", "api_key", "proxy_id") if not data.get(key)]
    if missing:
        raise RuntimeError(f"{path.name} missing provider fields: {', '.join(missing)}")
    return {
        "path": path,
        "name": path.stem,
        "email": data["email"],
        "api_key": data["api_key"],
        "proxy_id": data["proxy_id"],
    }


def create_browser(provider: dict[str, Any], env: dict[str, str]) -> dict[str, Any]:
    env["KERNEL_API_KEY"] = provider["api_key"]
    command = [
        "kernel", "browsers", "create",
        "--stealth",
        "--proxy-id", provider["proxy_id"],
        "--timeout", "1800",
        "-o", "json",
    ]
    result = subprocess.run(
        command, capture_output=True, text=True, env=env, timeout=120
    )
    if result.returncode:
        raise RuntimeError(
            f"provider {provider['name']} browser create failed: "
            f"{(result.stderr or result.stdout)[:300]}"
        )
    browser = parse_json_output(result.stdout)
    browser["id"] = (
        browser.get("id") or browser.get("session_id") or browser.get("browser_id")
    )
    if not browser["id"] or not browser.get("cdp_ws_url"):
        raise RuntimeError(f"provider {provider['name']} returned incomplete browser JSON")
    return browser


def newest_created_session(provider_name: str, since_ns: int) -> Path | None:
    matches = []
    for path in SESSIONS.glob("onk_*.json"):
        if any(part in path.name for part in (".cookies", ".storage")):
            continue
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        if (
            data.get("browser_provider") == provider_name
            and path.stat().st_mtime_ns >= since_ns
        ):
            matches.append(path)
    return max(matches, key=lambda path: path.stat().st_mtime_ns, default=None)


def farm_one(provider: dict[str, Any], sequence: int) -> dict[str, Any]:
    env = clean_env()
    browser = create_browser(provider, env)
    browser_id = browser["id"]
    provider_label = provider["name"]
    started_ns = time.time_ns()
    log_path = Path(f"/tmp/onk-farm-{provider_label}-{sequence}.log")
    env["ONKERNEL_CDP_URL"] = browser["cdp_ws_url"]
    env["ONKERNEL_PROVIDER_NAME"] = provider_label
    try:
        with log_path.open("w") as log:
            process = subprocess.Popen(
                [
                    sys.executable, "-u", str(CREATOR),
                    "--end", "--attempts", "3",
                ],
                cwd=ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            assert process.stdout is not None
            for line in process.stdout:
                log.write(line)
                log.flush()
                print(f"[{provider_label}:{sequence}] {line}", end="", flush=True)
            return_code = process.wait()

        session = newest_created_session(provider_label, started_ns)
        if return_code or session is None:
            raise RuntimeError(
                f"creator failed rc={return_code}; log={log_path}; session={session}"
            )
        account = json.loads(session.read_text())
        return {
            "provider": provider_label,
            "session_file": str(session),
            "email": account.get("email"),
            "status": account.get("status"),
            "trial": account.get("trial"),
            "proxy_id": account.get("proxy_id"),
            "log": str(log_path),
        }
    finally:
        cleanup_env = clean_env()
        cleanup_env["KERNEL_API_KEY"] = provider["api_key"]
        subprocess.run(
            ["kernel", "browsers", "delete", browser_id],
            capture_output=True,
            text=True,
            env=cleanup_env,
            timeout=30,
        )


def farm_provider(provider: dict[str, Any], sequences: list[int]) -> list[dict[str, Any]]:
    results = []
    for sequence in sequences:
        try:
            results.append(farm_one(provider, sequence))
        except Exception as exc:
            results.append({
                "provider": provider["name"],
                "sequence": sequence,
                "status": "failed",
                "error": str(exc),
            })
    return results


def allocations(count: int, providers: list[dict[str, Any]]) -> dict[str, list[int]]:
    result = {provider["name"]: [] for provider in providers}
    for sequence in range(1, count + 1):
        provider = providers[(sequence - 1) % len(providers)]
        result[provider["name"]].append(sequence)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Spread OnKernel signups across provider orgs")
    parser.add_argument("--count", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--providers",
        nargs="*",
        default=[str(SESSIONS / name) for name in DEFAULT_PROVIDERS],
    )
    args = parser.parse_args()
    if args.count < 1:
        raise SystemExit("--count must be positive")

    providers = [load_provider(Path(path)) for path in args.providers]
    plan = allocations(args.count, providers)
    print("Allocation:", json.dumps(plan, indent=2))
    if args.dry_run:
        return

    all_results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(providers)) as pool:
        futures = [
            pool.submit(farm_provider, provider, plan[provider["name"]])
            for provider in providers
            if plan[provider["name"]]
        ]
        for future in concurrent.futures.as_completed(futures):
            all_results.extend(future.result())

    all_results.sort(
        key=lambda item: (
            item.get("provider", ""),
            str(item.get("session_file") or item.get("sequence", 0)),
        )
    )
    summary = Path("/tmp/onk-farm-summary.json")
    summary.write_text(json.dumps(all_results, indent=2) + "\n")
    print(json.dumps(all_results, indent=2))
    print(f"Summary: {summary}")
    if any(item.get("status") != "ready" for item in all_results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
