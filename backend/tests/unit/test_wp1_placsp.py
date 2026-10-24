"""PLACSP: no-winner results, lot counts, and the correction of stored records (correctness:D3,
D10, fields:D2, D3 of the verification of 13 October 2026).

The result codes were read off the live feed of 13 October 2026 (350 entries, 683 results):
8 and 9 always name a winning party, 3 never does ("se declara desierto", 87 of 87), 4 is the
buyer's withdrawal with a DESISTIMIENTO notice (3 of 3).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from dgate import db
from dgate.normalise import Opportunity
from dgate.ops import remap_source
from dgate.sources import placsp

from .test_placsp import _page


def _entry(status: str = "RES", results: tuple[str, ...] = (), lots: int = 0,
           end: str | None = None) -> placsp.Opportunity:
    res = "".join(f"<cac:TenderResult><cbc:ResultCode>{c}</cbc:ResultCode></cac:TenderResult>"
                  for c in results)
    lot = "".join(f"<cac:ProcurementProjectLot><cbc:ID>{i}</cbc:ID></cac:ProcurementProjectLot>"
                  for i in range(lots))
    period = (f"<cac:TenderingProcess><cac:TenderSubmissionDeadlinePeriod><cbc:EndDate>{end}"
              "</cbc:EndDate></cac:TenderSubmissionDeadlinePeriod></cac:TenderingProcess>"
              if end else "")
    entry = (
        "<entry><id>x</id><title>t</title><updated>2026-10-11T19:54:50+02:00</updated>"
        "<cac-place-ext:ContractFolderStatus><cbc:ContractFolderID>F-1</cbc:ContractFolderID>"
        f"<cbc-place-ext:ContractFolderStatusCode>{status}</cbc-place-ext:ContractFolderStatusCode>"
        f"<cac:ProcurementProject><cbc:Name>t</cbc:Name></cac:ProcurementProject>{period}"
        f"{lot}{res}</cac-place-ext:ContractFolderStatus></entry>")
    opps, _ = placsp.parse_feed(_page(entry, None))
    return opps[0]


# --------------------------------------------------------- the outcome

@pytest.mark.parametrize("results", [("3",), ("3", "3"), ("4",), ("3", "4")])
def test_a_folder_whose_every_result_awarded_nothing_is_cancelled(results):
    assert _entry("RES", results).status == "cancelled"
    assert _entry("ADJ", results).status == "cancelled"


@pytest.mark.parametrize("results", [(), ("8",), ("9",), ("8", "3"), ("9", "4", "9")])
def test_a_folder_with_a_winner_or_without_results_stays_awarded(results):
    assert _entry("RES", results).status == "awarded"


def test_a_call_in_progress_is_not_touched_by_a_result_code():
    assert _entry("PUB", ("3",)).status == "open"


# ------------------------------------------------------------------ lots

def test_the_lots_of_an_entry_are_counted_and_none_is_not_one():
    assert _entry(lots=4).lot_count == 4
    assert _entry(lots=1).lot_count == 1
    assert _entry(lots=0).lot_count is None


# --------------------------------------------- the stored record mapper

def stored(**kw) -> dict:
    base = dict(source_code="es_placsp", native_id="X-1", buyer_name_raw="b", title_original="t",
                country="ES", status="awarded", status_native="RES", procedure_type="9",
                published_at=date(2026, 8, 4),
                deadline_at=datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc),
                source_updated_at=datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc))
    base.update(kw)
    return db.opportunity_payload(Opportunity(**base))


def test_a_bare_procedure_code_is_named_and_an_unverified_one_is_left():
    assert remap_source.from_placsp_stored(stored(procedure_type="9")).procedure_type == \
        "Abierto simplificado"
    assert remap_source.from_placsp_stored(stored(procedure_type="1")).procedure_type == "Abierto"
    # WP-113: code 7 is named now (8,185 stored entries, a call-off of a framework); 5 is still unverified
    assert remap_source.from_placsp_stored(stored(procedure_type="7")).procedure_type == "Derivado de acuerdo marco"
    assert remap_source.from_placsp_stored(stored(procedure_type="5")).procedure_type == "5"
    named = remap_source.from_placsp_stored(stored(procedure_type="Negociado con publicidad"))
    assert named.procedure_type == "Negociado con publicidad"


def test_a_prior_notice_filed_open_is_forthcoming_and_a_cancelled_one_stays():
    old = stored(status="open", status_native="PRE")
    assert remap_source.from_placsp_stored(old).status == "forthcoming"
    kept = stored(status="cancelled", status_native="RES")
    assert remap_source.from_placsp_stored(kept).status == "cancelled"
    live = stored(status="open", status_native="PUB")
    assert remap_source.from_placsp_stored(live).status == "open"


def test_the_correction_clears_a_publication_after_the_deadline_and_writes_a_version():
    payload = stored()
    new = remap_source.from_placsp_stored(payload)
    clears = remap_source.placsp_stored_clears(payload, new)
    assert clears == {"published_at"}
    change = remap_source.plan(payload, {}, new, clears)
    assert "published_at" in change.changed and "procedure_type" in change.changed
    assert change.candidate.published_at is None


def test_without_the_clear_a_fact_is_never_replaced_by_an_absent_one():
    payload = stored()
    absent = Opportunity(source_code="es_placsp", native_id="X-1", buyer_name_raw="b",
                         title_original="t")
    change = remap_source.plan(payload, {}, absent)
    assert change.candidate.published_at == date(2026, 8, 4)


def test_a_record_the_first_mapper_read_is_left_for_the_replay():
    """No update stamp: its date is the feed's, which the replay corrects with the right one."""
    payload = stored(source_updated_at=None)
    new = remap_source.from_placsp_stored(payload)
    assert remap_source.placsp_stored_clears(payload, new) == set()


def test_a_publication_before_the_deadline_is_kept():
    payload = stored(published_at=date(2026, 5, 1))
    new = remap_source.from_placsp_stored(payload)
    assert remap_source.placsp_stored_clears(payload, new) == set()


def test_a_second_pass_plans_nothing():
    payload = stored()
    new = remap_source.from_placsp_stored(payload)
    first = remap_source.plan(payload, {}, new, {"published_at"})
    again_payload = db.opportunity_payload(first.candidate)
    again = remap_source.from_placsp_stored(again_payload)
    second = remap_source.plan(again_payload, {**first.direct}, again,
                               remap_source.placsp_stored_clears(again_payload, again))
    assert second.nothing
