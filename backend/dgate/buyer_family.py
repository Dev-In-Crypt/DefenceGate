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

from .buyer_vocab import buyer_class_of


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


# ------------------------------------------------------------- public bodies and their units
#
# A tax id proves one legal entity, not one buyer: a regional government, a ministry or a city
# council files every department under its one number (WP-74: on 21 October 2026 the merge of rows
# sharing a number put the Basque Government's 116 departments under 'gobierno vasco - seguridad').
# Such rows are never merged by a shared number (`ops/accept_merge_candidates`, refusal
# `public_body`); `ops/buyer_families` shows them as one buyer under the parent body's name
# (rule `shared_tax_id`). Names are the stored form: lower case, accents folded.

SHARED_TAX_ID = "shared_tax_id"

# a name that names a unit of a body: a department, a directorate, a service, a branch
SUB_UNIT = re.compile("|".join((
    r"\bdepartamento?\b|\bdepartament\b|\bconsejeria\b|\bconselleria\b|\bviceconsejeria\b",
    r"\barea de gobierno\b|\bdireccion\b|\bsubdireccion\b|\bdelegacion\b|\bgerencia\b",
    r"\bsecretaria general\b|\bservicio de\b|\bservei de\b|\bconcejalia\b|\bregidoria\b",
    r"\btenencia de alcaldia\b|\bdistrito\b|\bdistricte\b|\bunidad de contratacion\b",
    r"\bdirezione\b|\bdipartimento\b|\bsettore\b|\bservizio\b|\bufficio\b|\bdivisione\b",
    r"\bprovveditorato\b|\bassessorato\b|\bstazione unica appaltante\b|\bu d\b",
    r"\bdirection\b|\bsous-direction\b|\bsecretariat general\b|\bservice (?:de|d|des|du)\b|\bpole\b",
    r"\bdelegation (?:regionale|territoriale|departementale)\b|\bdirection territoriale\b",
    r"\babteilung\b|\babt\b|\bfachbereich\b|\bfachdienst\b|\breferat\b|\bdezernat\b|\bamt fur\b",
    r"\bsachgebiet\b|\bdienststelle\b|\bniederlassung\b|\blandesstelle\b|\bdienstort\b|betriebsstelle",
    r"\balue\b|\bvestiging\b",
    r"\bafdeling\b|\bdirectie\b|\blocatie\b|\bdirectia\b|\bdirectiei\b|\bsucursala\b|\bserviciul\b",
    r"\bdirecao\b|\bdivisao\b|\bwydzial\b|\bdepartament\b|\boddzial\b|\bdelegatura\b|\bdzielnica\b",
    r"\bodbor\b|\boddeleni\b|\bpobocka\b|\bmestsky obvod\b|\bmestska cast\b",
    r"\bavdeling\b|\bavdelning\b|\bforvaltning\b|\bosasto\b|\bdivisjon\b|\benhed\b",
    r"\bdepartment\b|\bdirectorate\b|\bdivision\b|\boffice of\b",
    r"териториално поделение|\bтп\b|дирекция|филиал|\bотдел\b|διευθυνση|τμημα|περιφερειακη ενοτητα",
)))

# a name that says public authority (the classes of `buyer_vocab.buyer_class_of` cover towns,
# regions, hospitals, schools, police, ministries of the interior and justice, armed forces)
PUBLIC_NAME = re.compile("|".join((
    r"minist|министерств|υπουργ|\bgobierno\b|\bgovern|regierung|\bsenat|\bjunta\b",
    r"\bagenzia\b|\bagencia\b|\bagence\b|\bagentia\b|\bagency\b|\bagentur\b|\bagencja\b|агенци",
    r"\bcommunaute\b|\bagglo|intercommunal|\bsyndicat mixte\b|\bcias\b|\bparc naturel\b",
    r"landratsamt|\w+kreis\b|\bstad\b|\bstads|^region\b|etaten\b|verket\b|direktorat|styrelsen\b",
    r"myndighet|virasto\b|\blaitos\b|\buniversit|\bhogeschool\b|\bdiensten\b|\bassociatie\b",
    r"\bdepartement\b|landesbetrieb|landesbehorde|\blra\b|\breditelstvi\b",
    r"bundesamt|landesamt|landesverwaltung|\bamt der\b|\bland \w+$|\bfreistaat\b|\bfreie hansestadt\b",
    r"\badministracion\b|\badministration\b|\bamministrazione\b|\badministracao\b",
    r"\brijks|\bstatens\b|staatsbetrieb|\bstaat\b|\bstato\b|\bestado\b|\betat\b|\brepublik|\brepublic",
    r"\bskarb panstwa\b|\burzad\b|\burad\b|\bstatni\b|\bdrzavn|\bдържавн|\bdirectoratul\b",
    r"\bprefecture\b|\bprefettura\b|\bservicio (?:andaluz|vasco|canario|navarro|madrileno)\b",
)))

# legal forms of public bodies (the `legal_form` column, or written into the name)
PUBLIC_FORM = re.compile("|".join((
    r"anstalt des offentlichen rechts|korperschaft des offentlichen rechts|\baor\b|\bkdor\b",
    r"etablissement public|\bepic\b|\bepa\b|ente pubblico|organismo autonomo|entidad publica",
    r"\be p e\b|\bepe\b|statni organizace|prispevkova organizace|public body|public authority",
)))

_PUBLIC_CLASSES = frozenset({
    # `infrastructure` too: road, rail, port and utility operators are contracting entities that buy
    # by region and department under the one number of the operator (ASFINAG: 78 rows in the batch)
    "defence", "security", "municipal", "international", "fire_rescue", "education", "health",
    "infrastructure",
})


def is_sub_unit(name: str | None) -> bool:
    return bool(name and SUB_UNIT.search(name))


def is_public_body(name: str | None, country: str | None = None, *, legal_form: str | None = None,
                   org_role: str | None = None, defence_buyer: bool = False) -> bool:
    """A public authority or a unit of one, by its flags, its legal form or its name.
    ponytail: a vocabulary, not a register; a company whose name says 'pharma' or 'agency' is
    held as public too, which only means it waits for a person instead of being merged."""
    if defence_buyer or (org_role or "").lower() == "buyer":
        return True
    if legal_form and PUBLIC_FORM.search(legal_form.lower()):
        return True
    n = (name or "").strip()
    if not n:
        return False
    return bool(SUB_UNIT.search(n) or PUBLIC_NAME.search(n) or PUBLIC_FORM.search(n)
                or buyer_class_of(n, country) in _PUBLIC_CLASSES)
