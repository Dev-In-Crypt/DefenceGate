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


@dataclass
class DefenceSignals:
    """Result of classification. Every signal is retained, not just the verdict."""

    legal_basis: bool = False
    cpv_military: bool = False
    cpv_civil_security: bool = False
    cpv_dual_use: bool = False
    buyer: bool = False
    clearance: bool = False
    matched_cpv: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def cpv(self) -> bool:
        return self.cpv_military or self.cpv_civil_security

    @property
    def is_defence(self) -> bool:
        """Verdict.

        Strong signals stand alone. Weak signals need a partner. Dual-use CPV
        is never sufficient by itself, or the feed fills with IT contracts.
        """
        if self.legal_basis or self.cpv_military or self.clearance:
            return True
        if self.buyer and (self.cpv or self.cpv_dual_use):
            return True
        if self.buyer:
            # A defence ministry buying anything is worth surfacing to a
            # supplier trying to get into that ministry's supply chain.
            return True
        if self.cpv_civil_security and self.clearance:
            return True
        return False

    @property
    def confidence(self) -> float:
        if self.legal_basis and self.cpv_military:
            return 1.00
        if self.legal_basis or self.cpv_military:
            return 0.90
        if self.clearance:
            return 0.85
        if self.buyer and self.cpv:
            return 0.80
        if self.buyer:
            return 0.60
        if self.cpv_civil_security:
            return 0.40
        return 0.10


def classify(
    *,
    legal_basis: str | None,
    cpv_codes: list[str] | None,
    buyer_is_defence: bool,
    security_clearance_text: str | None = None,
    nda_required: bool = False,
) -> DefenceSignals:
    """Classify one notice.

    Args map onto TED fields as follows:
      legal_basis             BT-01-notice
      cpv_codes               BT-262 / BT-263 (classification-cpv)
      security_clearance_text BT-732-Lot
      nda_required            BT-801-Lot
      buyer_is_defence        from our curated defence buyer list
    """
    sig = DefenceSignals()
    codes = [c.strip() for c in (cpv_codes or []) if c and c.strip()]

    if legal_basis and _LEGAL_BASIS_DEFENCE.search(legal_basis):
        sig.legal_basis = True
        sig.reasons.append("legal basis is Directive 2009/81/EC")

    for code in codes:
        div, grp = cpv_division(code), cpv_group(code)
        if div == CPV_DEFENCE_DIVISION:
            sig.matched_cpv.append(code)
            if grp in CPV_MILITARY_GROUPS:
                sig.cpv_military = True
            elif grp in CPV_CIVIL_GROUPS:
                sig.cpv_civil_security = True
            else:
                # 35000000 itself, or an unrecognised group inside 35
                sig.cpv_civil_security = True
        elif div in CPV_DUAL_USE_DIVISIONS:
            sig.cpv_dual_use = True

    if sig.cpv_military:
        sig.reasons.append(f"military CPV: {', '.join(sorted(set(sig.matched_cpv)))}")
    elif sig.cpv_civil_security:
        sig.reasons.append(f"security CPV: {', '.join(sorted(set(sig.matched_cpv)))}")

    if buyer_is_defence:
        sig.buyer = True
        sig.reasons.append("buyer is on the defence buyer list")

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
