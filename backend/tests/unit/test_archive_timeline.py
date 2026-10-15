"""What the archive says changed, and what the timeline shows of it.

Shapes are real ones from 12 October 2026: notice 2844 (a PLACSP notice whose deadline is
stored with +02:00), notice 257 (a feed date move together with a CPV re-ordering), and
the 66 listed lines that read the same before and after. The archive itself is
append-only and cannot be rewritten, so these are read-side rules, and the write side
stops adding to them.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dgate.db import changed_fields, same_value
from dgate.funding import anomalies
from dgate.tenders import NOT_AN_AMENDMENT, _human, _show, procedure_label, tender_order, timeline

AT = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _row(version, changed, kinds=(), **payload):
    return {"version": version, "observed_at": AT, "changed_fields": changed,
            "payload": payload, "kinds": list(kinds)}


# ------------------------------------------------------------ the write side

def test_a_cpv_list_in_another_order_is_not_a_change():
    before = {"cpv_codes": ["35200000", "35810000", "35123400", "35121300"]}
    after = {"cpv_codes": ["35200000", "35123400", "35121300", "35810000"]}
    assert changed_fields(before, after) == []


def test_a_cpv_code_added_is_a_change_and_the_order_is_not_asked_about():
    before = {"cpv_codes": ["35200000", "35810000"]}
    after = {"cpv_codes": ["35810000", "35200000", "35121300"]}
    assert changed_fields(before, after) == ["cpv_codes"]


def test_the_same_moment_written_with_another_offset_is_not_a_change():
    before = {"deadline_at": "2026-10-09T23:59:00+02:00"}
    after = {"deadline_at": "2026-10-09T21:59:00+00:00"}
    assert changed_fields(before, after) == []
    assert same_value("deadline_at", "2026-10-09T21:59:00Z", "2026-10-09T23:59:00+02:00")


def test_a_deadline_that_moved_is_a_change_whatever_the_offset():
    before = {"deadline_at": "2026-09-17T23:59:00+02:00"}
    after = {"deadline_at": "2026-10-09T23:59:00+02:00"}
    assert changed_fields(before, after) == ["deadline_at"]


@pytest.mark.parametrize("left,right", [(None, []), ("", None), ([], "")])
def test_not_stated_is_one_value(left, right):
    assert same_value("cpv_codes", left, right)


# ------------------------------------------------------------- the read side

def test_the_deadline_is_converted_to_utc_not_relabelled():
    """Notice 2844, version 3: stored 23:59 at +02:00, which is 21:59 UTC. It was
    printed as 23:59 UTC, two hours late, on 86 of 89 deadline changes."""
    assert _show("deadline_at", "2026-10-09T23:59:00+02:00") == "2026-10-09 21:59 UTC"
    assert _show("deadline_at", "2026-12-09T23:59:00+01:00") == "2026-12-09 22:59 UTC"
    assert _show("deadline_at", "2026-10-09T12:00:00Z") == "2026-10-09 12:00 UTC"
    assert _show("deadline_at", "2026-10-09") == "2026-10-09"


def test_a_whole_number_reads_the_same_as_the_float_it_was_stored_as():
    assert _show("value_amount", 1000000.0) == _show("value_amount", 1000000) == "1000000"


def test_notice_2844_lists_its_cancellation_and_its_deadline_extension():
    rows = [
        _row(1, [], status="open", deadline_at="2026-09-17T23:59:00+02:00", published_at="2026-09-02"),
        _row(2, ["status"], status="cancelled", deadline_at="2026-09-17T23:59:00+02:00",
             published_at="2026-09-02"),
        _row(3, ["published_at", "deadline_at", "status"], status="open",
             deadline_at="2026-10-09T23:59:00+02:00", published_at="2026-09-25"),
    ]
    out = timeline(rows)
    assert [v["version"] for v in out] == [1, 2, 3]
    third = {c["field"]: (c["before"], c["after"]) for c in out[2]["changes"]}
    # Said for a person (QA 12 October 2026): the dates and the status as words.
    assert third["deadline_at"] == ("17 Sep 2026, 21:59 UTC", "9 Oct 2026, 21:59 UTC")
    assert third["status"] == ("Cancelled", "Open")


def test_a_version_that_only_moved_the_publication_date_is_not_an_amendment():
    rows = [
        _row(1, [], published_at="2026-08-24", cpv_codes=["35200000", "35810000"]),
        _row(2, ["published_at"], published_at="2026-08-26", cpv_codes=["35200000", "35810000"]),
    ]
    assert [v["version"] for v in timeline(rows)] == [1]


def test_a_feed_date_move_with_a_cpv_reordering_is_still_not_an_amendment():
    """Notice 257, version 3: {published_at, cpv_codes}, the codes only re-ordered."""
    rows = [
        _row(1, [], published_at="2026-08-24", cpv_codes=["35200000", "35810000", "35123400"]),
        _row(2, ["published_at", "cpv_codes"], published_at="2026-08-26",
             cpv_codes=["35200000", "35123400", "35810000"]),
    ]
    assert [v["version"] for v in timeline(rows)] == [1]


def test_a_real_change_next_to_a_date_move_keeps_both_lines():
    rows = [
        _row(1, [], published_at="2026-08-24", value_amount=100.0),
        _row(2, ["published_at", "value_amount"], published_at="2026-08-26", value_amount=250.0),
    ]
    out = timeline(rows)
    assert [(c["field"], c["before"], c["after"]) for c in out[1]["changes"]] == [
        ("published_at", "24 Aug 2026", "26 Aug 2026"), ("value_amount", "100", "250")]


def test_a_listed_line_that_reads_the_same_before_and_after_is_dropped():
    rows = [
        _row(1, [], status="open", deadline_at="2026-09-17T23:59:00+02:00"),
        _row(2, ["deadline_at", "status"], status="awarded",
             deadline_at="2026-09-17T21:59:00+00:00"),
    ]
    out = timeline(rows)
    assert [c["field"] for c in out[1]["changes"]] == ["status"]


def test_a_remapped_version_is_neither_listed_nor_an_amendment_but_is_the_baseline():
    """A bulk correction re-read the same payload and moved the status. Nobody
    amended anything, and the next real change is measured from the corrected state."""
    rows = [
        _row(1, [], status="open", deadline_at="2026-10-09T23:59:00+02:00"),
        _row(2, ["status"], ["remapped"], status="awarded", deadline_at="2026-10-09T23:59:00+02:00"),
        _row(3, ["status"], status="cancelled", deadline_at="2026-10-09T23:59:00+02:00"),
    ]
    out = timeline(rows)
    assert [v["version"] for v in out] == [1, 3]
    assert (out[1]["changes"][0]["before"], out[1]["changes"][0]["after"]) == ("Awarded", "Cancelled")


def test_reread_and_out_of_order_versions_are_skipped_without_moving_the_baseline():
    rows = [
        _row(1, [], status="open"),
        _row(2, ["status"], ["reread"], status="awarded"),
        _row(3, ["status"], ["out_of_order"], status="forthcoming"),
        _row(4, ["status"], status="closed"),
    ]
    out = timeline(rows)
    assert [v["version"] for v in out] == [1, 4]
    assert out[1]["changes"][0]["before"] == "Open"


def test_remapped_counts_as_not_an_amendment_everywhere_the_constant_is_used():
    assert "'remapped'" in NOT_AN_AMENDMENT
    assert "'reread'" in NOT_AN_AMENDMENT and "'out_of_order'" in NOT_AN_AMENDMENT


# ------------------------------------------------------------- the procedure

@pytest.mark.parametrize("raw,label", [
    ("open", "Open procedure"),
    ("restricted", "Restricted procedure"),
    ("neg-w-call", "Negotiated procedure with prior call for competition"),
    ("neg-wo-call", "Negotiated procedure without prior call for competition"),
    ("comp-dial", "Competitive dialogue"),
    ("innovation", "Innovation partnership"),
    ("oth-single", "Other single-stage procedure"),
    ("OPEN", "Open procedure"),
    ("Procédure NC", "Procédure NC"),
    ("procédure adaptée", "Procédure adaptée"),
    ("Andere procedure in meerdere fasen", "Andere procedure in meerdere fasen"),
    ("ContractNotice", "Contract notice"),
    ("16", None),
    ("", None),
    (None, None),
])
def test_the_procedure_keeps_the_sources_casing_and_spells_out_ted_codes(raw, label):
    assert procedure_label(raw) == label


# ------------------------------------------------------------ the anomalies

NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)


def test_a_deadline_before_the_publication_is_flagged():
    deadline = datetime(2026, 9, 30, 21, 59, tzinfo=timezone.utc)
    assert anomalies(deadline, datetime(2026, 10, 2).date(), now=NOW) == [
        "deadline-before-publication"]


def test_a_deadline_on_the_publication_day_is_not():
    deadline = datetime(2026, 10, 2, 21, 59, tzinfo=timezone.utc)
    assert anomalies(deadline, datetime(2026, 10, 2).date(), now=NOW) == []


def test_a_deadline_more_than_three_years_out_is_flagged():
    far = datetime(2032, 1, 1, tzinfo=timezone.utc)
    assert anomalies(far, None, now=NOW) == ["deadline-more-than-3y"]
    assert anomalies(datetime(2028, 1, 1, tzinfo=timezone.utc), None, now=NOW) == []


def test_no_deadline_has_no_anomaly():
    assert anomalies(None, datetime(2026, 10, 2).date(), now=NOW) == []


# ------------------------------------------------- the sequence a reader counts by

def test_a_version_carries_its_sequence_and_keeps_the_archive_number():
    """The header said "v11" and the footer "2 versions observed": the archive's row
    number has gaps (reread, remapped, feed-stamp versions are not listed). The reader
    counts 1, 2 and the archive number stays beside it."""
    rows = [
        _row(1, [], status="open"),
        _row(4, ["status"], ["reread"], status="awarded"),
        _row(7, ["published_at"], status="open", published_at="2026-08-26"),
        _row(11, ["status"], status="awarded"),
    ]
    out = timeline(rows)
    assert [(v["sequence"], v["version"]) for v in out] == [(1, 1), (2, 11)]


# ---------------------------------------------- values said the way a person reads

@pytest.mark.parametrize("field,value,shown", [
    ("deadline_at", "2026-09-10", "10 Sep 2026"),
    ("deadline_at", "2026-09-10T14:05:00Z", "10 Sep 2026, 14:05 UTC"),
    ("deadline_at", "2026-09-10T16:05:00+02:00", "10 Sep 2026, 14:05 UTC"),
    ("deadline_at", "2026-09-10T00:00:00+00:00", "10 Sep 2026"),
    ("published_at", "2026-08-24", "24 Aug 2026"),
    ("status", "open", "Open"),
    ("status", "awarded", "Awarded"),
    ("status", "forthcoming", "Planned"),
    ("procedure_type", "restricted", "Restricted procedure"),
    ("cpv_codes", ["35200000", "35810000"], "35200000, 35810000"),
    ("cpv_codes", "['35200000', '35810000']", "35200000, 35810000"),
    ("cpv_codes", '["35200000"]', "35200000"),
    ("legal_basis", "32009L0081", "Directive 2009/81/EC (defence and security procurement)"),
])
def test_a_change_is_said_in_words_a_person_reads(field, value, shown):
    assert _human(field, value) == shown


def test_an_amount_carries_its_currency_and_thousands():
    assert _human("value_amount", 1000000.0, "EUR") == "EUR 1,000,000"
    assert _human("value_amount", 12345.5, "PLN") == "PLN 12,345.50"
    assert _human("value_amount", 250.0) == "250"


def test_a_stored_mapping_is_never_printed_as_a_python_repr():
    assert _human("value_amount", "{'amount': 5000, 'currency': 'EUR'}") == "EUR 5,000"
    assert _human("title_original", "{'a': 1}") == "a: 1"


def test_a_stored_text_nested_past_the_parser_is_left_as_text_not_an_error(monkeypatch):
    """Review finding of 13 October 2026: `json.loads` raises RecursionError on deep
    nesting and `ast.literal_eval` RecursionError or MemoryError, none of which was
    caught, so one stored value of that shape made the tender's versions answer 500.
    How deep is deep depends on the interpreter, so the parsers are made to fail the
    way they do."""
    import ast
    import json

    from dgate.tenders import PLAIN_MAX_CHARS, _plain

    def too_deep(*args, **kwargs):
        raise RecursionError("maximum recursion depth exceeded")

    def too_big(*args, **kwargs):
        raise MemoryError

    nested = "[" * 4000 + "]" * 4000
    monkeypatch.setattr(json, "loads", too_deep)
    monkeypatch.setattr(ast, "literal_eval", too_big)
    assert _plain(nested) == nested
    assert _human("title_original", nested) is not None        # and it reads as text
    monkeypatch.undo()

    huge = "[" + "1," * PLAIN_MAX_CHARS + "1]"
    assert _plain(huge) == huge, "over the cap it is not parsed at all"
    assert _plain("['35200000', '35810000']") == ["35200000", "35810000"]
    assert _plain('{"amount": 5, "currency": "EUR"}') == {"amount": 5, "currency": "EUR"}


def test_an_amount_change_names_the_currency_of_its_own_version():
    rows = [
        _row(1, [], value_amount=100000.0, value_currency="EUR"),
        _row(2, ["value_amount", "value_currency"], value_amount=450000.0, value_currency="PLN"),
    ]
    out = timeline(rows)
    lines = {c["field"]: (c["before"], c["after"]) for c in out[1]["changes"]}
    assert lines["value_amount"] == ("EUR 100,000", "PLN 450,000")


def test_two_spellings_of_one_status_word_are_not_a_change():
    rows = [_row(1, [], status="closed"), _row(2, ["status"], status="expired")]
    # `closed` and `expired` are both "Closed" to a reader: no line, so no amendment
    assert [v["sequence"] for v in timeline(rows)] == [1]


# ----------------------------------------------------- the order of a closed list

def test_a_closed_list_runs_newest_deadline_first_unless_a_sort_was_asked_for():
    eff = "EFF"
    closed = tender_order(None, "closed", eff)
    assert closed.startswith("o.deadline_at DESC NULLS LAST, o.published_at DESC NULLS LAST")
    assert tender_order("deadline-desc", "open", eff) == closed
    # an explicit ascending sort on a closed list is honoured, and open stays soonest-first
    assert "o.deadline_at ASC" in tender_order("deadline-asc", "closed", eff)
    assert "o.deadline_at ASC" in tender_order(None, "open", eff)
    assert "o.deadline_at ASC" in tender_order(None, "all", eff)
    # WP-12: a folder with only its award sorts by that notice's date, so it is not lost at the end
    assert tender_order("published-desc", "closed", eff).startswith(
        "coalesce(o.published_at, o.notice_date) DESC")
