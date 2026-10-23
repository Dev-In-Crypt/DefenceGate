"""WP-90: the English titles of the CPV vocabulary, for the tender search.

`data/cpv-full.json` is the site's copy (`web/lib/data/cpv-full.json`, the Publications Office's CPV 2008, English
titles verbatim; source and licence inside the file), kept identical by `tests/unit/test_wp90.py`. A search word
matches a code when it begins a word of the code's title, folded as `dg_fold` folds (migration 0054), so "radar"
finds 35722000 Radar and 38115000 Radar apparatus. The list then keeps a notice that has one of those codes
(`o.cpv_codes && codes`, the GIN index `opp_cpv`): its own codes, not their parents.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent / "data" / "cpv-full.json"
SEPARATORS = re.compile(r"[\s\-–—/_.,;:()\"'’]+")
# A word shorter than this names no product ("a", "of"), and a word in more titles than this ("services", "parts":
# thousands of codes) narrows nothing: the title search alone reads it. Said on the page beside the box.
MIN_WORD = 3
MAX_CODES = 200


def fold(text: str) -> str:
    """Lower case, accents off, the separators of `dg_fold` as single spaces, with a leading space."""
    t = unicodedata.normalize("NFKD", (text or "").lower().replace("ß", "ss").replace("æ", "ae").replace("œ", "oe"))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " " + " ".join(w for w in SEPARATORS.split(t) if w)


@lru_cache(maxsize=1)
def _titles() -> tuple[tuple[str, str], ...]:
    codes = json.loads(DATA.read_text(encoding="utf-8"))["codes"]
    return tuple((code, fold(title)) for code, title in codes.items())


@lru_cache(maxsize=512)
def codes_for_word(word: str) -> tuple[str, ...]:
    """The codes whose English title has a word beginning with `word`; empty when the word is too short or names
    more than MAX_CODES codes."""
    w = fold(word).strip()
    if len(w) < MIN_WORD or " " in w:
        return ()
    needle = " " + w
    got = tuple(code for code, title in _titles() if needle in title)
    return got if len(got) <= MAX_CODES else ()
