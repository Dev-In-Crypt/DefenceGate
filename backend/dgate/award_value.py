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
TED_VALUE_FIELDS = ["BT-161-NoticeResult", "BT-118-NoticeResult", "BT-709-LotResult", "BT-720-Tender",
                    "total-value-cur", "result-value-cur-notice", "estimated-value-cur-proc"]
_EFORMS_VALUE_KEYS = ("BT-161-NoticeResult", "BT-118-NoticeResult", "BT-709-LotResult", "BT-720-Tender")

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
_FRAMEWORK = re.compile(
    r"framework|acuerdos?\s+marco|(?<![a-z])a\.?\s?m\.?\s+\d|accord[oi]\s+quadro|accords?[- ]cadres?|rahmenvertr[aä]g"
    r"|rahmenvereinbarung|raamovereenkomst|raamcontract|rammeaftale|rammeavtale|ramavtal|puitesopimus|puitej[aä]rjestely"
    r"|umow[ay]\s+ramow|r[aá]mcov[aá]\s+(?:dohoda|zmluva|smlouva)|keretmeg[aá]llapod|acordo[- ]quadro|acord[- ]cadru"
    r"|okvirn\w*\s+sporazum|raamleping|dynamic\s+purchasing|sistema\s+din[aá]mico\s+de\s+adquisici|dynamisches\s+beschaffungssystem"
    r"|syst[eè]me\s+d.acquisition\s+dynamique|(?<![a-z])dps(?![a-z])",
    re.IGNORECASE)


def kind_of_title(*titles: str | None) -> str | None:
    """CONTRACT for a call-off, FRAMEWORK for a framework or dynamic purchasing system, None when no title says."""
    text = " ".join(t for t in titles if t)
    if not text:
        return None
    if _CALL_OFF.search(text):
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


def ted_value(rec: dict[str, Any] | None, opp: dict[str, Any]) -> tuple[float | None, str | None, str | None]:
    """(amount, currency, kind) of a TED result notice from its award record `rec` (with `TED_VALUE_FIELDS`, or None)
    and its serving row `opp` (value_amount, value_currency, value_kind, notice_subtype, title_original, title_en).
    A record that states one of the eForms value fields decides; one that states none (an older-format notice, a
    record fetched before WP-95, an eForms notice TED answers without them) leaves the stored value as the mapper
    chose it: a total is a contract value unless the title says framework, a sum of lot estimates an estimate.
    ponytail: an eForms notice whose framework maximum TED leaves out is then read as a contract value."""
    rec = rec or {}
    cur = (_currency(rec.get("total-value-cur")) or _currency(rec.get("result-value-cur-notice"))
           or _currency(rec.get("estimated-value-cur-proc")) or _currency(opp.get("value_currency")))
    stored = float(opp["value_amount"]) if opp.get("value_amount") is not None else None
    if any(k in rec for k in _EFORMS_VALUE_KEYS):
        frame = _amount(rec.get("BT-118-NoticeResult"))
        if not _usable(frame):
            lots = [a for a in _amounts(rec.get("BT-709-LotResult")) if _usable(a)]
            frame = sum(lots) if lots else None
        if _usable(frame):
            return round(frame, 2), cur, FRAMEWORK
        notice = _amount(rec.get("BT-161-NoticeResult"))
        if _usable(notice):
            return round(notice, 2), cur, CONTRACT
        tenders = [a for a in _amounts(rec.get("BT-720-Tender")) if _usable(a)]
        if tenders:
            return round(sum(tenders), 2), cur, CONTRACT
        # the award states its values as placeholders (712069-2026: -1): what TED filled `total-value` with is the
        # procedure's estimate
        return (stored, cur, ESTIMATE) if _usable(stored) and cur else (None, None, None)
    # no eForms value field: the stored value as the mapper chose it
    if not _usable(stored) or not cur:
        return None, None, None
    kind = opp.get("value_kind")
    if kind == "total":
        return stored, cur, kind_of_title(opp.get("title_original"), opp.get("title_en")) or CONTRACT
    if kind in ("lot_sum", "estimated"):
        return stored, cur, ESTIMATE
    return None, None, None
