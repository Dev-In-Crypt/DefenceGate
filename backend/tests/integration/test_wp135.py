"""WP-135 against a real Postgres: a Polish notice held from the bulletin (`pl_ezam`) and from its mirror (`pl_atlas`) under
the same BZP number and buyer family is one notice: one card in the list, counted once in the list's total, the scope counts,
the buyer's counts and profile, the CSV export and the sitemap; the bulletin's copy is kept unless only the mirror states a
value; the hidden copy's page is still served and names the kept one (`copyOf`). A bulletin notice without a mirror, two
different numbers and two unrelated buyers stay two; the TED rule is unchanged."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, stats, tenders
from tests.integration.test_changes import opp, store
from tests.integration.test_wp52 import _store_exact_base

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _fresh_cache():
    stats.reset_cache()
    yield
    stats.reset_cache()


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def pl(conn, number: str, source: str, *, value: float | None = None, buyer: str = "Ministry PL",
       title: str = "Armoured vehicles", ted_ref: str | None = None, **kw) -> int:
    o = opp(number, source=source, country="PL", value=value, title=title, ted_ref=ted_ref, **kw)
    return store(conn, replace(o, buyer_name_raw=buyer))


def listing(client, **params) -> dict:
    r = client.get("/v1/tenders", params={"status": "all", "scope": "all", "pageSize": 100, **params})
    assert r.status_code == 200, r.text
    return r.json()


def shown(client, **params) -> list[tuple[str, str]]:
    return sorted((t["source"]["sourceId"], t["noticeId"]) for t in listing(client, **params)["items"])


def exported(client, **params) -> list[str]:
    r = client.get("/v1/tenders/export", params={"status": "all", "scope": "all", **params})
    assert r.status_code == 200, r.text
    return sorted(t["id"] for t in r.json()["items"])


def test_a_pair_is_one_notice_the_bulletins_copy_and_the_mirror_page_names_it(client, conn):
    bulletin = pl(conn, "2025/BZP 00000001", "pl_ezam")
    mirror = pl(conn, "2025/BZP 00000001", "pl_atlas")
    body = listing(client)
    assert [(t["id"], t["source"]["sourceId"]) for t in body["items"]] == [(str(bulletin), "pl_ezam")]
    assert body["total"] == 1
    assert exported(client) == [str(bulletin)]
    counts = client.get("/v1/tenders/scope-counts", params={"status": "all"}).json()
    assert (counts["relevant"], counts["core"]) == (1, 1)
    # the kept copy names the other; the other's page is served and names the kept one as its address
    kept = client.get(f"/v1/tenders/{bulletin}").json()
    assert [(s["id"], s["source"]) for s in kept["sameNotice"]] == [(str(mirror), "pl_atlas")]
    assert kept["copyOf"] is None
    hidden = client.get(f"/v1/tenders/{mirror}")
    assert hidden.status_code == 200
    assert hidden.json()["copyOf"] == kept["slug"]
    # the sitemap lists the notice once
    sitemap = [i["slug"].split("-")[0] for i in client.get("/v1/tenders/sitemap").json()["items"]]
    assert sitemap == [str(bulletin)]
    assert [s["slug"].split("-")[0] for s in client.get("/v1/tenders/slugs").json()] == [str(bulletin)]
    # the data model's own list collapses it too
    assert [o["id"] for o in client.get("/v1/opportunities", params={"status": "open"}).json()] == [bulletin]


def test_the_mirror_is_kept_when_only_it_states_a_value(client, conn):
    bulletin = pl(conn, "2025/BZP 00000002", "pl_ezam")
    mirror = pl(conn, "2025/BZP 00000002", "pl_atlas", value=120000.0)
    assert [t["id"] for t in listing(client)["items"]] == [str(mirror)]
    assert client.get(f"/v1/tenders/{bulletin}").json()["copyOf"].startswith(f"{mirror}-")
    assert client.get(f"/v1/tenders/{mirror}").json()["copyOf"] is None
    # a placeholder value is no value: the bulletin's copy is kept
    pl(conn, "2025/BZP 00000003", "pl_ezam")
    placeholder = pl(conn, "2025/BZP 00000003", "pl_atlas", value=1.0)
    assert str(placeholder) not in [t["id"] for t in listing(client)["items"]]
    # both state one: the bulletin's
    both = pl(conn, "2025/BZP 00000004", "pl_ezam", value=5000.0)
    pl(conn, "2025/BZP 00000004", "pl_atlas", value=6000.0)
    ids = [t["id"] for t in listing(client)["items"]]
    assert str(both) in ids and len(ids) == 3


def test_a_filter_that_only_the_mirror_meets_lists_the_mirror(client, conn):
    pl(conn, "2025/BZP 00000005", "pl_ezam", title="Armoured vehicles")
    mirror = pl(conn, "2025/BZP 00000005", "pl_atlas", title="Night vision goggles")
    assert [t["id"] for t in listing(client, q="Night")["items"]] == [str(mirror)]
    assert listing(client, q="Night")["total"] == 1
    # and a value range only the mirror's value meets
    pl(conn, "2025/BZP 00000006", "pl_ezam", value=10.0)
    valued = pl(conn, "2025/BZP 00000006", "pl_atlas", value=50000.0)
    assert [t["id"] for t in listing(client, min=1000, currency="EUR")["items"]] == [str(valued)]


def test_a_bulletin_notice_without_mirror_two_numbers_and_two_buyers_stay(client, conn):
    alone = pl(conn, "2025/BZP 00000010", "pl_ezam")
    a = pl(conn, "2025/BZP 00000011", "pl_ezam")
    b = pl(conn, "2025/BZP 00000012", "pl_atlas")                 # another number: another notice
    mine = pl(conn, "2025/BZP 00000013", "pl_ezam")
    other = pl(conn, "2025/BZP 00000013", "pl_atlas", buyer="Gmina Zupelnie Inna")   # another buyer family: not joined
    ids = sorted(int(t["id"]) for t in listing(client)["items"])
    assert ids == sorted([alone, a, b, mine, other])
    assert listing(client)["total"] == 5
    assert client.get(f"/v1/tenders/{other}").json()["copyOf"] is None


def test_the_ted_rule_is_unchanged_and_holds_with_the_mirror(client, conn):
    ted = pl(conn, "700001-2025", "ted")
    pl(conn, "2025/BZP 00000020", "pl_ezam", ted_ref="700001-2025")          # a national copy of the TED notice
    assert shown(client) == [("ted", "700001-2025")]
    # its mirror copies the TED notice as well: still the TED notice alone
    pl(conn, "2025/BZP 00000020", "pl_atlas", ted_ref="700001-2025")
    assert shown(client) == [("ted", "700001-2025")]
    # the mirror with the value and no TED reference: the bulletin's copy goes, and the mirror stands for the notice
    stats.reset_cache()
    pl(conn, "2025/BZP 00000021", "pl_ezam", ted_ref="700002-2025")         # its TED notice is not held
    m = pl(conn, "2025/BZP 00000021", "pl_atlas", value=9000.0)
    assert [t["id"] for t in listing(client, q="Armoured")["items"] if t["noticeId"] == "2025/BZP 00000021"] == [str(m)]
    assert ted


def test_a_buyer_shaped_like_7310_is_counted_as_its_list(client, conn):
    """7310 on 25 October 2026: 553 bulletin + 74 TED + 3 mirror notices; 26 of the bulletin's are copies of its TED
    notices and the 3 mirror notices are its bulletin notices: 601. Scaled down: 10 + 4 + 3, 2 copies of TED: 12."""
    for i in range(4):
        pl(conn, f"80000{i}-2025", "ted")
    for i in range(10):
        pl(conn, f"2025/BZP 0000010{i}", "pl_ezam", ted_ref=f"80000{i}-2025" if i < 2 else None)
    for i in range(3):
        pl(conn, f"2025/BZP 0000010{i + 5}", "pl_atlas")
    body = listing(client, scope="relevant")
    assert body["total"] == len(body["items"]) == 12
    slug, buyer = body["items"][0]["buyerSlug"], body["items"][0]["buyerId"]
    assert listing(client, scope="relevant", buyer=buyer)["total"] == 12
    _store_exact_base(conn)                       # the worker's collapsed aggregate
    page = client.get(f"/v1/buyers/{slug}").json()
    assert page["tenderCount"] == 12
    assert page["openCount"] == listing(client, status="open", scope="relevant", buyer=buyer)["total"] == 12
    profile = client.get(f"/v1/buyers/{slug}/profile").json()
    assert profile["tenderCount"] == 12
    assert sum(s["count"] for s in profile["sources"]) == 12
    assert len(exported(client, buyer=buyer)) == 12
    directory = next(b for b in client.get("/v1/buyers").json()["items"] if b["id"] == buyer)
    assert directory["tenderCount"] == 12


def test_the_rule_carries_the_filters_once_more():
    where, params, _ = tenders._tender_filters(None, "PL", None, "open", "relevant", None, None, None, None, None, None, None)
    sql = " AND ".join(where) + " AND " + tenders.collapse_clauses(where)
    assert sql.count("%s") == len(params) * tenders.COLLAPSE_REPEATS
    assert "pl_atlas" in tenders.collapse_clauses(where)


def test_a_pair_is_one_notice_in_every_status_list(client, conn):
    past = datetime.now(timezone.utc) - timedelta(days=3)
    pl(conn, "2025/BZP 00000030", "pl_ezam", deadline=past)
    pl(conn, "2025/BZP 00000030", "pl_atlas", deadline=past)
    assert listing(client, status="closed")["total"] == 1
    assert listing(client, status="open")["total"] == 0
    assert listing(client, status="all")["total"] == 1
