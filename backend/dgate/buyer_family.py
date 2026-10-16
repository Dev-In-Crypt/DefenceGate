"""Which organisation rows are one body (display layer only, WP-22).

A pure function over (country, normalised name). It decides nothing about the data: the
rows stay as they are and `ops/buyer_families.py` stores the result in `buyer_family_member`,
which the buyer list reads. Explicit rules, no fuzzy matching, no similarity score and no
grouping across countries; a wrong group is worse than none, so a rule that cannot be
defended from the names alone is not here.

Rules, strongest first:

  named agency   a short list written as regular expressions, each with the reason it is
                 one body (confidence 0.90)
  fr_ministry    French names carry the ministry's own prefix (`minarm`, `mindef`) and
                 sometimes its title as a suffix; with those removed the same service has
                 one name (0.90)
  identical_name the same normalised name in the same country (0.95)
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Family:
    key: str            # rows with the same key are one family
    method: str         # the rule, stored with the member
    confidence: float


IDENTICAL = 0.95
RULE = 0.90

# (name, country, pattern on the normalised name, why it is one body)
NAMED: tuple[tuple[str, str, re.Pattern[str], str], ...] = (
    # The Federal Office for Bundeswehr Equipment, IT and In-Service Support. Its desks
    # (K2 4, G2 1, E3 6 ...), its Koblenz seat, its tender collection point and the
    # misspelt long names (the notices are typed by hand) are all the one federal office.
    ("baainbw", "DE", re.compile(r"^(?:baainbw\b|bundesamt fu(?:r|er) ausr(?:u|ue)stung\b)"),
     "one federal office; the names begin with its name or its abbreviation"),
    # The Navy arsenal: two sites (Wilhelmshaven, Rostock/Warnowwerft), one authority.
    ("marinearsenal", "DE", re.compile(r"^marinearsenal\b"),
     "one authority with two sites, both named after it"),
    # Heeresinstandsetzungslogistik GmbH, written with or without its abbreviation.
    ("hil", "DE", re.compile(r"^(?:hil )?heeresinstandsetzungslog\w*$"),
     "one company, with and without its abbreviation (and one typo)"),
    # BW Bekleidungsmanagement GmbH (BwBM), the Bundeswehr's clothing company.
    ("bwbm", "DE", re.compile(r"^(?:bw bekleidungsmanagement|bwbm)\b"),
     "one company, written in full or by its abbreviation"),
    # The Polish Armament Agency; 'Skarb Panstwa' is the State Treasury, the owner the
    # budget unit signs for, and one record carries a removed e-mail address after the name.
    ("agencja_uzbrojenia", "PL", re.compile(r"^(?:skarb panstwa\s*-?\s*)?agencja uzbrojenia\b"),
     "one budget unit, with and without the State Treasury in front"),
    # Its predecessor under the same form of words (renamed on 1 January 2022, stated in
    # a notice that carries both names). Kept as a family of its own: the two names are
    # not merged with each other.
    ("inspektorat_uzbrojenia", "PL",
     re.compile(r"^(?:skarb panstwa\s*-?\s*)?inspektorat uzbrojenia\b"),
     "one budget unit, with and without the State Treasury in front"),
)

_FR_PREFIX = re.compile(r"^(?:minarm|mindef) ")
_FR_SUFFIX = re.compile(r" ministere (?:des armees|de la defense)\b(.*)$")
# A suffix that goes on to name a division, a site or a production pole describes a
# sub-unit, not the service in front of it: those names are left whole.
_FR_SUBUNIT = re.compile(r"\b(?:division|site|prod|pole|da-\w+)\b")


def _fr_stripped(name: str) -> str:
    out = _FR_PREFIX.sub("", name, count=1)
    m = _FR_SUFFIX.search(out)
    if m and m.start() > 0 and not _FR_SUBUNIT.search(m.group(1)):
        out = out[:m.start()]
    return out


def family_of(country: str | None, name: str | None) -> Family | None:
    """The family a (country, normalised name) belongs to, or None for an empty name.
    A family of one row is not a family: the caller keeps only keys with two rows."""
    c = (country or "").strip().upper()
    n = (name or "").strip()
    if not c or not n:
        return None
    for label, country_, pattern, _why in NAMED:
        if c == country_ and pattern.search(n):
            # "rule:" cannot occur in a normalised name, so a row that is merely called "hil"
            # never lands in the key of the HIL rule
            return Family(f"{c}:rule:{label}", f"rule:{label}", RULE)
    if c == "FR":
        stripped = _fr_stripped(n)
        if stripped and stripped != n:
            return Family(f"{c}:{stripped}", "fr_ministry", RULE)
    return Family(f"{c}:{n}", "identical_name", IDENTICAL)


def family_key(country: str | None, name: str | None) -> str | None:
    f = family_of(country, name)
    return f.key if f else None
