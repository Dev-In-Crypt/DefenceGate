"""The comparison the spot check rests on: what counts as the row disagreeing with the record."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from dgate.normalise import Opportunity
from dgate.ops.spot_check import ADAPTERS, differences


def _opp(**kw) -> Opportunity:
    base = dict(source_code="ted", native_id="1-2026", buyer_name_raw="Ministry", title_original="Ammo",
                country="PL", published_at=date(2026, 10, 1), cpv_codes=["35000000"], is_defence=True)
    return Opportunity(**{**base, **kw})


def _row(**kw) -> dict:
    return {"title_original": "Ammo", "buyer_name_raw": "Ministry", "country": "PL",
            "published_at": date(2026, 10, 1), "deadline_at": None, "cpv_codes": ["35000000"],
            "legal_basis": None, "value_amount": None, "value_currency": None,
            "procedure_type": None, "status": "open", "source_url": None, "is_defence": True,
            **kw}


def test_identical_record_and_row_do_not_differ():
    assert differences(_row(), _opp()) == {}


def test_the_database_returns_money_as_decimal_and_it_is_the_same_amount():
    assert differences(_row(value_amount=Decimal("125000.50")), _opp(value_amount=125000.5)) == {}


def test_cpv_order_and_surrounding_whitespace_are_not_differences():
    row = _row(cpv_codes=["35000000", "18000000"], title_original="Ammo ")
    assert differences(row, _opp(cpv_codes=["18000000", "35000000"])) == {}


def test_a_changed_deadline_is_reported_with_both_values():
    when = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
    assert differences(_row(), _opp(deadline_at=when)) == {"deadline_at": (None, when)}


def test_a_wrong_defence_verdict_is_a_difference():
    assert set(differences(_row(), _opp(is_defence=False))) == {"is_defence"}


def test_every_source_that_has_opportunities_can_be_checked():
    assert {"ted", "fr_boamp", "pl_ezam", "pl_atlas", "nl_tenderned",
            "es_placsp", "es_placsp_agg"} <= set(ADAPTERS)
    for code in ("pl_atlas", "es_placsp", "es_placsp_agg"):
        assert ADAPTERS[code].live is None and ADAPTERS[code].why_no_live
