"""`GET /v1/changes` (WP-10): the real changes of the last 14 days, against a real Postgres.

  - a notice first collected in the window is `new`; an old one, or one only read in by a
    history load (published long before), is not
  - an amendment is a deadline, value, status or procedure change taken from the archive;
    `reread`, `out_of_order`, `remapped` and `correction` versions and a publication-date-only
    version are not amendments
  - one entry per notice per UTC day, lines running from the day's first before to its last after
  - the default scope is core and supply; the scope and the country filter like /v1/tenders
  - a national notice listed under its TED twin is listed once
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, db, stats
from dgate.normalise import Opportunity

pytestmark = pytest.mark.integration

NOW = datetime.now(timezone.utc)
FUTURE = NOW + timedelta(days=30)
LATER = NOW + timedelta(days=45)
TODAY = NOW.date()


@pytest.fixture(autouse=True)
def _fresh_cache():
    stats.reset_cache()
    yield
    stats.reset_cache()


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def opp(native_id: str, *, source: str = "ted", country: str = "FR", kind: str = "core",
        deadline: datetime | None = FUTURE, published: date | None = None,
        value: float | None = None, title: str = "Armoured vehicles",
        ted_ref: str | None = None) -> Opportunity:
    flags = {
        "core": dict(sig_cpv=True, sig_cpv_military=True, dual_use=False, sig_buyer=False),
        "supply": dict(sig_cpv=False, sig_cpv_military=False, dual_use=False, sig_buyer=True),
        "dual": dict(sig_cpv=True, sig_cpv_military=True, dual_use=True, sig_buyer=False),
    }[kind]
    return Opportunity(
        source_code=source, native_id=native_id, buyer_name_raw=f"Ministry {country}",
        title_original=title, country=country, published_at=published or TODAY,
        deadline_at=deadline, cpv_codes=["45000000"] if kind == "supply" else ["35400000"],
        status="open", is_defence=True, value_amount=value, value_currency="EUR" if value else None, ted_ref=ted_ref,
        buyer_class="defence", **flags)


def store(conn, o: Opportunity, tag: str = "a") -> int:
    src = db.source_id(conn, o.source_code)
    o.buyer_org_id = db.resolve_organisation(conn, o.buyer_name_raw, o.country, src_id=src)
    oid, _ = db.upsert_opportunity(conn, o, f"h-{o.source_code}-{o.native_id}-{tag}", src)
    conn.commit()
    return oid


def amend(conn, o: Opportunity, tag: str, **changes) -> Opportunity:
    newer = replace(o, **changes)
    store(conn, newer, tag)
    return newer


def age(conn, oid: int, days: float, *, version: int | None = None) -> None:
    """Make a notice's versions look `days` older. The archive refuses UPDATE of
    `observed_at` (trigger); a test says out loud that it is bypassing that."""
    conn.execute("SET LOCAL session_replication_role = replica")
    conn.execute(
        "UPDATE opportunity_version SET observed_at = observed_at - make_interval(secs => %s), "
        "valid_from = valid_from - make_interval(secs => %s) "
        "WHERE opportunity_id = %s AND (%s::int IS NULL OR version = %s)",
        (days * 86400, days * 86400, oid, version, version))
    conn.execute("SET LOCAL session_replication_role = DEFAULT")
    conn.commit()


def note(conn, oid: int, version: int, kind: str) -> None:
    conn.execute(
        "INSERT INTO opportunity_version_note (opportunity_version_id, kind, note) "
        "SELECT id, %s, 'test' FROM opportunity_version WHERE opportunity_id = %s AND version = %s",
        (kind, oid, version))
    conn.commit()


def feed(client, **params) -> dict:
    r = client.get("/v1/changes", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def by_notice(body: dict) -> dict[str, dict]:
    return {c["tender"]["noticeId"]: c for c in body["items"]}


# ---------------------------------------------------------------- new notices

def test_a_notice_first_collected_today_is_new(client, conn):
    store(conn, opp("N-1"))
    got = feed(client)
    assert got["windowDays"] == 14
    assert got["total"] == 1 and got["counts"] == {"new": 1, "amended": 0}
    item = got["items"][0]
    assert item["kind"] == "new" and item["changes"] == []
    assert item["tender"]["noticeId"] == "N-1" and item["tender"]["title"] == "Armoured vehicles"
    assert item["day"] == TODAY.isoformat()
    assert item["id"] == f"{item['tender']['id']}-{TODAY:%Y%m%d}"


def test_a_notice_first_seen_before_the_window_is_not_listed(client, conn):
    old = store(conn, opp("OLD"))
    age(conn, old, 20)
    assert feed(client)["total"] == 0


def test_an_old_notice_read_in_by_a_history_load_is_not_news(client, conn):
    """First observed today, published long ago: a backfill, not a new notice."""
    store(conn, opp("HIST", published=TODAY - timedelta(days=400)))
    assert feed(client)["total"] == 0


def test_a_notice_published_a_few_days_before_the_window_still_counts(client, conn):
    """TED notices are collected a day or more after their publication date."""
    store(conn, opp("LATE", published=TODAY - timedelta(days=18)))
    assert feed(client)["counts"]["new"] == 1


# ----------------------------------------------------------------- amendments

def test_a_moved_deadline_is_an_amendment_with_before_and_after(client, conn):
    first = opp("A-1")
    oid = store(conn, first)
    age(conn, oid, 20)                       # first seen five days ago
    amend(conn, first, "b", deadline_at=LATER)
    got = feed(client)
    assert got["counts"] == {"new": 0, "amended": 1}
    item = by_notice(got)["A-1"]
    assert item["kind"] == "amended"
    [line] = item["changes"]
    assert line["field"] == "deadline_at" and line["label"] == "Deadline"
    assert line["before"] and line["after"] and line["before"] != line["after"]
    assert item["tender"]["amended"] is True


def test_a_value_status_and_procedure_change_are_listed(client, conn):
    first = opp("A-2", value=100000.0)
    oid = store(conn, first)
    age(conn, oid, 20)
    amend(conn, first, "b", value_amount=250000.0, procedure_type="restricted", status="awarded")
    item = by_notice(feed(client, scope="all"))["A-2"]
    fields = {c["field"]: c for c in item["changes"]}
    assert set(fields) == {"value_amount", "procedure_type", "status"}
    assert fields["value_amount"]["before"] == "EUR 100,000"
    assert fields["value_amount"]["after"] == "EUR 250,000"
    assert fields["status"]["after"] == "Awarded"


def test_several_amendments_of_one_day_are_one_entry(client, conn):
    first = opp("A-3", value=100000.0)
    oid = store(conn, first)
    age(conn, oid, 20)
    second = amend(conn, first, "b", value_amount=200000.0)
    amend(conn, second, "c", value_amount=300000.0, deadline_at=LATER)
    got = feed(client)
    assert got["total"] == 1
    fields = {c["field"]: c for c in got["items"][0]["changes"]}
    assert fields["value_amount"]["before"] == "EUR 100,000"
    assert fields["value_amount"]["after"] == "EUR 300,000"
    assert "deadline_at" in fields


def test_a_change_there_and_back_in_one_day_is_no_entry(client, conn):
    first = opp("A-4", value=100000.0)
    oid = store(conn, first)
    age(conn, oid, 20)
    second = amend(conn, first, "b", value_amount=200000.0)
    amend(conn, second, "c", value_amount=100000.0)
    assert feed(client)["total"] == 0


def test_a_new_notice_amended_the_same_day_is_one_new_entry(client, conn):
    first = opp("A-5", value=100000.0)
    store(conn, first)
    amend(conn, first, "b", value_amount=200000.0)
    got = feed(client)
    assert got["total"] == 1 and got["items"][0]["kind"] == "new"


def test_an_amendment_older_than_the_window_is_not_listed(client, conn):
    first = opp("A-6")
    oid = store(conn, first)
    age(conn, oid, 30)
    amend(conn, first, "b", deadline_at=LATER)
    age(conn, oid, 20, version=2)           # the amendment is 20 days old
    assert feed(client)["total"] == 0


@pytest.mark.parametrize("kind", ["reread", "out_of_order", "remapped", "correction"])
def test_a_version_annotated_as_not_the_publishers_doing_is_not_an_amendment(client, conn, kind):
    first = opp("A-7")
    oid = store(conn, first)
    age(conn, oid, 20)
    amend(conn, first, "b", deadline_at=LATER)
    note(conn, oid, 2, kind)
    assert feed(client)["total"] == 0


def test_a_publication_date_only_or_cpv_only_version_is_not_an_amendment(client, conn):
    first = opp("A-8", published=TODAY - timedelta(days=3))
    oid = store(conn, first)
    age(conn, oid, 20)
    second = amend(conn, first, "b", published_at=TODAY - timedelta(days=2))
    amend(conn, second, "c", cpv_codes=["35400000", "35500000"])
    assert feed(client)["total"] == 0


# ------------------------------------------------------- scope, country, paging

def test_the_default_is_core_and_supply_and_the_scope_filters(client, conn):
    store(conn, opp("CORE-1", kind="core"))
    store(conn, opp("SUP-1", kind="supply"))
    store(conn, opp("DUAL-1", kind="dual"))
    assert set(by_notice(feed(client))) == {"CORE-1", "SUP-1"}
    assert set(by_notice(feed(client, scope="core"))) == {"CORE-1"}
    assert set(by_notice(feed(client, scope="supply"))) == {"SUP-1"}
    assert set(by_notice(feed(client, scope="all"))) == {"CORE-1", "SUP-1", "DUAL-1"}
    assert client.get("/v1/changes", params={"scope": "nonsense"}).status_code == 422


def test_the_country_filter(client, conn):
    store(conn, opp("FR-1", country="FR"))
    store(conn, opp("PL-1", country="PL"))
    assert set(by_notice(feed(client, country="pl"))) == {"PL-1"}
    assert set(by_notice(feed(client, country="FR,PL"))) == {"FR-1", "PL-1"}


def test_a_national_notice_is_listed_once_under_its_ted_twin(client, conn):
    store(conn, opp("TED-1", source="ted"))
    national = store(conn, opp("ES-1", source="es_placsp", country="ES", ted_ref="TED-1"))
    conn.execute("UPDATE opportunity SET ted_ref = 'TED-1' WHERE id = %s", (national,))
    conn.commit()
    assert set(by_notice(feed(client))) == {"TED-1"}


def test_pages_and_totals(client, conn):
    for i in range(5):
        store(conn, opp(f"P-{i}"))
    first = feed(client, pageSize=2)
    assert first["total"] == 5 and len(first["items"]) == 2 and first["page"] == 1
    third = feed(client, pageSize=2, page=3)
    assert len(third["items"]) == 1
    seen = {c["id"] for p in (1, 2, 3) for c in feed(client, pageSize=2, page=p)["items"]}
    assert len(seen) == 5
    assert client.get("/v1/changes", params={"pageSize": 201}).status_code == 422


def test_the_newest_come_first(client, conn):
    older = opp("O-1", value=1000.0)
    oid = store(conn, older)
    age(conn, oid, 6)
    amend(conn, older, "b", deadline_at=LATER)                       # amended today
    two = store(conn, opp("O-2"))
    age(conn, two, 2)                                                # new two days ago
    items = feed(client)["items"]
    assert [(c["tender"]["noticeId"], c["kind"]) for c in items] == [
        ("O-1", "amended"), ("O-2", "new"), ("O-1", "new")]


def test_the_response_carries_no_contact_fields(client, conn):
    store(conn, opp("X-1", title="Supply of boots, contact j.doe@example.org"))
    text = client.get("/v1/changes").text
    assert "j.doe@example.org" not in text
