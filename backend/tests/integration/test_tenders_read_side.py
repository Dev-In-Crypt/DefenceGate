"""The read side of the tenders list (verification of 13 October 2026, package WP-4).

  - a notice with no deadline is not served open when its procedure is over
  - a notice with no value borrows its TED twin's, said so, never stored
  - the lists say when their data was last collected
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, db, stats
from dgate.normalise import Opportunity

pytestmark = pytest.mark.integration

FUTURE = datetime.now(timezone.utc) + timedelta(days=30)
PAST = datetime.now(timezone.utc) - timedelta(days=30)


@pytest.fixture()
def client(conn):
    stats.reset_cache()
    with TestClient(api.app) as c:
        yield c
    stats.reset_cache()


def put(conn, native_id: str, *, source: str = "ted", status: str = "open",
        deadline: datetime | None = FUTURE, published: date = date(2026, 10, 1),
        value: float | None = None, currency: str | None = None, value_kind: str | None = None,
        ted_ref: str | None = None, twin_method: str | None = None, procedure: str | None = None,
        related: str | None = None, title: str = "Armoured vehicles") -> int:
    opp = Opportunity(source_code=source, native_id=native_id, buyer_name_raw="Ministry of Defence",
                      title_original=title, country="FR", published_at=published,
                      deadline_at=deadline, cpv_codes=["35400000"], status=status,
                      is_defence=True, sig_cpv=True, sig_cpv_military=True,
                      value_amount=value, value_currency=currency, value_kind=value_kind,
                      ted_ref=ted_ref, related_native_id=related, procedure_identifier=procedure)
    src = db.source_id(conn, source)
    opp.buyer_org_id = db.resolve_organisation(conn, "Ministry of Defence", "FR", src_id=src)
    oid, _ = db.upsert_opportunity(conn, opp, f"hash-{source}-{native_id}", src)
    conn.execute("UPDATE opportunity SET twin_method = %s, procedure_identifier = %s, "
                 "related_native_id = %s, ted_ref = %s WHERE id = %s",
                 (twin_method, procedure, related, ted_ref, oid))
    conn.commit()
    return oid


def listed(client, **params) -> dict[str, dict]:
    body = client.get("/v1/tenders", params={"scope": "all", "pageSize": 100, **params}).json()
    return {t["noticeId"]: t for t in body["items"]}


# ------------------------------------------------- superseded, no deadline

def test_a_no_deadline_notice_whose_ted_twin_has_passed_is_not_open(client, conn):
    """79 of the 410 notices the default list showed on 13 October 2026 were French
    notices with no deadline whose TED twin's deadline had passed."""
    put(conn, "100-2026", source="ted", deadline=PAST)
    national = put(conn, "26-1", source="fr_boamp", deadline=None, ted_ref="100-2026",
                   twin_method="procedure_id")
    put(conn, "26-2", source="fr_boamp", deadline=None)            # no twin: the 365-day rule

    open_now = listed(client)
    assert set(open_now) == {"26-2"}
    assert open_now["26-2"]["deadlineKnown"] is False
    assert open_now["26-2"]["status"] == "open"

    # shown once, under its twin, and closed
    assert set(listed(client, status="closed")) == {"100-2026"}
    one = client.get(f"/v1/tenders/{national}").json()
    assert one["status"] == "closed" and one["statusNative"] == "expired"
    assert one["deadlineKnown"] is False


def test_a_notice_with_a_deadline_of_its_own_is_not_judged_by_its_twin(client, conn):
    put(conn, "100-2026", source="ted", deadline=PAST)
    put(conn, "ES-1", source="es_placsp", deadline=FUTURE, ted_ref="100-2026",
        twin_method="procedure_id")
    got = listed(client)
    assert got["ES-1"]["status"] == "open" and got["ES-1"]["deadlineKnown"] is True


def test_a_live_ted_twin_leaves_the_national_notice_open(client, conn):
    put(conn, "200-2026", source="ted", deadline=FUTURE)
    national = put(conn, "26-3", source="fr_boamp", deadline=None, ted_ref="200-2026",
                   twin_method="procedure_id", title="Another title")
    assert client.get(f"/v1/tenders/{national}").json()["statusNative"] == "open"


def test_a_notice_followed_by_an_award_of_its_procedure_is_not_open(client, conn):
    put(conn, "26-10", source="fr_boamp", deadline=None, procedure="proc-a",
        published=date(2026, 9, 1))
    put(conn, "26-11", source="fr_boamp", status="awarded", deadline=None, procedure="proc-a",
        published=date(2026, 10, 1), title="Award notice")
    # an award published before the call does not close it
    put(conn, "26-20", source="fr_boamp", deadline=None, procedure="proc-b",
        published=date(2026, 10, 1))
    put(conn, "26-21", source="fr_boamp", status="awarded", deadline=None, procedure="proc-b",
        published=date(2026, 9, 1), title="Earlier award")
    assert set(listed(client)) == {"26-20"}
    assert listed(client, status="closed")["26-10"]["statusNative"] == "expired"


def test_a_parent_with_no_deadline_gives_way_to_its_rectificatif_even_when_that_is_not_open(client, conn):
    parent = put(conn, "26-30", source="fr_boamp", deadline=None)
    put(conn, "26-31", source="fr_boamp", status="unknown", deadline=None, related="26-30",
        title="Rectificatif")
    assert listed(client) == {}
    assert set(listed(client, status="closed")) == {"26-31"}      # shown once, newest wins
    assert client.get(f"/v1/tenders/{parent}").json()["statusNative"] == "expired"


def test_the_opportunities_endpoint_agrees(client, conn):
    put(conn, "100-2026", source="ted", deadline=PAST)
    put(conn, "26-1", source="fr_boamp", deadline=None, ted_ref="100-2026",
        twin_method="procedure_id")
    body = client.get("/v1/opportunities", params={"status": "expired", "scope": "all",
                                                    "collapse": "false"}).json()
    assert [o["native_id"] for o in body if o["source"] == "fr_boamp"] == ["26-1"]
    assert [o["status"] for o in body if o["source"] == "fr_boamp"] == ["expired"]


# ------------------------------------------------------- value from a twin

def one(client, oid: int) -> dict:
    """The notice's own page: the list shows a national notice under its TED twin."""
    return client.get(f"/v1/tenders/{oid}").json()


def stored_value(conn, oid: int):
    return conn.execute("SELECT value_amount FROM opportunity WHERE id = %s",
                        (oid,)).fetchone()["value_amount"]


def test_a_national_notice_borrows_its_ted_twins_value_and_says_so(client, conn):
    twin = put(conn, "300-2026", source="ted", value=15_798_000, currency="EUR", value_kind="total")
    nl = put(conn, "NL-1", source="nl_tenderned", ted_ref="300-2026", twin_method="stated_ted_ref",
             title="Raamovereenkomst")
    got = one(client, nl)
    assert got["estimatedValue"] == {"amount": 15_798_000.0, "currency": "EUR"}
    assert got["valueFrom"] == "ted_twin" and got["valueKind"] == "total"
    assert stored_value(conn, nl) is None, "read time only, the row is never written"
    assert one(client, twin)["valueFrom"] is None
    # and in a list, where it is not collapsed under its twin
    page = client.get("/v1/tenders", params={"q": "Raamovereenkomst", "scope": "all"}).json()
    assert [t["valueFrom"] for t in page["items"]] == ["ted_twin"]


def test_a_value_the_notice_states_itself_is_never_replaced(client, conn):
    put(conn, "301-2026", source="ted", value=9_000_000, currency="EUR", value_kind="total")
    nl = put(conn, "NL-2", source="nl_tenderned", value=5_000, currency="EUR", ted_ref="301-2026",
             twin_method="stated_ted_ref", title="Own value")
    got = one(client, nl)
    assert got["estimatedValue"]["amount"] == 5_000.0 and got["valueFrom"] is None


@pytest.mark.parametrize("kind, amount", [
    ("first_lot", 400_000),     # one lot of several is not the notice's value
    ("total", 0.01),            # TED's placeholders are not prices
    ("total", 1),
])
def test_a_twin_value_that_would_mislead_is_not_borrowed(client, conn, kind, amount):
    put(conn, "302-2026", source="ted", value=amount, currency="EUR", value_kind=kind)
    nl = put(conn, "NL-3", source="nl_tenderned", ted_ref="302-2026", twin_method="stated_ted_ref",
             title="Different lot")
    got = one(client, nl)
    assert got["estimatedValue"] is None and got["valueFrom"] is None


def test_a_linked_by_procedure_twin_must_be_the_same_stage(client, conn):
    """The link by procedure identifier is to the newest TED notice of the procedure,
    which may be the call while the national notice is its award."""
    put(conn, "303-2026", source="ted", status="open", value=700_000, currency="EUR",
        value_kind="estimated")
    award = put(conn, "26-40", source="fr_boamp", status="awarded", deadline=None,
                ted_ref="303-2026", twin_method="procedure_id", title="Award")
    call = put(conn, "26-41", source="fr_boamp", status="open", ted_ref="303-2026",
               twin_method="procedure_id", title="Call")
    stated = put(conn, "26-42", source="fr_boamp", status="awarded", deadline=None,
                 ted_ref="303-2026", twin_method="stated_ted_ref", title="Stated link")
    assert one(client, award)["valueFrom"] is None
    assert one(client, call)["valueFrom"] == "ted_twin"
    assert one(client, stated)["valueFrom"] == "ted_twin"


def test_the_detail_page_borrows_in_the_twins_currency(client, conn):
    put(conn, "304-2026", source="ted", value=227_343.67, currency="PLN", value_kind="total")
    pl = put(conn, "PL-1", source="pl_ezam", ted_ref="304-2026", twin_method="stated_ted_ref",
             title="Polish notice")
    assert one(client, pl)["estimatedValue"] == {"amount": 227_343.67, "currency": "PLN"}


# --------------------------------------------------------------- updatedAt

def _run(conn, code: str, status: str, finished: datetime) -> None:
    run_id = db.start_run(conn, code, expected_min=None)
    db.finish_run(conn, run_id, fetched=1, new=0, changed=0, status="success")
    conn.execute("UPDATE ingest_run SET status = %s, finished_at = %s, started_at = %s "
                 "WHERE id = %s", (status, finished, finished - timedelta(minutes=5), run_id))
    conn.commit()


def test_the_lists_say_when_their_sources_were_last_collected(client, conn):
    base = datetime(2026, 10, 13, 6, 0, tzinfo=timezone.utc)
    assert client.get("/v1/tenders").json()["meta"] == {"updatedAt": None, "updatedBy": None}
    stats.reset_cache()
    _run(conn, "ted", "success", base)
    _run(conn, "fr_boamp", "partial", base + timedelta(hours=1))
    _run(conn, "ted", "failed", base + timedelta(hours=2))          # added nothing
    _run(conn, "eu_portal", "success", base + timedelta(hours=3))   # another list
    meta = client.get("/v1/tenders").json()["meta"]
    assert datetime.fromisoformat(meta["updatedAt"]) == base + timedelta(hours=1)
    # WP-87: the list names the source of that run, so "Data updated" cannot be read as the footer's any-source run
    name = conn.execute("SELECT name FROM source WHERE code = 'fr_boamp'").fetchone()["name"]
    assert meta["updatedBy"] == name
    grants = client.get("/v1/funding").json()["meta"]
    assert datetime.fromisoformat(grants["updatedAt"]) == base + timedelta(hours=3)
    assert grants["updatedBy"] == conn.execute("SELECT name FROM source WHERE code = 'eu_portal'").fetchone()["name"]


# ------------------------------------------------- placeholders, page size

def test_a_value_range_does_not_match_a_placeholder_and_none_is_shown(client, conn):
    """Ids 146218, 146213 (value 0) matched "max EUR 100k" while shown as "Not stated"."""
    zero = put(conn, "T-0", value=0, currency="EUR", title="Zero")
    one = put(conn, "T-1", value=1, currency="EUR", title="One euro")
    small = put(conn, "T-2", value=50_000, currency="EUR", title="Fifty thousand")
    put(conn, "T-3", value=500_000, currency="EUR", title="Half a million")
    assert set(listed(client, max=100000, currency="EUR")) == {"T-2"}
    assert set(listed(client, min=1, currency="EUR")) == {"T-2", "T-3"}
    assert one_page(client, zero)["estimatedValue"] is None
    assert one_page(client, one)["estimatedValue"] is None
    assert one_page(client, small)["estimatedValue"]["amount"] == 50_000.0


def one_page(client, oid: int) -> dict:
    return client.get(f"/v1/tenders/{oid}").json()


def test_same_notice_names_the_other_notice(client, conn):
    twin = put(conn, "400-2026", source="ted", value=1_000_000, currency="EUR", value_kind="total")
    nat = put(conn, "ES-9", source="es_placsp", ted_ref="400-2026", twin_method="procedure_id",
              title="Spanish notice")
    got = one_page(client, nat)["sameNotice"]
    assert got and got[0]["id"] == str(twin) and got[0]["noticeId"] == "400-2026"


def test_a_page_may_hold_250_notices_and_not_251(client, conn):
    assert client.get("/v1/tenders", params={"pageSize": 250}).status_code == 200
    assert client.get("/v1/tenders", params={"pageSize": 251}).status_code == 422
