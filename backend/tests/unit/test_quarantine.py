"""The bookkeeping of the per-record quarantine, without a database."""

from __future__ import annotations

import pytest

from dgate.pipeline import MAX_QUARANTINED, Quarantine, _record_id


class FakeConn:
    def __init__(self):
        self.statements: list[str] = []

    def execute(self, sql, *args):
        self.statements.append(sql)


def test_a_record_that_passes_is_released_and_leaves_nothing_behind():
    conn, q = FakeConn(), Quarantine("src")
    with q.guard(conn, {"id": "1"}):
        pass
    assert conn.statements == ["SAVEPOINT dgate_record", "RELEASE SAVEPOINT dgate_record"]
    assert q.note() is None and q.outcome() == {}


def test_a_record_error_rolls_back_to_the_savepoint_and_is_listed():
    conn, q = FakeConn(), Quarantine("src")
    with q.guard(conn, {"publicatieId": "N-7"}):
        raise KeyError("x")
    assert conn.statements == ["SAVEPOINT dgate_record", "ROLLBACK TO SAVEPOINT dgate_record",
                               "RELEASE SAVEPOINT dgate_record"]
    assert q.note() == "1 records quarantined: N-7 (KeyError)"
    assert q.outcome()["status"] == "partial"


def test_an_error_that_is_not_the_records_passes_straight_through():
    conn, q = FakeConn(), Quarantine("src")
    with pytest.raises(RuntimeError):
        with q.guard(conn, {"id": "1"}):
            raise RuntimeError("the run's problem")
    assert q.items == []


def test_the_limit_turns_a_pile_of_bad_records_into_a_failure():
    conn, q = FakeConn(), Quarantine("src")
    with pytest.raises(RuntimeError, match="shape has probably changed"):
        for n in range(MAX_QUARANTINED + 1):
            with q.guard(conn, {"id": str(n)}):
                raise ValueError("bad")


def test_merge_keeps_a_runs_own_failure_and_adds_the_note():
    conn, q = FakeConn(), Quarantine("src")
    with q.guard(conn, {"id": "9"}):
        raise TypeError("x")
    assert q.merge("success", None) == ("partial", "1 records quarantined: 9 (TypeError)")
    status, error = q.merge("partial", "3 publications without their detail page")
    assert status == "partial" and error.startswith("3 publications") and "9 (TypeError)" in error


def test_the_note_names_ten_and_counts_the_rest():
    conn, q = FakeConn(), Quarantine("src", limit=100)
    for n in range(13):
        with q.guard(conn, {"id": str(n)}):
            raise ValueError("bad")
    assert q.note().endswith("and 3 more") and q.note().startswith("13 records quarantined")


@pytest.mark.parametrize("record, expected", [
    ({"publication-number": ["123-2026"]}, "123-2026"),
    ({"slug": "call-a"}, "call-a"),
    ({"unrelated": 1}, "?"),
])
def test_a_record_is_named_by_whatever_identifier_its_source_uses(record, expected):
    assert _record_id(record) == expected
