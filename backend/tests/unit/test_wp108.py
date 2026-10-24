"""WP-108 (persona round 4, 24 October 2026): award values without an estimate, and the version history. Evidence:
D:/DEFENCEGATE TESTS/ux-oct24b (p10 ted-verify.json, 33-t-videoscopio.txt; p02 incm.txt; p04 m-digest.txt)."""

from __future__ import annotations

from datetime import datetime, timezone

from dgate import award_value as av
from dgate import db
from dgate import tenders as T


def opp(value=None, kind="total", currency="EUR", procedure=None, title="Dostawa") -> dict:
    return {"value_amount": value, "value_currency": currency if value else None, "value_kind": kind if value else None,
            "notice_subtype": "29", "title_original": title, "title_en": None, "procedure_value": procedure}


# ------------------------------------------------------------------------------------------------ 1. plausibility

def test_faser_the_notice_value_a_thousand_times_its_tenders_is_set_aside_and_the_tenders_stand():
    """394720-2025: total-value PLN 7,247,040,000; tender-value 1,001,400 + 2,197,800 + 3,157,920 + 889,920 = 7,247,040."""
    held = opp(7247040000.0, currency="PLN")
    tenders = ["1001400", "2197800", "3157920", "889920"]
    # TED answers its tenders only (as in the persona's ted-verify.json): the tenders stand, the total is said
    rec = {"tender-value": tenders, "total-value-cur": ["PLN"]}
    assert av.ted_value(rec, held) == (7247040.0, "PLN", "contract")
    assert (av.ted_value_set_aside(rec, held), av.ted_value_set_aside_reason(rec, held)) == (7247040000.0, "lots")
    # TED answers a notice value as well
    rec = {"BT-161-NoticeResult": "7247040000", "tender-value": tenders}
    assert av.ted_value(rec, held) == (7247040.0, "PLN", "contract")
    assert av.ted_value_set_aside_reason(rec, held) == "lots"
    # a framework maximum against its lots' maxima
    rec = {"BT-118-NoticeResult": "5000000000", "BT-709-LotResult": ["2000000", "3000000"]}
    assert av.ted_value(rec, opp(None)) == (5000000.0, None, "framework")


def test_incm_a_figure_eight_hundred_times_its_procedures_estimate_is_set_aside_and_the_estimate_stands():
    """499753-2026: EUR 1,159,000,000 for Land Cruiser modernisation; the procedure's contract notice 126958-2026 states
    EUR 1,450,000. No eForms value field held (read on 18 October)."""
    held = opp(1159000000.0, procedure=1450000.0)
    assert av.ted_value(None, held) == (1450000.0, "EUR", "estimate")
    assert (av.ted_value_set_aside(None, held), av.ted_value_set_aside_reason(None, held)) == (1159000000.0, "procedure")
    # the same with a fetched notice value
    assert av.ted_value({"BT-161-NoticeResult": "1159000000"}, held)[2] == "estimate"


def test_the_checks_leave_plausible_figures_alone():
    assert av.implausible_against(690_000_000, 690_000)                  # 107790-2025: exactly a thousand times
    assert av.implausible_against(2_500_000, 2_500)                       # a thousandfold from a million
    assert not av.implausible_against(2_500_000, 20_000)                  # 125 times, under ten million: stands
    assert not av.implausible_against(2_035_000_000, 77_000_000)          # 666181-2026: a framework 26 times its estimate
    assert not av.implausible_against(1e9, None) and not av.implausible_against(None, 5.0)
    # Arquus 38915-2026: the ceiling equals the tenders and the total
    rec = {"framework-maximum-value-lot": ["2449392735"], "tender-value": ["2449392735"]}
    assert av.ted_value_set_aside(rec, opp(2449392735.0)) is None
    # a large total without a procedure value or parts stands (419618-2026)
    assert av.ted_value(None, opp(9311212000.0, currency="PLN")) == (9311212000.0, "PLN", "contract")
    # a procedure value in another currency is not compared (the column reads the same currency only)
    assert av.ted_value(None, opp(5e7, procedure=None)) == (5e7, "EUR", "contract")
    # WP-103's estimate rule keeps its reason
    held = opp(7317073.17, kind="estimated")
    assert av.ted_value_set_aside_reason({"BT-161-NoticeResult": "7274615930"}, held) == "estimate"


# ------------------------------------------------------------------------------------------------ 2. mapper fields

def test_mapper_fields_split_a_reread_that_came_with_the_award():
    prev, new = {"status_native": "EV", "value_amount": 45980.0}, {"status_native": "ADJ", "value_amount": 38000.0}
    ours, whole = db.mapper_fields(["legal_basis", "value_amount", "published_at", "status"], prev, new)
    assert (ours, whole) == (["legal_basis", "value_amount", "published_at"], False)
    igic = db.mapper_fields(["value_amount", "status"], {**prev, "value_amount": 11000.0}, {**new, "value_amount": 10280.37})
    assert igic == (["value_amount"], False)
    # beside a real change, a value that moved by no tax rate is the buyer's (2026/EA15/00002526: eightfold, with the deadline)
    eight = db.mapper_fields(["legal_basis", "value_amount", "deadline_at"], {"status_native": "PUB", "value_amount": 5000.0},
                             {"status_native": "PUB", "value_amount": 41000.0})
    assert eight == (["legal_basis"], False)
    ours, whole = db.mapper_fields(["legal_basis", "value_amount", "status"], {"status_native": "RES"}, {"status_native": "RES"})
    assert whole and ours == ["legal_basis", "value_amount", "status"]
    assert db.mapper_fields(["deadline_at"], prev, new) == ([], False)


# ------------------------------------------------------------------------------------------------ 3, 4. timeline

def _row(version, payload, changed=(), kinds=(), fields=None):
    return {"version": version, "observed_at": datetime(2026, 9, 13 + version, tzinfo=timezone.utc),
            "changed_fields": list(changed), "payload": payload, "kinds": list(kinds), "remapped_fields": fields}


V1 = {"value_amount": 45980.0, "value_currency": "EUR", "published_at": "2026-09-28", "status": "open"}
V2 = {**V1, "value_amount": 38000.0, "published_at": "2026-09-03", "status": "awarded", "legal_basis": "32014L0024"}


def test_videoscopio_the_noted_fields_are_a_correction_and_the_award_the_publishers_change():
    rows = [_row(1, V1), _row(2, V2, ["legal_basis", "value_amount", "published_at", "status"], ["remapped_fields"],
                              ["legal_basis", "value_amount", "published_at"])]
    page = T.timeline(rows, corrections=True)
    own = [e for e in page if not e["correction"]]
    fixes = [e for e in page if e["correction"]]
    assert [c["field"] for c in own[1]["changes"]] == ["status"]
    assert len(fixes) == 1 and fixes[0]["reason"] == "remapped"
    assert {c["field"] for c in fixes[0]["changes"]} == {"legal_basis", "value_amount", "published_at"}
    # the counts and the change list: the status only, never "value changed from 45,980 to 38,000"
    counts = T.timeline(rows)
    assert [c["field"] for c in counts[1]["changes"]] == ["status"]


def test_a_publication_date_moved_with_the_award_is_the_source_redating_not_an_amendment():
    rows = [_row(1, V1), _row(2, {**V1, "status": "awarded", "published_at": "2026-09-03"}, ["published_at", "status"])]
    page = T.timeline(rows, corrections=True)
    assert len(page) == 2 and not page[1]["correction"]
    assert [c["field"] for c in page[1]["changes"]] == ["status"]
    assert [(c["field"], c["before"], c["after"]) for c in page[1]["redated"]] == [("published_at", "28 Sep 2026", "3 Sep 2026")]
    # an open notice's date moved alone is still not listed at all, as before
    assert len(T.timeline([_row(1, V1), _row(2, {**V1, "published_at": "2026-09-01"}, ["published_at"])],
                          corrections=True)) == 1
