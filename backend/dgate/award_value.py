"""What kind of amount an award value is (WP-95, persona round of 23 October 2026, finding A1.1).

A notice's figure is one of three things, and only the first is money a supplier won:

    contract   the value of the contract awarded (a call-off under a framework is a contract)
    framework  the ceiling (maximum or estimated total) of a framework agreement or dynamic purchasing system:
               what may be called off over years, not what was bought
    estimate   the buyer's estimate of the procedure, stated where the award states no value

Sums of a supplier count contract values only; framework ceilings and estimates are listed apart, never added to
them (`suppliers.value_totals`). A framework and its call-offs are never counted twice: the framework's ceiling is
not a contract value, its call-offs are.

TED. The search API's `total-value` is not one field: measured on the persona audit's notices, it is the notice value
(BT-161) on 808800-2025, the framework maximum (BT-118) on 390572-2026 (EUR 11,930,000; the tenders were 318,900) and
854350-2025 (DKK 97,000,000), and the procedure's estimate (BT-27) on 712069-2026, whose award states no value (-1).
So the award loader asks for the eForms fields themselves (`TED_VALUE_FIELDS`, field names as the API answered them
that day) and `ted_value` reads them: a framework maximum makes the value a ceiling, a notice value or the winning
tenders' values a contract value, and an eForms award that states them only as placeholders (-1) has only an estimate. A notice in the
older (pre-eForms) format has none of these fields: its `total-value` is the awarded total (`sources/ted.py`), a
contract value, unless the title says framework (`kind_of_title`).

PLACSP. The awarded amount (`importe de adjudicación`) of a folder that establishes a framework agreement (acuerdo
marco) or a dynamic purchasing system is its ceiling; a contract based on one (contrato basado, CB en AM) is a
contract. `cbc:ContractingSystemCode` says which where the entry carries it (`placsp_kind`); otherwise the title
(`kind_of_title`). A call-off whose title states its framework's file number ("1º CB AM (2025/AR43U/00001894)") is
linked to that framework's notice (`framework_refs`).
"""

from __future__ import annotations

import re
from typing import Any

CONTRACT, FRAMEWORK, ESTIMATE = "contract", "framework", "estimate"
KINDS = (CONTRACT, FRAMEWORK, ESTIMATE)

# eForms fields read with the winners (all accepted by the TED search API, persona audit p10, 23 October 2026):
#   BT-161-NoticeResult  notice value: the contracts awarded
#   BT-118-NoticeResult  notice framework value: the maximum of the framework agreements
#   BT-709-LotResult     framework maximum value per lot
#   BT-720-Tender        tender value, per winning tender
# and the currencies the daily pull already reads.
# WP-103: and the same fields under TED's own names, which the persona audit of 24 October read on the notices the site had
# wrong (p10 ted-verify.json): `framework-maximum-value-lot` (BT-709) on STRABAG 638010-2024 (EUR 280,000,000) and Arquus
# 38915-2026 (EUR 2,449,392,735, equal to its result value), `tender-value` (BT-720). Both spellings are read alike.
TED_VALUE_FIELDS = ["BT-161-NoticeResult", "BT-118-NoticeResult", "BT-709-LotResult", "BT-720-Tender",
                    "framework-maximum-value-lot", "tender-value",
                    "total-value-cur", "result-value-cur-notice", "estimated-value-cur-proc"]
_EFORMS_VALUE_KEYS = ("BT-161-NoticeResult", "BT-118-NoticeResult", "BT-709-LotResult", "BT-720-Tender",
                      "framework-maximum-value-lot", "tender-value")
# A notice's figure of a billion or more that its own estimate puts a hundred times lower was entered in the wrong unit
# (the mapper's rule for the notice value, `normalise._CONTRADICTED_*`): World Aviation 220199-2026 states a result of EUR
# 7,274,615,930 for one lot estimated at EUR 7,317,073.17, which topped the whole EUR ranking of suppliers (persona p10).
CONTRADICTED_FROM = 1e9
CONTRADICTED_RATIO = 100

# Whole words of a title that make it a call-off, or a framework / dynamic purchasing system (EU languages the
# archive holds most). The call-off words are tested first: "CB en AM" and "contratos basados en acuerdo marco"
# name a framework too.
# ponytail: a title rule, the fallback where the source states no structured field; it misses a framework whose
# title does not say so (390572-2026), which only the eForms fields catch.
_CALL_OFF = re.compile(
    r"contratos?\s+basados?|basad[oa]s?\s+en\s+(?:el\s+|un\s+)?(?:acuerdo\s+marco|a\.?\s?m\.?(?![a-z]))"
    r"|(?<![a-z])c\.?\s?b\.?\s+(?:en\s+|del?\s+)?a\.?\s?m(?![a-z])|(?<![a-z])cbam(?![a-z])|derivad[oa]s?\s+del?\s+acuerdo\s+marco"
    r"|call[- ]offs?(?![a-z])|mini[- ]competition|contratt[oi]\s+attuativ|appalt[oi]\s+specific|march[ée]s?\s+subs[ée]quent"
    r"|umow[ay]\s+wykonawcz|zam[óo]wieni[ea]\s+wykonawcz|nadere\s+overeenkomst|einzelabruf|abrufauftrag",
    re.IGNORECASE)
# WP-103 (persona p07, Indra): Spanish call-off titles write the "CB" (contrato basado) or "basado" apart from the "AM"
# (acuerdo marco) they name: "CB Cuarto AM 2024/...", "20º CB en el AM 1640/22", "5º Basado AM 202340A1", "CB Nº2 Acuerdo
# Marco", "Basado acuerdo marco exp. ...", "CB EN 24_AM 1388", "Quinto CD AM" (contrato derivado). The two words anywhere
# in one title make it a call-off.
_CALL_OFF_WORD = re.compile(r"(?<![a-z0-9])c\.?\s?[bd]\.?(?![a-z])|(?<![a-z])(?:basad|derivad)[oa]s?(?![a-z])",
                            re.IGNORECASE)
_FRAMEWORK_WORD = re.compile(r"(?<![a-z])a\.?\s?m(?![a-z])|acuerdos?\s+marco", re.IGNORECASE)
_FRAMEWORK = re.compile(
    r"framework|acuerdos?\s+marco|(?<![a-z])a\.?\s?m\.?\s+\d|accord[oi]\s+quadro|accords?[- ]cadres?|rahmenvertr[aä]g"
    r"|rahmenvereinba\w*|raamovereenkomst|raamcontract|rammeaftale|rammeavtale|ramavtal|puitesopimus|puitej[aä]rjestely"
    r"|umow[ay]\s+ramow|r[aá]mcov[aá]\s+(?:dohoda|zmluva|smlouva)|keretmeg[aá]llapod|acordo[- ]quadro|acord[- ]cadru"
    r"|okvirn\w*\s+sporazum|raamleping|dynamic\s+purchasing|sistema\s+din[aá]mico\s+de\s+adquisici|dynamisches\s+beschaffungssystem"
    r"|syst[eè]me\s+d.acquisition\s+dynamique|(?<![a-z])dps(?![a-z])",
    re.IGNORECASE)


def kind_of_title(*titles: str | None) -> str | None:
    """CONTRACT for a call-off, FRAMEWORK for a framework or dynamic purchasing system, None when no title says."""
    text = " ".join(t for t in titles if t)
    if not text:
        return None
    if _CALL_OFF.search(text) or (_CALL_OFF_WORD.search(text) and _FRAMEWORK_WORD.search(text)):
        return CONTRACT
    if _FRAMEWORK.search(text):
        return FRAMEWORK
    return None


# CODICE `cac:TenderingProcess/cbc:ContractingSystemCode` (PLACSP syndication specification, list
# ContractingSystemTypeCode): 0 not applicable, 1 a framework agreement is established, 2 a dynamic purchasing
# system is established, 3 a contract based on a framework agreement, 4 a contract based on a dynamic purchasing
# system. ponytail: read from the specification, not yet seen in a landed payload (none carried the field before
# WP-95); `python -m dgate.ops.award_values` reports the codes it meets, and an unknown one falls back to the title.
PLACSP_SYSTEM = {"1": FRAMEWORK, "2": FRAMEWORK, "3": CONTRACT, "4": CONTRACT, "0": CONTRACT}


def placsp_kind(system_code: str | None, *titles: str | None) -> str:
    """The kind of a PLACSP awarded amount: the contracting system where stated, else the title, else a contract."""
    code = (system_code or "").strip()
    if code in PLACSP_SYSTEM and code != "0":
        return PLACSP_SYSTEM[code]
    return kind_of_title(*titles) or CONTRACT


# A PLACSP file number as titles quote it: 2025/AR43U/00001894 (the folder id adds a final letter, 00001894E).
_FILE_NUMBER = re.compile(r"(?<![\w/])(\d{4}/[A-Z0-9]{2,15}/\d{6,10})([A-Z])?(?![\w/])")


def framework_refs(title: str | None) -> list[str]:
    """The folder ids a call-off's title may name its framework by: each quoted file number as written and with the
    final letter PLACSP adds. Only for a title that reads as a call-off."""
    if not title or not _CALL_OFF.search(title):
        return []
    out: list[str] = []
    for m in _FILE_NUMBER.finditer(title):
        base = m.group(1)
        out += [base + (m.group(2) or ""), base + "E", base]
    return list(dict.fromkeys(out))


def _amount(value: Any) -> float | None:
    v = value[0] if isinstance(value, list) and value else value
    if v in (None, "", []):
        return None
    try:
        return float(str(v).replace(",", "").replace(" ", ""))
    except ValueError:
        return None


def _amounts(value: Any) -> list[float]:
    items = value if isinstance(value, list) else [value]
    return [a for a in (_amount(x) for x in items) if a is not None]


def _usable(a: float | None) -> bool:
    from .normalise import _IMPLAUSIBLE_AMOUNT_FROM, PLACEHOLDER_AMOUNT_MAX
    return a is not None and PLACEHOLDER_AMOUNT_MAX < a < _IMPLAUSIBLE_AMOUNT_FROM


def _currency(value: Any) -> str | None:
    v = value[0] if isinstance(value, list) and value else value
    v = str(v or "").strip().upper()
    return v[:3] if len(v) >= 3 and v[:3].isalpha() else None


def contradicted(amount: float | None, opp: dict[str, Any]) -> bool:
    """WP-103: whether `amount` is a figure in the wrong unit: a billion or more, and over CONTRADICTED_RATIO times the
    notice's own estimate (the serving row's value where the mapper read an estimate or a sum of lot estimates)."""
    if amount is None or amount < CONTRADICTED_FROM or opp.get("value_kind") not in ("estimated", "lot_sum"):
        return False
    stored = float(opp["value_amount"]) if opp.get("value_amount") is not None else None
    return _usable(stored) and amount > CONTRADICTED_RATIO * stored


# WP-108 (persona round 4, p10 and p02): the same wrong-unit entry where the notice states no estimate. A figure is checked
# against what the notice's own parts sum to (its lots' framework maxima, its winning tenders' values) and against the
# value the procedure's other notices state (`procedure_value`, `awards.VALUE_COLUMNS`: the largest estimate of another
# notice of the same eForms procedure, in the same currency). FASER 394720-2025 states PLN 7,247,040,000 for four tenders
# summing to PLN 7,247,040; Imprensa Nacional Casa da Moeda 499753-2026 EUR 1,159,000,000 for a procedure estimated at
# EUR 1,450,000.
SET_ASIDE_ESTIMATE, SET_ASIDE_LOTS, SET_ASIDE_PROCEDURE = "estimate", "lots", "procedure"
SET_ASIDE_REASONS = (SET_ASIDE_ESTIMATE, SET_ASIDE_LOTS, SET_ASIDE_PROCEDURE)

# WP-126: a PLACSP awarded amount above the placeholder and under EUR 100 is a unit price (a pair of shoes EUR 84.95, a
# jacket 61.90, a magazine 28.00 of "un mínimo de 2000 cargadores" estimated at 68,000, a menu, an hour of maintenance),
# not a contract total: production of 25 October 2026 held 431 contract + 25 framework rows so, 411 and 25 of them with
# an estimate over a hundred times the amount. It is set aside per award row (`award.value_set_aside`, reason
# `unit_price`), in no sum. Between 100 and 1,000 the amounts are mixed (128 of 351 contract rows that far below the
# estimate; a Spanish contract of EUR 300 is real, owner 23 Oct): they stand.
# ponytail: the limit is checked on a winner's summed amount, so unit prices of several lots summing to 100 or more stand.
PLACSP_UNIT_PRICE_MAX = 100.0
SET_ASIDE_UNIT_PRICE = "unit_price"


def placsp_unit_price(amount: float | None) -> bool:
    """WP-126: whether a PLACSP awarded amount is a unit price (over the placeholder, under PLACSP_UNIT_PRICE_MAX)."""
    from .normalise import PLACEHOLDER_AMOUNT_MAX
    return amount is not None and PLACEHOLDER_AMOUNT_MAX < amount < PLACSP_UNIT_PRICE_MAX
# A clean unit error from a million (the amount typed in thousands: 107790-2025 states EUR 690,000,000 for a procedure of
# EUR 690,000; or the cents read as units), and against the procedure also over CONTRADICTED_RATIO times it from a billion
# (WP-119; it was from ten million, which set aside plausible totals for absurd lot sums and one odd estimate).
# ponytail: the floors are in the notice's own currency, so HUF and CZK figures reach them sooner.
THOUSANDFOLD_FROM = 1e6


def unit_error_of(amount: float | None, other: float | None) -> bool:
    """WP-119: whether `amount` is `other` typed in the wrong unit, digit for digit, from THOUSANDFOLD_FROM: a thousand
    times it (typed in thousands: FASER 394720-2025, PLN 7,247,040,000 for tenders of 7,247,040), or a hundred times it
    with the cents read as units (313429-2026, PLN 741,576,016.16 for 7,415,760.16; 142545-2026, PLN 120,969,785 for a
    lot of 1,209,697). A round hundredfold (5,000,000 against 50,000) is no such slip and stands."""
    if amount is None or amount < THOUSANDFOLD_FROM or not _usable(other):
        return False
    if abs(amount / 1000 - other) < 0.01:
        return True
    return amount % 100 != 0 and abs(amount / 100 - other) < 1


def implausible_against(amount: float | None, other: float | None) -> bool:
    """WP-108: whether `amount` is a wrong-unit entry measured against `other`, a smaller figure of the same procedure:
    a clean unit error of it (`unit_error_of`), or (WP-119) a billion or more (CONTRADICTED_FROM) and over
    CONTRADICTED_RATIO times it (INCM 499753-2026, EUR 1,159,000,000 for a procedure estimated at 1,450,000).
    WP-119: below a billion a hundredfold gap is no proof: 451107-2025 states a framework of EUR 22,922,861 whose 2023
    contract notice estimated EUR 23,918.70 (x958), and the estimate, not the framework, was the odd figure."""
    if amount is None or not _usable(other):
        return False
    if amount >= CONTRADICTED_FROM and amount > CONTRADICTED_RATIO * other:
        return True
    return unit_error_of(amount, other)


def procedure_set_aside(amount: float | None, opp: dict[str, Any], cur: str | None = None) -> tuple[float, str] | None:
    """WP-108: (the procedure's estimate, its currency) when `amount` is implausible against it; None otherwise."""
    other = float(opp["procedure_value"]) if opp.get("procedure_value") is not None else None
    cur = cur or _currency(opp.get("value_currency"))
    if cur and implausible_against(amount, other):
        return round(other, 2), cur
    return None


def ted_value(rec: dict[str, Any] | None, opp: dict[str, Any]) -> tuple[float | None, str | None, str | None]:
    """(amount, currency, kind) of a TED result notice from its award record `rec` (with `TED_VALUE_FIELDS`, or None)
    and its serving row `opp` (value_amount, value_currency, value_kind, notice_subtype, title_original, title_en; WP-108
    procedure_value). A record that states one of the eForms value fields decides; one that states none (an older-format
    notice, a record fetched before WP-95, an eForms notice TED answers without them) leaves the stored value as the
    mapper chose it: a total is a contract value unless the title says framework, a sum of lot estimates an estimate.
    WP-103: a figure the notice's own estimate contradicts (`contradicted`) is set aside (`ted_value_set_aside`) and
    the estimate stands, as an estimate. WP-108: a figure implausible against the sum of the notice's own lot or tender
    values (`implausible_against`) is set aside and that sum stands, of the same kind; one implausible against the
    procedure's value is set aside and the procedure's estimate stands, as an estimate. `ted_value_set_aside_reason`
    says which (`SET_ASIDE_REASONS`).
    ponytail: an eForms notice whose framework maximum TED leaves out is then read as a contract value."""
    return _ted_value(rec, opp)[:3]


def ted_value_set_aside(rec: dict[str, Any] | None, opp: dict[str, Any]) -> float | None:
    """WP-103: the figure `ted_value` set aside as implausible, or None."""
    return _ted_value(rec, opp)[3]


def ted_value_set_aside_reason(rec: dict[str, Any] | None, opp: dict[str, Any]) -> str | None:
    """WP-108: why `ted_value` set its figure aside (`SET_ASIDE_REASONS`), or None."""
    return _ted_value(rec, opp)[4]


def _checked(amount: float, cur: str | None, kind: str, parts: float | None, opp: dict[str, Any], estimate: tuple) -> tuple:
    """(amount, currency, kind, set aside, reason) of a candidate figure: the figure itself, or, set aside, the estimate
    (WP-103), the sum of its parts or the procedure's estimate (WP-108)."""
    if contradicted(amount, opp):
        return (*estimate, round(amount, 2), SET_ASIDE_ESTIMATE)
    # WP-119: the sum of the lots replaces the total only when the total is a clean unit error of it; a lot sum of a few
    # units is a placeholder, not a value (Marine Alutech 676175-2026: EUR 2 for a total of 76,000,000)
    if unit_error_of(amount, parts):
        return round(parts, 2), cur, kind, round(amount, 2), SET_ASIDE_LOTS
    proc = procedure_set_aside(amount, opp, cur)
    if proc:
        return *proc, ESTIMATE, round(amount, 2), SET_ASIDE_PROCEDURE
    return round(amount, 2), cur, kind, None, None


def _ted_value(rec: dict[str, Any] | None, opp: dict[str, Any]) -> tuple:
    rec = rec or {}
    cur = (_currency(rec.get("total-value-cur")) or _currency(rec.get("result-value-cur-notice"))
           or _currency(rec.get("estimated-value-cur-proc")) or _currency(opp.get("value_currency")))
    stored = float(opp["value_amount"]) if opp.get("value_amount") is not None else None
    if any(k in rec for k in _EFORMS_VALUE_KEYS):
        estimate = (stored, cur, ESTIMATE) if _usable(stored) and cur else (None, None, None)
        lots = [a for a in _amounts(rec.get("BT-709-LotResult")) or _amounts(rec.get("framework-maximum-value-lot"))
                if _usable(a)]
        lot_sum = sum(lots) if lots else None
        frame = _amount(rec.get("BT-118-NoticeResult"))
        frame_parts = lot_sum if _usable(frame) else None       # the notice's maximum against its lots' maxima
        if not _usable(frame):
            frame = lot_sum
        notice = _amount(rec.get("BT-161-NoticeResult"))
        tenders = [a for a in _amounts(rec.get("BT-720-Tender")) or _amounts(rec.get("tender-value")) if _usable(a)]
        tender_sum = sum(tenders) if tenders else None
        for amount, kind, parts in ((frame, FRAMEWORK, frame_parts), (notice, CONTRACT, tender_sum),
                                    (tender_sum, CONTRACT, None)):
            if not _usable(amount):
                continue
            out = _checked(amount, cur, kind, parts, opp, estimate)
            if out[3] is None and parts is None and opp.get("value_kind") == "total" and _usable(stored):
                if unit_error_of(stored, amount):
                    # WP-108: the value read from the parts stands, and the notice's own total, a wrong-unit entry of
                    # their sum (FASER 394720-2025 when TED answers its tenders and no notice value), is said and not used
                    return (*out[:3], round(stored, 2), SET_ASIDE_LOTS)
                if stored > CONTRADICTED_RATIO * amount:
                    # WP-119: parts that sum to a placeholder against the notice's own total (Marine Alutech 676175-2026:
                    # EUR 2 for 76,000,000; Surcom 436610-2026: SEK 13 for 13,107,317) are no value: the total stands
                    return _checked(stored, cur, kind, None, opp, estimate)
            return out
        # the award states its values as placeholders (712069-2026: -1): what TED filled `total-value` with is the
        # procedure's estimate
        return (*estimate, None, None)
    # no eForms value field: the stored value as the mapper chose it
    if not _usable(stored) or not cur:
        return None, None, None, None, None
    kind = opp.get("value_kind")
    if kind == "total":
        title_kind = kind_of_title(opp.get("title_original"), opp.get("title_en")) or CONTRACT
        return _checked(stored, cur, title_kind, None, opp, (None, None, None))
    if kind in ("lot_sum", "estimated"):
        return stored, cur, ESTIMATE, None, None
    return None, None, None, None, None
