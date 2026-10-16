"""Buyer families (WP-22, migration 0055): one body under several organisation rows is one
buyer on the list, the buyer page, the tender filter, the profile and a followed buyer's
changes. Display layer: no organisation, alias or notice is changed, and emptying
`buyer_family_member` undoes it."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import accounts, api, db, stats
from dgate.normalise import Opportunity
from dgate.ops import buyer_families, suppress

from .test_accounts import (  # noqa: F401 - fixtures and helpers of the account tests
    H,
    sent,
    sign_in,
)

pytestmark = pytest.mark.integration

FUTURE = datetime.now(timezone.utc) + timedelta(days=30)
LONG = "Bundesamt für Ausrüstung, Informationstechnik und Nutzung der Bundeswehr"
LONG_NORM = "bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr"


@pytest.fixture(autouse=True)
def _fresh_cache():
    stats.reset_cache()
    yield
    stats.reset_cache()


@pytest.fixture()
def client(conn, sent):  # noqa: F811
    accounts._cache.clear()
    with TestClient(api.app) as c:
        yield c
    accounts._cache.clear()


def put(conn, native_id: str, buyer: str, *, country="DE", source="ted", ted_ref=None,
        deadline=FUTURE, title="Armoured vehicles") -> int:
    opp = Opportunity(source_code=source, native_id=native_id, buyer_name_raw=buyer,
                      title_original=title, country=country, published_at=date.today(),
                      deadline_at=deadline, cpv_codes=["35400000"], status="open",
                      is_defence=True, sig_cpv=True, sig_cpv_military=True, dual_use=False,
                      buyer_class="defence", ted_ref=ted_ref)
    src = db.source_id(conn, source)
    opp.buyer_org_id = db.resolve_organisation(conn, buyer, country, src_id=src)
    oid, _ = db.upsert_opportunity(conn, opp, f"hash-{native_id}-{title}-{deadline}", src)
    conn.commit()
    return oid


def org_of(conn, oid: int) -> int:
    return conn.execute("SELECT buyer_org_id AS o FROM opportunity WHERE id = %s", (oid,)).fetchone()["o"]


@pytest.fixture()
def baainbw(conn):
    """Three rows of one office (the long name, 3 notices; BAAINBw, 2; BAAINBw Koblenz, 1) and
    a Bundeswehr service centre that must stay alone."""
    for i in range(3):
        put(conn, f"L-{i}", LONG)
    for i in range(2):
        put(conn, f"S-{i}", "BAAINBw")
    put(conn, "K-0", "BAAINBw Koblenz")
    put(conn, "D-0", "Bundeswehr-Dienstleistungszentrum Köln")
    return {n: conn.execute("SELECT id FROM organisation WHERE canonical_name = %s", (n,)).fetchone()["id"]
            for n in (LONG_NORM, "baainbw", "baainbw koblenz")}


def families(conn) -> dict[int, int]:
    return {r["org_id"]: r["head_org_id"]
            for r in conn.execute("SELECT org_id, head_org_id FROM buyer_family_member").fetchall()}


# ------------------------------------------------------------------ the tool

def test_a_dry_run_writes_nothing_and_a_run_is_idempotent(conn, baainbw):
    head = baainbw[LONG_NORM]
    counts = buyer_families.run(conn)
    assert counts["groups"] == 1 and counts["members"] == 2 and families(conn) == {}
    assert buyer_families.run(conn, write=True)["written"] == 2
    assert families(conn) == {baainbw["baainbw"]: head, baainbw["baainbw koblenz"]: head}
    again = buyer_families.run(conn, write=True)
    assert (again["written"], again["removed"]) == (0, 0)
    row = conn.execute("SELECT method, confidence FROM buyer_family_member WHERE org_id = %s",
                       (baainbw["baainbw"],)).fetchone()
    assert (row["method"], float(row["confidence"])) == ("rule:baainbw", 0.90)


def test_a_row_no_rule_produces_any_more_is_deleted_and_nothing_else_is_touched(conn, baainbw):
    buyer_families.run(conn, write=True)
    other = conn.execute("SELECT id FROM organisation WHERE canonical_name LIKE 'bundeswehr-dienst%'"
                         ).fetchone()["id"]
    conn.execute("INSERT INTO buyer_family_member (org_id, head_org_id, method, confidence) "
                 "VALUES (%s, %s, 'stale', 0.9)", (other, baainbw["baainbw"]))
    conn.commit()
    before = conn.execute("SELECT count(*) n FROM organisation").fetchone()["n"]
    assert buyer_families.run(conn, write=True)["removed"] == 1
    assert other not in families(conn)
    assert conn.execute("SELECT count(*) n FROM organisation").fetchone()["n"] == before
    assert conn.execute("SELECT count(*) n FROM organisation_alias WHERE organisation_id = %s",
                        (other,)).fetchone()["n"] >= 1


def test_the_buyer_of_every_notice_is_unchanged(conn, baainbw):
    ids = {r["id"]: r["buyer_org_id"] for r in conn.execute("SELECT id, buyer_org_id FROM opportunity")}
    buyer_families.run(conn, write=True)
    assert ids == {r["id"]: r["buyer_org_id"] for r in conn.execute("SELECT id, buyer_org_id FROM opportunity")}


def test_an_organisation_suppressed_on_request_leaves_its_family(conn, baainbw):
    buyer_families.run(conn, write=True)
    head = baainbw[LONG_NORM]
    suppress.add(conn, kind="organisation", source=None, native_id=None, organisation=head,
                 reason="request", requested_at=datetime.now(timezone.utc), decided_by="test")
    conn.commit()
    assert families(conn) == {}                               # the family is gone with its head
    assert buyer_families.run(conn, write=True)["groups"] == 1    # the two others are still a family
    assert head not in set(families(conn)) | set(families(conn).values())


# ------------------------------------------------------------------ the read side

def test_the_list_shows_one_card_per_family_with_summed_counts(client, conn, baainbw):
    assert client.get("/v1/buyers").json()["total"] == 4               # three rows and the centre
    buyer_families.run(conn, write=True)
    body = client.get("/v1/buyers").json()
    assert body["total"] == 2
    top, other = body["items"]
    assert (top["tenderCount"], top["nameVariants"]) == (6, 2)
    assert top["name"] == LONG and top["id"] == str(baainbw[LONG_NORM])
    assert (other["tenderCount"], other["nameVariants"]) == (1, 0)
    assert top["openCount"] == 6


def test_search_finds_a_family_by_the_name_of_any_member(client, conn, baainbw):
    buyer_families.run(conn, write=True)
    for q in ("koblenz", "baainbw", "Ausrüstung", "informationstechnik"):
        items = client.get("/v1/buyers", params={"q": q}).json()["items"]
        assert [i["tenderCount"] for i in items] == [6], q
    assert client.get("/v1/buyers", params={"q": "koblenz", "page": 2}).json()["items"] == []
    assert client.get("/v1/buyers", params={"hasOpen": "true"}).json()["total"] == 2


def test_the_page_of_a_member_shows_the_family(client, conn, baainbw):
    buyer_families.run(conn, write=True)
    head = baainbw[LONG_NORM]
    for member in (head, baainbw["baainbw"], baainbw["baainbw koblenz"]):
        b = client.get(f"/v1/buyers/{member}").json()
        assert (b["id"], b["tenderCount"], b["nameVariants"]) == (str(head), 6, 2), member
        p = client.get(f"/v1/buyers/{member}/profile").json()
        assert (p["buyerId"], p["tenderCount"], p["openNow"]) == (str(head), 6, 6), member
        assert sum(s["count"] for s in p["sources"]) == 6
    assert client.get("/v1/buyers/slugs").json()[0]["slug"].startswith(str(head))


def test_the_tender_filter_by_buyer_lists_every_member(client, conn, baainbw):
    params = {"buyer": baainbw["baainbw"], "status": "all", "scope": "all"}
    assert client.get("/v1/tenders", params=params).json()["total"] == 2       # no family yet
    buyer_families.run(conn, write=True)
    assert client.get("/v1/tenders", params=params).json()["total"] == 6
    assert client.get("/v1/tenders", params={**params, "buyer": baainbw["baainbw koblenz"]}).json()["total"] == 6
    assert client.get("/v1/tenders", params={**params, "buyer": baainbw[LONG_NORM]}).json()["total"] == 6


def test_open_counts_collapse_a_twin_filed_under_another_name_variant(client, conn):
    ted = put(conn, "TED-1", LONG, source="ted")
    put(conn, "NAT-1", "BAAINBw", source="nl_tenderned", ted_ref="TED-1")
    put(conn, "NAT-2", "BAAINBw Koblenz", source="nl_tenderned")
    buyer_families.run(conn, write=True)
    top = client.get("/v1/buyers").json()["items"][0]
    listed = client.get("/v1/tenders", params={"buyer": org_of(conn, ted), "status": "open",
                                               "scope": "all"}).json()["total"]
    assert listed == 2 and top["openCount"] == listed, (top, listed)
    assert top["tenderCount"] == 3                          # the count of the archive is not collapsed


def test_a_followed_member_shows_the_family_and_its_changes(client, sent, conn, baainbw):  # noqa: F811
    buyer_families.run(conn, write=True)
    member = baainbw["baainbw koblenz"]
    session, _ = sign_in(client, sent)
    assert client.put(f"/v1/account/follows/buyer/{member}", headers=H(session)).status_code == 200
    item = client.get("/v1/account/follows", headers=H(session)).json()["items"][0]["item"]
    assert (item["tenderCount"], item["nameVariants"]) == (6, 2)
    client.get("/v1/account/dashboard", headers=H(session))                  # the baseline visit
    put(conn, "S-0", "BAAINBw", deadline=FUTURE + timedelta(days=9))         # a sibling's notice, amended
    board = client.get("/v1/account/dashboard", headers=H(session)).json()
    assert [c["item"]["noticeId"] for c in board["changes"]] == ["S-0"]
    assert board["following"][0]["openCount"] == item["openCount"]
