"""An amount of one or less is a placeholder in every source, not only TED (correctness:D4
across sources): BOAMP held 0.01, 0.10 and 1.00 on six awards, PLACSP 0.00 on 45 entries.
"""

from __future__ import annotations

from datetime import date

import pytest

from dgate import db
from dgate.normalise import Opportunity, _fr_amount
from dgate.ops import remap_source
from dgate.sources import placsp

from .test_placsp import _page


@pytest.mark.parametrize("raw,expected", [
    ("0.01", None), ("0,10", None), ("1", None), ("1.00", None), ("1.01", 1.01), ("2", 2.0),
])
def test_boamp_does_not_read_a_placeholder_as_a_value(raw, expected):
    assert _fr_amount(raw) == expected


def _entry(budget: str) -> placsp.Opportunity:
    entry = (
        "<entry><id>x</id><title>t</title><updated>2026-10-11T19:54:50+02:00</updated>"
        "<cac-place-ext:ContractFolderStatus><cbc:ContractFolderID>F-1</cbc:ContractFolderID>"
        f"<cac:ProcurementProject><cbc:Name>t</cbc:Name><cac:BudgetAmount>{budget}"
        "</cac:BudgetAmount></cac:ProcurementProject></cac-place-ext:ContractFolderStatus></entry>")
    opps, _ = placsp.parse_feed(_page(entry, None))
    return opps[0]


def test_placsp_with_only_a_zero_budget_has_no_value():
    o = _entry('<cbc:EstimatedOverallContractAmount currencyID="EUR">0.00'
               '</cbc:EstimatedOverallContractAmount>')
    assert (o.value_amount, o.value_currency) == (None, None)


def test_placsp_zero_estimate_still_gives_way_to_the_budget():
    o = _entry('<cbc:EstimatedOverallContractAmount currencyID="EUR">0'
               '</cbc:EstimatedOverallContractAmount>'
               '<cbc:TotalAmount currencyID="EUR">8583.87</cbc:TotalAmount>')
    assert (o.value_amount, o.value_currency) == (8583.87, "EUR")


def stored(amount, source="fr_boamp"):
    return db.opportunity_payload(Opportunity(
        source_code=source, native_id="21-164596", buyer_name_raw="b", title_original="t",
        country="FR", published_at=date(2021, 9, 1), status="awarded", value_amount=amount,
        value_currency="EUR"))


def test_a_stored_placeholder_the_mapper_no_longer_offers_is_cleared():
    new = Opportunity(source_code="fr_boamp", native_id="21-164596", buyer_name_raw="b",
                      title_original="t", country="FR", published_at=date(2021, 9, 1),
                      status="awarded")
    change = remap_source.plan(stored(0.01), {}, new)
    assert {"value_amount", "value_currency"} <= set(change.changed)
    assert change.candidate.value_amount is None


def test_a_stored_real_amount_the_mapper_does_not_offer_is_kept():
    new = Opportunity(source_code="pl_ezam", native_id="21-164596", buyer_name_raw="b",
                      title_original="t", country="FR", published_at=date(2021, 9, 1),
                      status="awarded")
    change = remap_source.plan(stored(250000.0), {}, new)
    assert change.candidate.value_amount == 250000.0
    assert "value_amount" not in change.changed


def test_a_placsp_zero_is_cleared_from_the_stored_payload():
    payload = stored(0.0, source="es_placsp")
    new = remap_source.from_placsp_stored(payload)
    assert new.value_amount is None and new.value_currency is None
    change = remap_source.plan(payload, {}, new)
    assert "value_amount" in change.changed and change.candidate.value_amount is None
