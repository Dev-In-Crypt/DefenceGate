"""Names for entity resolution across the networks layer (plan M2-07).

`normalise_org_name` (dgate/normalise.py) is the key the buyer side has used since the first
ingest, and names already stored carry it: changing it would orphan every alias. The networks
layer needs more (Cyrillic, the legal forms of Ukraine, Romania, Czechia and the Baltics), so
the extra work is done here, on top of it:

    key_of("ТОВ \\"Укроборонпром\\"")   ->  "ukroboronprom"
    key_of("Ukroboronprom LLC")        ->  "ukroboronprom"

`key_of` returns the new key and the legacy key (what `normalise_org_name` gives for the raw
name). They are equal for every Latin name that carries no legal form added here; a lookup
tries both, a new row is written with the new one.
"""

from __future__ import annotations

import re

from ..normalise import normalise_org_name

# One consistent scheme: the Ukrainian national transliteration of 2010 (Cabinet resolution
# 55), with the Russian, Belarusian and Bulgarian letters that have no Ukrainian counterpart
# added in the same spirit. Hard and soft signs are dropped.
_CYR = {
    "а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d", "е": "e", "є": "ye", "ж": "zh",
    "з": "z", "и": "y", "і": "i", "ї": "yi", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "shch", "ь": "", "ю": "yu", "я": "ya", "'": "", "’": "", "ʼ": "",
    "ы": "y", "э": "e", "ъ": "", "ё": "yo", "ў": "u",
}
_CYR_TABLE = {ord(k): v for k, v in _CYR.items()}
_CYR_TABLE.update({ord(k.upper()): v.capitalize() for k, v in _CYR.items()})


def transliterate(raw: str) -> str:
    """Cyrillic to Latin; every other character is left as it is."""
    return raw.translate(_CYR_TABLE)


# Legal forms the shared list does not know, as token sequences of the *normalised* name
# (punctuation already gone, so "spol. s r.o." is spol s r o). Only at the start or the end of
# the name: "at" or "as" inside a name are words.
_EXTRA_FORMS: tuple[tuple[str, ...], ...] = (
    # Ukraine (after transliteration): TOV, PrAT, PAT, FOP, TzOV; and the English renderings. The
    # bare AT and PP of the Ukrainian forms are left alone: at and pp end Latin names as well.
    ("tov",), ("prat",), ("pat",), ("fop",), ("tzov",),
    ("limited", "liability", "company"), ("joint", "stock", "company"),
    ("private", "joint", "stock", "company"), ("public", "joint", "stock", "company"),
    # Romania
    ("s", "r", "l"), ("s", "c"), ("s", "n", "c"), ("s", "c", "a"),
    # Czechia and Slovakia
    ("spol", "s", "r", "o"), ("s", "r", "o"), ("sro",), ("a", "s"), ("vos",), ("v", "o", "s"),
    ("k", "s"), ("akciova", "spolecnost"),
    # Baltics: SIA (LV), OU (EE, from OÜ), AS (LV, EE), UAB, AB, MB, VSI (LT), IK
    ("sia",), ("ou",), ("as",), ("uab",), ("ab",), ("mb",), ("vsi",), ("ik",),
    # Forms the shared list has only with their dots ("b.v.", "s.a."), as the EDF factsheets and
    # CORDIS write them without ("THALES NEDERLAND B.V" and "BV": measured 17 October 2026)
    ("b", "v"), ("n", "v"), ("s", "a"), ("s", "l"), ("s", "p", "a"), ("s", "a", "s"),
    ("s", "a", "u"), ("s", "l", "u"), ("sau",), ("slu",), ("bvba",), ("e", "v"), ("ev",),
    ("ggmbh",), ("scpa",), ("d", "o", "o"), ("doo",), ("d", "d"), ("sp", "z", "o", "o"),
    ("spzoo",), ("zoo",), ("kft",), ("zrt",), ("eood",), ("ood",), ("ae",), ("epe",), ("ike",),
    # and the long forms, spelled out ("SPOLKA AKCYJNA" for "S.A."), which otherwise make every
    # Polish limited company look 0.85 alike
    ("spolka", "z", "ograniczona", "odpowiedzialnoscia"), ("spolka", "akcyjna"),
    ("aktiengesellschaft",), ("gesellschaft", "mit", "beschrankter", "haftung"),
    ("sociedade", "anonima"), ("societa", "per", "azioni"), ("societe", "anonyme"),
    ("anonymi", "etaireia"), ("anonymos", "etaireia"), ("etaireia", "periorismenis", "efthynis"),
)
_EXTRA_BY_LEN = sorted(_EXTRA_FORMS, key=len, reverse=True)


def _strip_extra_forms(key: str) -> str:
    tokens = key.split()
    changed = True
    while changed and len(tokens) > 1:
        changed = False
        for form in _EXTRA_BY_LEN:
            n = len(form)
            if len(tokens) > n and tuple(tokens[-n:]) == form:
                tokens = tokens[:-n]
                changed = True
                break
            if len(tokens) > n and tuple(tokens[:n]) == form:
                tokens = tokens[n:]
                changed = True
                break
    return " ".join(tokens)


def key_of(raw: str) -> tuple[str, str]:
    """(the networks key, the legacy key) of a raw organisation name. Either may be empty."""
    legacy = normalise_org_name(raw)
    if not raw:
        return "", legacy
    key = normalise_org_name(transliterate(raw))
    # a hyphen or an ampersand is spacing, not a letter: "KOCH- INSTITUT", "KOCH-INSTITUT" and
    # "KOCH INSTITUT" are one name, and so are "A&B" and "A & B" (the legacy key keeps both)
    key = re.sub(r"[-&]+", " ", key)
    key = _strip_extra_forms(re.sub(r"\s+", " ", key).strip())
    return key, legacy
