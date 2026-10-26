"""WP-144: a buyer's units (the names its notices state, folded), without a database."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from dgate import tenders


def row(head, k, raw, n, core=0):
    return {"head": head, "k": k, "raw": raw, "n": n, "core": core}


def test_units_add_up_the_spellings_of_one_name_and_take_the_commonest():
    got = tenders._units_by_head([
        row(1, " politechnika warszawska", "POLITECHNIKA WARSZAWSKA", 5, 5),
        row(1, " politechnika warszawska", "Politechnika Warszawska", 2, 1),
        row(1, " politechnika warszawska wydzial fizyki", "Wydział Fizyki Politechnika Warszawska", 1),
        row(2, " agencja uzbrojenia", "Agencja Uzbrojenia", 9),          # one name: no choice
        row(3, " ", None, 4), row(3, " x", "X", 1),                     # an empty name is no unit
    ])
    assert list(got) == [1]
    assert got[1] == [
        {"key": "politechnika warszawska", "name": "POLITECHNIKA WARSZAWSKA", "tenderCount": 7, "coreCount": 6},
        {"key": "politechnika warszawska wydzial fizyki", "name": "Wydział Fizyki Politechnika Warszawska",
         "tenderCount": 1, "coreCount": 0},
    ]


def test_the_collapse_of_a_units_count_keeps_the_twin_in_the_unit():
    sql = tenders.collapse_clauses(["o.is_defence = TRUE"], same_unit=True)
    for alias in ("t", "c", "r", "p"):           # the TED twin, the rectificatif, the re-publication, the Polish mirror
        assert f"dg_fold({alias}.buyer_name_raw) = dg_fold(o.buyer_name_raw)" in sql
    assert "dg_fold(" not in tenders.collapse_clauses(["o.is_defence = TRUE"])


def test_a_unit_is_read_only_with_its_buyer():
    with pytest.raises(HTTPException) as e:
        tenders._tender_filters(None, None, None, "all", "relevant", None, None, None, None, None, None, None, unit="x")
    assert e.value.status_code == 422
    where, params, _ = tenders._tender_filters(None, None, None, "all", "relevant", None, 7, None, None, None, None, None,
                                               unit="  Politechnika Warszawska ")
    assert where[-2:] == ["NOT o.buyer_withheld", "dg_fold(o.buyer_name_raw) = dg_fold(%s)"]
    assert params[-1] == "Politechnika Warszawska"
    assert tenders._tender_filters(None, None, None, "all", "relevant", None, 7, None, None, None, None, None,
                                   unit="  ")[0][-1] != "dg_fold(o.buyer_name_raw) = dg_fold(%s)"
