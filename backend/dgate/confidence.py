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

WP-95 (persona round of 23 October 2026, A1.4): "Probably defence" stood on 84 % of the list,
on refuse collection, bed linen and air conditioning bought by defence buyers, and "Clearly
defence" on a gatehouse repair whose long list of repair codes held one military-vehicle code.
So `high` now needs the military code to be the notice's MAIN code (its first CPV code), with a
listed defence buyer or the directive beside it, or the directive used by a listed defence buyer
(a ministry buying pyrotechnics under 2009/81/EC with a chemical code); the directive with a main military
code counts as corroboration only from a body that is not of a civil or security class. And each level is said by
what it rests on, not as a probability (`label`): "Clearly defence"; "Defence buyer, ordinary
purchase" (no military code), "Defence buyer, some military codes" (one, not the main code),
"Defence directive, unlisted buyer"; "Weak defence signal".
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
MILITARY_NOT_MAIN = "Military product code, not the main code"
DEFENCE_BUYER = "Defence buyer"
NOT_LISTED = "Buyer is not on the defence list"


def confidence(*, legal_basis: bool, military_cpv: bool, buyer: bool,
               linked_defence: bool = False, dual_use: bool = False,
               buyer_class: str | None = None, main_military: bool | None = None) -> tuple[str, list[str]]:
    """(level, basis): the level and the plain-word signals behind it, in the order a reader
    weighs them. Inputs are the stored signal columns and (WP-95) whether the notice's main CPV
    code is a military one (`main_military`; None: taken to be, for a caller that does not know)."""
    main = military_cpv if main_military is None else (military_cpv and main_military)
    code = MILITARY_CODE if main else MILITARY_NOT_MAIN
    corroborated = buyer or (legal_basis and buyer_class in (None, *_DEFENCE_OR_UNKNOWN))
    if not dual_use and ((main and corroborated) or (legal_basis and buyer)):
        return HIGH, ([DIRECTIVE] * legal_basis + [code] * military_cpv + [DEFENCE_BUYER] * buyer
                      + ([NOT_LISTED] if not buyer else []))
    if buyer:
        return MEDIUM, [DIRECTIVE] * legal_basis + (
            [code, DEFENCE_BUYER] if military_cpv else [DEFENCE_BUYER, "No military product code in the notice"])
    if legal_basis and military_cpv and buyer_class in (None, *_DEFENCE_OR_UNKNOWN):
        return MEDIUM, [DIRECTIVE, code, NOT_LISTED]
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


def label(level: str, *, buyer: bool, military_cpv: bool) -> str:
    """WP-95: the level in words, by what it rests on (never a probability word)."""
    if level == HIGH:
        return "Clearly defence"
    if level == MEDIUM:
        if buyer:
            return "Defence buyer, some military codes" if military_cpv else "Defence buyer, ordinary purchase"
        return "Defence directive, unlisted buyer"
    return "Weak defence signal"


def main_is_military(codes: list[str] | None) -> bool:
    """Whether the notice's main CPV code (its first) is one `classify` reads as military."""
    from .classify import military_cpv_codes

    first = next((c.strip() for c in codes or [] if c and c.strip()), None)
    return bool(first and military_cpv_codes([first]))


def confidence_of_row(r: dict[str, Any]) -> dict[str, Any]:
    """The API's `confidence` object for one stored tender row."""
    military = bool(r.get("sig_cpv_military"))
    level, basis = confidence(
        legal_basis=bool(r.get("sig_legal_basis")), military_cpv=military,
        buyer=bool(r.get("sig_buyer")), linked_defence=bool(r.get("sig_linked_defence")),
        dual_use=bool(r.get("dual_use")), buyer_class=r.get("buyer_class"),
        main_military=main_is_military(r.get("cpv_codes")))
    return {"level": level, "basis": basis,
            "label": label(level, buyer=bool(r.get("sig_buyer")), military_cpv=military)}


def _main_military_sql() -> str:
    """The SQL twin of `main_is_military` over `o.cpv_codes[1]` (classify's military groups and added codes)."""
    from .classify import CPV_CIVIL_EXCEPTIONS, CPV_MILITARY_ADJACENT

    added = ", ".join(f"'{c}'" for c in sorted(CPV_MILITARY_ADJACENT))
    civil = ", ".join(f"'{c}'" for c in sorted(CPV_CIVIL_EXCEPTIONS))
    return (f"(o.cpv_codes[1] IN ({added}) OR (o.cpv_codes[1] ~ '^35[3-8]' AND o.cpv_codes[1] NOT IN ({civil})))")


_MAIN = f"COALESCE(o.sig_cpv_military AND {_main_military_sql()}, FALSE)"
_HIGH = (f"(NOT COALESCE(o.dual_use, FALSE) AND (({_MAIN} AND (o.sig_buyer OR (o.sig_legal_basis"
         " AND (o.buyer_class IS NULL OR o.buyer_class IN ('defence', 'other'))))) OR (o.sig_legal_basis AND o.sig_buyer)))")
_MEDIUM = ("(o.sig_buyer OR (o.sig_legal_basis AND o.sig_cpv_military"
           " AND (o.buyer_class IS NULL OR o.buyer_class IN ('defence', 'other'))))")
# The SQL of each level over `opportunity o`, written so that the three partition every row.
CONFIDENCE_SQL = {
    HIGH: _HIGH,
    MEDIUM: f"(NOT {_HIGH} AND {_MEDIUM})",
    LOW: f"(NOT {_HIGH} AND NOT {_MEDIUM})",
}
