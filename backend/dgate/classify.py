"""Defence classification.

Four independent signals, kept separate on purpose. Storing only the boolean
result would make the logic impossible to tune later, and this logic will need
tuning: the false-positive rate on CPV alone is high (every municipal fire
extinguisher purchase sits in division 35).

Nothing here calls an LLM. The classifier narrows the candidate set cheaply;
the LLM then runs only over what survives.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .buyer_vocab import DEMOTING_CLASSES

# --------------------------------------------------------------------- CPV

# Division 35: Security, fire-fighting, police and defence equipment.
# Legal basis: Regulation (EC) No 2195/2002, nomenclature per (EC) No 213/2008.
CPV_DEFENCE_DIVISION = "35"

# Groups within 35 that are unambiguously military. A hit here is strong.
CPV_MILITARY_GROUPS = {
    "353",  # Weapons, ammunition and associated parts
    "354",  # Military vehicles and associated parts
    "355",  # Warships and associated parts
    "356",  # Military aircraft, missiles and spacecraft
    "357",  # Military electronic systems
    "358",  # Individual and support equipment
}

# Groups within 35 that are mostly civil. A hit here alone is weak and needs
# corroboration from another signal.
CPV_CIVIL_GROUPS = {
    "351",  # Emergency and security equipment (incl. firefighting)
    "352",  # Police equipment
}

# Exceptions inside the otherwise military groups. Group 358 is individual and
# support equipment, and not all of it is military: class 3581 is uniforms, of
# which only 35811300 is military, and 35821000 is flags. Both were found in
# live feeds, the uniforms on TED and the flags on a Polish village school
# buying teaching aids, which the group alone put in a defence feed.
CPV_CIVIL_EXCEPTIONS = {
    "35811100",   # fire-brigade uniforms
    "35811200",   # police uniforms
    "35821000",   # flags
}

# Military-specific codes outside division 35. Each was read against the CPV list
# (CPV 2008, Regulation 213/2008) on 12 October 2026: 45216200 construction work
# for military buildings and installations; 50640000 repair and maintenance of
# warships; 75220000 defence services; 75221000 military defence services. Exact
# codes, not prefixes: 75222000 is civil defence services, and the parent
# division is not military. Counted as military CPVs, kept apart as a signal.
#
# Added 13 October 2026 after the verification round (classification:D9), each read
# against the eForms SDK codelist cpv.gc (Publications Office, CPV 2008):
#   50620000 repair and maintenance of firearms and ammunition
#   50630000 ... of military vehicles
#   50650000 ... of military aircrafts, missiles and spacecrafts
#   50660000 ... of military electronic systems
#   50840000 ... of weapons and weapon systems (50841000 weapons, 50842000 weapon systems)
#   80630000 / 80640000 / 80650000 training and simulation in military vehicles,
#   warships, aircrafts/missiles/spacecrafts.
# Left out on purpose: 50600000 and 80600000 (the parents: "security AND defence
# materials", which also covers alarms and cameras), 50610000 (security equipment:
# a civil market), 80610000 and 80620000 (training in security equipment and in
# firearms: police ranges) and 80660000 (military electronic systems training: not in
# the verifier's list; add with the same reading when it is).
CPV_ADJACENT_2026_10_12 = {"45216200", "50640000", "75220000", "75221000"}
CPV_ADJACENT_2026_10_13 = {
    "50620000", "50630000", "50650000", "50660000", "50840000", "50841000", "50842000",
    "80630000", "80640000", "80650000",
}
CPV_MILITARY_ADJACENT = CPV_ADJACENT_2026_10_12 | CPV_ADJACENT_2026_10_13

# Groups of division 35 where the code names equipment civil bodies buy as well:
# 356 (UAV and drones, "military" aircraft codes used for survey drones), 357 (command
# and control systems, radar: airports, meteorological and maritime authorities, road
# works that carry 35710000) and 358 (individual equipment: protective clothing, helmets
# and masks for a municipal works department). A notice whose military codes are all
# in these groups, from a body the vocabulary cannot name as defence, security, health,
# education and so on, is labelled dual-use like a municipality's (classification:D2,
# D4 of 13 October 2026; 24 of 30 read were not defence). Never applies with the legal
# basis, a listed buyer, or any other military group.
CPV_AMBIGUOUS_GROUPS = {"356", "357", "358"}

# The same rule in SQL, for the serving rows that predate the column
# (migration 0029); tests/unit/test_buyer_classes.py keeps the two in step.
MILITARY_CPV_SQL_REGEX = "^35[3-8]"

# Divisions outside 35 that carry dual-use work. Never sufficient alone.
CPV_DUAL_USE_DIVISIONS = {
    "34",  # Transport equipment
    "38",  # Laboratory, optical and precision instruments
    "48",  # Software packages and information systems
    "50",  # Repair and maintenance services
    "51",  # Installation services
    "71",  # Architectural and engineering services
    "73",  # R&D services
}

# ------------------------------------------------------------- legal basis

# BT-01-notice. Matching is loose because the field is not always a clean
# CELEX reference in practice.
_LEGAL_BASIS_DEFENCE = re.compile(
    r"(2009[/\-]81|32009L0081)", re.IGNORECASE
)


def cpv_division(code: str) -> str:
    return (code or "")[:2]


def cpv_group(code: str) -> str:
    return (code or "")[:3]


def military_cpv_codes(codes: list[str] | None) -> list[str]:
    """The codes of a notice that `classify` reads as military (a division-35 military
    group, or one of the added codes), in the notice's order and without repeats. What a
    page names when it says "military product code": the code that qualified, not the
    whole list."""
    out: list[str] = []
    for raw in codes or []:
        code = (raw or "").strip()
        if code in out:
            continue
        if code in CPV_MILITARY_ADJACENT or (
                cpv_division(code) == CPV_DEFENCE_DIVISION and code not in CPV_CIVIL_EXCEPTIONS
                and cpv_group(code) in CPV_MILITARY_GROUPS):
            out.append(code)
    return out


@dataclass
class DefenceSignals:
    """Result of classification. Every signal is retained, not just the verdict."""

    legal_basis: bool = False
    cpv_military: bool = False
    cpv_adjacent: bool = False
    cpv_civil_security: bool = False
    cpv_dual_use: bool = False
    buyer: bool = False
    clearance: bool = False
    # The TED notice a national defence notice was forwarded as. Set by the
    # caller, from the link the national source states.
    linked_defence: bool = False
    # What kind of body the buyer is (dgate/buyer_vocab.py); None = not asked.
    buyer_class: str | None = None
    # Every military CPV of the notice is in CPV_AMBIGUOUS_GROUPS (and none is one of
    # the added military codes outside division 35).
    cpv_ambiguous_only: bool = False
    matched_cpv: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def military_cpv(self) -> bool:
        """A division-35 military group, or one of the added military codes."""
        return self.cpv_military or self.cpv_adjacent

    @property
    def cpv(self) -> bool:
        return self.military_cpv or self.cpv_civil_security

    @property
    def dual_use(self) -> bool:
        """A military CPV that only its buyer's own needs explain.

        A municipality buying a military-CPV item (protective clothing, a flag
        mast, a lifeboat) is not a defence lead. Demoted unless the legal basis
        or a listed defence buyer agrees. The signal columns stay as they were;
        this is a label on top of them, and the notice stays in the table.
        """
        return (self.military_cpv and not self.legal_basis and not self.buyer
                and (self.buyer_class in DEMOTING_CLASSES
                     or (self.buyer_class == "other" and self.cpv_ambiguous_only)))

    @property
    def is_defence(self) -> bool:
        """Verdict.

        Strong signals stand alone: the defence directive as legal basis, and
        an unambiguously military CPV group. A military CPV demoted to
        dual-use still counts here -- it is labelled, not dropped -- and
        leaves the `core` scope instead (api.SCOPE_SQL).

        The clearance field is deliberately NOT a signal that decides, despite
        being documented as one. Checked against live TED notices, BT-732
        mostly carries something else entirely: the Russia sanctions
        declaration under Regulation (EU) 2022/576, which appears on ordinary
        contracts, and criminal-record checks for staff. One live sample
        flagged a cleaning contract (CPV 90911100) as defence on the strength
        of "extended police clearance certificates for the cleaning staff".
        Until 12 October 2026 clearance plus a civil security CPV qualified;
        316 such rows were read and none was relevant (fire engines, guard
        services). So clearance corroborates; it never decides.
        """
        if self.legal_basis or self.military_cpv:
            return True
        if self.buyer:
            # A defence ministry buying anything is worth surfacing to a
            # supplier trying to get into that ministry's supply chain.
            return True
        if self.linked_defence:
            return True
        return False

    @property
    def confidence(self) -> float:
        if self.legal_basis and self.military_cpv:
            return 1.00
        if self.legal_basis:
            return 0.90
        if self.military_cpv and not self.dual_use:
            return 0.90
        if self.buyer and self.cpv:
            return 0.80
        if self.dual_use:
            return 0.45
        if self.buyer:
            return 0.60
        if self.linked_defence:
            return 0.60
        if self.cpv_civil_security:
            return 0.40
        if self.clearance and self.cpv:
            return 0.35
        if self.clearance:
            # Recorded, but on its own it is as likely to be a sanctions clause
            # as a security requirement.
            return 0.30
        return 0.10


def classify(
    *,
    legal_basis: str | None,
    cpv_codes: list[str] | None,
    buyer_is_defence: bool,
    security_clearance_text: str | None = None,
    nda_required: bool = False,
    buyer_class: str | None = None,
    linked_defence: bool = False,
) -> DefenceSignals:
    """Classify one notice.

    Args map onto TED fields as follows:
      legal_basis             BT-01-notice
      cpv_codes               BT-262 / BT-263 (classification-cpv)
      security_clearance_text BT-732-Lot
      nda_required            BT-801-Lot
      buyer_is_defence        from our curated defence buyer list
      buyer_class             from the buyer's name (buyer_vocab.buyer_class_of)
      linked_defence          a defence notice of another source points at this one
    """
    sig = DefenceSignals(buyer_class=buyer_class, linked_defence=linked_defence)
    codes = [c.strip() for c in (cpv_codes or []) if c and c.strip()]

    if legal_basis and _LEGAL_BASIS_DEFENCE.search(legal_basis):
        sig.legal_basis = True
        sig.reasons.append("legal basis is Directive 2009/81/EC")

    military_groups: set[str] = set()
    for code in codes:
        div, grp = cpv_division(code), cpv_group(code)
        if code in CPV_MILITARY_ADJACENT:
            sig.matched_cpv.append(code)
            sig.cpv_adjacent = True
        elif div == CPV_DEFENCE_DIVISION:
            sig.matched_cpv.append(code)
            if code in CPV_CIVIL_EXCEPTIONS:
                sig.cpv_civil_security = True
            elif grp in CPV_MILITARY_GROUPS:
                sig.cpv_military = True
                military_groups.add(grp)
            elif grp in CPV_CIVIL_GROUPS:
                sig.cpv_civil_security = True
            else:
                # 35000000 itself, or an unrecognised group inside 35
                sig.cpv_civil_security = True
        elif div in CPV_DUAL_USE_DIVISIONS:
            sig.cpv_dual_use = True

    sig.cpv_ambiguous_only = (sig.cpv_military and not sig.cpv_adjacent
                              and military_groups <= CPV_AMBIGUOUS_GROUPS)

    if sig.military_cpv:
        sig.reasons.append(f"military CPV: {', '.join(sorted(set(sig.matched_cpv)))}")
        if sig.dual_use:
            sig.reasons.append(
                "demoted to dual-use: only CPV groups 356-358, bought by a body that is "
                "not on the defence list" if sig.buyer_class == "other"
                else f"demoted to dual-use: buyer is a {sig.buyer_class} body")
    elif sig.cpv_civil_security:
        sig.reasons.append(f"security CPV: {', '.join(sorted(set(sig.matched_cpv)))}")

    if buyer_is_defence:
        sig.buyer = True
        sig.reasons.append("buyer is on the defence buyer list")

    if linked_defence:
        sig.reasons.append("same procurement as a defence notice of another source")

    # BT-732 presence is itself the signal. We do not parse or store the
    # clearance description: it can name systems and programmes and is not
    # something this product needs to republish.
    if security_clearance_text and security_clearance_text.strip():
        sig.clearance = True
        sig.reasons.append("security clearance requirement stated (BT-732)")
    elif nda_required:
        sig.clearance = True
        sig.reasons.append("NDA required (BT-801)")

    return sig


# ------------------------------------------------- subcontracting detection

# Multilingual, because the whole point is that the other 93% is not in English.
_SUBCONTRACT_PATTERNS = [
    r"\bsub-?contract",           # en
    r"\bsubcontrat",              # fr
    r"\bsubcontrat[ao]",          # es/pt
    r"\bsubcontrataci[óo]n",      # es
    r"\bunterauftrag",            # de
    r"\bonderaanneming",          # nl
    r"\bpodwykonaw",              # pl
    r"\bsubcontractare",          # ro
    r"\bsubdodav",                # cs
    r"\bsubranga|\bsubrangov",    # lt
    r"\bapak[sš]uz[nņ]",          # lv
    r"\balltöövõt",               # et
]
_SUBCONTRACT_RE = re.compile("|".join(_SUBCONTRACT_PATTERNS), re.IGNORECASE)


def detects_subcontracting(*texts: str | None) -> bool:
    """Flag notices that mention subcontracting in any covered language.

    This is the single most commercially useful flag in the product: a tier-2
    supplier cannot win a prime contract, but can win a subcontract, and no
    generic tender feed surfaces this.
    """
    for t in texts:
        if t and _SUBCONTRACT_RE.search(t):
            return True
    return False
