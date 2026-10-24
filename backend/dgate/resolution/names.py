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
import unicodedata

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
    # WP-104: the mark of a Spanish state company (Sociedad Mercantil Estatal: "NAVANTIA, S.A., S.M.E.", "NAVANTIA SA,
    # SME"), which the name carries after its form, and the singular the notices misspell ("Leonardo, Societa per Azione")
    ("s", "m", "e"), ("sme",), ("societa", "per", "azione"),
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
    key = normalise_org_name(transliterate(_cut_address(raw)))
    # a hyphen or an ampersand is spacing, not a letter: "KOCH- INSTITUT", "KOCH-INSTITUT" and
    # "KOCH INSTITUT" are one name, and so are "A&B" and "A & B" (the legacy key keeps both)
    key = re.sub(r"[-&]+", " ", key)
    key = _strip_extra_forms(re.sub(r"\s+", " ", key).strip())
    return key, legacy


# Legal forms after which a name may go on with its address (WP-87: "HENSOLDT NEXEYA FRANCE SAS 1 rue ..." beside
# "Hensoldt Nexeya France"). The short ones that are words as well (as, ab, se, ev, kg) are left out.
_CUT_FORMS = ("gmbh", "mbh", "ag", "sas", "sa", "sarl", "srl", "spa", "bv", "nv", "ltd", "limited", "plc", "llc",
              "inc", "oy", "oyj", "sl", "slu", "sau", "sro", "aps")


def _cut_address(raw: str) -> str:
    """The raw name without an address written after its legal form: a legal-form word that is not the first word,
    followed by at least two more words of which one holds a digit (a street number, a postcode). The name up to and
    with its form is kept (the key strips the form as before); a name with no such tail is returned as it is."""
    words = raw.split()
    for i in range(1, len(words) - 2):
        if (_form_tokens(words[i]) in ([f] for f in _CUT_FORMS)
                and any(any(ch.isdigit() for ch in w) for w in words[i + 1:])):
            return " ".join(words[:i + 1])
    return raw


# ------------------------------------------------------------------ legal form (WP-41)

# The legal form a raw name states, as a class: the spellings of one form are one class ("GmbH",
# "G.m.b.H.", "Gesellschaft mit beschraenkter Haftung"), two different forms are two classes. A
# company limited by shares and a limited company of the same group are different legal bodies even
# when everything else of the name is equal (RENK AG, RENK GmbH): the key strips both, so the key
# alone cannot tell them apart. Only the forms listed here count; any other name has no class and
# is never kept apart by this rule. Token sequences of the *unstripped* name, folded as `key_of`
# folds (accents, case, punctuation as spacing), at the end or at the start of the name.
_FORM_CLASSES: dict[str, tuple[tuple[str, ...], ...]] = {
    "gmbh_co_kg": (("gmbh", "co", "kg"), ("gmbh", "u", "co", "kg"), ("gmbh", "co", "ohg")),
    "gmbh": (("gmbh",), ("g", "m", "b", "h"), ("mbh",), ("gesellschaft", "mit", "beschrankter", "haftung"),
             ("gesellschaft", "mit", "beschraenkter", "haftung")),
    "ag": (("ag",), ("aktiengesellschaft",)),
    "se": (("se",),),
    "kg": (("kg",), ("kommanditgesellschaft",)),
    "ev": (("e", "v"), ("ev",), ("eingetragener", "verein")),
    "sa": (("sa",), ("s", "a"), ("societe", "anonyme"), ("sociedad", "anonima"), ("sociedade", "anonima"),
           ("spolka", "akcyjna"), ("s", "a", "u"), ("sau",)),
    "sas": (("sas",), ("s", "a", "s"), ("societe", "par", "actions", "simplifiee")),
    "sarl": (("sarl",), ("s", "a", "r", "l"), ("societe", "a", "responsabilite", "limitee")),
    "sl": (("sl",), ("s", "l"), ("sociedad", "limitada"), ("slu",), ("s", "l", "u")),
    "srl": (("srl",), ("s", "r", "l"), ("societa", "a", "responsabilita", "limitata")),
    "spa": (("spa",), ("s", "p", "a"), ("societa", "per", "azioni"), ("societa", "per", "azione")),
    "bv": (("bv",), ("b", "v"), ("besloten", "vennootschap")),
    "nv": (("nv",), ("n", "v"), ("naamloze", "vennootschap")),
    "zoo": (("sp", "z", "o", "o"), ("spzoo",), ("spolka", "z", "ograniczona", "odpowiedzialnoscia")),
    "oy": (("oy",), ("osakeyhtio",)),
    "oyj": (("oyj",),),
    "ab": (("ab",), ("aktiebolag",)),
    "as": (("as",), ("a", "s"), ("aksjeselskap",), ("aktieselskab",)),
    "aps": (("aps",),),
    "ltd": (("ltd",), ("limited",)),
    "plc": (("plc",),),
    "llc": (("llc",), ("limited", "liability", "company")),
    "inc": (("inc",), ("incorporated",)),
    "sro": (("s", "r", "o"), ("sro",)),
}
_FORM_LOOKUP: list[tuple[tuple[str, ...], str]] = sorted(
    ((seq, cls) for cls, seqs in _FORM_CLASSES.items() for seq in seqs),
    key=lambda x: len(x[0]), reverse=True)


def _form_tokens(raw: str) -> list[str]:
    s = unicodedata.normalize("NFKD", transliterate(raw or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower().replace("ß", "ss")
    return re.findall(r"[a-z0-9]+", s)


def legal_form_of(raw: str | None) -> str | None:
    """The legal-form class a raw name states at its end or its start, or None."""
    tokens = _form_tokens(raw or "")
    if len(tokens) < 2:
        return None
    for seq, cls in _FORM_LOOKUP:
        n = len(seq)
        if len(tokens) > n and (tuple(tokens[-n:]) == seq or tuple(tokens[:n]) == seq):
            return cls
    return None


def fold_key(key: str) -> str:
    """The key with every space removed: names that differ only by where a space falls ("ANGEWA NDTEN"
    against "ANGEWANDTEN", "UNIVERSITEDULUXEMBOURG") fold to one string. A weaker equality than the key
    itself, used only by the merge tool and with its own, lower confidence."""
    return re.sub(r"[\s.]+", "", key or "")
