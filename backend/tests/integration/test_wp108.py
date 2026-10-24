"""WP-108 (persona round 4, 24 October 2026): implausible award values without an estimate, re-read versions that came
with the award, the corrections on the page, and the digest's current status. Evidence: D:/DEFENCEGATE TESTS/ux-oct24b."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest

from dgate import weekly_digest
from dgate.ops import award_values, tag_rereads
from tests.integration.test_wp95 import FakeTed, award, award_notice, notice, org
from tests.integration.test_wp103 import client, env, placsp, store  # noqa: F401  (fixtures and helpers)

pytestmark = pytest.mark.integration


def procedure(conn, oid: int, ident: str) -> None:
    conn.execute("UPDATE opportunity SET procedure_identifier = %s WHERE id = %s", (ident, oid))


@pytest.fixture
def held(conn, env):  # noqa: F811
    """INCM 499753-2026 as held (contract EUR 1.159 bn, no estimate) with its procedure's contract notice (EUR 1.45 m),
    FASER 394720-2025 (contract PLN 7,247,040,000, tenders of PLN 7,247,040 at TED) and a plausible large contract."""
    army = org(conn, "exercito portugues", "PT", is_defence_buyer=True)
    incm = org(conn, "imprensa nacional casa da moeda", "PT")
    a = notice(conn, "ted", "499753-2026", buyer=army, country="PT", value=(1159000000.0, "EUR", "total"))
    award(conn, a, incm, "Imprensa Nacional Casa da Moeda", value=(1159000000.0, "EUR", "contract"), country="PT")
    award_notice(conn, a, value_amount=1159000000, value_currency="EUR", value_kind="contract")
    cn = notice(conn, "ted", "126958-2026", buyer=army, country="PT", value=(1450000.0, "EUR", "estimated"), subtype="16")
    procedure(conn, a, "4d442456")
    procedure(conn, cn, "4d442456")
    rbl = org(conn, "2 regionalna baza logistyczna", "PL", is_defence_buyer=True)
    faser = org(conn, "faser", "PL")
    f = notice(conn, "ted", "394720-2025", buyer=rbl, country="PL", value=(7247040000.0, "PLN", "total"))
    award(conn, f, faser, "FASER S.A", value=(7247040000.0, "PLN", "contract"), country="PL")
    award_notice(conn, f, value_amount=7247040000, value_currency="PLN", value_kind="contract")
    big = notice(conn, "ted", "419618-2026", buyer=rbl, country="PL", value=(9311212000.0, "PLN", "total"))
    award(conn, big, faser, "FASER S.A", value=(9311212000.0, "PLN", "contract"), country="PL")
    award_notice(conn, big, value_amount=9311212000, value_currency="PLN", value_kind="contract")
    conn.commit()
    return {"incm": a, "faser": f, "big": big, "incm_org": incm}


def test_the_procedure_check_sets_aside_incm_without_a_ted_request_and_a_second_run_writes_nothing(conn, client, held):  # noqa: F811
    report = award_values.run_set_aside(conn, write=False)
    conn.rollback()
    assert report["ted_values_set_aside"] == 1 and report["ted_values_set_aside_procedure"] == 1
    award_values.run_set_aside(conn, write=True)
    n = conn.execute("SELECT * FROM award_notice WHERE opportunity_id = %s", (held["incm"],)).fetchone()
    assert (float(n["value_amount"]), n["value_kind"], float(n["value_set_aside"]), n["value_set_aside_reason"]) == (
        1450000.0, "estimate", 1159000000.0, "procedure")
    a = conn.execute("SELECT value_amount, value_kind FROM award WHERE opportunity_id = %s", (held["incm"],)).fetchone()
    assert (float(a["value_amount"]), a["value_kind"]) == (1450000.0, "estimate")
    v = client.get(f"/v1/tenders/{held['incm']}").json()["awardValue"]
    assert v == {"amount": 1450000.0, "currency": "EUR", "kind": "estimate", "setAside": 1159000000.0,
                 "setAsideReason": "procedure"}
    # out of the contract sums (the Portuguese Army's 1.17 bn)
    assert not client.get(f"/v1/suppliers/{held['incm_org']}").json()["values"]["byCurrency"]
    assert award_values.run_set_aside(conn, write=True)["ted_values_set_aside"] == 0
    big = conn.execute("SELECT value_kind FROM award_notice WHERE opportunity_id = %s", (held["big"],)).fetchone()
    assert big["value_kind"] == "contract"                                    # no procedure, no parts: stands


def test_the_lots_check_sets_aside_faser_when_ted_answers_its_tenders(conn, env, held, monkeypatch):  # noqa: F811
    fake = FakeTed({"394720-2025": {"publication-number": "394720-2025", "total-value-cur": ["PLN"],
                                    "tender-value": ["1001400", "2197800", "3157920", "889920"]},
                    "499753-2026": {"publication-number": "499753-2026"},
                    "419618-2026": {"publication-number": "419618-2026", "BT-161-NoticeResult": "9311212000"}})
    monkeypatch.setattr(award_values, "new_client", lambda **kw: fake.client())
    c = award_values.run_ted(conn, fetch=True, write=True, pause=0, every=True)
    assert c["ted_set_aside_lots"] == 1
    n = conn.execute("SELECT * FROM award_notice WHERE opportunity_id = %s", (held["faser"],)).fetchone()
    assert (float(n["value_amount"]), n["value_kind"], float(n["value_set_aside"]), n["value_set_aside_reason"]) == (
        7247040.0, "contract", 7247040000.0, "lots")
    a = conn.execute("SELECT value_amount FROM award WHERE opportunity_id = %s", (held["faser"],)).fetchone()
    assert float(a["value_amount"]) == 7247040.0
    # the loader's own query carries the procedure value: INCM, answered with no value field, is set aside by it
    n = conn.execute("SELECT value_kind, value_set_aside_reason FROM award_notice WHERE opportunity_id = %s",
                     (held["incm"],)).fetchone()
    assert (n["value_kind"], n["value_set_aside_reason"]) == ("estimate", "procedure")


# --------------------------------------------------------------------------------------- 2-4. versions

AWARDED = dict(status="awarded", status_native="ADJ")


def test_a_reread_that_came_with_the_award_notes_the_mapper_fields_and_keeps_the_award(conn, client):  # noqa: F811
    """videoscopio 2812: 45,980 -> 38,000 (/ 1.21), published 28 Sep -> 3 Sep, Open -> Awarded, 15 October 2026."""
    old = placsp("2026/EA12/00001466E", value_amount=45980.0, status_native="EV",
                 published_at=date.today() - timedelta(days=2))
    oid = store(conn, old, "a")
    new = replace(old, value_amount=38000.0, legal_basis="32014L0024", published_at=date.today() - timedelta(days=27),
                  source_updated_at=datetime.now(timezone.utc) - timedelta(hours=2), **AWARDED)
    store(conn, new, "b")
    note = conn.execute("""SELECT n.kind, n.fields FROM opportunity_version_note n JOIN opportunity_version v
                             ON v.id = n.opportunity_version_id WHERE v.opportunity_id = %s AND v.version = 2""",
                        (oid,)).fetchone()
    assert note["kind"] == "remapped_fields"
    assert set(note["fields"]) == {"legal_basis", "value_amount", "published_at"}
    versions = client.get(f"/v1/tenders/{oid}/versions").json()
    fixes = [v for v in versions if v["correction"]]
    own = [v for v in versions if not v["correction"]]
    assert [c["field"] for c in own[0]["changes"]] == ["status"]
    assert {c["field"] for c in fixes[0]["changes"]} == {"legal_basis", "value_amount", "published_at"}
    assert fixes[0]["reason"] == "remapped"


def test_tag_rereads_notes_the_mapper_fields_of_the_versions_written_before(conn, env):  # noqa: F811
    from dgate import db

    old = placsp("2026/EA14/00002782E", value_amount=11000.0, status_native="PUB")
    oid = store(conn, old, "a")
    new = replace(old, value_amount=10280.37, legal_basis="Ley 9/2017 (LCSP)",                 # / 1.07, IGIC
                  source_updated_at=datetime.now(timezone.utc) - timedelta(hours=2), **AWARDED)
    db.append_version(conn, oid, new, "h-b", ["legal_basis", "value_amount", "status"], after=1)
    conn.commit()
    c, examples = tag_rereads.run(conn, write=False)
    assert c["versions"] == 1 and c["mapper fields only (the rest a real change)"] == 1 and c["value ratio 1.07"] == 1
    assert "status PUB -> ADJ stays a change" in examples[0]
    c, _ = tag_rereads.run(conn, write=True)
    assert c["annotated_fields"] == 1
    n = conn.execute("""SELECT n.kind, n.fields FROM opportunity_version_note n JOIN opportunity_version v
                          ON v.id = n.opportunity_version_id WHERE v.opportunity_id = %s""", (oid,)).fetchone()
    assert (n["kind"], sorted(n["fields"])) == ("remapped_fields", ["legal_basis", "value_amount"])
    assert tag_rereads.run(conn, write=True)[0]["versions"] == 0
    rows = conn.execute("SELECT count(*) AS n FROM opportunity_version WHERE opportunity_id = %s", (oid,)).fetchone()
    assert rows["n"] == 2                                                       # notes only: nothing written to versions


# --------------------------------------------------------------------------------------- 5. the digest

def test_the_digest_says_the_status_of_a_notice_now(conn, env):  # noqa: F811
    oid = notice(conn, "ted", "ZLT-50", value=None)
    conn.execute("UPDATE opportunity SET status = 'cancelled' WHERE id = %s", (oid,))
    conn.commit()
    body = {"tendersNew": [{"id": str(oid), "title": "ZLT-50"}], "tendersAmended": [], "week": "2026-W42"}
    out = weekly_digest.with_current_status(conn, body)
    assert out["tendersNew"][0]["statusNative"] == "cancelled" and out["week"] == "2026-W42"
    assert weekly_digest.with_current_status(conn, {"tendersNew": [], "tendersAmended": []})["tendersNew"] == []
