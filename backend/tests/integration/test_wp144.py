"""WP-144 on a real Postgres: one buyer, several units. A legal body (a head and the rows merged into it) shows its units, the
names its notices state (folded), each counted as the tender list counts it with `unit=`; the list, its scope counts and the
export read `unit=` with the same filters; the worker stores every buyer's units and the API reads them."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from dgate import api, db, stats, tenders
from dgate.listcache import stored
from dgate.normalise import Opportunity
from dgate.ops import warm_lists

pytestmark = pytest.mark.integration

FUTURE = datetime.now(timezone.utc) + timedelta(days=30)
UNI = "politechnika warszawska"
FACULTY = "politechnika warszawska wydzial transportu"


@pytest.fixture(autouse=True)
def _fresh_cache():
    stats.reset_cache()
    yield
    stats.reset_cache()


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def notice(conn, native_id: str, buyer: str, *, source: str = "ted", status: str = "open") -> int:
    opp = Opportunity(source_code=source, native_id=native_id, buyer_name_raw=buyer, title_original=f"Notice {native_id}",
                      title_en=f"Notice {native_id}", country="PL", published_at=date.today() - timedelta(days=10),
                      deadline_at=FUTURE, cpv_codes=["35400000"], status=status, is_defence=True,
                      sig_cpv=True, sig_cpv_military=True, sig_buyer=False, dual_use=False, buyer_class="defence")
    src = db.source_id(conn, source)
    opp.buyer_org_id = db.resolve_organisation(conn, buyer, "PL", src_id=src)
    oid, _ = db.upsert_opportunity(conn, opp, f"hash-{source}-{native_id}", src)
    conn.commit()
    return oid


def buyer_of(conn, opp: int) -> int:
    return conn.execute("SELECT buyer_org_id FROM opportunity WHERE id = %s", (opp,)).fetchone()["buyer_org_id"]


def merge(conn, head: int, member: int) -> None:
    db.merge_organisations(conn, head, member, method="person_review", confidence=0.95, evidence="test", detected_by="test")
    conn.commit()


def university(conn) -> int:
    """Politechnika Warszawska after the merge of its faculty row: two units (the university, written two ways, and one
    faculty, written two ways), a TED notice of the faculty and its national copy, and a notice whose buyer is withheld."""
    head = buyer_of(conn, notice(conn, "1-2026", "Politechnika Warszawska"))
    notice(conn, "2-2026", "POLITECHNIKA WARSZAWSKA", status="closed")
    faculty = buyer_of(conn, notice(conn, "3-2026", "Politechnika Warszawska, Wydział Transportu"))
    notice(conn, "4-2026", "Politechnika Warszawska Wydział Transportu")
    copy = notice(conn, "2026/BZP 00000003", "Politechnika Warszawska, Wydział Transportu", source="pl_ezam")
    conn.execute("UPDATE opportunity SET ted_ref = '3-2026' WHERE id = %s", (copy,))   # the national copy of 3-2026
    # one Polish notice held from the bulletin and from its mirror, each copy stating another unit: the list of all units
    # shows the bulletin's copy once; each unit's list shows its own copy (the copy of another unit is not in it)
    notice(conn, "2026/BZP 00000007", "Politechnika Warszawska Wydział Transportu", source="pl_ezam")
    notice(conn, "2026/BZP 00000007", "Politechnika Warszawska", source="pl_atlas")
    withheld = notice(conn, "5-2026", "Pracownia Testowa")
    conn.commit()
    merge(conn, head, faculty)
    merge(conn, head, buyer_of(conn, withheld))
    # set after the merge (re-pointing the buyer recomputes the flag from the suppression list)
    conn.execute("UPDATE opportunity SET buyer_withheld = TRUE WHERE id = %s", (withheld,))
    conn.commit()
    return head


def total(client, head: int, unit: str | None, status: str = "all") -> int:
    params = {"buyer": head, "status": status, **({"unit": unit} if unit is not None else {})}
    r = client.get("/v1/tenders", params=params)
    assert r.status_code == 200, r.text
    return r.json()["total"]


def test_a_body_shows_its_units_each_counted_as_its_list_counts_it(conn, client):
    head = university(conn)
    page = client.get(f"/v1/buyers/{head}").json()
    units = {u["key"]: u for u in page["units"]}
    assert list(units) == [UNI, FACULTY]                         # most tenders first, then by name
    assert units[UNI]["tenderCount"] == 3 and units[FACULTY]["tenderCount"] == 3   # the national copy of 3-2026 once
    assert units[FACULTY]["name"] in ("Politechnika Warszawska, Wydział Transportu", "Politechnika Warszawska Wydział Transportu")
    assert units[UNI]["coreCount"] == 3
    for key, u in units.items():
        assert total(client, head, key) == u["tenderCount"]     # the dropdown's count is its list's total
    assert total(client, head, UNI, "open") == 2 and total(client, head, FACULTY, "open") == 3
    # all units: the whole body, the withheld notice too (listed as before); its name is no unit and finds nothing
    assert total(client, head, None) == 6
    assert total(client, head, "Pracownia Testowa") == 0
    # the name as stated finds its unit too (folded the same way)
    assert total(client, head, "Politechnika Warszawska,  WYDZIAŁ Transportu") == 3


def test_the_counts_and_the_export_read_the_unit_with_the_same_filters(conn, client):
    head = university(conn)
    counts = client.get("/v1/tenders/scope-counts", params={"buyer": head, "unit": FACULTY, "status": "all"}).json()
    assert counts["relevant"] == total(client, head, FACULTY) == 3
    listed = {t["id"] for t in client.get("/v1/tenders", params={"buyer": head, "unit": FACULTY, "status": "all"}).json()["items"]}
    exported = {t["id"] for t in client.get("/v1/tenders/export", params={"buyer": head, "unit": FACULTY, "status": "all"}).json()["items"]}
    assert listed == exported and len(listed) == 3


def test_a_unit_needs_its_buyer(conn, client):
    university(conn)
    assert client.get("/v1/tenders", params={"unit": UNI}).status_code == 422
    assert client.get("/v1/tenders", params={"unit": "x" * 401, "buyer": 1}).status_code == 422


def test_a_buyer_of_one_name_has_no_unit_choice(conn, client):
    head = buyer_of(conn, notice(conn, "9-2026", "Agencja Uzbrojenia"))
    notice(conn, "10-2026", "AGENCJA UZBROJENIA")
    assert client.get(f"/v1/buyers/{head}").json()["units"] == []


def test_the_worker_stores_every_buyers_units_and_the_api_reads_them(conn, client):
    head = university(conn)
    live = client.get(f"/v1/buyers/{head}").json()["units"]
    assert ("buyer-units", tenders.BUYER_UNITS_KEY, {}) in warm_lists.views([])
    body = tenders.compute_buyer_units(conn)
    assert body == {str(head): live}                              # the stored ones are the live ones
    conn.execute("INSERT INTO list_snapshot (key, body, computed_at) VALUES (%s, %s, now())",
                 (tenders.BUYER_UNITS_KEY, Jsonb(stored(jsonable_encoder(body)))))
    conn.commit()
    merge(conn, head, buyer_of(conn, notice(conn, "6-2026", "Politechnika Warszawska Wydział Fizyki")))   # a third unit, later
    stats.reset_cache()
    assert client.get(f"/v1/buyers/{head}").json()["units"] == live   # read from the snapshot until the next run
    assert [u["key"] for u in tenders.compute_buyer_units(conn)[str(head)]][-1] == "politechnika warszawska wydzial fizyki"


# ------------------------------------------------------------------ item 5: a buyer of notices outside the default scope

def dual_use(conn, native_id: str, buyer: str) -> int:
    """A military product code bought by a civil buyer (production's 40319, TED 122655-2017, of the maritime office 9421): in
    neither the core nor the supply scope, only under `all`."""
    opp = Opportunity(source_code="ted", native_id=native_id, buyer_name_raw=buyer, title_original=f"Notice {native_id}",
                      title_en=f"Notice {native_id}", country="PL", published_at=date(2017, 3, 30),
                      deadline_at=FUTURE, cpv_codes=["35700000"], status="open", is_defence=True,
                      sig_cpv=True, sig_cpv_military=True, sig_buyer=False, dual_use=True, buyer_class="other")
    src = db.source_id(conn, "ted")
    opp.buyer_org_id = db.resolve_organisation(conn, buyer, "PL", src_id=src)
    oid, _ = db.upsert_opportunity(conn, opp, f"hash-ted-{native_id}", src)
    conn.commit()
    return oid


def test_a_buyer_whose_notices_are_all_outside_the_default_scope_has_a_page_and_its_notice_links_to_it(conn, client):
    opp = dual_use(conn, "122655-2017", "Dyrektor Urzędu Morskiego w Gdyni")
    office = buyer_of(conn, opp)
    old = buyer_of(conn, dual_use(conn, "1-2018", "Urzad Morski w Gdyni"))
    merge(conn, office, old)                                     # as 283618 was merged into 9421
    assert client.get("/v1/tenders", params={"buyer": office, "status": "all"}).json()["total"] == 0   # none in the default scope
    page = client.get(f"/v1/buyers/{office}")
    assert page.status_code == 200, page.text
    b = page.json()
    assert b["scope"] == "all" and b["tenderCount"] == 2 and b["openCount"] == 2 and b["openCoreCount"] is None
    assert b["tenderCount"] == client.get("/v1/tenders", params={"buyer": office, "scope": "all", "status": "all"}).json()["total"]
    assert b["units"] == [] and b["lastPublishedAt"].startswith("2017-03-30")
    assert client.get(f"/v1/buyers/{old}").json()["id"] == str(office)                    # the merged row answers its head
    assert client.get(f"/v1/tenders/{opp}").json()["buyerSlug"] == b["slug"]              # the notice's buyer line links to it
    # neither on the buyer list nor in the sitemap, which list the default scope (a notice page is indexed in the core scope only)
    assert str(office) not in {x["id"] for x in client.get("/v1/buyers").json()["items"]}
    assert not [s for s in client.get("/v1/buyers/slugs").json() if s["slug"].startswith(f"{office}-")]


def test_a_buyer_with_a_notice_in_the_default_scope_keeps_its_counts_there(conn, client):
    head = university(conn)
    extra = dual_use(conn, "7-2017", "Politechnika Warszawska")
    assert buyer_of(conn, extra) == head
    b = client.get(f"/v1/buyers/{head}").json()
    assert b["scope"] == "relevant" and len(b["units"]) == 2      # the dual-use notice is no unit's and no count's
    assert client.get("/v1/buyers/999999").status_code == 404
