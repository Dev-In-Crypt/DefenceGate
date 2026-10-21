"""Rectificatifs and re-publications are shown once, under the notice they repeat."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, db, stats
from dgate.normalise import Opportunity

pytestmark = pytest.mark.integration

FUTURE = datetime.now(timezone.utc) + timedelta(days=30)


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def put(conn, native_id: str, *, source="ted", status="open", published=date(2026, 10, 1),
        related=None, procedure=None, title="Armoured vehicles", deadline=FUTURE) -> int:
    opp = Opportunity(source_code=source, native_id=native_id, buyer_name_raw="Ministry of Defence",
                      title_original=title, country="PL", published_at=published, deadline_at=deadline,
                      cpv_codes=["35400000"], status=status, is_defence=True, sig_cpv=True,
                      sig_cpv_military=True, related_native_id=related, procedure_identifier=procedure)
    src = db.source_id(conn, source)
    opp.buyer_org_id = db.resolve_organisation(conn, "Ministry of Defence", "PL", src_id=src)
    oid, _ = db.upsert_opportunity(conn, opp, f"hash-{native_id}", src)
    conn.execute("UPDATE opportunity SET procedure_identifier = %s, related_native_id = %s WHERE id = %s",
                 (procedure, related, oid))
    conn.commit()
    return oid


def ids(client, **params) -> list[str]:
    body = client.get("/v1/tenders", params={"status": "all", "scope": "all", **params}).json()
    return sorted(t["noticeId"] for t in body["items"])


def test_the_newest_wins_a_parent_gives_way_to_its_rectificatif_which_is_never_hidden(client, conn):
    """Changed on 13 October 2026 (review of the data-quality work). It used to be the
    other way round: the rectificatif was hidden whenever its parent existed, whatever
    the parent's status or the filters, so a live corrected notice vanished when the
    parent had expired. Now the parent is the one that gives way, and only to a
    rectificatif that is itself in the result."""
    put(conn, "PARENT", source="fr_boamp")
    put(conn, "RECT-1", source="fr_boamp", related="PARENT")
    put(conn, "RECT-2", source="fr_boamp", related="MISSING")
    assert ids(client) == ["RECT-1", "RECT-2"]


def test_a_live_rectificatif_is_listed_when_its_parent_has_expired(client, conn):
    past = datetime.now(timezone.utc) - timedelta(days=30)
    put(conn, "PARENT", source="fr_boamp", deadline=past)
    put(conn, "RECT-1", source="fr_boamp", related="PARENT", title="Armoured vehicles, amended")
    assert ids(client, status="open") == ["RECT-1"]
    assert ids(client, status="all") == ["RECT-1"], "the correction stands for the notice"
    # a filter the rectificatif does not meet leaves the parent in the list
    assert ids(client, status="closed") == ["PARENT"]
    assert ids(client, status="all", q="Armoured vehicles, amended") == ["RECT-1"]


def test_a_filter_that_excludes_the_rectificatif_lists_the_parent(client, conn):
    put(conn, "PARENT", source="fr_boamp", title="Armoured vehicles")
    put(conn, "RECT-1", source="fr_boamp", related="PARENT", title="Night vision goggles")
    assert ids(client, q="Armoured") == ["PARENT"]
    assert ids(client, q="Night") == ["RECT-1"]
    assert ids(client) == ["RECT-1"]


def test_an_award_is_not_hidden_under_an_expired_call_of_the_same_procedure(client, conn):
    """A link by procedure identifier ties a national row to the newest TED notice of the
    procedure, which may be the call; the award must not vanish under it."""
    past = datetime.now(timezone.utc) - timedelta(days=30)
    call = put(conn, "100-2026", source="ted", status="open", deadline=past)
    award = put(conn, "NAT-1", source="fr_boamp", status="awarded", deadline=None)
    same = put(conn, "NAT-2", source="fr_boamp", status="open", deadline=past,
               title="Armoured vehicles")
    assert call
    for opp_id, method in ((award, "procedure_id"), (same, "procedure_id")):
        conn.execute("UPDATE opportunity SET ted_ref = '100-2026', twin_method = %s WHERE id = %s",
                     (method, opp_id))
    conn.commit()
    # NAT-2 has the call's own status, so it is its twin and is collapsed into it
    assert ids(client) == ["100-2026", "NAT-1"]
    # the same link, but as the source stated it: the old rule, every status collapses
    conn.execute("UPDATE opportunity SET twin_method = 'stated_ted_ref' WHERE id = %s", (award,))
    conn.commit()
    assert ids(client) == ["100-2026"]
    conn.execute("UPDATE opportunity SET twin_method = 'heuristic' WHERE id = %s", (award,))
    conn.commit()
    assert ids(client) == ["100-2026", "NAT-1"]


def test_a_national_copy_of_an_older_ted_stage_collapses_into_that_stage(client, conn):
    """WP-59 (re-audit of the data pages, NEW-3): the national row's `ted_ref` names the newest TED notice of the
    procedure, still open; the stage it copies is closed. In Closed the two copies stood side by side."""
    past = datetime.now(timezone.utc) - timedelta(days=1)
    put(conn, "708324-2026", procedure="proc-h", deadline=past, published=date(2026, 10, 14))
    put(conn, "713394-2026", procedure="proc-h", published=date(2026, 10, 15))
    # A national source that is served (de_bkms, the source of the case, is inactive until the owner switches it
    # on, so its rows are suppressed by the trigger of migration 0050 and the test passed or failed on the order
    # the suite ran in). It is listed before it is linked: the assertions below are not vacuous.
    nat = put(conn, "NAT-H", source="fr_boamp", procedure="proc-h", deadline=past, published=date(2026, 10, 13))
    assert ids(client, status="closed", q="Armoured") == ["708324-2026", "NAT-H"]
    conn.execute("UPDATE opportunity SET ted_ref = '713394-2026', twin_method = 'procedure_id' WHERE id = %s", (nat,))
    conn.commit()
    assert ids(client, status="closed") == ["708324-2026"]
    assert ids(client, status="open") == ["713394-2026"]
    # a national row linked some other way keeps the old rule: only the TED notice it names replaces it
    conn.execute("UPDATE opportunity SET twin_method = 'heuristic' WHERE id = %s", (nat,))
    conn.commit()
    stats.reset_cache()                         # the data changed under the list caches
    assert ids(client, status="closed") == ["708324-2026", "NAT-H"]


def test_only_the_newest_republication_of_a_procedure_is_shown(client, conn):
    put(conn, "100-2026", procedure="proc-1", published=date(2026, 9, 1))
    put(conn, "200-2026", procedure="proc-1", published=date(2026, 10, 1))
    put(conn, "300-2026", procedure="proc-2")
    assert ids(client) == ["200-2026", "300-2026"]


def test_an_award_notice_does_not_hide_the_call_for_competition(client, conn):
    put(conn, "400-2026", procedure="proc-9", status="open", published=date(2026, 9, 1))
    put(conn, "500-2026", procedure="proc-9", status="awarded", published=date(2026, 10, 1))
    assert ids(client) == ["400-2026", "500-2026"]


def test_a_filter_that_keeps_only_the_older_republication_does_not_make_the_notice_vanish(client, conn):
    put(conn, "600-2026", procedure="proc-5", published=date(2026, 9, 1), title="Night vision")
    put(conn, "700-2026", procedure="proc-5", published=date(2026, 10, 1), title="Armoured vehicles")
    assert ids(client, q="Night") == ["600-2026"]
