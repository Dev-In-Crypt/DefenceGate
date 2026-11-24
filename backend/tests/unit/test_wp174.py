"""WP-174 (full QA of 24 November 2026, tenders and feeds): the rules that need no database."""

from __future__ import annotations

from datetime import date, datetime, timezone

from dgate.api import EFFECTIVE_STATUS_SQL, effective_status
from dgate.buyer_vocab import buyer_class_of
from dgate.classify import classify
from dgate.tenders import _kept_in_snapshot, core_first, procedure_label, status_conditions

NOW = datetime(2026, 11, 24, 9, 30, tzinfo=timezone.utc)


def test_a_planned_notice_turns_closed_on_the_anniversary_as_the_filter_says():
    """B-20: 777791-2025 (published 24 Nov 2025) was in the Closed filter and read "Planned" on its card."""
    assert effective_status("forthcoming", None, date(2025, 11, 24), NOW) == "expired"
    assert effective_status("forthcoming", None, date(2025, 11, 25), NOW) == "forthcoming"
    assert effective_status("open", None, date(2025, 11, 24), NOW) == "expired"
    assert effective_status("open", None, date(2025, 11, 25), NOW) == "open"


def test_an_open_notice_with_no_deadline_and_no_date_is_unknown():
    """B-21: BKMS 285904 and 50 more, "Open" with no deadline and no date at all."""
    assert effective_status("open", None, None, NOW) == "unknown"
    assert effective_status("open", None, None, NOW, notice_date=date(2026, 11, 1)) == "open"
    assert effective_status("open", None, None, NOW, notice_date=date(2025, 1, 1)) == "expired"
    assert "coalesce(o.published_at, o.notice_date)" in EFFECTIVE_STATUS_SQL
    assert "o.published_at IS NULL AND o.notice_date IS NULL\n    THEN 'unknown'" in EFFECTIVE_STATUS_SQL


def test_closed_leaves_the_unknown_out():
    assert status_conditions("closed", "E") == ["E NOT IN ('open', 'forthcoming', 'unknown')"]


def test_everything_leads_with_the_military_goods_and_works():
    """B-7: the sort box said "Military goods and works first" over scope Everything, which was not."""
    assert core_first("open", "all", None) and core_first("open", "relevant", "core-first")
    assert not core_first("open", "supply", None) and not core_first("open", "core", None)
    assert not core_first("closed", "all", None)


def test_all_with_its_open_part_is_read_live():
    """B-1: a stored `all` page led "Open first" with notices closed since."""
    assert not _kept_in_snapshot({"status": "all", "sort": None})
    assert not _kept_in_snapshot({"status": "all", "sort": "open-first"})
    assert _kept_in_snapshot({"status": "all", "sort": "deadline-desc"})
    assert _kept_in_snapshot({"status": "closed", "sort": None})
    assert not _kept_in_snapshot({"status": "open", "sort": None})


def test_a_landscape_park_and_an_autonomous_province_are_civil_buyers():
    """B-2: Mazurski Park Krajobrazowy (one CPV 35512400 of six) and Provincia Autonoma di Trento (flight simulators) were
    filed under military goods and works; the scope promise is that a civil buyer's military code is dual-use."""
    assert buyer_class_of("Mazurski Park Krajobrazowy", "PL") == "infrastructure"
    assert buyer_class_of("Provincia Autonoma di Trento", "IT") == "municipal"
    assert buyer_class_of("Agencja Uzbrojenia", "PL") == "defence"
    park = classify(legal_basis=None, cpv_codes=["34970000", "35512400"], buyer_is_defence=False,
                    buyer_class=buyer_class_of("Mazurski Park Krajobrazowy", "PL"))
    assert park.military_cpv and park.dual_use and not park.in_core       # the signal column stays, the verdict moves
    trento = classify(legal_basis=None, cpv_codes=["80650000"], buyer_is_defence=False,
                      buyer_class=buyer_class_of("Provincia Autonoma di Trento", "IT"))
    assert trento.dual_use and not trento.in_core


def test_the_german_national_procedures_are_named():
    """F15: "De-open" stood on a BKMS notice's page."""
    assert procedure_label("de-open") == "Open procedure (German national)"
    assert procedure_label("De-restricted-w-call") == "Restricted procedure with a call for competition (German national)"
    assert procedure_label("de-comp-wo-call") == "Negotiated award without a call for competition (German national)"
