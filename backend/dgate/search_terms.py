"""WP-98 (persona round of 23 October 2026, section C): the search words of other languages and the buyers' abbreviations.

One keyword map (`data/search-terms.json`, curated, no language model; `web/lib/data/search-terms.json` is the same file,
held identical by `tests/unit/test_wp98.py`) read by the tender search (`tenders._tender_filters`, and so the global
search's tender part) and the buyer search (`tenders.list_buyers`):

  - `expand`: the words of a search as slots. A run of words that is a term of a group ("spare parts", "fardamento") is one
    slot that any term of the group fills ("Ersatzteile", "recambios", "części zamienne"); every other word is a slot of its
    own. The list keeps a notice where every slot is filled, in any order: each word of a term begins a word of the title or
    the buyer's name (`dg_word_pattern`), as the search always read a word.
  - `buyer_names`: a search that is exactly an abbreviation (BAAINBw, DMO, DGA, JAE MALE) also finds the families named in
    full, and they come first.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .normalise import _TRANSLITERATE

DATA = Path(__file__).parent / "data" / "search-terms.json"
SEPARATORS = re.compile(r"[\s\-–—/_.,;:()\"'’]+")      # dg_fold's (migration 0054), as tenders.SEARCH_SEPARATORS
MAX_ALTERNATIVES = 24


def fold_words(text: str) -> list[str]:
    """The words of `text` as dg_fold folds them: lower case, accents and ł/ß/æ... off, split at its separators."""
    s = unicodedata.normalize("NFKD", text or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).translate(_TRANSLITERATE).casefold()
    return [w for w in SEPARATORS.split(s) if w]


@dataclass(frozen=True)
class Group:
    id: str
    label: str
    cpv: tuple[str, ...]
    terms: tuple[tuple[str, ...], ...]       # each term as its words, as written
    folded: tuple[tuple[str, ...], ...]      # the same, folded


@dataclass(frozen=True)
class BuyerAbbreviation:
    abbr: str
    country: str
    names: tuple[tuple[str, ...], ...]       # each full name as its words


@lru_cache(maxsize=1)
def _data() -> tuple[tuple[Group, ...], tuple[BuyerAbbreviation, ...]]:
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    groups = tuple(Group(g["id"], g["label"], tuple(g["cpv"]),
                         tuple(tuple(SEPARATORS.split(t.strip())) for t in g["terms"]),
                         tuple(tuple(fold_words(t)) for t in g["terms"])) for g in raw["groups"])
    buyers = tuple(BuyerAbbreviation(b["abbr"], b["country"], tuple(tuple(fold_words(n)) for n in b["names"]))
                   for b in raw["buyers"])
    return groups, buyers


def groups() -> tuple[Group, ...]:
    return _data()[0]


@dataclass
class Expanded:
    # Each slot: its alternatives, each a list of words (the typed words first). Every slot must be filled.
    slots: list[list[list[str]]] = field(default_factory=list)
    # The terms searched beyond the typed words, for the page's "also searched" line, and the groups they came from.
    also: list[str] = field(default_factory=list)
    groups: list[Group] = field(default_factory=list)


def _subsumed(alts: list[list[str]]) -> list[list[str]]:
    """The alternatives without those another one already covers: a one-word term that begins with another one-word
    term ("uniformes" under "uniform") matches nothing more, since a word matches by its start."""
    one = [fold_words(a[0])[0] for a in alts if len(a) == 1 and fold_words(a[0])]
    out, seen = [], set()
    for a in alts:
        key = tuple(w for x in a for w in fold_words(x))
        if not key or key in seen:
            continue
        if len(key) == 1 and any(o != key[0] and key[0].startswith(o) for o in one):
            continue
        seen.add(key)
        out.append(a)
    return out


def expand(words: list[str]) -> Expanded:
    """The slots of a search's words (`tenders.search_words`): the longest term of a group at each position first."""
    gs = groups()
    folded = [" ".join(fold_words(w)) for w in words]
    out = Expanded()
    i = 0
    while i < len(words):
        best: tuple[int, Group] | None = None
        for g in gs:
            for term in g.folded:
                n = len(term)
                if n and tuple(folded[i:i + n]) == term and (best is None or n > best[0]):
                    best = (n, g)
        if best is None:
            out.slots.append([[words[i]]])
            i += 1
            continue
        n, g = best
        typed = words[i:i + n]
        alts = _subsumed([typed] + [list(t) for t in g.terms])[:MAX_ALTERNATIVES]
        out.slots.append(alts)
        for alt in alts[1:]:
            label = " ".join(alt)
            if label not in out.also:
                out.also.append(label)
        if g not in out.groups:
            out.groups.append(g)
        i += n
    return out


def buyer_names(text: str) -> list[tuple[str, ...]]:
    """The full names an abbreviation stands for, when the search is exactly that abbreviation (a space inside it
    optional: JAEMALE, JAE MALE); empty otherwise."""
    typed = "".join(fold_words(text))
    return [n for b in _data()[1] if "".join(fold_words(b.abbr)) == typed for n in b.names] if typed else []
