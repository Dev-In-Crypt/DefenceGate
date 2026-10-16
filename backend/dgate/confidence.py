"""How sure we are that a listed notice is defence procurement (WP-23, 16 October 2026).

Derived at read time from the signals the classifier stored (`classify.py`); nothing is
written, so a rule change needs no data migration. Three levels, each a statement about the
MEASURED precision of the notices that receive it (sample of 16 October 2026, the table and
the labelled notices are in docs/verification/ux/confidence-sample.md, the reasoning in
docs/design/CONFIDENCE.md):

  high    a military product code AND a listed defence buyer agree
          (sample: 96 % of the notices are themselves defence goods or services)
  medium  the buyer is a listed defence body, or the directive and a military code agree on
          a buyer that is not a security or civil body; the item is often ordinary
          (sample: 93 % are from or for a defence body, 11 % are defence-specific)
  low     everything else that is listed: one weak signal, or a signal from the wrong kind
          of buyer (sample: 21 % from or for a defence body, a third not defence at all)

The level never changes the `is_defence` verdict or the scope. `CONFIDENCE_SQL` is the SQL
twin of `confidence()` for the `confidence` filter; tests/unit/test_confidence.py and the
integration test keep the two in step.
"""

from __future__ import annotations

from typing import Any

HIGH, MEDIUM, LOW = "high", "medium", "low"
LEVELS = (HIGH, MEDIUM, LOW)

# Buyer classes (buyer_vocab.py) for which the directive plus a military code is still a
# defence notice: the sample held 12 of 13 such notices defence-specific. A security,
# health, education, municipal, infrastructure or international body is not (1 of 13).
_DEFENCE_OR_UNKNOWN = ("defence", "other")

_BODY_WORDS = {
    "defence": "Buyer looks like a defence body but is not on the defence list",
    "security": "Buyer is a police, prison, border, customs or tax body",
    "fire_rescue": "Buyer is a fire and rescue body",
    "health": "Buyer is a health body",
    "education": "Buyer is an education body",
    "municipal": "Buyer is a municipal body",
    "infrastructure": "Buyer is an infrastructure or utility body",
    "international": "Buyer is an international body",
}

DIRECTIVE = "Defence directive (2009/81/EC)"
MILITARY_CODE = "Military product code"
DEFENCE_BUYER = "Defence buyer"
NOT_LISTED = "Buyer is not on the defence list"


def confidence(*, legal_basis: bool, military_cpv: bool, buyer: bool,
               linked_defence: bool = False, dual_use: bool = False,
               buyer_class: str | None = None) -> tuple[str, list[str]]:
    """(level, basis): the level and the plain-word signals behind it, in the order a reader
    weighs them. Inputs are the stored signal columns."""
    if military_cpv and buyer:
        return HIGH, [DIRECTIVE] * legal_basis + [MILITARY_CODE, DEFENCE_BUYER]
    if buyer:
        return MEDIUM, [DIRECTIVE] * legal_basis + [DEFENCE_BUYER, "No military product code in the notice"]
    if legal_basis and military_cpv and buyer_class in (None, *_DEFENCE_OR_UNKNOWN):
        return MEDIUM, [DIRECTIVE, MILITARY_CODE, NOT_LISTED]
    basis: list[str] = []
    if legal_basis:
        basis.append(DIRECTIVE)
    if military_cpv:
        basis.append("Military product code, bought by a civil body" if dual_use else MILITARY_CODE)
    if linked_defence:
        basis.append("Same procurement as a defence notice of another source")
    if len(basis) == 1 and (legal_basis or military_cpv) and not dual_use:
        basis[0] += " only"
    basis.append(NOT_LISTED)
    if buyer_class in _BODY_WORDS:
        basis.append(_BODY_WORDS[buyer_class])
    return LOW, basis


def confidence_of_row(r: dict[str, Any]) -> dict[str, Any]:
    """The API's `confidence` object for one stored tender row."""
    level, basis = confidence(
        legal_basis=bool(r.get("sig_legal_basis")), military_cpv=bool(r.get("sig_cpv_military")),
        buyer=bool(r.get("sig_buyer")), linked_defence=bool(r.get("sig_linked_defence")),
        dual_use=bool(r.get("dual_use")), buyer_class=r.get("buyer_class"))
    return {"level": level, "basis": basis}


_HIGH = "(o.sig_cpv_military AND o.sig_buyer)"
_MEDIUM = ("(o.sig_buyer OR (o.sig_legal_basis AND o.sig_cpv_military"
           " AND (o.buyer_class IS NULL OR o.buyer_class IN ('defence', 'other'))))")
# The SQL of each level over `opportunity o`, written so that the three partition every row.
CONFIDENCE_SQL = {
    HIGH: _HIGH,
    MEDIUM: f"(NOT {_HIGH} AND {_MEDIUM})",
    LOW: f"(NOT {_MEDIUM})",
}
