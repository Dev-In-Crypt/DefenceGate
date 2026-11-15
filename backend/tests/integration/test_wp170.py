"""WP-170 against a real Postgres: the next page of a search reads its rows only. The counts of a list do not depend on the page;
page 2 of "fuel" counted them all again (about 4 s on production, backlog of 26 October 2026). With the list cache on, a page
after the first runs no count and says the first page's total; with it off (the test suite's default) every page counts, as
before."""

from __future__ import annotations

import pytest

from dgate import tenders
from tests.integration.test_warm_lists import _put, cache_on  # noqa: F401 - fixture
from tests.integration.test_wp95 import client, env  # noqa: F401 - fixtures

pytestmark = pytest.mark.integration


def _fuel(conn, n: int, status: str = "closed") -> None:
    for i in range(n):
        oid = _put(conn, f"W-170-{status}-{i}", status=status)
        # open: a deadline ahead (`_put` sets one a month ago, which the list reads as closed)
        conn.execute("UPDATE opportunity SET title_original = 'Fuel supply', deadline_at = CASE WHEN status = 'open' "
                     "THEN now() + interval '30 days' ELSE deadline_at END WHERE id = %s", (oid,))
    conn.commit()


def _counting(monkeypatch) -> list[int]:
    calls: list[int] = []
    real = tenders._count_live
    monkeypatch.setattr(tenders, "_count_live", lambda *a: calls.append(a[4]) or real(*a))
    return calls


@pytest.mark.parametrize("status", ["closed", "all", "open"])
def test_the_next_page_of_a_search_reads_its_rows_and_repeats_the_first_pages_total(client, conn, cache_on, monkeypatch, status):  # noqa: F811
    _fuel(conn, 5)
    _fuel(conn, 5, "open")
    calls = _counting(monkeypatch)
    first = client.get("/v1/tenders", params={"q": "fuel", "status": status, "pageSize": 2}).json()
    assert calls, "the first page counts"
    calls.clear()
    second = client.get("/v1/tenders", params={"q": "fuel", "status": status, "pageSize": 2, "page": 2}).json()
    assert calls == [], "the second page counted again"
    assert second["total"] == first["total"] == {"closed": 5, "all": 10, "open": 5}[status]
    assert len(second["items"]) == 2
    assert {i["id"] for i in first["items"]}.isdisjoint(i["id"] for i in second["items"])


def test_without_the_list_cache_every_page_counts(client, conn, monkeypatch):  # noqa: F811
    _fuel(conn, 5)
    calls = _counting(monkeypatch)
    for page in (1, 2):
        calls.clear()
        got = client.get("/v1/tenders", params={"q": "fuel", "status": "closed", "pageSize": 2, "page": page}).json()
        assert calls and got["total"] == 5



# ----------------------------------------------------------------------------- a reviewed pair no candidate holds

def test_a_reviewed_pair_without_a_candidate_is_reported_then_merged_with_its_method_and_confidence(conn):
    from dgate.ops import accept_merge_candidates as amc
    from tests.integration.test_wp95 import org

    quiet = {"out": lambda *_: None}
    a = org(conn, "idv defence vehicles espana", "ES", vat_number="ESA00000000")
    b = org(conn, "idv defensa sl antes iveco espana", "ES")
    other = org(conn, "idv defence vehicles espana", "IT")
    conn.commit()
    why = "one company: the second name says it was Iveco Espana; same address in both notices"

    dry = amc.run_pair(conn, a, b, confidence=0.95, evidence=why, head=a, **quiet)
    assert (dry["groups"], dry["rows_to_merge"], dry["heads"]) == (1, 1, [(a, [b])])
    assert conn.execute("SELECT count(*) AS n FROM organisation_merge_candidate").fetchone()["n"] == 0    # a report writes nothing
    assert conn.execute("SELECT merged_into FROM organisation WHERE id = %s", (b,)).fetchone()["merged_into"] is None

    done = amc.run_pair(conn, a, b, confidence=0.95, evidence=why, head=a, apply=True, **quiet)
    row = conn.execute("SELECT merged_into, merge_method, merge_confidence FROM organisation WHERE id = %s", (b,)).fetchone()
    assert done["merged"] == 1 and (row["merged_into"], row["merge_method"], float(row["merge_confidence"])) == (
        a, amc.REVIEWED, 0.95)
    cand = conn.execute("SELECT match_method, status, evidence FROM organisation_merge_candidate").fetchall()
    assert [(c["match_method"], c["status"], c["evidence"]) for c in cand] == [(amc.REVIEWED, "merged", why)]

    # the facts still refuse: another country
    refused = amc.run_pair(conn, a, other, confidence=0.95, evidence="same name", apply=True, **quiet)
    assert refused["merged"] == 0 and refused["refused"] == {"different_countries": 1}
    with pytest.raises(ValueError):
        amc.run_pair(conn, a, b, confidence=0.95, evidence=" ", **quiet)


# ----------------------------------------------------------------------------- generic buyer rows

def test_a_generic_rows_notices_move_to_the_unit_their_text_names_and_the_rest_stay(conn):
    from dgate.ops import generic_buyers
    from tests.integration.test_wp95 import notice, org

    quiet = {"out": lambda *_: None}
    bare = "komenda powiatowa panstwowej strazy pozarnej"
    generic, glub, swieb = (org(conn, bare, "PL"), org(conn, f"{bare} w glubczycach", "PL"),
                            org(conn, f"{bare} w swiebodzinie", "PL"))
    ids = [notice(conn, "pl_ezam", f"BZP-{i}", title=t, buyer=generic, country="PL") for i, t in enumerate((
        "Dostawa paliwa dla KP PSP w Głubczycach",                       # one unit named: moves
        "Zakup samochodu dla Komendy Powiatowej PSP w Świebodzinie",       # the other unit: moves
        "Dostawa sprzętu",                                                 # no place: stays
        "Paliwo dla KP PSP w Głubczycach i KP PSP w Świebodzinie"))]      # two units: stays
    conn.execute("UPDATE opportunity SET buyer_name_raw = 'Komenda Powiatowa Państwowej Straży Pożarnej' WHERE id = ANY(%s)",
                 (ids,))
    own = notice(conn, "pl_ezam", "BZP-9", title="Paliwo w Głubczycach", buyer=generic, country="PL")   # states its own name
    conn.execute("UPDATE opportunity SET buyer_name_raw = 'KP PSP Opole' WHERE id = %s", (own,))
    conn.commit()

    report = generic_buyers.run(conn, [generic], **quiet)
    assert (report["notices"], report["to_move"]) == (5, 2)
    assert report["stay"] == {"no place of a known unit": 1, "several places": 1, "states another name": 1}
    buyer = lambda i: conn.execute("SELECT buyer_org_id FROM opportunity WHERE id = %s", (i,)).fetchone()["buyer_org_id"]  # noqa: E731
    assert [buyer(i) for i in ids] == [generic] * 4                                       # a report writes nothing

    done = generic_buyers.run(conn, [generic], apply=True, **quiet)
    assert done["moved"] == 2
    assert [buyer(i) for i in (*ids, own)] == [glub, swieb, generic, generic, generic]
    rows = conn.execute("SELECT org_a, org_b, method, confidence, evidence, status FROM resolution_review ORDER BY org_b").fetchall()
    assert [(r["org_a"], r["org_b"], r["method"], float(r["confidence"]), r["evidence"]["notices"], r["status"]) for r in rows] == [
        (generic, glub, "place_in_notice", 0.9, [ids[0]], "related"), (generic, swieb, "place_in_notice", 0.9, [ids[1]], "related")]
    assert generic_buyers.run(conn, [generic], apply=True, **quiet)["moved"] == 0         # again: nothing left to move
