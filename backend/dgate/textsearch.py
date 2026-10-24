"""Word search for the funding list (`q`), in Python because the corpus is a few hundred calls.

What the old substring match got wrong (ux-funding F3, 16 October 2026): `counter-drone` and
`counter drone` were different searches, `AI` matched "against" and "available", and a grant writer
who types `drone` never saw the call titled "Unmanned systems and counter-unmanned systems".

The rules, in the order they are applied:

  - both sides are folded: accents and Polish/Danish letters removed, lower case, and every run of
    anything that is not a letter or digit is a word break, so `counter-drone` is two words;
  - a word of the query must match a WORD of the text (never the middle of one), and every word of
    the query must match (stop words such as "for" are dropped unless nothing else is left);
  - how a word matches depends on its length: up to 3 letters (`AI`, `UAS`) the whole word, 4 letters
    a word that begins with it, 5 or more any word that contains it (`logistic` finds "logistics",
    `cyber` finds "cybersecurity");
  - the identifiers of a call (topic code, call identifier) are searched by the start of their
    words, whatever the length: `HORIZON-CL3-2026-01-FC` finds `HORIZON-CL3-2026-01-FCT-01`;
  - a word with synonyms (SYNONYMS below, curated by hand, small on purpose) may be matched by any
    of them. The synonyms that were used are returned, so the page can say what else was searched.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache

from .normalise import _TRANSLITERATE
from .search_terms import groups

STOP_WORDS = frozenset({"a", "an", "and", "for", "in", "of", "on", "or", "the", "to", "with"})

# One row is one idea. A multi-word entry is a phrase: its words must follow each other.
# Not a thesaurus: only terms a funding search is known to use for the same thing.
SYNONYMS: tuple[tuple[str, ...], ...] = (
    ("drone", "uas", "uav", "unmanned", "rpas"),
    ("logistics", "supply", "mobility"),
    ("ai", "artificial intelligence", "machine learning"),
    # WP-91 (UX audit 6, a drone-software start-up): words its founder typed that found nothing. Kept to the same idea per row.
    ("software", "algorithms", "computing", "data fusion", "simulation"),
    ("autonomy", "autonomous", "uncrewed", "robotic", "robotics", "swarm"),
    ("cyber", "cybersecurity", "cyber security", "cyber defence"),
    ("sme", "smes", "small and medium", "pme", "pyme", "msp"),
    # WP-99: ASAP (the Act in Support of Ammunition Production) also finds the EDIP calls; no primary source we hold names a successor
    ("asap", "edip"),
)

MAX_TERMS = 8


@lru_cache(maxsize=1)
def _rows() -> tuple[tuple[str, ...], ...]:
    """WP-110: the product groups of the tender search (`search_terms`, the other languages' words), for the funding
    search's words SYNONYMS does not know: "cybersécurité" found no funding call and the header search said no open calls, though ECCC cyber calls were open."""
    return tuple(tuple(dict.fromkeys(fold(" ".join(t)) for t in g.terms)) for g in groups())


def fold(text: str) -> str:
    """Lower case, no accents, words separated by single spaces."""
    s = unicodedata.normalize("NFKD", text or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).translate(_TRANSLITERATE)
    return " ".join(re.findall(r"[^\W_]+", s.casefold()))


def words(text: str) -> list[str]:
    return fold(text).split()


def _word_matches(wanted: str, have: str) -> bool:
    if len(wanted) <= 3:
        return have == wanted
    if len(wanted) == 4:
        return have.startswith(wanted)
    return wanted in have


def _code_matches(wanted: str, have: str) -> bool:
    return have.startswith(wanted) or (len(wanted) >= 5 and wanted in have)


def _phrase_in(phrase: list[str], tokens: list[str], same=_word_matches) -> bool:
    return any(all(same(w, tokens[i + j]) for j, w in enumerate(phrase))
               for i in range(len(tokens) - len(phrase) + 1))


@dataclass
class Query:
    """The folded query: for each typed word, the alternatives (each a list of words)."""
    terms: list[str] = field(default_factory=list)
    alternatives: list[list[list[str]]] = field(default_factory=list)
    # The synonyms offered beyond what was typed, for the "also searched" line.
    also: list[str] = field(default_factory=list)

    def matches(self, text: str, codes: str = "") -> bool:
        """`text` is words (a title, a body); `codes` are identifiers, matched by their start."""
        have, ids = words(text), words(codes)
        return all(any(_phrase_in(alt, have) or _phrase_in(alt, ids, _code_matches) for alt in group)
                   for group in self.alternatives)


def parse(q: str | None, products: bool = False) -> Query | None:
    """None when the text holds no word at all (a query of punctuation searches nothing)."""
    typed = words(q or "")[: MAX_TERMS * 2]
    kept = [w for w in typed if w not in STOP_WORDS] or typed
    kept = kept[:MAX_TERMS]
    if not kept:
        return None
    query = Query(terms=kept)
    for word in kept:
        group = [[word]]
        # WP-110: the product groups only for a word the funding synonyms do not know (drone, cyber keep their own rows)
        known = any(word in row for row in SYNONYMS)
        for row in (_rows() if products and not known else SYNONYMS):
            if word in row:
                for other in row:
                    if other != word:
                        group.append(other.split())
                        if other not in query.also:
                            query.also.append(other)
        query.alternatives.append(group)
    # a synonym that is also one of the typed words was searched, not "also" searched
    query.also = [a for a in query.also if a not in kept]
    return query
