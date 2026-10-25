"""dgate/credentials.py and the sign-in delay: RFC 4226/6238 vectors, the password policy,
Argon2id, sealed TOTP keys, recovery codes (WP-79)."""

from __future__ import annotations

import base64

import pytest

from dgate import accounts, credentials

SEED_SHA1 = b"12345678901234567890"
SEED_SHA256 = b"12345678901234567890123456789012"
SEED_SHA512 = b"1234567890123456789012345678901234567890123456789012345678901234"

# RFC 6238, appendix B: time, then the 8-digit TOTP for SHA1, SHA256, SHA512.
RFC6238 = [
    (59, "94287082", "46119246", "90693936"),
    (1111111109, "07081804", "68084774", "25091201"),
    (1111111111, "14050471", "67062674", "99943326"),
    (1234567890, "89005924", "91819424", "93441116"),
    (2000000000, "69279037", "90698825", "38618901"),
    (20000000000, "65353130", "77737706", "47863826"),
]


@pytest.mark.parametrize("at,sha1,sha256,sha512", RFC6238)
def test_totp_matches_the_rfc_6238_test_vectors(at, sha1, sha256, sha512):
    assert credentials.totp(SEED_SHA1, at, digits=8, digest="sha1") == sha1
    assert credentials.totp(SEED_SHA256, at, digits=8, digest="sha256") == sha256
    assert credentials.totp(SEED_SHA512, at, digits=8, digest="sha512") == sha512


def test_hotp_matches_the_rfc_4226_test_vectors():
    expected = ["755224", "287082", "359152", "969429", "338314",
                "254676", "287922", "162583", "399871", "520489"]
    assert [credentials.hotp(SEED_SHA1, i) for i in range(10)] == expected


def test_a_code_is_valid_one_step_either_side_and_only_once():
    secret, at = SEED_SHA1, 1_700_000_000.0
    now = int(at // 30)
    for drift in (-1, 0, 1):
        code = credentials.hotp(secret, now + drift)
        assert credentials.totp_step(secret, code, at, None) == now + drift
    assert credentials.totp_step(secret, credentials.hotp(secret, now + 2), at, None) is None
    assert credentials.totp_step(secret, credentials.hotp(secret, now - 2), at, None) is None
    code = credentials.hotp(secret, now)
    assert credentials.totp_step(secret, code, at, now) is None          # replay of the used step
    assert credentials.totp_step(secret, code, at, now - 1) == now
    assert credentials.totp_step(secret, "12 34 5", at, None) is None
    assert credentials.totp_step(secret, "abcdef", at, None) is None
    spaced = f"{code[:3]} {code[3:]}"
    assert credentials.totp_step(secret, spaced, at, None) == now


def test_the_otpauth_uri_carries_the_key_the_app_needs():
    secret = credentials.new_totp_secret()
    uri = credentials.otpauth_uri(secret, "ann@example.com")
    assert uri.startswith("otpauth://totp/DefenceGate%3Aann%40example.com?secret=")
    key = uri.split("secret=")[1].split("&")[0]
    assert base64.b32decode(key + "=" * (-len(key) % 8)) == secret
    assert "digits=6" in uri and "period=30" in uri and len(secret) == 20


@pytest.mark.parametrize("password,problem", [
    ("short-pass1", "too_short"),
    ("x" * 129, "too_long"),
    ("password1234", "common"),
    ("Password2026!", "common"),               # a stem with digits and a symbol around it
    ("2026qwertyuiop!", "common"),
    ("123456789012", "common"),
    ("aaaaaaaaaaaaaaaa", "common"),            # fewer than five distinct characters
    ("abcdabcdabcdabcd", "common"),
    ("my defencegate login", "common"),
    ("annabelle-rocks-the-river", "common"),   # the address's own name, below
])
def test_the_password_policy_refuses_short_long_and_common_passwords(password, problem):
    assert credentials.password_problem(password, "annabelle@example.com") == problem


@pytest.mark.parametrize("password", [
    "correct horse battery mule", "Tr4m-Lantern-Orbit", "zwölf Äpfel im Korb", "x7#Qp9!vL2@m",
])
def test_the_password_policy_has_no_composition_rule(password):
    assert credentials.password_problem(password, "ann@example.com") is None


def test_the_common_list_is_lower_case_and_has_no_blank_entries():
    words = credentials._common()
    assert len(words) > 200 and all(w == w.lower() and w.strip() == w and w for w in words)


def test_argon2id_hash_verifies_only_the_same_password():
    stored = credentials.hash_password("correct horse battery mule")
    assert stored.startswith("$argon2id$v=19$m=19456,t=2,p=1$")
    assert "correct" not in stored
    assert credentials.verify_password("correct horse battery mule", stored)
    assert not credentials.verify_password("correct horse battery mulE", stored)
    assert credentials.hash_password("correct horse battery mule") != stored      # salted
    # NFKC: the same text in composed and decomposed form is one password
    assert credentials.verify_password("zwölf Äpfel", credentials.hash_password("zwölf Äpfel"))


def test_no_hash_and_a_broken_hash_are_a_no_never_an_error():
    assert credentials.verify_password("anything at all", None) is False
    assert credentials.verify_password("anything at all", "not a hash") is False
    assert credentials.verify_password("anything at all", "$argon2id$v=19$m=1,t=1,p=1$xx$yy") is False


def test_a_sealed_key_opens_only_with_the_same_server_key_and_account():
    blob = credentials.seal(b"k" * 20, b"server-key", "user-1")
    assert b"k" * 20 not in blob
    assert credentials.unseal(blob, b"server-key", "user-1") == b"k" * 20
    assert credentials.unseal(blob, b"other-key", "user-1") is None
    assert credentials.unseal(blob, b"server-key", "user-2") is None
    assert credentials.unseal(blob[:-1] + bytes([blob[-1] ^ 1]), b"server-key", "user-1") is None


def test_recovery_codes_are_distinct_readable_and_keyed():
    codes = credentials.new_recovery_codes()
    assert len(codes) == 10 and len(set(codes)) == 10
    assert all(len(c) == 11 and c[5] == "-" and not set(c) & set("01ilo") for c in codes)
    h = credentials.recovery_code_hash(codes[0], b"key")
    assert h == credentials.recovery_code_hash(codes[0].upper().replace("-", " "), b"key")
    assert h != credentials.recovery_code_hash(codes[0], b"other")


def test_the_sign_in_delay_starts_after_the_free_attempts_and_doubles_up_to_an_hour():
    free = accounts.LOGIN_FREE
    assert accounts.login_wait(free - 1, 0, free) == 0
    assert accounts.login_wait(free, 0, free) == accounts.LOGIN_DELAY
    assert accounts.login_wait(free + 1, 0, free) == 2 * accounts.LOGIN_DELAY
    assert accounts.login_wait(free + 1, 2 * accounts.LOGIN_DELAY, free) == 0     # waited it out
    assert accounts.login_wait(free + 20, 0, free) == 3600
    assert accounts.login_wait(10_000, 0, free) == 3600
