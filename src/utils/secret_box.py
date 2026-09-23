#!/usr/bin/env python3
"""Encrypt / decrypt small secrets (GitHub PAT) for Railway farm workers.

Ciphertext may live in the repo or in GH_TOKEN_ENC. The passphrase never does —
inject HOLY_SECRET_KEY only at runtime (Railway env / sandbox --variable).

Usage:
  # one-time on laptop (writes finals/secrets/gh_token.enc)
  HOLY_SECRET_KEY='your-passphrase' GITHUB_TOKEN='ghp_...' \\
    python3 -m src.utils.secret_box encrypt --out finals/secrets/gh_token.enc

  # decrypt check
  HOLY_SECRET_KEY='your-passphrase' python3 -m src.utils.secret_box decrypt \\
    --in finals/secrets/gh_token.enc
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import os
import sys
from pathlib import Path

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError as e:  # pragma: no cover
    raise SystemExit("cryptography required: pip install cryptography") from e


def fernet_from_passphrase(passphrase: str) -> Fernet:
    if not passphrase:
        raise ValueError("empty passphrase")
    digest = hashlib.sha256(passphrase.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_text(plain: str, passphrase: str) -> str:
    token = fernet_from_passphrase(passphrase).encrypt(plain.encode("utf-8"))
    return token.decode("ascii")


def decrypt_text(blob: str, passphrase: str) -> str:
    blob = (blob or "").strip()
    if not blob:
        raise ValueError("empty ciphertext")
    try:
        return fernet_from_passphrase(passphrase).decrypt(blob.encode("ascii")).decode("utf-8")
    except InvalidToken as e:
        raise ValueError("decrypt failed (wrong HOLY_SECRET_KEY or corrupt blob)") from e


def load_ciphertext(path: Path | None = None, env_key: str = "GH_TOKEN_ENC") -> str:
    env = (os.environ.get(env_key) or "").strip()
    if env:
        return env
    if path is None:
        # repo-relative default
        here = Path(__file__).resolve()
        path = here.parents[2] / "finals" / "secrets" / "gh_token.enc"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    raise FileNotFoundError(
        f"no ciphertext: set {env_key} or create {path} via secret_box encrypt"
    )


def decrypt_github_token(
    passphrase: str | None = None,
    path: Path | None = None,
) -> str:
    pw = passphrase if passphrase is not None else (os.environ.get("HOLY_SECRET_KEY") or "")
    if not pw:
        raise ValueError("HOLY_SECRET_KEY required to decrypt GitHub token")
    return decrypt_text(load_ciphertext(path=path), pw)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Encrypt/decrypt GitHub token for Holy farm")
    sub = ap.add_subparsers(dest="cmd", required=True)

    enc = sub.add_parser("encrypt", help="Encrypt GITHUB_TOKEN with HOLY_SECRET_KEY")
    enc.add_argument("--out", type=Path, default=Path("finals/secrets/gh_token.enc"))
    enc.add_argument("--token-env", default="GITHUB_TOKEN")
    enc.add_argument("--pass-env", default="HOLY_SECRET_KEY")

    dec = sub.add_parser("decrypt", help="Decrypt and print token (stdout)")
    dec.add_argument("--in", dest="infile", type=Path, default=None)
    dec.add_argument("--pass-env", default="HOLY_SECRET_KEY")

    args = ap.parse_args(argv)
    if args.cmd == "encrypt":
        token = (os.environ.get(args.token_env) or "").strip()
        pw = (os.environ.get(args.pass_env) or "").strip()
        if not token:
            print(f"❌ set {args.token_env}", file=sys.stderr)
            return 1
        if not pw:
            print(f"❌ set {args.pass_env}", file=sys.stderr)
            return 1
        args.out.parent.mkdir(parents=True, exist_ok=True)
        blob = encrypt_text(token, pw)
        args.out.write_text(blob + "\n", encoding="utf-8")
        print(f"✅ wrote {args.out} ({len(blob)} chars)")
        print("Inject HOLY_SECRET_KEY at runtime only. Commit the .enc file, never the raw token.")
        return 0

    if args.cmd == "decrypt":
        pw = (os.environ.get(args.pass_env) or "").strip()
        try:
            print(decrypt_github_token(passphrase=pw, path=args.infile))
        except Exception as e:
            print(f"❌ {e}", file=sys.stderr)
            return 1
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
