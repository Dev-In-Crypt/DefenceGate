"""TED placeholder and implausible amounts are not served as money (correctness:D4, D11,
fields:D17 of the verification of 13 October 2026).

TED itself states 0, 0.01, 1 and -1 where the buyer did not know an amount (5,771 stored
rows) and a few notices carry a total above ten billion with lot values of millions (50
rows). The mapper now returns no amount, and `value_kind` says why; the repair tool clears
what is stored, which an absent value would otherwise never do (a repair preserves facts).
"""

from __future__ import annotations

from datetime import date

import pytest

from dgate import db
from dgate.normalise import Opportunity, from_ted
from dgate.ops.repair_ted import REMAPPED, plan_change


def ted(**fields):
    return from_ted({"publication-number": "1-2026", "notice-title": "t", "buyer-name": "b",
                     "notice-type": "cn-standard", **fields})


@pytest.mark.parametrize("amount", ["-1", "-1.00", "0", "0.00", "0.01", "1", "1.00"])
def test_a_placeholder_amount_is_not_a_value(amount):
    o = ted(**{"estimated-value-proc": amount, "estimated-value-cur-proc": "EUR"})
    assert (o.value_amount, o.value_currency, o.value_kind) == (None, None, "not_stated")


def test_a_result_notice_total_of_a_cent_is_not_the_award():
    o = ted(**{"notice-type": "can-standard", "total-value": "0.01", "total-value-cur": "EUR"})
    assert (o.value_amount, o.value_currency, o.value_kind) == (None, None, "not_stated")


def test_a_placeholder_gives_way_to_the_next_value_the_notice_states():
    o = ted(**{"notice-type": "can-standard", "total-value": "0.01", "total-value-cur": "EUR",
               "estimated-value-proc": "500000", "estimated-value-cur-proc": "EUR"})
    assert (o.value_amount, o.value_currency, o.value_kind) == (500000.0, "EUR", "estimated")


def test_a_sound_value_is_untouched():
    o = ted(**{"estimated-value-proc": "2", "estimated-value-cur-proc": "EUR"})
    assert (o.value_amount, o.value_kind) == (2.0, "estimated")


def test_an_implausible_total_gives_way_to_the_lots():
    """609036-2026: total-value 13,622,400,000 EUR against lot values of 4,800,000."""
    o = ted(**{"total-value": "13622400000", "total-value-cur": "EUR",
               "estimated-value-lot": ["4800000"], "estimated-value-cur-lot": ["EUR"],
               "description-lot": {"eng": ["a"]}})
    assert (o.value_amount, o.value_currency, o.value_kind) == (4800000.0, "EUR", "lot_sum")


def test_an_implausible_amount_alone_is_no_value():
    o = ted(**{"estimated-value-proc": "16473600000", "estimated-value-cur-proc": "EUR"})
    assert (o.value_amount, o.value_currency, o.value_kind) == (None, None, "implausible")


def test_ten_billion_exactly_is_not_a_value_either():
    """Changed on purpose, 14 October 2026 (data-correctness DC3): the rule was "above ten
    billion", which let 127753-2025 (exactly 10,000,000,000) and 98602-2021
    (9,999,999,999.99) through; both are fill characters."""
    for stated in ("10000000000", "9999999999.99"):
        o = ted(**{"estimated-value-proc": stated, "estimated-value-cur-proc": "EUR"})
        assert (o.value_amount, o.value_kind) == (None, "implausible")


def test_a_billion_the_lots_contradict_a_hundredfold_is_not_the_notices_value():
    """220199-2026 states 7.27 billion for one lot of 7.3 million: a figure in the wrong
    unit. The lot's own is served, as `lot_sum`; the archive keeps what TED stated."""
    o = ted(**{"total-value": "7270000000", "total-value-cur": "EUR",
               "estimated-value-lot": ["7300000"], "estimated-value-cur-lot": ["EUR"],
               "description-lot": {"eng": ["a"]}})
    assert (o.value_amount, o.value_kind) == (7300000.0, "lot_sum")


def test_an_estimate_a_hundred_times_below_the_total_contradicts_it():
    """177041-2026: a total of 5.44 billion against an estimate of 29 million."""
    o = ted(**{"notice-type": "can-standard",
               "total-value": "5440000000", "total-value-cur": "EUR",
               "estimated-value-proc": "29000000", "estimated-value-cur-proc": "EUR"})
    assert (o.value_amount, o.value_kind) == (29000000.0, "estimated")


def test_a_large_total_its_lots_agree_with_is_kept():
    o = ted(**{"total-value": "2400000000", "total-value-cur": "EUR",
               "estimated-value-lot": ["800000000", "800000000", "800000000"],
               "estimated-value-cur-lot": ["EUR"],
               "description-lot": {"eng": ["a", "b", "c"]}})
    assert (o.value_amount, o.value_kind) == (2400000000.0, "total")


def test_lots_that_all_state_a_placeholder_are_no_value():
    o = ted(**{"estimated-value-lot": ["0.01", "0.01"], "estimated-value-cur-lot": ["EUR"],
               "description-lot": {"eng": ["a", "b"]}})
    assert (o.value_amount, o.value_currency, o.value_kind) == (None, None, "not_stated")


def test_a_placeholder_lot_does_not_enter_the_sum_it_is_a_first_lot_figure():
    o = ted(**{"estimated-value-lot": ["0.01", "700"], "estimated-value-cur-lot": ["EUR"],
               "description-lot": {"eng": ["a", "b"]}})
    assert (o.value_amount, o.value_kind) == (700.0, "first_lot")


def test_a_notice_with_no_value_field_at_all_has_no_kind():
    o = ted()
    assert (o.value_amount, o.value_currency, o.value_kind) == (None, None, None)


# ------------------------------------------------------------ the repair

def stored_row(amount: float) -> tuple[dict, dict]:
    opp = Opportunity(source_code="ted", native_id="1-2026", buyer_name_raw="b",
                      title_original="t", country="PL", published_at=date(2026, 7, 31),
                      status="open", value_amount=amount, value_currency="EUR",
                      value_kind="estimated")
    serving = {"is_defence": True, "buyer_org_id": 7, "value_kind": "estimated"}
    return db.opportunity_payload(opp), serving


def test_the_repair_clears_a_stored_placeholder_instead_of_preserving_it():
    payload, serving = stored_row(0.01)
    new = ted(**{"estimated-value-proc": "0.01", "estimated-value-cur-proc": "EUR"})
    change = plan_change(payload, serving, new, REMAPPED)
    assert {"value_amount", "value_currency"} <= set(change.changed)
    assert change.candidate.value_amount is None and change.candidate.value_currency is None
    assert change.direct["value_kind"] == "not_stated"


def test_the_repair_clears_an_implausible_amount_too():
    payload, serving = stored_row(16473600000.0)
    new = ted(**{"estimated-value-proc": "16473600000", "estimated-value-cur-proc": "EUR"})
    change = plan_change(payload, serving, new, REMAPPED)
    assert change.candidate.value_amount is None
    assert change.direct["value_kind"] == "implausible"


def test_a_second_pass_over_a_cleared_notice_plans_nothing():
    payload, serving = stored_row(0.01)
    new = ted(**{"estimated-value-proc": "0.01", "estimated-value-cur-proc": "EUR"})
    first = plan_change(payload, serving, new, REMAPPED)
    second = plan_change(db.opportunity_payload(first.candidate),
                         {**serving, **first.direct}, new, REMAPPED)
    assert second.nothing


def test_the_repair_still_preserves_a_value_when_the_notice_states_none():
    """The clearing is for a stated placeholder, not for an absent field."""
    payload, serving = stored_row(500000.0)
    change = plan_change(payload, serving, ted(), REMAPPED)
    assert change.candidate.value_amount == 500000.0
    assert "value_amount" not in change.changed
