"""The market overview, the buyer profile and the source spans (dgate/stats.py).

Counts of notices published over core-scope notices, cached for an hour. Every helper is
checked on a small seeded database, the empty one included, and the two endpoints through
the real application.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import psycopg
import pytest
from fastapi.testclient import TestClient

from dgate import api, db, stats
from dgate.normalise import Opportunity

pytestmark = pytest.mark.integration

TODAY = date(2026, 10, 13)


@pytest.fixture(autouse=True)
def _fresh_cache():
    stats.reset_cache()
    yield
    stats.reset_cache()


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def _put(conn, native_id: str, *, source: str = "ted", buyer: str = "Ministry of Defence",
         country: str | None = "PL", published: date | None = date(2026, 10, 1),
         days: int | None = 30, cpv: tuple[str, ...] = ("35400000",), status: str = "open",
         is_defence: bool = True, sig_legal_basis: bool = False, sig_buyer: bool = False,
         dual_use: bool = False, tag: str = "") -> int:
    """`days` is the response window: the deadline that many days after publication."""
    deadline = (datetime.combine(published, datetime.min.time(), tzinfo=timezone.utc)
                + timedelta(days=days)) if days is not None and published else None
    opp = Opportunity(
        source_code=source, native_id=native_id, buyer_name_raw=buyer, title_original="Notice",
        country=country, published_at=published, deadline_at=deadline, cpv_codes=list(cpv),
        status=status, is_defence=is_defence, sig_cpv=True, sig_buyer=sig_buyer,
        sig_legal_basis=sig_legal_basis, dual_use=dual_use)
    src_id = db.source_id(conn, source)
    opp.buyer_org_id = db.resolve_organisation(conn, buyer, country or "PL", src_id=src_id)
    opp_id, _ = db.upsert_opportunity(
        conn, opp, f"hash-{source}-{native_id}-{published}-{deadline}-{status}{tag}", src_id)
    conn.commit()
    return opp_id


# ------------------------------------------------------------ month series

def test_the_month_series_is_36_months_zero_filled_with_the_ted_share(conn):
    _put(conn, "A", published=date(2026, 10, 2))
    _put(conn, "B", published=date(2026, 10, 3), source="fr_boamp", country="FR")
    _put(conn, "C", published=date(2026, 8, 20))
    _put(conn, "D", published=date(2023, 11, 1))          # the first month of the window
    _put(conn, "E", published=date(2023, 10, 31))         # one day before it
    months = stats.notices_per_month(conn, TODAY)
    assert len(months) == 36
    assert (months[0]["month"], months[-1]["month"]) == ("2023-11", "2026-10")
    by_month = {m["month"]: m for m in months}
    assert by_month["2026-10"] == {"month": "2026-10", "count": 2, "ted": 1, "partial": True}
    assert by_month["2026-09"] == {"month": "2026-09", "count": 0, "ted": 0, "partial": False}
    assert by_month["2026-08"]["count"] == 1 and by_month["2023-11"]["count"] == 1
    assert sum(m["count"] for m in months) == 4


def test_a_notice_published_after_today_is_not_in_any_month(conn):
    _put(conn, "F", published=date(2026, 10, 14))
    assert sum(m["count"] for m in stats.notices_per_month(conn, TODAY)) == 0


def test_only_core_scope_notices_are_counted(conn):
    _put(conn, "CORE")
    _put(conn, "LEGAL", cpv=("90000000",), sig_legal_basis=True)
    _put(conn, "SUPPLY", cpv=("15000000",), sig_buyer=True)               # only the buyer says defence
    _put(conn, "DUAL", dual_use=True)                                     # a military CPV a buyer's own needs explain
    _put(conn, "NOT", is_defence=False)
    assert sum(m["count"] for m in stats.notices_per_month(conn, TODAY)) == 2


# ---------------------------------------------------------- the 12 months

def test_countries_rank_by_notices_and_the_rest_is_one_figure(conn):
    for n in range(3):
        _put(conn, f"PL{n}", country="PL")
    for n in range(2):
        _put(conn, f"DE{n}", country="DE")
    _put(conn, "FR", country="FR")
    _put(conn, "ES", country="ES")
    where, params = stats._scope(TODAY - timedelta(days=365), TODAY)
    top2 = stats.notices_per_country(conn, where, params, top=2)
    assert top2["total"] == 7
    assert [(i["country"], i["count"]) for i in top2["items"]] == [("PL", 3), ("DE", 2)]
    assert top2["other"] == 2
    # a tie is ordered by code, so the figure does not move between runs
    top3 = stats.notices_per_country(conn, where, params, top=3)
    assert [i["country"] for i in top3["items"]] == ["PL", "DE", "ES"]


def test_a_notice_with_no_country_is_in_the_total_and_in_other(conn):
    _put(conn, "PL", country="PL")
    _put(conn, "NOCOUNTRY", country=None)
    where, params = stats._scope(TODAY - timedelta(days=365), TODAY)
    got = stats.notices_per_country(conn, where, params)
    assert got["total"] == 2 and got["other"] == 1
    assert [i["country"] for i in got["items"]] == ["PL"]


def test_the_window_excludes_what_is_older_than_a_year(conn):
    _put(conn, "OLD", published=date(2025, 10, 1))
    _put(conn, "NEW", published=date(2025, 10, 20))
    where, params = stats._scope(TODAY - timedelta(days=stats.WINDOW_DAYS), TODAY)
    assert stats.notices_per_country(conn, where, params)["total"] == 1


def test_sources_are_counted_by_the_source_of_the_notice(conn):
    _put(conn, "A", source="ted")
    _put(conn, "B", source="ted")
    _put(conn, "C", source="fr_boamp", country="FR")
    where, params = stats._scope(TODAY - timedelta(days=365), TODAY)
    got = stats.notices_per_source(conn, where, params)
    assert [(s["id"], s["count"]) for s in got] == [("ted", 2), ("fr_boamp", 1)]
    assert all(s["name"] for s in got)


def test_the_response_window_is_the_middle_number_of_days(conn):
    for n, days in enumerate((10, 20, 30, 40, 50)):
        _put(conn, f"W{n}", days=days)
    _put(conn, "NONE", days=None)                # states no deadline: not in the figure
    _put(conn, "BEFORE", days=-5)                # deadline before publication: a fault
    _put(conn, "FAR", days=4000)                 # more than three years away: a fault
    where, params = stats._scope(TODAY - timedelta(days=365), TODAY)
    got = stats.response_window(conn, where, params)
    assert got == {"notices": 5, "median": 30, "p25": 20, "p75": 40}


def test_the_response_window_of_nothing_is_none_not_zero(conn):
    where, params = stats._scope(TODAY - timedelta(days=365), TODAY)
    assert stats.response_window(conn, where, params) == {
        "notices": 0, "median": None, "p25": None, "p75": None}


def test_cpv_groups_count_a_notice_once_in_each_group_it_has(conn):
    _put(conn, "A", cpv=("35400000", "35410000", "35420000"))     # three codes, one group
    _put(conn, "B", cpv=("35400000", "35810000"))                 # two groups
    _put(conn, "C", cpv=("35810000",))
    where, params = stats._scope(TODAY - timedelta(days=365), TODAY)
    got = stats.cpv_groups(conn, where, params, top=12)
    assert got == [{"group": "354", "count": 2}, {"group": "358", "count": 2}]
    assert stats.cpv_groups(conn, where, params, top=1) == [{"group": "354", "count": 2}]


def test_a_malformed_cpv_code_is_not_a_group(conn):
    _put(conn, "A", cpv=("35400000", "n/a", ""))
    where, params = stats._scope(TODAY - timedelta(days=365), TODAY)
    assert [g["group"] for g in stats.cpv_groups(conn, where, params, top=12)] == ["354"]


def test_the_amendment_share_is_the_timelines_own_rule(conn):
    _put(conn, "STILL")
    _put(conn, "MOVED", days=30)
    _put(conn, "MOVED", days=45)                                  # a deadline extension
    _put(conn, "STAMP", published=date(2026, 10, 1))
    _put(conn, "STAMP", published=date(2026, 10, 2), days=29)     # only the feed date moved
    where, params = stats._scope(TODAY - timedelta(days=365), TODAY)
    got = stats.amendment_share(conn, where, params)
    assert got["notices"] == 3 and got["amended"] == 1 and got["share"] == 0.3333


def test_the_amendment_share_of_nothing_is_none(conn):
    where, params = stats._scope(TODAY - timedelta(days=365), TODAY)
    assert stats.amendment_share(conn, where, params) == {
        "notices": 0, "amended": 0, "share": None}


# ---------------------------------------------------------------- endpoints

def test_the_market_of_an_empty_database_is_all_zeros_and_says_what_it_counts(client):
    body = client.get("/v1/stats/market").json()
    assert body["scope"] == "core" and body["unit"] == "notices published"
    assert body["sourceCount"] == 0 and len(body["months"]) == 36
    assert sum(m["count"] for m in body["months"]) == 0
    assert body["countries"] == {"total": 0, "items": [], "other": 0}
    assert body["amendments"]["share"] is None and body["responseWindow"]["median"] is None
    assert body["cpvGroups"] == [] and body["asOf"]
    assert set(body["basis"]) >= {"months", "countries", "amendments", "responseWindow",
                                  "cpvGroups", "sources"}


def test_the_market_reads_core_notices_and_is_cached_for_the_hour(client, conn):
    day = datetime.now(timezone.utc).date() - timedelta(days=3)
    _put(conn, "A", published=day, country="PL")
    first = client.get("/v1/stats/market").json()
    assert first["sourceCount"] == 1 and first["countries"]["items"] == [
        {"country": "PL", "count": 1}]
    assert first["months"][-1]["count"] + first["months"][-2]["count"] == 1
    _put(conn, "B", published=day, country="DE")
    assert client.get("/v1/stats/market").json()["countries"]["total"] == 1     # cached
    stats.reset_cache()
    assert client.get("/v1/stats/market").json()["countries"]["total"] == 2


def test_a_figure_that_runs_out_of_budget_is_a_503_and_the_retry_redoes_only_it(
        client, conn, monkeypatch):
    """The API role has a 5 s budget. When one figure does not finish, the request fails
    (the API's own 503 with Retry-After) and what was computed stays cached, so the retry
    spends its budget on the figure that failed, not on the five that were done."""
    _put(conn, "A", published=datetime.now(timezone.utc).date())
    calls = {"months": 0, "amendments": 0}
    real_months, real_amend = stats.notices_per_month, stats.amendment_share

    def months(*a, **k):
        calls["months"] += 1
        return real_months(*a, **k)

    def amendments(*a, **k):
        calls["amendments"] += 1
        if calls["amendments"] == 1:
            raise psycopg.errors.QueryCanceled("canceling statement due to statement timeout")
        return real_amend(*a, **k)

    monkeypatch.setattr(stats, "notices_per_month", months)
    monkeypatch.setattr(stats, "amendment_share", amendments)
    first = client.get("/v1/stats/market")
    assert first.status_code == 503 and first.headers["retry-after"]
    second = client.get("/v1/stats/market")
    assert second.status_code == 200 and second.json()["countries"]["total"] == 1
    assert calls == {"months": 1, "amendments": 2}
    assert client.get("/v1/stats/market").status_code == 200 and calls["months"] == 1


def test_the_market_carries_no_company_names(client, conn):
    _put(conn, "A", buyer="Secret Buyer Ltd", published=datetime.now(timezone.utc).date())
    assert "Secret Buyer" not in client.get("/v1/stats/market").text


def test_a_buyer_profile_is_the_buyers_own_core_notices(client, conn):
    today = datetime.now(timezone.utc).date()
    for n in range(3):
        _put(conn, f"A{n}", buyer="Big Buyer", published=date(today.year, 1, 1) if n else today,
             days=20 + n)
    _put(conn, "OLD", buyer="Big Buyer", published=date(today.year - 2, 3, 1), days=40,
         cpv=("35810000",), source="fr_boamp")
    _put(conn, "LAPSED", buyer="Big Buyer", published=date(today.year - 1, 3, 1), days=10)
    _put(conn, "OTHER", buyer="Other Buyer")
    # WP-96: the profile is of the list's default scope (core and supply); a dual-use purchase is in neither
    _put(conn, "DUAL", buyer="Big Buyer", dual_use=True)
    listed = client.get("/v1/buyers").json()["items"]
    slug = next(b["slug"] for b in listed if b["name"] == "Big Buyer")

    body = client.get(f"/v1/buyers/{slug}/profile").json()
    assert body["tenderCount"] == 5 and body["scope"] == "relevant"
    assert body["unit"] == "notices published"
    years = {y["year"]: y["count"] for y in body["perYear"]}
    assert len(body["perYear"]) == stats.BUYER_YEARS
    assert body["perYear"][-1]["year"] == today.year
    assert years[today.year] == 3 and years[today.year - 2] == 1 and years[today.year - 1] == 1
    assert years[today.year - 5] == 0
    assert body["cpvGroups"][0] == {"group": "354", "count": 4}
    assert {c["group"] for c in body["cpvGroups"]} == {"354", "358"}
    assert {(s["id"], s["count"]) for s in body["sources"]} == {("ted", 4), ("fr_boamp", 1)}
    assert body["responseWindow"]["notices"] == 5 and body["responseWindow"]["median"] == 21
    observed = body["amendments"].pop("observedFrom")         # WP-87: since when these notices are watched
    assert body["amendments"] == {"notices": 5, "amended": 0, "share": 0.0} and observed is not None
    # WP-87: the years add up to the total with the notices before them and those without a date
    assert sum(y["count"] for y in body["perYear"]) + body["perYearEarlier"] + body["perYearUndated"] == body["tenderCount"]
    assert body["openNow"] == client.get(f"/v1/buyers/{slug}").json()["openCount"]


def test_an_unknown_buyer_or_one_with_no_core_notice_has_no_profile(client, conn):
    # WP-96: the profile is of the list's default scope: a buyer with only other purchases has one, a buyer with only a
    # dual-use purchase (in no default scope) has none
    _put(conn, "S", buyer="Supply Only", cpv=("15000000",), sig_buyer=True)
    _put(conn, "D", buyer="Dual Only", dual_use=True)
    assert client.get("/v1/buyers/999999-nobody/profile").status_code == 404
    assert client.get("/v1/buyers/not-a-number/profile").status_code == 404
    oid = conn.execute("SELECT id FROM organisation WHERE canonical_name ILIKE 'supply only'"
                       ).fetchone()["id"]
    assert client.get(f"/v1/buyers/{oid}-supply-only/profile").json()["tenderCount"] == 1
    oid = conn.execute("SELECT id FROM organisation WHERE canonical_name ILIKE 'dual only'").fetchone()["id"]
    assert client.get(f"/v1/buyers/{oid}-dual-only/profile").status_code == 404


def test_a_profile_is_cached_per_buyer_and_an_unknown_one_is_not_cached(client, conn):
    _put(conn, "A", buyer="Cached Buyer")
    slug = client.get("/v1/buyers").json()["items"][0]["slug"]
    assert client.get(f"/v1/buyers/{slug}/profile").json()["tenderCount"] == 1
    _put(conn, "B", buyer="Cached Buyer")
    assert client.get(f"/v1/buyers/{slug}/profile").json()["tenderCount"] == 1
    stats.reset_cache()
    assert client.get(f"/v1/buyers/{slug}/profile").json()["tenderCount"] == 2
    assert client.get("/v1/buyers/999999-nobody/profile").status_code == 404
    assert ("buyer", 999999) not in stats._cache


# ------------------------------------------------------------ source spans

def test_each_source_reports_the_span_of_dates_it_holds(client, conn):
    _put(conn, "T1", source="ted", published=date(2024, 3, 1))
    _put(conn, "T2", source="ted", published=date(2026, 9, 30))
    _put(conn, "B1", source="fr_boamp", country="FR", published=date(2026, 1, 15))
    spans = stats.source_spans(conn)
    # WP-20: also how many of them state a value (here none: `_put` states none)
    assert spans["ted"] == {"heldFrom": date(2024, 3, 1), "heldTo": date(2026, 9, 30),
                            "heldCount": 2, "valueStatedCount": 0}
    assert spans["fr_boamp"] == {"heldFrom": date(2026, 1, 15), "heldTo": date(2026, 1, 15),
                                 "heldCount": 1, "valueStatedCount": 0}
    assert "nl_tenderned" not in spans

    listed = {s["id"]: s for s in client.get("/v1/sources").json()["sources"]}
    assert listed["ted"]["heldFrom"] == "2024-03-01" and listed["ted"]["heldTo"] == "2026-09-30"
    assert listed["ted"]["heldCount"] == 2
    # nothing held reads 0 with no dates; a skipped read (a timeout) reads null, see below
    assert listed["nl_tenderned"]["heldCount"] == 0 and listed["nl_tenderned"]["heldFrom"] is None


def test_a_source_span_read_that_times_out_does_not_take_the_source_list_down(
        client, conn, monkeypatch):
    """`/v1/sources` is read by every page's footer."""
    _put(conn, "T1", source="ted")
    calls = []

    def slow(_conn):
        calls.append(1)
        raise psycopg.errors.QueryCanceled("canceling statement due to statement timeout")

    monkeypatch.setattr(stats, "source_spans", slow)
    body = client.get("/v1/sources")
    assert body.status_code == 200
    ted = next(s for s in body.json()["sources"] if s["id"] == "ted")
    assert ted["heldCount"] is None and ted["heldFrom"] is None and ted["name"]
    assert client.get("/v1/sources").status_code == 200
    assert len(calls) == 1                                  # not tried again within the minute
