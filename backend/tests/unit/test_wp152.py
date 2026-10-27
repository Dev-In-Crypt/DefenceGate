"""WP-152: competitor intelligence from the market's stored contract rows (`competition.analyse`), and the switch of the
paid company report (`billing.may`)."""

from __future__ import annotations

from dgate import billing, competition, config


def body(rows: list[tuple]) -> dict:
    cols = ("org", "k", "head", "country", "cpv", "cur", "amt")
    out = {c: [r[i] for r in rows] for i, c in enumerate(cols)}
    return {**out, "buyer": out["head"], "day": ["2026-01-01"] * len(rows), "since": "2023-10-27", "placspPublic": False}


ROWS = [
    (1, 10, 100, "DE", ["35410000"], "EUR", 1_000_000.0),
    (1, 11, 100, "DE", ["35410000", "34100000"], "EUR", 3_000_000.0),
    (1, 12, 200, "PL", ["35300000"], "PLN", 5_000_000.0),
    (1, 13, 200, "PL", ["35300000"], None, None),
    (2, 10, 100, "DE", ["35410000"], None, None),            # co-winner of contract 10: one contract in the slice
    (2, 20, 100, "DE", ["35410000"], "EUR", 2_000_000.0),
    (3, 30, 200, "PL", ["35300000"], "PLN", 1_000_000.0),
    (3, 31, 100, "DE", ["72000000"], None, None),             # same buyer, another class: no shared market
    (4, 40, 300, "FR", ["35410000"], None, None),             # same class, another buyer: no competitor
    (5, 50, None, "DE", ["35410000"], None, None),            # buyer withheld: in no market
]


def test_competitors_share_a_buyer_and_a_cpv_class_and_are_ranked_by_overlap():
    got = competition.analyse(competition.index(body(ROWS)), 1)
    assert got["contracts"] == 4 and got["markets"] == 3 and got["competitorCount"] == 2
    assert got["competitors"] == [
        {"org": 2, "overlap": 2, "markets": 1, "buyers": 1, "ours": 2},
        {"org": 3, "overlap": 1, "markets": 1, "buyers": 1, "ours": 2}]


def test_where_it_wins_and_its_typical_contract_value():
    got = competition.analyse(competition.index(body(ROWS)), 1)
    assert got["byCountry"] == [{"key": "DE", "contracts": 2}, {"key": "PL", "contracts": 2}]
    assert got["byClass"] == [{"key": "3530", "contracts": 2}, {"key": "3541", "contracts": 2},
                              {"key": "3410", "contracts": 1}]
    # the median of its contract values in its commonest currency; one contract states none, one is in another currency
    assert got["size"] == {"currency": "EUR", "median": 2_000_000.0, "valued": 2, "otherCurrencies": 1}
    assert got["withoutValue"] == 1


def test_its_share_counts_a_contract_of_several_winners_once_and_sums_one_currency():
    got = competition.analyse(competition.index(body(ROWS)), 1)
    by_class = {s["key"]: s for s in got["shareByClass"]}
    # contracts 10 (two winners), 11, 20, 40 and 50 (a withheld buyer is in no market, its contract is in the slice)
    assert by_class["3541"] == {"key": "3541", "contracts": 2, "total": 5, "currency": "EUR", "value": 4_000_000.0,
                                "valued": 2, "valueTotal": 6_000_000.0, "valuedTotal": 3}
    pl = {s["key"]: s for s in got["shareByCountry"]}["PL"]
    assert (pl["contracts"], pl["total"], pl["currency"], pl["value"], pl["valueTotal"]) == (2, 3, "PLN", 5_000_000.0,
                                                                                            6_000_000.0)


def test_a_company_without_rows_has_no_answer_and_a_rebuilt_snapshot_is_reindexed():
    b = body(ROWS)
    ix = competition.index(b)
    assert competition.index(b) is ix and competition.analyse(ix, 99) is None
    assert competition.index(body(ROWS)) is not ix


def test_the_company_report_is_nobodys_while_its_switch_is_off(monkeypatch):
    free = {"sub_plan": None, "sub_status": None, "sub_period_end": None}
    monkeypatch.delenv("DGATE_COMPANY_REPORT_OPEN", raising=False)
    config.reset_cache()
    assert not billing.may(free, "company_report") and "company_report" not in billing.features(free)
    monkeypatch.setenv("DGATE_COMPANY_REPORT_OPEN", "1")
    config.reset_cache()
    try:
        assert billing.may(free, "company_report")     # nothing on sale yet: nothing withheld (WP-124)
        assert billing.allows("consultant", "company_report") and not billing.allows("pro", "company_report")
    finally:
        monkeypatch.delenv("DGATE_COMPANY_REPORT_OPEN")
        config.reset_cache()
