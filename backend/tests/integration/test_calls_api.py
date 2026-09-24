"""The grants endpoint.

The one behaviour worth a test of its own is the ordering. Opportunities are
served newest first, because what a supplier wants is what has just appeared.
Calls are served by deadline ascending, because what an applicant wants is the
one closing next -- there is no point being shown a call that closed on Tuesday
above one that closes on Friday.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, db
from dgate.normalise import Call

pytestmark = pytest.mark.integration


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def _store(conn, native_id: str, *, programme: str = "EDF", days: int = 10,
           regime: str = "defence", status: str = "open") -> None:
    call = Call(
        programme_code=programme,
        native_id=native_id,
        title=f"Topic {native_id}",
        topic_code=f"{programme}-2026-{native_id}",
        deadline_at=datetime.now(timezone.utc) + timedelta(days=days),
        status=status,
        regime=regime,
        type_of_action=f"{programme}-RA",
    )
    db.upsert_call(conn, call, f"hash-{native_id}", db.source_id(conn, "eu_portal"))
    conn.commit()


def test_the_call_closing_next_comes_first(client, conn):
    _store(conn, "late", days=40)
    _store(conn, "soon", days=3)
    _store(conn, "middle", days=12)
    body = client.get("/v1/calls").json()
    assert [c["native_id"] for c in body] == ["soon", "middle", "late"]
    assert body[0]["days_left"] in (2, 3)


def test_a_defence_supplier_can_ask_for_the_defence_programmes_only(client, conn):
    _store(conn, "edf", programme="EDF", regime="defence")
    _store(conn, "horizon", programme="HORIZON", regime="dual_use", days=2)
    assert [c["native_id"] for c in client.get("/v1/calls?regime=defence").json()] == ["edf"]
    assert [c["native_id"] for c in client.get("/v1/calls?programme=HORIZON").json()] == \
        ["horizon"]
    assert len(client.get("/v1/calls").json()) == 2


def test_a_closed_call_is_not_served_as_open(client, conn):
    _store(conn, "closed", status="closed", days=-5)
    assert client.get("/v1/calls").json() == []
    served = client.get("/v1/calls?status=closed").json()
    assert [c["native_id"] for c in served] == ["closed"]
    assert served[0]["days_left"] < 0


def test_the_source_is_attributed_on_every_call(client, conn):
    """Commission Decision 2011/833/EU allows the reuse; it requires the source
    to be acknowledged, so the acknowledgement travels with the record rather
    than living in a footer somebody can forget."""
    _store(conn, "edf")
    body = client.get("/v1/calls").json()
    assert body[0]["attribution"] == "Source: European Commission, Funding and Tenders Portal"
    assert body[0]["programme"] == "EDF"
    assert body[0]["type_of_action"] == "EDF-RA"
