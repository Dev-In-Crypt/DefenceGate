"""Planning the correction of TED notices mapped before 12 October 2026, and the
daily pull that now also asks for whole days.

The planning is pure: stored state in, what would change out. Writing it, and
the archive guarantees around that, are in tests/integration/test_repair_ted.py.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from dgate import db
from dgate.normalise import Opportunity, from_ted, strip_personal_data
from dgate.ops.repair_ted import REMAPPED, plan_change, raw_fields
from dgate.sources import ted

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ted_live_notices_2026_10.json"
LIVE = {n["publication-number"]: n for n in json.loads(FIXTURE.read_text(encoding="utf-8"))}

# Fields TED's API returned only after the connector asked for them on 12 October.
REQUESTED_LATER = ("publication-date", "deadline-receipt-request", "deadline-receipt-request-time-lot",
                   "procedure-type", "total-value", "total-value-cur", "result-value-notice",
                   "result-value-cur-notice", "winner-selection-status", "procedure-identifier")


def stored_payload(pub: str) -> dict:
    """What the raw store holds for a notice landed before that day."""
    raw = strip_personal_data(LIVE[pub])
    return {k: v for k, v in raw.items() if k not in REQUESTED_LATER}


def serving_row(**kw) -> dict:
    return {"is_defence": True, "sig_legal_basis": True, "sig_cpv": True, "sig_buyer": False,
            "sig_clearance": False, "subcontracting_signal": False,
            "security_clearance_required": False, "buyer_org_id": 7, "title_en": None,
            "summary_en": None, "ted_ref": None, "status_native": None, "notice_subtype": None,
            "procedure_identifier": None, "lot_count": None, "value_kind": None, **kw}


def before_state(**kw) -> dict:
    """The version payload as the old mapper wrote it: open, dispatch date, numeric subtype."""
    opp = Opportunity(source_code="ted", native_id="534116-2026", buyer_name_raw="Buyer",
                      title_original="Title", country="PL", procedure_type="31",
                      published_at=date(2026, 7, 31), status="open", value_amount=None,
                      is_defence=True, **kw)
    return db.opportunity_payload(opp)


def test_from_raw_corrects_what_the_stored_payload_can_speak_for():
    raw = stored_payload("534116-2026")
    new = from_ted(raw)
    fields = raw_fields(raw, new.status_native)
    assert "status" in fields and "country" in fields and "notice_subtype" in fields
    # Not requested when this payload was fetched: left alone, not blanked.
    for name in ("published_at", "procedure_type", "procedure_identifier"):
        assert name not in fields
    # A result notice's value is its total, and this payload does not carry it.
    assert "value_amount" not in fields

    change = plan_change(before_state(), serving_row(), new, fields)
    assert change.changed == ["status"]
    assert change.transitions == ["status:open>awarded"]
    assert change.direct["status_native"] == "can-standard"
    assert change.direct["notice_subtype"] == "31"
    assert change.candidate.procedure_type == "31", "the stored procedure is not erased"
    assert change.candidate.published_at == date(2026, 7, 31)


def test_a_current_payload_that_states_the_total_corrects_the_value_too():
    raw = strip_personal_data(LIVE["534116-2026"])      # carries total-value
    fields = raw_fields(raw, "can-standard")
    assert {"value_amount", "value_currency", "value_kind", "published_at",
            "procedure_type", "procedure_identifier"} <= set(fields)


def test_a_corrigendum_status_waits_for_the_deadline_it_may_state():
    """A corrigendum is open with a deadline and unknown without one. A stored payload
    that predates `deadline-receipt-request` cannot say which, and must not be written
    `unknown` only to be corrected again by the refetch."""
    stored = stored_payload("1268-2024")
    assert "status" not in raw_fields(stored, "corr")
    assert "status" in raw_fields(strip_personal_data(LIVE["1268-2024"]), "corr")


def test_the_repair_never_reclassifies():
    raw = stored_payload("534116-2026")
    row = serving_row(is_defence=True, sig_buyer=True, buyer_org_id=99)
    change = plan_change(before_state(), row, from_ted(raw), raw_fields(raw, "can-standard"))
    assert change.candidate.is_defence is True
    assert change.candidate.sig_buyer is True
    assert change.candidate.buyer_org_id == 99


def test_a_repair_carries_the_demotion_and_the_link_the_payload_never_held():
    """Review finding of 13 October 2026. The classification is not versioned, so the
    payload of the current version has no `dual_use`, `buyer_class` or
    `sig_linked_defence`; a repair version written from it reset the serving row, and a
    municipality's military CPV came back to `core`."""
    raw = stored_payload("534116-2026")
    row = serving_row(dual_use=True, buyer_class="municipal", sig_linked_defence=True,
                      sig_cpv_military=True, sig_cpv_adjacent=False)
    new = from_ted(raw)
    change = plan_change(before_state(), row, new, raw_fields(raw, new.status_native))
    assert change.changed, "a version is due, which is what writes the serving row"
    cand = change.candidate
    assert (cand.dual_use, cand.buyer_class, cand.sig_linked_defence) == (True, "municipal", True)
    assert cand.sig_cpv_military is True


def test_remap_source_carries_them_too():
    from dgate.ops import remap_source

    row = serving_row(dual_use=True, buyer_class="health", sig_linked_defence=True)
    moved = from_ted(strip_personal_data(LIVE["534116-2026"]))
    change = remap_source.plan(before_state(), row, moved)
    assert (change.candidate.dual_use, change.candidate.buyer_class,
            change.candidate.sig_linked_defence) == (True, "health", True)


def test_a_refetch_never_replaces_a_stored_fact_by_an_absent_one():
    """A notice TED now returns without a value, a date or a currency has not lost them."""
    stored = db.opportunity_payload(Opportunity(
        source_code="ted", native_id="1-2026", buyer_name_raw="Buyer", title_original="T",
        country="PL", procedure_type="16", published_at=date(2026, 7, 31), status="open",
        value_amount=500000.0, value_currency="EUR", value_kind="estimated", lot_count=3,
        procedure_identifier="c3c8137c-d92b-4f7f-8175-36decaf1451d"))
    bare = from_ted({"publication-number": "1-2026", "notice-title": "t", "buyer-name": "b",
                     "notice-type": "cn-standard"})
    assert bare.value_amount is None and bare.published_at is None
    held = serving_row(value_kind="estimated", lot_count=3,
                       procedure_identifier="c3c8137c-d92b-4f7f-8175-36decaf1451d")
    change = plan_change(stored, held, bare, REMAPPED)
    cand = change.candidate
    assert (cand.value_amount, cand.value_currency, cand.published_at) == (
        500000.0, "EUR", date(2026, 7, 31))
    assert "value_amount" not in change.changed and "published_at" not in change.changed
    assert "value_kind" not in change.direct and "lot_count" not in change.direct
    assert "procedure_identifier" not in change.direct


def test_a_second_pass_over_a_corrected_notice_plans_nothing():
    raw = stored_payload("534116-2026")
    new = from_ted(raw)
    first = plan_change(before_state(), serving_row(), new, raw_fields(raw, new.status_native))
    assert not first.nothing

    corrected_payload = db.opportunity_payload(first.candidate)
    corrected_row = serving_row(**first.direct)
    second = plan_change(corrected_payload, corrected_row, new,
                         raw_fields(raw, new.status_native))
    assert second.nothing


def test_refetch_moves_every_field_the_mapper_now_owns():
    raw = strip_personal_data(LIVE["93334-2024"])       # restricted, 08:00+01:00, CZK
    new = from_ted(raw)
    old = db.opportunity_payload(Opportunity(
        source_code="ted", native_id="93334-2024", buyer_name_raw="Buyer", title_original="T",
        country="CZ", procedure_type="18", published_at=date(2024, 2, 13), status="open",
        value_amount=86776859.5, value_currency="CZK"))
    change = plan_change(old, serving_row(), new, REMAPPED)
    assert set(change.changed) == {"procedure_type", "published_at", "deadline_at"}
    assert change.candidate.procedure_type == "restricted"
    assert change.candidate.published_at == date(2024, 2, 14)
    assert change.candidate.deadline_at.isoformat() == "2024-03-22T08:00:00+01:00"
    assert change.direct["value_kind"] == "estimated"
    assert change.direct["procedure_identifier"] == "c3c8137c-d92b-4f7f-8175-36decaf1451d"


def test_remapped_fields_are_fields_the_mapper_sets():
    new = from_ted(strip_personal_data(LIVE["93334-2024"]))
    for name in REMAPPED:
        assert hasattr(new, name)


# ----------------------------------------------------- the daily pull

def _n(number: str) -> dict:
    return {"publication-number": [number]}


def test_the_daily_pull_adds_today_and_yesterday_in_full_once(monkeypatch):
    today = date(2026, 10, 12)
    answers = {
        ted.defence_query(date(2026, 10, 10), today): [_n("1-2026"), _n("2-2026")],
        ted.day_query(today): [_n("3-2026")],
        ted.day_query(date(2026, 10, 11)): [_n("2-2026"), _n("4-2026")],
    }
    asked: list[str] = []

    def fake_search(query, fields=None, *, client=None, max_pages=0):
        asked.append(query)
        return iter(answers[query])

    monkeypatch.setattr(ted, "search", fake_search)
    pull = ted.fetch_window(days_back=2, today=today)
    got = [n["publication-number"][0] for n in pull]

    assert got == ["1-2026", "2-2026", "3-2026", "4-2026"], "a notice both queries return is once"
    assert pull.defence_fetched == 2, "the coverage floor is for the defence query alone"
    assert asked == list(answers)


def test_the_connector_requests_the_fields_the_mapper_reads():
    for name in ("publication-date", "deadline-receipt-request",
                 "deadline-receipt-request-time-lot", "procedure-type", "total-value",
                 "total-value-cur", "result-value-notice", "result-value-cur-notice",
                 "winner-selection-status", "procedure-identifier", "buyer-identifier"):
        assert name in ted.TED_FIELDS
    assert "deadline-date-lot" not in ted.TED_FIELDS, "BT-13 is not the tender deadline"
