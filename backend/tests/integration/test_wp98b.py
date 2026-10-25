"""WP-98b (persona round of 23 October 2026, section C items 6 and 7) against a real Postgres: /v1/buyers?cpv= counts and orders
the buyers by their notices under the codes (each once, as the list shows them); /v1/suppliers gives each supplier the contract
values of its wins (WP-95's contract values, per currency) and orders by their sum in one currency; `source=ted` lists the winners
of TED's own result notices only."""

from __future__ import annotations

from dataclasses import replace

import pytest

from dgate import tenders
from tests.integration.test_changes import opp, store
from tests.integration.test_wp95 import award, client, env, madzeal, notice, org  # noqa: F401 - fixtures

pytestmark = pytest.mark.integration


def get(c, path: str, **params) -> dict:
    r = c.get(path, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def put(conn, native_id: str, country: str, cpv: list[str], **kw) -> int:
    return store(conn, replace(opp(native_id, country=country, **kw), cpv_codes=cpv))


# ======================================================================= 6. buyers under the codes

def test_buyers_under_a_code_say_how_many_and_can_be_ordered_by_it(client, conn):  # noqa: F811
    # France: 3 notices, 1 of them under 343; Poland: 2 notices under 343, one of them also forwarded as a national copy
    put(conn, "FR-1", "FR", ["34320000"])
    put(conn, "FR-2", "FR", ["35400000"])
    put(conn, "FR-3", "FR", ["35400000"])
    put(conn, "1-2026", "PL", ["34320000"])
    put(conn, "2-2026", "PL", ["34330000"])
    put(conn, "PL-N-1", "PL", ["34320000"], source="pl_ezam", ted_ref="1-2026")    # the national copy of 1-2026: once
    plain = get(client, "/v1/buyers")
    assert all(b["cpvCount"] is None for b in plain["items"])
    by_total = get(client, "/v1/buyers", cpv="343")
    assert [b["country"] for b in by_total["items"]] == ["FR", "PL"]                 # most tenders first, as before
    assert {b["country"]: b["cpvCount"] for b in by_total["items"]} == {"FR": 1, "PL": 2}
    by_code = get(client, "/v1/buyers", cpv="343", sort="cpv")
    assert [b["country"] for b in by_code["items"]] == ["PL", "FR"]
    assert by_code["total"] == 2
    assert get(client, "/v1/buyers", cpv="343", sort="cpv", country="FR")["items"][0]["cpvCount"] == 1
    # without codes the order is the default one
    assert [b["id"] for b in get(client, "/v1/buyers", sort="cpv")["items"]] == [b["id"] for b in plain["items"]]


def test_a_count_under_the_codes_that_takes_too_long_is_the_plain_count_and_says_so(client, conn, monkeypatch):  # noqa: F811
    put(conn, "1-2026", "PL", ["34320000"])
    put(conn, "PL-N-1", "PL", ["34320000"], source="pl_ezam", ted_ref="1-2026")
    assert get(client, "/v1/buyers", cpv="343")["cpvCountCollapsed"] is True
    # the collapse made slow (a sleep per notice) past a budget of 10 ms: the plain count, the copy counted too
    monkeypatch.setattr(tenders, "UNDER_CODES_MS", 10)
    real = tenders.collapse_clauses
    # one placeholder per collapse rule, as the real clauses carry the filters' (WP-135: four rules)
    slow = "(SELECT true FROM pg_sleep(0.05)) AND " + " AND ".join(["%s::text[] IS NOT NULL"] * (tenders.COLLAPSE_REPEATS - 1))
    monkeypatch.setattr(tenders, "collapse_clauses", lambda w, same_buyer=False: (
        slow if tenders.CPV_HEADS in w else real(w, same_buyer=same_buyer)))
    late = get(client, "/v1/buyers", cpv="343")
    assert late["cpvCountCollapsed"] is False
    assert [b["cpvCount"] for b in late["items"]] == [2]
    # the list's own statements ran with the API's budget, not the 10 ms
    assert late["total"] == 1


# ======================================================================= 6. supplier values

def test_the_supplier_list_gives_the_contract_values_the_profile_sums(client, madzeal):  # noqa: F811
    item = get(client, "/v1/suppliers", q="madzeal")["items"][0]
    profile = get(client, f"/v1/suppliers/{madzeal['org']}")["values"]["byCurrency"]
    assert item["contractValues"] == profile == [{"currency": "EUR", "amount": 1243802.0, "count": 2, "lotEstimates": 0}]


def test_suppliers_can_be_ordered_by_their_contract_values_in_one_currency(client, conn, madzeal):  # noqa: F811
    jae = org(conn, "agencja uzbrojenia", "PL", is_defence_buyer=True)
    pl = org(conn, "mesko", "PL")
    small = org(conn, "small parts", "ES")
    for i, amount in enumerate((3_000_000.0, 4_000_000.0)):
        o = notice(conn, "ted", f"90{i}-2026", buyer=jae, country="PL")
        award(conn, o, pl, "MESKO S.A.", value=(amount, "PLN", "contract"), country="PL")
    for i in range(3):            # more wins than anybody, the smallest values
        o = notice(conn, "ted", f"80{i}-2026", buyer=jae)
        award(conn, o, small, "Small Parts SL", value=(10_000.0, "EUR", "contract"))
    conn.commit()
    names = lambda r: [i["name"].lower().split()[0].strip(",") for i in r["items"]]    # noqa: E731
    assert names(get(client, "/v1/suppliers"))[0] == "madzeal"                     # 6 wins
    eur = get(client, "/v1/suppliers", sort="value-EUR")
    assert names(eur) == ["madzeal", "small", "mesko"]                               # none in EUR: last
    assert eur["total"] == 3
    pln = get(client, "/v1/suppliers", sort="value-PLN")
    assert names(pln)[0] == "mesko"
    assert pln["items"][0]["contractValues"] == [{"currency": "PLN", "amount": 7000000.0, "count": 2, "lotEstimates": 0}]
    assert client.get("/v1/suppliers", params={"sort": "value-eur"}).status_code == 422


def test_the_ted_only_view_leaves_out_the_national_award_results(client, madzeal):  # noqa: F811
    every = get(client, "/v1/suppliers", q="madzeal")["items"][0]
    ted = get(client, "/v1/suppliers", q="madzeal", source="ted")["items"][0]
    assert (every["awardCount"], ted["awardCount"]) == (6, 4)       # the two PLACSP results are out
    assert ted["contractValues"] == []                              # TED's are a ceiling, an estimate, a lot sum, a unit price
    assert client.get("/v1/suppliers", params={"source": "placsp"}).status_code == 422
