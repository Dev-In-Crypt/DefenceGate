"""Rectificatifs and re-publications are shown once, under the notice they repeat."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, db
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


def test_a_rectificatif_is_hidden_when_its_parent_is_held_and_shown_when_it_is_not(client, conn):
    put(conn, "PARENT", source="fr_boamp")
    put(conn, "RECT-1", source="fr_boamp", related="PARENT")
    put(conn, "RECT-2", source="fr_boamp", related="MISSING")
    assert ids(client) == ["PARENT", "RECT-2"]


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
