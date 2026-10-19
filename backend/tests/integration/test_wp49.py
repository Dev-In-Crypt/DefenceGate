"""WP-49: the currency filter, the reason for an empty budget, the sources that read no value, the buyer list cost and
the bound on database connections, through the API."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, config, db, stats, tenders
from dgate.normalise import Call, Opportunity

pytestmark = pytest.mark.integration

NOW = datetime.now(timezone.utc)
FUTURE = NOW + timedelta(days=30)


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def _tender(conn, native_id: str, *, value: float | None = None, currency: str | None = None, country: str = "PL",
            buyer: str = "Ministry of Defence", source: str = "ted", deadline: datetime | None = FUTURE) -> int:
    opp = Opportunity(
        source_code=source, native_id=native_id, buyer_name_raw=buyer, title_original="Armoured vehicles",
        country=country, published_at=date(2026, 10, 1), deadline_at=deadline, cpv_codes=["35400000"], status="open",
        is_defence=True, sig_cpv=True, value_amount=value, value_currency=currency)
    src = db.source_id(conn, source)
    opp.buyer_org_id = db.resolve_organisation(conn, buyer, country, src_id=src)
    opp_id, _ = db.upsert_opportunity(conn, opp, f"hash-{source}-{native_id}", src)
    conn.commit()
    return opp_id


def _call(conn, native_id: str, *, programme: str = "HORIZON", source: str = "eu_portal", budget: float | None = None,
          currency: str | None = None, conditions: dict | None = None, country: str | None = None) -> None:
    call = Call(
        programme_code=programme, native_id=native_id, title=f"Call {native_id}", topic_code=f"{programme}-{native_id}",
        deadline_at=NOW + timedelta(days=20), status="open", regime="defence", budget=budget, currency=currency,
        budget_scope="topic" if budget is not None else None, country=country, conditions_raw=conditions)
    db.upsert_call(conn, call, f"hash-{programme}-{native_id}", db.source_id(conn, source))
    conn.commit()


def _notices(client, **params) -> list[str]:
    body = client.get("/v1/tenders", params={"status": "all", "scope": "all", **params}).json()
    return sorted(t["noticeId"] for t in body["items"])


def _topics(client, **params) -> list[str]:
    body = client.get("/v1/funding", params={"status": "all", **params}).json()
    return sorted(c["topicId"].rsplit("-", 1)[-1] for c in body["items"])


# ------------------------------------------------------------------ the currency filter (tenders)

def test_a_currency_alone_lists_the_notices_that_state_a_value_in_it(client, conn):
    _tender(conn, "EUR1", value=1_000_000, currency="EUR")
    _tender(conn, "PLN1", value=9_000_000, currency="PLN")
    _tender(conn, "PLN2", value=250_000, currency="PLN")
    _tender(conn, "PLNX", value=1, currency="PLN")            # a placeholder is "not stated"
    _tender(conn, "NONE")
    assert _notices(client) == ["EUR1", "NONE", "PLN1", "PLN2", "PLNX"]          # no currency: no filter
    assert _notices(client, currency="PLN") == ["PLN1", "PLN2"]
    assert _notices(client, currency="pln") == ["PLN1", "PLN2"]
    assert _notices(client, currency="EUR") == ["EUR1"]                           # explicit EUR is a filter too
    assert _notices(client, currency="SEK") == []


def test_a_range_still_reads_in_its_currency_and_eur_when_none_is_given(client, conn):
    _tender(conn, "EUR1", value=1_000_000, currency="EUR")
    _tender(conn, "PLN1", value=9_000_000, currency="PLN")
    _tender(conn, "PLN2", value=250_000, currency="PLN")
    assert _notices(client, min=500_000) == ["EUR1"]                              # unchanged: EUR by default
    assert _notices(client, min=500_000, currency="PLN") == ["PLN1"]
    assert _notices(client, min=100_000, max=300_000, currency="PLN") == ["PLN2"]
    assert _notices(client, min=100_000, currency="PLN") == ["PLN1", "PLN2"]


def test_the_export_and_the_scope_counts_follow_the_currency_the_same_way(client, conn):
    _tender(conn, "EUR1", value=1_000_000, currency="EUR")
    _tender(conn, "PLN1", value=9_000_000, currency="PLN")
    got = client.get("/v1/tenders/export", params={"status": "all", "scope": "all", "currency": "PLN"}).json()
    assert [t["noticeId"] for t in got["items"]] == ["PLN1"]
    counts = client.get("/v1/tenders/scope-counts", params={"status": "all", "currency": "PLN"}).json()
    every = client.get("/v1/tenders/scope-counts", params={"status": "all"}).json()
    assert counts["relevant"] == 1 and every["relevant"] == 2


def test_a_bad_currency_is_refused_not_ignored(client, conn):
    assert client.get("/v1/tenders", params={"currency": "EURO"}).status_code == 422
    assert client.get("/v1/funding", params={"currency": "E"}).status_code == 422


# ------------------------------------------------------------------ the currency filter (funding)

def test_a_currency_alone_lists_the_calls_that_state_a_budget_in_it(client, conn):
    _call(conn, "eur", budget=5_000_000, currency="EUR")
    _call(conn, "sek", programme="SE-VINNOVA", source="se_vinnova", budget=2_000_000, currency="SEK", country="SE")
    _call(conn, "none")
    assert _topics(client) == ["eur", "none", "sek"]
    assert _topics(client, currency="SEK") == ["sek"]
    assert _topics(client, currency="EUR") == ["eur"]
    assert _topics(client, min=1_000_000) == ["eur"]                              # unchanged
    assert _topics(client, min=1_000_000, currency="SEK") == ["sek"]


# ------------------------------------------------------------------ why a call has no budget

def _note(client, topic: str):
    items = client.get("/v1/funding", params={"status": "all"}).json()["items"]
    return next(c for c in items if c["topicId"].endswith(f"-{topic}"))["budgetNote"]


def test_a_call_without_a_budget_says_why_and_one_with_a_budget_says_nothing(client, conn):
    _call(conn, "eic", conditions={"budget_line": {"action": "x", "budgetYearMap": {"2026": "0"}}})
    _call(conn, "edip", programme="EDF", conditions={"budget_line": {"action": "y", "budgetYearMap": {}}})
    _call(conn, "unlisted")
    _call(conn, "paid", budget=3_000_000, currency="EUR")
    _call(conn, "vin", programme="SE-VINNOVA", source="se_vinnova", country="SE")
    _call(conn, "aid", programme="FR-AID", source="fr_aid", country="FR", conditions={"max_aid_eur_per_project": 400000})
    assert _note(client, "eic")["reason"] == "portal_zero"
    assert _note(client, "edip")["reason"] == "portal_empty"
    assert _note(client, "unlisted")["reason"] == "portal_no_line"
    assert _note(client, "paid") is None
    assert _note(client, "vin")["reason"] == "source_no_field" and _note(client, "vin")["perProject"] is None
    assert _note(client, "aid")["perProject"] == {"amount": 400000.0, "currency": "EUR"}


# ------------------------------------------------------------------ the sources that read no value

def test_the_source_list_says_which_tender_sources_read_a_value(client, conn):
    sources = {s["id"]: s for s in client.get("/v1/sources").json()["sources"]}
    assert sources["pl_ezam"]["valueRead"] is False and sources["nl_tenderned"]["valueRead"] is False
    assert sources["ted"]["valueRead"] is True and sources["fr_boamp"]["valueRead"] is True
    assert sources["eu_portal"]["valueRead"] is None                              # a grant source has no estimated value


# ------------------------------------------------------------------ the buyer list

def test_the_buyer_aggregate_is_computed_once_for_every_filter_and_the_filters_still_work(client, conn, monkeypatch, request):
    _tender(conn, "A1", buyer="Ministry of Defence", country="PL")
    _tender(conn, "A2", buyer="Ministry of Defence", country="PL")
    _tender(conn, "S1", buyer="Ejercito de Tierra", country="ES")
    monkeypatch.setenv("DGATE_LIST_CACHE_SECONDS", "60")
    config.reset_cache()
    stats.reset_cache()
    request.addfinalizer(stats.reset_cache)            # what this test cached must not reach the next one
    runs: list[int] = []
    real = tenders.aggregate_sql
    monkeypatch.setattr(tenders, "aggregate_sql", lambda: (runs.append(1), real())[1])

    names = lambda **p: [b["name"] for b in client.get("/v1/buyers", params=p).json()["items"]]  # noqa: E731
    assert names() == ["Ministry of Defence", "Ejercito de Tierra"]
    assert names(country="ES") == ["Ejercito de Tierra"]
    assert names(q="ministry") == ["Ministry of Defence"]
    assert names(hasOpen="true", sort="name") == ["Ejercito de Tierra", "Ministry of Defence"]
    assert client.get("/v1/buyers", params={"country": "ES", "page": 2}).json()["items"] == []
    assert len(runs) == 1                                        # five distinct queries, one pass over the notices


def test_without_a_cache_each_buyer_request_reads_the_data_it_has_now(client, conn):
    """The suite runs with the cache off (conftest): a notice added between two reads shows."""
    _tender(conn, "A1", buyer="Ministry of Defence")
    assert client.get("/v1/buyers").json()["total"] == 1
    _tender(conn, "S1", buyer="Ejercito de Tierra", country="ES")
    assert client.get("/v1/buyers").json()["total"] == 2


# ------------------------------------------------------------------ the bound on connections

def test_a_saturated_pool_answers_503_with_retry_after_and_the_health_check_still_answers(client, conn, monkeypatch):
    monkeypatch.setenv("DGATE_API_CONNECTIONS", "1")
    monkeypatch.setenv("DGATE_POOL_WAIT_MS", "100")
    config.reset_cache()
    cfg = config.settings()
    with db.bounded_connect(cfg.api_dsn or cfg.dsn, cfg.api_connections, 1):       # the one slot is taken
        busy = client.get("/v1/sources")
        assert busy.status_code == 503 and busy.headers["retry-after"] == "2"
        assert "busy" in busy.json()["detail"]
        assert client.get("/v1/health").status_code == 200                         # uses the reserved headroom
    assert client.get("/v1/sources").status_code == 200                            # freed: served again


def test_a_burst_over_the_bound_is_served_in_turn_not_refused(client, conn, monkeypatch):
    import concurrent.futures as cf

    monkeypatch.setenv("DGATE_API_CONNECTIONS", "2")
    monkeypatch.setenv("DGATE_POOL_WAIT_MS", "5000")
    config.reset_cache()
    with cf.ThreadPoolExecutor(8) as pool:
        codes = list(pool.map(lambda _: client.get("/v1/sources").status_code, range(16)))
    assert codes == [200] * 16
