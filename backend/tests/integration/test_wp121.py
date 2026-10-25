"""WP-121 (verification round 6, 25 October 2026): an old notice address that answers 404 because the notice left the defence
scope leads to its in-scope publication of the same procurement, or says what it was and where the original is (p10: /tenders/267780,
a Latvian police vehicle purchase, cited in round 2). Evidence: D:/DEFENCEGATE TESTS/verify-oct25/personas/recheck.csv row 103."""

from __future__ import annotations

import pytest

from tests.integration.test_wp95 import notice
from tests.integration.test_wp103 import client, env  # noqa: F401  (fixtures)

pytestmark = pytest.mark.integration


def out_of_scope(conn, oid: int) -> None:
    conn.execute("UPDATE opportunity SET is_defence = false WHERE id = %s", (oid,))


def test_a_notice_that_left_the_scope_says_what_it_was_and_links_its_source(conn, client):  # noqa: F811
    gone = notice(conn, "ted", "711894-2026", title="Utility vehicles", country="LV")
    out_of_scope(conn, gone)
    conn.commit()
    assert client.get(f"/v1/tenders/{gone}").status_code == 404
    r = client.get(f"/v1/tenders/{gone}/moved")
    assert r.status_code == 200
    assert r.json() == {"slug": None, "left": {"title": "Utility vehicles", "noticeId": "711894-2026", "sourceName": r.json()["left"]["sourceName"],
                                                "url": "https://example.test/711894-2026"}}
    assert r.json()["left"]["sourceName"]


def test_a_national_copy_that_left_the_scope_leads_to_its_ted_twin_in_scope_and_back(conn, client):  # noqa: F811
    ted = notice(conn, "ted", "500100-2026", title="Ammunition")
    national = notice(conn, "es_placsp", "2026/ES/0001", title="Municion")
    conn.execute("UPDATE opportunity SET ted_ref = '500100-2026' WHERE id = %s", (national,))
    out_of_scope(conn, national)
    conn.commit()
    assert client.get(f"/v1/tenders/{national}/moved").json() == {"slug": f"{ted}-ammunition", "left": None}
    # the other way: a TED notice out of scope whose national copy is in scope
    conn.execute("UPDATE opportunity SET is_defence = true WHERE id = %s", (national,))
    out_of_scope(conn, ted)
    conn.commit()
    assert client.get(f"/v1/tenders/{ted}/moved").json()["slug"].startswith(f"{national}-")


def test_an_id_never_held_a_removed_one_and_one_in_scope_are_not_moved(conn, client):  # noqa: F811
    held = notice(conn, "ted", "500200-2026")
    removed = notice(conn, "ted", "500201-2026")
    conn.execute("UPDATE opportunity SET suppressed = true WHERE id = %s", (removed,))
    conn.commit()
    assert client.get("/v1/tenders/987654321/moved").status_code == 404
    assert client.get(f"/v1/tenders/{removed}/moved").status_code == 410
    assert client.get(f"/v1/tenders/{held}/moved").status_code == 404
    assert client.get(f"/v1/tenders/{held}").status_code == 200
