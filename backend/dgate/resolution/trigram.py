"""pg_trgm's similarity in Python, and the rule that turns a similar pair into a candidate.

Stage 3 of the cascade finds candidates in the database with the `%` operator; the gold
set is evaluated here, without a database, with the same arithmetic. A test compares the
two on sample names, so the arithmetic cannot drift from the extension's.
"""

from __future__ import annotations

import re

THRESHOLD = 0.85


def trigrams(text: str) -> set[str]:
    """The trigram set pg_trgm builds: each word lower-cased, two spaces before it and one
    after, every run of three characters."""
    out: set[str] = set()
    for word in re.findall(r"[^\W_]+", text.lower()):
        padded = f"  {word} "
        out.update(padded[i:i + 3] for i in range(len(padded) - 2))
    return out


def similarity(a: str, b: str) -> float:
    ta, tb = trigrams(a), trigrams(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _digits(text: str) -> list[str]:
    return re.findall(r"\d+", text)


def is_candidate(key_a: str, country_a: str, key_b: str, country_b: str) -> float | None:
    """The similarity of two normalised names when they are a candidate pair, else None.

    A candidate is a pair of different keys in one country with similarity at or above 0.85
    and the same numbers in the name ("Szkola Podstawowa nr 1" and "nr 2" are 0.9 alike and
    are two schools). A country mismatch is a hard veto.
    """
    if not key_a or not key_b or key_a == key_b:
        return None
    if country_a != country_b:
        return None
    if _digits(key_a) != _digits(key_b):
        return None
    sim = similarity(key_a, key_b)
    return sim if sim >= THRESHOLD else None
