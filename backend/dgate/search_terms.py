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
MAX_ALTERNATIVES = 40


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
    # WP-110: the codes whose main-code notices are the product itself (the search's code part; never a secondary code)
    anchors: tuple[str, ...] = ()
    # WP-125: words that, typed, search the group, but that no other word of it searches ("foundry": the place, not the
    # product; "castings" found a water-pipe tender through the code title "Foundry moulds"), folded
    typed_only: tuple[tuple[str, ...], ...] = ()


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
                         tuple(tuple(fold_words(t)) for t in g["terms"]), tuple(g.get("anchors", ())),
                         tuple(tuple(fold_words(t)) for t in g.get("typed_only", ())))
                   for g in raw["groups"])
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
    # WP-110: the group of each slot (None: a word of no group), in the order of `slots`
    slot_groups: list[Group | None] = field(default_factory=list)


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
    """The slots of a search's words (`tenders.search_words`): the longest term of a group at each position first.

    WP-101: a run of terms of one group is one slot ("Drehteile Frästeile": any term of the spare-parts group, or both
    words), not a slot per term. Two slots of one group asked for the group twice, which is the same notices (every term
    of the group fills either), at twice the work: the search ran past the API's 5 s on production every time."""
    gs = groups()
    folded = [" ".join(fold_words(w)) for w in words]
    out = Expanded()
    typed_keys: list[set[tuple[str, ...]]] = []      # per slot: the typed terms, never "also" searched
    slot_group: list[Group | None] = []
    i = 0
    while i < len(words):
        best: tuple[int, Group] | None = None
        for g in gs:
            for term in g.folded + g.typed_only:
                n = len(term)
                if n and tuple(folded[i:i + n]) == term and (best is None or n > best[0]):
                    best = (n, g)
        if best is None:
            out.slots.append([[words[i]]])
            typed_keys.append(set())
            slot_group.append(None)
            i += 1
            continue
        n, g = best
        typed = words[i:i + n]
        keys = {tuple(w for x in typed for w in fold_words(x))}
        if slot_group and slot_group[-1] is g:
            typed = out.slots.pop()[0] + typed
            keys |= typed_keys.pop()
            slot_group.pop()
        out.slots.append(_subsumed([typed] + [list(t) for t in g.terms])[:MAX_ALTERNATIVES])
        typed_keys.append(keys)
        slot_group.append(g)
        if g not in out.groups:
            out.groups.append(g)
        i += n
    out.slot_groups = slot_group
    for alts, keys in zip(out.slots, typed_keys, strict=True):
        for alt in alts[1:]:
            label = " ".join(alt)
            if tuple(w for x in alt for w in fold_words(x)) not in keys and label not in out.also:
                out.also.append(label)
    return out


def buyer_names(text: str) -> list[tuple[str, ...]]:
    """The full names an abbreviation stands for, when the search is exactly that abbreviation (a space inside it
    optional: JAEMALE, JAE MALE); empty otherwise."""
    typed = "".join(fold_words(text))
    return [n for b in _data()[1] if "".join(fold_words(b.abbr)) == typed for n in b.names] if typed else []
