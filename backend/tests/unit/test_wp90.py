"""WP-90 (the analyst path) without a database: the CPV titles the search reads, the commercial subject of a notice,
the kinds of change, the week under way."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dgate import changes, cpv_labels, hardening, tenders
from dgate.weekly_digest import week_bounds, week_id

WEB_COPY = Path(__file__).resolve().parents[3] / "web" / "lib" / "data" / "cpv-full.json"


def test_the_vocabulary_is_the_sites_copy():
    if not WEB_COPY.exists():
        pytest.skip("the web folder is not beside the backend here")
    assert cpv_labels.DATA.read_bytes() == WEB_COPY.read_bytes()


def test_a_word_finds_the_codes_whose_title_has_a_word_beginning_with_it():
    radar = cpv_labels.codes_for_word("Radar")
    assert {"35722000", "35723000", "38115000"} <= set(radar)
    assert cpv_labels.codes_for_word("sonars") == ("38113000",)
    assert "35300000" in cpv_labels.codes_for_word("ammunition")
    assert cpv_labels.codes_for_word("adar") == ()                 # the beginning of a word, not a part of one
    assert cpv_labels.codes_for_word("of") == ()                   # too short
    assert cpv_labels.codes_for_word("services") == ()             # in more than MAX_CODES titles
    assert cpv_labels.fold("Équipements, de-sûreté") == " equipements de surete"


@pytest.mark.parametrize("text, subject", [
    ("Supply of spare parts for military trucks. Engines of 450 kW.", "Supply of spare parts for military trucks."),
    ("  Rahmenvertrag   über Wartung  ", "Rahmenvertrag über Wartung"),
    ("Radar with a range of 300 km.", None),
    ("Lieferung von Munition Kaliber 5,56 mm.", None),
    ("The technical specifications are in annex 2.", None),
    ("Questions to Mr Huber, tel. 030 1234 5678.", None),
    ("Write to x@example.org for the documents.", None),
    ("", None),
    (None, None),
])
def test_the_commercial_subject_is_the_first_sentence_without_a_specification_or_a_contact(text, subject):
    assert tenders.commercial_subject(text) == subject


def test_a_long_first_sentence_is_cut_at_a_word():
    got = tenders.commercial_subject("Maintenance " + "and repair " * 60 + "of vehicles.")
    assert got is not None and len(got) <= tenders.SUBJECT_MAX + 1 and got.endswith("…") and "  " not in got


def test_a_kind_of_change_reads_the_fields_that_moved():
    deadline = {"kind": "amended", "changes": [{"field": "deadline_at"}]}
    value = {"kind": "amended", "changes": [{"field": "value_currency"}, {"field": "procedure_type"}]}
    new = {"kind": "new", "changes": []}
    assert changes.of_kind(deadline, "deadline") and not changes.of_kind(deadline, "value")
    assert changes.of_kind(value, "value") and changes.of_kind(value, "amended") and not changes.of_kind(value, "status")
    assert changes.of_kind(new, "new") and not changes.of_kind(new, "deadline")


def test_the_week_under_way_ends_now():
    now = datetime(2026, 10, 22, 15, 0, tzinfo=timezone.utc)                      # a Thursday
    end, days = changes.week_end(week_id(now.date()), now)
    assert end == now and days == pytest.approx(3 + 15 / 24)
    past = week_id((now - timedelta(days=7)).date())
    assert changes.week_end(past, now) == (week_bounds(past)[1], 7.0)


def test_a_buyers_top_suppliers_cost_like_an_aggregate():
    assert hardening.request_cost("/v1/buyers/28871-baainbw/suppliers", {}) == 3
