"""Key management for encrypted backups. Run this on the owner's machine.

    python -m dgate.ops.backup_keys generate --out-dir DIR
    python -m dgate.ops.backup_keys decrypt --private-key FILE --in X.sql.gz.enc --out X.sql.gz

`generate` makes the RSA-4096 pair. Only the PUBLIC key (`backup-public.pem`)
goes to the server (DGATE_BACKUP_PUBLIC_KEY). The private key stays with the
owner: whoever holds it can read every dump, and the server holding it would
undo the point of encrypting before the dump leaves the host. That is why key
generation lives here and nothing under the worker imports it.

`decrypt` is the restore drill: it streams, authenticates every frame, and
leaves no output file unless the whole input verified.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from .backup import (
    BackupFormatError,
    check_manifest,
    decrypt_stream,
    key_fingerprint,
    load_private_key,
    manifest_path,
)

PRIVATE_NAME = "backup-private.pem"
PUBLIC_NAME = "backup-public.pem"


def _write_new(path: Path, data: bytes, mode: int) -> None:
    """Create a file that must not exist, with its final mode from the start."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), mode)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    os.chmod(path, mode)


def _inside_git_work_tree(directory: Path) -> bool:
    return any((p / ".git").exists() for p in (directory, *directory.parents))


def generate(out_dir: Path) -> tuple[Path, Path, str]:
    """Write the key pair; returns (private path, public path, fingerprint)."""
    out_dir = out_dir.resolve()
    if _inside_git_work_tree(out_dir):
        raise SystemExit(f"refusing to write a private key inside a git work tree: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    private_path, public_path = out_dir / PRIVATE_NAME, out_dir / PUBLIC_NAME
    for path in (private_path, public_path):
        if path.exists():
            raise SystemExit(f"{path} already exists; refusing to overwrite a key")

    private = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    public = private.public_key()
    _write_new(private_path, private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()), 0o600)
    _write_new(public_path, public.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo), 0o644)
    return private_path, public_path, key_fingerprint(public)


def decrypt(private_key: Path, source: Path, target: Path) -> int:
    """Decrypt `source` into `target`; returns bytes written."""
    if target.exists():
        raise SystemExit(f"{target} already exists; refusing to overwrite")
    key = load_private_key(private_key)
    if manifest_path(source).exists():
        check_manifest(source)                      # raises on any mismatch
        print(f"manifest ok: {manifest_path(source).name}")
    else:
        print(f"warning: no {manifest_path(source).name} beside the file; hash not checked",
              file=sys.stderr)
    partial = target.with_name(target.name + ".partial")
    try:
        with open(source, "rb") as src, open(partial, "wb") as dst:
            written = decrypt_stream(src, dst, key)
        partial.replace(target)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dgate-backup-keys")
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate", help="make an RSA-4096 key pair")
    gen.add_argument("--out-dir", type=Path, required=True)
    dec = sub.add_parser("decrypt", help="decrypt one dump (restore drill)")
    dec.add_argument("--private-key", type=Path, required=True)
    dec.add_argument("--in", dest="source", type=Path, required=True)
    dec.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.command == "generate":
        private_path, public_path, fingerprint = generate(args.out_dir)
        print(f"private key: {private_path}")
        print(f"public key:  {public_path}")
        print(f"public key sha256 fingerprint: {fingerprint}")
        return 0

    try:
        written = decrypt(args.private_key, args.source, args.out)
    except (BackupFormatError, RuntimeError) as exc:
        print(f"decrypt failed: {exc}", file=sys.stderr)
        return 1
    print(f"{args.out} ({written} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
