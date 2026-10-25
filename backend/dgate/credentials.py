"""Credentials: password hashing and policy, TOTP (RFC 6238), recovery codes, sealed secrets.

Pure functions, no database: `accounts.py` holds the flows. Built to the rows A7-A10 that WP-79
adds to docs/SECURITY_REQUIREMENTS.md (written out in docs/verification/product/wp79-selfcheck.md).

- Passwords: Argon2id through `cryptography` (already a dependency for the backups; it has
  Argon2id with PHC strings since 45, so no second library), with the OWASP minimum
  parameters (19 MiB, 2 passes, 1 lane). NFKC-normalised before hashing, so the same password
  typed on two keyboards is the same password.
- Policy (NIST SP 800-63B 5.1.1.2): at least 12 characters, at most 128, not on a list of
  common passwords, not built on a common word with digits around it, not the address's own
  name. No composition rules.
- TOTP: HMAC-SHA1, 6 digits, 30 s steps, one step of clock drift either way, a step used once.
- Secrets that the server must read back (the TOTP key) are sealed with AES-GCM under a key
  derived from the server's own secret, bound to the account id, so a row copied to another
  account or read from a dump is useless without the server.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import struct
import unicodedata
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from cryptography.exceptions import InvalidKey, InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

PASSWORD_MIN = 12
PASSWORD_MAX = 128
ARGON_MEMORY_KIB = 19456
ARGON_ITERATIONS = 2
ARGON_LANES = 1

COMMON_FILE = Path(__file__).resolve().parents[1] / "seeds" / "common_passwords.txt"

TOTP_STEP = 30
TOTP_DIGITS = 6
TOTP_ISSUER = "DefenceGate"
RECOVERY_CODES = 10
_RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"      # no 0/o, 1/l/i


# ------------------------------------------------------------------ passwords
def _norm(password: str) -> bytes:
    return unicodedata.normalize("NFKC", password).encode("utf-8")


@lru_cache(maxsize=1)
def _common() -> frozenset[str]:
    lines = COMMON_FILE.read_text(encoding="utf-8").splitlines()
    return frozenset(s.strip().lower() for s in lines if s.strip() and not s.startswith("#"))


def password_problem(password: str, email: str = "") -> str | None:
    """None when the password is acceptable, else `too_short`, `too_long` or `common`."""
    if len(password) < PASSWORD_MIN:
        return "too_short"
    if len(password) > PASSWORD_MAX:
        return "too_long"
    low = unicodedata.normalize("NFKC", password).lower()
    core = re.sub(r"^[\d\W_]+|[\d\W_]+$", "", low)        # "Password2026!" -> "password"
    local = email.split("@", 1)[0].lower()
    if (low in _common() or core in _common() or len(set(low)) < 5
            or "defencegate" in low or (len(local) >= 4 and local in low)):
        return "common"
    return None


def hash_password(password: str) -> str:
    kdf = Argon2id(salt=os.urandom(16), length=32, iterations=ARGON_ITERATIONS,
                   lanes=ARGON_LANES, memory_cost=ARGON_MEMORY_KIB)
    return kdf.derive_phc_encoded(_norm(password))


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return hash_password(secrets.token_urlsafe(16))


def verify_password(password: str, encoded: str | None) -> bool:
    """The same work whether or not there is a hash: an unknown address costs one Argon2id
    run too, so the answer time does not say whether an account exists."""
    try:
        Argon2id.verify_phc_encoded(_norm(password), encoded or _dummy_hash())
    except (InvalidKey, ValueError, TypeError):
        return False
    return encoded is not None


# ------------------------------------------------------------------ TOTP
def new_totp_secret() -> bytes:
    return secrets.token_bytes(20)                      # 160 bits, RFC 4226 recommendation


def b32(secret: bytes) -> str:
    return base64.b32encode(secret).decode("ascii").rstrip("=")


def hotp(secret: bytes, counter: int, digits: int = TOTP_DIGITS, digest: str = "sha1") -> str:
    mac = hmac.new(secret, struct.pack(">Q", counter), digest).digest()
    offset = mac[-1] & 0x0F
    value = (struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(value).zfill(digits)


def totp(secret: bytes, at: float, digits: int = TOTP_DIGITS, digest: str = "sha1") -> str:
    return hotp(secret, int(at // TOTP_STEP), digits, digest)


def totp_step(secret: bytes, code: str, at: float, last_step: int | None) -> int | None:
    """The step a code is valid for (now, or one step either side), if that step is later than
    the last one used (a code works once), else None."""
    code = re.sub(r"\s", "", code or "")
    if not re.fullmatch(rf"[0-9]{{{TOTP_DIGITS}}}", code):
        return None
    now = int(at // TOTP_STEP)
    for step in (now - 1, now, now + 1):
        if step > (last_step if last_step is not None else -1) and hmac.compare_digest(hotp(secret, step), code):
            return step
    return None


def otpauth_uri(secret: bytes, account: str) -> str:
    label = quote(f"{TOTP_ISSUER}:{account}")
    return (f"otpauth://totp/{label}?secret={b32(secret)}&issuer={TOTP_ISSUER}"
            f"&algorithm=SHA1&digits={TOTP_DIGITS}&period={TOTP_STEP}")


# ------------------------------------------------------------------ recovery codes
def new_recovery_codes(n: int = RECOVERY_CODES) -> list[str]:
    """`xxxxx-xxxxx`, 10 characters of a 31-letter alphabet: about 49 bits each."""
    def one() -> str:
        s = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(10))
        return f"{s[:5]}-{s[5:]}"
    return [one() for _ in range(n)]


def recovery_code_hash(code: str, server_key: bytes) -> bytes:
    """Keyed: 49 bits is too few for a plain hash to survive a stolen dump."""
    clean = re.sub(r"[\s-]", "", (code or "").lower())
    return hmac.new(server_key, b"recovery\x00" + clean.encode("utf-8"), hashlib.sha256).digest()


# ------------------------------------------------------------------ sealed secrets
def _seal_key(server_key: bytes) -> bytes:
    return hmac.new(server_key, b"dgate totp seal v1", hashlib.sha256).digest()


def seal(secret: bytes, server_key: bytes, bound_to: str) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(_seal_key(server_key)).encrypt(nonce, secret, bound_to.encode("utf-8"))


def unseal(blob: bytes, server_key: bytes, bound_to: str) -> bytes | None:
    try:
        return AESGCM(_seal_key(server_key)).decrypt(bytes(blob[:12]), bytes(blob[12:]),
                                                     bound_to.encode("utf-8"))
    except (InvalidTag, ValueError):
        return None
