"""The CORDIS connector (WP-26): robots first, keyset pages, tolerant record readers. No network."""

from __future__ import annotations

import json
import re
from datetime import date

import httpx
import pytest

from dgate.sources import cordis

ROBOTS_OPEN_SPARQL = """User-agent: *
Disallow: /data/
Disallow: /search
"""
ROBOTS_CLOSED = """User-agent: *
Disallow: /datalab/
"""


def _bindings(rows: list[dict[str, str]]) -> dict:
    return {"results": {"bindings": [{k: {"type": "literal", "value": v} for k, v in r.items()}
                                     for r in rows]}}


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _sparql(client: httpx.Client) -> cordis.Sparql:
    return cordis.Sparql(client, min_interval=0, sleep=lambda s: None)


def test_it_reads_the_sparql_path_that_robots_allows_and_never_the_data_files():
    sp = _sparql(_client(lambda r: httpx.Response(200, text=ROBOTS_OPEN_SPARQL)))
    sp.check_robots()                                    # the bulk files are disallowed, SPARQL is not
    assert "/data/" in ROBOTS_OPEN_SPARQL
    assert cordis.SPARQL_URL.startswith("https://cordis.europa.eu/datalab/")


def test_it_refuses_to_start_when_robots_disallows_the_sparql_path():
    sp = _sparql(_client(lambda r: httpx.Response(200, text=ROBOTS_CLOSED)))
    with pytest.raises(cordis.RobotsDisallowed):
        sp.check_robots()


def test_it_refuses_to_start_when_robots_cannot_be_read():
    sp = _sparql(_client(lambda r: httpx.Response(503)))
    with pytest.raises(cordis.RobotsDisallowed):
        sp.check_robots()


def test_pages_are_read_by_keyset_and_end_on_a_short_page():
    asked: list[str] = []
    keys = [f"k{i:02d}" for i in range(5)]

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params["query"]
        asked.append(query)
        m = re.search(r'FILTER \(STR\(\?x\) > "[^"]*?/([^/"]*)"\)', query)
        after = m.group(1) if m else ""
        limit = int(re.search(r"LIMIT (\d+)", query).group(1))
        rest = [k for k in keys if k > after][:limit]
        return httpx.Response(200, json=_bindings([{"key": k, "rcn": k} for k in rest]))

    sp = _sparql(_client(handler))
    pages = list(sp.pages("projects", limit=2))
    assert [[r["key"] for r in p["rows"]] for p in pages] == [["k00", "k01"], ["k02", "k03"], ["k04"]]
    assert [p["after"] for p in pages] == ["", "k01", "k03"]
    assert "FILTER" not in asked[0] and 'k01"' in asked[1]
    # the service is asked in a form that groups per entity, so a row is never half a project
    assert "GROUP BY ?x ORDER BY STR(?x)" in asked[0]


def test_a_page_of_exactly_the_limit_is_followed_by_one_more_request():
    n = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        n["calls"] += 1
        return httpx.Response(200, json=_bindings([{"key": "a"}, {"key": "b"}]) if n["calls"] == 1
                              else _bindings([]))

    pages = list(_sparql(_client(handler)).pages("organisations", limit=2))
    assert len(pages) == 1 and n["calls"] == 2


def test_requests_are_spaced_by_the_minimum_interval():
    now = [0.0]
    waits: list[float] = []

    def sleep(s: float) -> None:
        waits.append(s)
        now[0] += s

    sp = cordis.Sparql(_client(lambda r: httpx.Response(200, json=_bindings([]))), min_interval=1.0,
                       sleep=sleep, clock=lambda: now[0])
    sp.select("select * where {}")
    sp.select("select * where {}")
    assert waits == [pytest.approx(1.0)]


def test_a_server_error_is_retried_before_it_is_given_up(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] < 3 else httpx.Response(200, json=_bindings([]))

    assert _sparql(_client(handler)).select("select * where {}") == []
    assert calls["n"] == 3


# ------------------------------------------------------------------ the record readers

def test_a_project_row_becomes_a_record_with_its_programme():
    rec = cordis.project_record({
        "key": "x", "rcn": "230238", "ga": "953040", "title": "Community\nEnergy \x19 for RES",
        "acronym": "COME RES", "start": "2020-09-01", "end": "2023-02-28", "duration": "30",
        "status": "CLOSED", "cost": "2998847.5", "fund": "2998847.5",
        "call": "H2020-LC-SC3-2020-RES-IA-CSA", "topic": "H2020_LC-SC3-RES-28-2018-2019-2020"})
    assert rec.programme == "H2020" and rec.start == date(2020, 9, 1)
    assert rec.title == "Community Energy for RES"
    assert rec.eu_contribution == 2998847.5 and rec.duration_months == 30


@pytest.mark.parametrize("topic,call,ga,start,expected", [
    ("HORIZON_HORIZON-CL4-2021-X", None, "101021111", date(2021, 5, 1), "HORIZON"),
    ("FP7_SEC-2013-1", None, "607000", date(2013, 1, 1), "FP7"),
    (None, "FP7-ICT-2009-4", None, None, "FP7"),
    (None, "ERC-2014-STG", "638000", date(2015, 1, 1), "H2020"),       # the date decides
    (None, None, "101055555", date(2022, 1, 1), "HORIZON"),
    (None, None, "250000", date(2010, 1, 1), "FP7"),
    (None, None, None, None, None),
])
def test_the_framework_programme_comes_from_the_topic_then_the_call_then_the_dates(
        topic, call, ga, start, expected):
    assert cordis.programme_of(topic, call, ga, start) == expected


def test_a_project_without_a_title_or_record_number_is_skipped():
    assert cordis.project_record({"key": "x", "rcn": "1"}) is None
    assert cordis.project_record({"key": "x", "title": "T"}) is None


def test_zero_total_cost_is_not_a_cost():
    rec = cordis.project_record({"rcn": "1", "title": "T", "cost": "0", "fund": "1000"})
    assert rec.total_cost is None and rec.eu_contribution == 1000.0


def test_organisation_countries_use_iso_codes():
    assert cordis.country_of("UK") == "GB" and cordis.country_of("EL") == "GR"
    assert cordis.country_of("DE") == "DE" and cordis.country_of("") is None
    assert cordis.country_of("DEU") is None


def test_an_organisation_row_keeps_a_nine_digit_pic_only():
    rec = cordis.org_record({"key": "u", "pic": "999847192", "name": "MALMO UNIVERSITET",
                             "country": "SE"})
    assert rec.pic == "999847192" and rec.country == "SE"
    assert cordis.org_record({"key": "u", "pic": "12", "name": "X", "country": "SE"}).pic is None
    assert cordis.org_record({"key": "u", "pic": "999847192", "country": "SE"}) is None


def test_the_roles_are_named_the_way_the_schema_names_them():
    rows = [("coordinator", "coordinator"), ("thirdParty", "third_party"),
            ("associatedPartner", "associated_partner"), ("participant", "participant")]
    for raw, expected in rows:
        assert cordis.role_record({"project": "1", "org": "o", "role": raw}).role == expected
    assert cordis.role_record({"project": "1", "org": "o", "role": "mystery"}) is None


def test_the_queries_ask_for_commercial_facts_only():
    for kind in ("organisations", "projects", "roles"):
        text = cordis._query(kind, "", 10)
        for forbidden in ("abstract", "keyword", "hasResult", "objective"):
            assert forbidden not in text
    assert "SELECT" in json.dumps(cordis._count_query("roles"))


def test_a_key_that_is_not_an_identifier_is_never_sent_back_into_a_query():
    bad = 'k" ) } SELECT * WHERE { ?s ?p ?o'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_bindings([{"key": "a"}, {"key": bad}]))

    with pytest.raises(ValueError, match="unexpected key"):
        list(_sparql(_client(handler)).pages("organisations", limit=2))
