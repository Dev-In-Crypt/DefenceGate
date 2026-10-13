"""BOAMP: the deadline of an eForms notice is read from the notice, and its lots are counted
(correctness:D1, fields:D1, fields:D4 of the verification of 13 October 2026).

`tests/fixtures/boamp_eforms_deadlines.json` holds five real records of the production raw
store reduced to the lots' tendering periods and ids; the first three have no
`datelimitereponse` (2,049 stored call notices are like that, 119 of the 129 served as open
past their deadline), the last two have one, written as the wall time labelled UTC for the
`.000+02:00` spelling of the time.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dgate.normalise import from_boamp

NOTICES = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "boamp_eforms_deadlines.json")
    .read_text(encoding="utf-8"))


def at(day: str, hh: int, mm: int, offset_hours: int) -> datetime:
    return datetime.fromisoformat(f"{day}T{hh:02d}:{mm:02d}:00").replace(
        tzinfo=timezone(timedelta(hours=offset_hours)))


def test_a_notice_without_the_column_gets_its_deadline_from_the_body():
    """26-98330: EndDate 2026-11-30+01:00, EndTime 16:00:00.000+02:00 on a single lot."""
    o = from_boamp(NOTICES["single_lot_offset_mismatch"])
    assert o.deadline_at == at("2026-11-30", 16, 0, 2)
    assert o.status == "open"


def test_the_latest_lot_deadline_of_a_multi_lot_notice_is_taken():
    o = from_boamp(NOTICES["thirteen_lots"])      # 26-90291: 13 lots, one deadline
    assert o.deadline_at == at("2026-10-02", 17, 30, 2)
    assert o.lot_count == 13


def test_the_information_request_period_is_not_the_deadline():
    """26-90291 also states AdditionalInformationRequestPeriod, 2026-09-25: a week earlier."""
    o = from_boamp(NOTICES["thirteen_lots"])
    assert o.deadline_at.date().isoformat() == "2026-10-02"


def test_a_negotiated_notice_reads_its_participation_period():
    o = from_boamp(NOTICES["single_lot_negotiated"])
    assert o.deadline_at == at("2026-09-24", 13, 0, 2)
    assert o.lot_count == 1


def test_the_body_beats_a_column_that_carries_the_wall_time_as_utc():
    """26-62315: the body says 15:00:00.000+02:00 (13:00 UTC, as its TED twin
    says); the column says 15:00 UTC. For 12 of 30 notices with a TED twin the column
    differed from TED by exactly the offset."""
    o = from_boamp(NOTICES["column_is_wall_time_as_utc"])
    assert NOTICES["column_is_wall_time_as_utc"]["datelimitereponse"] == "2026-09-14T15:00:00+00:00"
    assert o.deadline_at == at("2026-09-14", 15, 0, 2)
    assert o.deadline_at.astimezone(timezone.utc).hour == 13


def test_where_the_column_is_the_true_instant_the_body_says_the_same():
    """26-74042: 17:00:00+02:00 in the body, 15:00 UTC in the column."""
    o = from_boamp(NOTICES["column_matches_true_instant"])
    assert o.deadline_at == datetime(2026, 9, 14, 15, 0, tzinfo=timezone.utc)


def test_a_notice_whose_body_states_no_period_keeps_the_column():
    record = {**NOTICES["single_lot_negotiated"], "datelimitereponse": "2026-09-30T10:00:00+00:00",
              "donnees": json.dumps({"EFORMS": {"ContractNotice": {}}})}
    assert from_boamp(record).deadline_at == datetime(2026, 9, 30, 10, 0, tzinfo=timezone.utc)


def test_a_part_of_a_notice_is_not_a_lot():
    body = {"EFORMS": {"ContractNotice": {"cac:ProcurementProjectLot": [
        {"cbc:ID": {"#text": "LOT-0001", "@schemeName": "Lot"}},
        {"cbc:ID": {"#text": "PAR-0001", "@schemeName": "Part"}}]}}}
    record = {**NOTICES["single_lot_negotiated"], "donnees": json.dumps(body)}
    assert from_boamp(record).lot_count == 1


def test_the_legacy_and_simplified_shapes_list_their_lots_too():
    legacy = {"OBJET": {"LOTS": {"LOT": [{"N": "1"}, {"N": "2"}, {"N": "3"}]}}}
    simple = {"FNSimple": {"initial": {"lots": {"lot": [{"n": "1"}, {"n": "2"}]}}}}
    for body, expected in ((legacy, 3), (simple, 2), ({"OBJET": {"TITRE_MARCHE": "x"}}, None)):
        record = {**NOTICES["single_lot_negotiated"], "donnees": json.dumps(body)}
        assert from_boamp(record).lot_count == expected
